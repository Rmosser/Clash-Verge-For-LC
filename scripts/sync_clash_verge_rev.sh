#!/usr/bin/env bash
set -Eeuo pipefail

# This script is intentionally pinned. A floating upstream ref would make the
# vendored WebPort non-reproducible and could silently import desktop code.
readonly UPSTREAM_URL="https://github.com/clash-verge-rev/clash-verge-rev.git"
readonly UPSTREAM_REF="v2.5.2"
readonly UPSTREAM_COMMIT="28f2efc504059b1dc75c793618b775c8e1b2a5f1"

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly OVERLAY_ROOT="$ROOT_DIR/src/mihomo-dashboard-app/vendor-overlays/clash-verge-rev"
readonly VENDOR_ROOT="$ROOT_DIR/src/mihomo-dashboard-app/vendor/clash-verge-rev"
readonly SERIES_FILE="$OVERLAY_ROOT/series"

MODE="verify"
case "${1:-}" in
  "") ;;
  --verify) MODE="verify" ;;
  --apply) MODE="apply" ;;
  --help|-h)
    printf '%s\n' "Usage: $0 [--verify|--apply]"
    printf '%s\n' "  --verify  stage and compare the pinned upstream plus overlay (default)"
    printf '%s\n' "  --apply   atomically replace the committed vendor from the verified stage"
    exit 0
    ;;
  *)
    printf 'unknown option: %s\n' "$1" >&2
    exit 2
    ;;
esac

die() {
  printf 'sync_clash_verge_rev: %s\n' "$*" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || die "git is required"
command -v diff >/dev/null 2>&1 || die "diff is required"
command -v rg >/dev/null 2>&1 || die "rg is required"

[[ -f "$OVERLAY_ROOT/manifest.json" ]] || die "missing overlay manifest"
[[ -f "$SERIES_FILE" ]] || die "missing overlay series"
[[ -d "$VENDOR_ROOT" ]] || die "missing committed vendor directory"

manifest_commit="$(python3 -I -B - "$OVERLAY_ROOT/manifest.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["commit"])
PY
)"
manifest_ref="$(python3 -I -B - "$OVERLAY_ROOT/manifest.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["ref"])
PY
)"

[[ "$manifest_ref" == "$UPSTREAM_REF" ]] || die "manifest ref is not pinned to $UPSTREAM_REF"
[[ "$manifest_commit" == "$UPSTREAM_COMMIT" ]] || die "manifest commit is not pinned to $UPSTREAM_COMMIT"

remote_tag="$(git ls-remote "$UPSTREAM_URL" "refs/tags/$UPSTREAM_REF" | awk 'NR == 1 { print $1 }')"
[[ "$remote_tag" == "$UPSTREAM_COMMIT" ]] || die "remote tag $UPSTREAM_REF is $remote_tag, expected $UPSTREAM_COMMIT"

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/clash-verge-rev-sync.XXXXXX")"
trap 'rm -rf -- "$TMP_ROOT"' EXIT

UPSTREAM_DIR="$TMP_ROOT/upstream"
STAGED_VENDOR="$TMP_ROOT/vendor"
mkdir -p "$UPSTREAM_DIR" "$STAGED_VENDOR"

git -C "$UPSTREAM_DIR" init -q
git -C "$UPSTREAM_DIR" remote add origin "$UPSTREAM_URL"
git -C "$UPSTREAM_DIR" fetch -q --depth=1 origin "refs/tags/$UPSTREAM_REF:refs/tags/$UPSTREAM_REF"
git -C "$UPSTREAM_DIR" checkout -q --detach "$UPSTREAM_REF"
actual_commit="$(git -C "$UPSTREAM_DIR" rev-parse HEAD)"
[[ "$actual_commit" == "$UPSTREAM_COMMIT" ]] || die "checked out $actual_commit, expected $UPSTREAM_COMMIT"

while IFS= read -r series_entry || [[ -n "$series_entry" ]]; do
  [[ -z "$series_entry" || "$series_entry" == \#* ]] && continue
  [[ "$series_entry" != /* && "$series_entry" != *..* ]] || die "unsafe series entry: $series_entry"
  patch_file="$OVERLAY_ROOT/$series_entry"
  [[ -f "$patch_file" ]] || die "missing overlay patch: $series_entry"
  git -C "$UPSTREAM_DIR" apply --check --binary --whitespace=nowarn "$patch_file" ||
    die "overlay check failed: $series_entry"
  git -C "$UPSTREAM_DIR" apply --binary --whitespace=nowarn "$patch_file"
done < "$SERIES_FILE"

cp -a "$UPSTREAM_DIR/src" "$STAGED_VENDOR/src"

if find "$STAGED_VENDOR" \( -type d -name src-tauri -o -name Cargo.toml \) -print | rg .; then
  die "desktop/Rust source appeared in staged vendor"
fi
if rg -n 'src-tauri|v1\.19\.29' "$STAGED_VENDOR/src"; then
  die "forbidden Mihomo core version appeared in staged Web source"
fi

cp "$UPSTREAM_DIR/LICENSE" "$STAGED_VENDOR/LICENSE"
cp "$UPSTREAM_DIR/README.md" "$STAGED_VENDOR/README.upstream.md"
[[ -f "$VENDOR_ROOT/README.local.txt" ]] && cp "$VENDOR_ROOT/README.local.txt" "$STAGED_VENDOR/README.local.txt"
printf '%s\n' "$UPSTREAM_REF $UPSTREAM_COMMIT" > "$STAGED_VENDOR/UPSTREAM_VERSION"

if diff -rq "$VENDOR_ROOT" "$STAGED_VENDOR" >/dev/null; then
  printf 'verified %s (%s); committed vendor is up to date\n' "$UPSTREAM_REF" "$UPSTREAM_COMMIT"
  exit 0
fi

if [[ "$MODE" == "verify" ]]; then
  die "committed vendor differs from the verified staging result"
fi

backup_root="$TMP_ROOT/previous-vendor"
mv "$VENDOR_ROOT" "$backup_root"
if mv "$STAGED_VENDOR" "$VENDOR_ROOT"; then
  printf 'applied %s (%s) with %s overlay patch series\n' "$UPSTREAM_REF" "$UPSTREAM_COMMIT" "$(rg -c '^[^#[:space:]]' "$SERIES_FILE")"
else
  mv "$backup_root" "$VENDOR_ROOT"
  die "atomic vendor replacement failed; previous vendor restored"
fi
