#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_paths.sh"
. "$ROOT/scripts/_lib_deploy_settings.sh"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

HOST="${MICROSERVER_HOST:-rainierserver.heiyu.space}"
SSH_USER="${MICROSERVER_SSH_USER:-root}"
SSH_KEY="${MICROSERVER_SSH_KEY:-$HOME/.ssh/id_ed25519}"
readonly EXPECTED_BOX="rainierserver"
readonly EXPECTED_HOST="rainierserver.heiyu.space"
LAZYCAT_BOX="${LAZYCAT_BOX:-}"
LEGACY_APP_ID="cloud.lazycat.app.mihomo-dashboard"
BACKUP_DIR=""
MUTATION_STARTED=0

if [[ "${1:-}" != "--execute" || "${2:-}" != "--confirm" || "$#" -ne 2 ]]; then
  echo "One-time cleanup for legacy app ID: $LEGACY_APP_ID"
  echo "Target: $SSH_USER@$HOST"
  echo "LazyCat box: ${LAZYCAT_BOX:-not set (required for --execute)}"
  echo "No changes made. Re-run with --execute --confirm after reviewing the exact target and SSH fingerprint."
  if [[ "$#" -gt 0 && "${1:-}" != "--execute" && "${1:-}" != "-h" && "${1:-}" != "--help" ]]; then
    echo "ERROR: usage: scripts/cleanup_legacy_dashboard.sh [--execute --confirm]" >&2
    exit 2
  fi
  exit 0
fi

if [[ -n "$LAZYCAT_BOX" && "$LAZYCAT_BOX" != "$EXPECTED_BOX" ]]; then
  echo "ERROR: LAZYCAT_BOX may only narrow to the reviewed box ${EXPECTED_BOX}" >&2
  exit 2
fi
if [[ "$HOST" != "$EXPECTED_HOST" ]]; then
  echo "ERROR: legacy cleanup is reviewed only for ${EXPECTED_HOST}" >&2
  exit 2
fi
current_box="$(lzc-cli box default)"
if [[ "$current_box" != "$EXPECTED_BOX" ]]; then
  echo "ERROR: lzc-cli default box '$current_box' does not match reviewed box '$EXPECTED_BOX'" >&2
  exit 2
fi

mihomo_require_apply_confirmation "$HOST" "$SSH_USER" "1" "cleanup_legacy_dashboard"

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$SSH_USER@$HOST" "$@"
}

restore_legacy_backup() {
  [[ -n "$BACKUP_DIR" ]] || return 0
  ssh_remote BACKUP_DIR="$BACKUP_DIR" bash -s <<'REMOTE'
set -euo pipefail
backup_dir="$BACKUP_DIR"
install -d -m 755 /run/lock
exec 9>/run/lock/clash-verge-deploy.lock
flock -n 9 || { echo "ERROR: another Clash-Verge deployment is active" >&2; exit 1; }
[[ "$backup_dir" =~ ^/var/lib/mihomo/rollback/legacy-dashboard\.[A-Za-z0-9]+$ ]] || exit 1
[[ -d "$backup_dir" && -f "$backup_dir/manifest.tsv" && -f "$backup_dir/manifest.sha256" &&
   -f "$backup_dir/service-state.tsv" && -f "$backup_dir/service-state.sha256" ]] || exit 1
sha256sum -c "$backup_dir/manifest.sha256" >/dev/null
sha256sum -c "$backup_dir/service-state.sha256" >/dev/null
unknown_marker="$backup_dir/UNKNOWN"
printf 'rollback_status=UNKNOWN\n' > "$unknown_marker"
while IFS=$'\t' read -r unit active enabled; do
  [[ "$unit" == mihomo-verge-api.service ]] || exit 1
  case "$active" in active|inactive) ;; *) exit 1 ;; esac
  case "$enabled" in enabled|disabled|static|masked) ;; *) exit 1 ;; esac
done < "$backup_dir/service-state.tsv"
approved_paths=(
  "/lzcsys/data/system/pkgm/apps/cloud.lazycat.app.mihomo-dashboard"
  "/lzcsys/data/system/pkgm/run/cloud.lazycat.app.mihomo-dashboard"
  "/lzcsys/data/system/pkgm/deploy.var/cloud.lazycat.app.mihomo-dashboard"
  "/lzcsys/data/system/pkgm/lpks/cloud.lazycat.app.mihomo-dashboard.lpk"
  "/lzcsys/data/appcache/cloud.lazycat.app.mihomo-dashboard"
  "/lzcsys/data/appvar/cloud.lazycat.app.mihomo-dashboard"
  "/lzcsys/run/app/cloud.lazycat.app.mihomo-dashboard"
  "/lzcsys/data/system/pkgm/deploy.db"
)
assert_approved_path() {
  local candidate
  for candidate in "${approved_paths[@]}"; do
    [[ "$1" == "$candidate" ]] && return 0
  done
  return 1
}
assert_no_symlink_components() {
  python3 - "$@" <<'PY'
import stat
import sys
from pathlib import Path

for raw in sys.argv[1:]:
    path = Path(raw)
    if not path.is_absolute():
        raise SystemExit(f"unsafe non-absolute path: {path}")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            break
        if stat.S_ISLNK(mode):
            raise SystemExit(f"refusing symlink path component: {current}")
PY
}
target_digest() {
  local path="$1"
  if [[ -f "$path" ]]; then
    sha256sum -- "$path" | awk '{print $1}'
  elif [[ -d "$path" ]]; then
    tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
      -cf - -C / "${path#/}" | sha256sum | awk '{print $1}'
  else
    return 1
  fi
}
while IFS=$'\t' read -r path state type size digest archive archive_digest; do
  [[ -n "$path" ]] || continue
  [[ "$path" == /* ]] || exit 1
  assert_approved_path "$path" || exit 1
  assert_no_symlink_components "$path"
  if [[ "$state" == present ]]; then
    [[ "$archive" =~ ^target-[0-9]+\.tar\.gz$ && "$archive_digest" =~ ^[0-9a-f]{64}$ ]] || exit 1
    sha256sum -- "$backup_dir/$archive" | awk -v expected="$archive_digest" '$1 != expected { exit 1 }'
    [[ -e "$path" || ! -L "$path" ]] || exit 1
    if [[ -e "$path" ]]; then rm -rf -- "$path"; fi
    install -d -m 755 "$(dirname "$path")"
    tar -xzf "$backup_dir/$archive" -C /
  elif [[ "$state" != present-no || "$type" != - || "$size" != 0 || "$digest" != - || "$archive" != - || "$archive_digest" != - ]]; then
    exit 1
  else
    if [[ -e "$path" ]]; then rm -rf -- "$path"; fi
  fi
done < "$backup_dir/manifest.tsv"
while IFS=$'\t' read -r path state type size digest archive archive_digest; do
  [[ -n "$path" ]] || continue
  if [[ "$state" == present ]]; then
    [[ -e "$path" && ! -L "$path" ]] || exit 1
    if [[ "$type" == file ]]; then
      [[ -f "$path" && "$(stat -c '%s' -- "$path")" == "$size" ]] || exit 1
    elif [[ "$type" != directory || ! -d "$path" ]]; then
      exit 1
    fi
    [[ "$(target_digest "$path")" == "$digest" ]] || exit 1
  else
    [[ ! -e "$path" && ! -L "$path" ]] || exit 1
  fi
done < "$backup_dir/manifest.tsv"
while IFS=$'\t' read -r unit active enabled; do
  [[ "$unit" == mihomo-verge-api.service ]] || exit 1
  case "$enabled" in
    enabled) systemctl enable "$unit" >/dev/null ;;
    disabled) systemctl disable "$unit" >/dev/null 2>&1 || true ;;
    static) : ;;
    masked) systemctl mask "$unit" >/dev/null ;;
    *) exit 1 ;;
  esac
  case "$active" in
    active) systemctl start "$unit" >/dev/null ;;
    inactive) systemctl stop "$unit" >/dev/null 2>&1 || true ;;
    *) exit 1 ;;
  esac
done < "$backup_dir/service-state.tsv"
actual_active="$(systemctl is-active mihomo-verge-api.service 2>/dev/null || true)"
actual_enabled="$(systemctl is-enabled mihomo-verge-api.service 2>/dev/null || true)"
expected_active="$(awk -F '\t' '$1 == "mihomo-verge-api.service" {print $2}' "$backup_dir/service-state.tsv")"
expected_enabled="$(awk -F '\t' '$1 == "mihomo-verge-api.service" {print $3}' "$backup_dir/service-state.tsv")"
[[ "$actual_active" == "$expected_active" && "$actual_enabled" == "$expected_enabled" ]] || exit 1
rm -f -- "$unknown_marker"
test ! -e "$unknown_marker"
echo "legacy cleanup rollback readback: manifest=ok service_state=ok"
REMOTE
}

on_exit() {
  local status=$?
  trap - EXIT
  set +e
  if [[ "$MUTATION_STARTED" == "1" && "$status" != "0" ]]; then
    if ! restore_legacy_backup; then
      echo "ERROR: legacy cleanup rollback failed; preserve ${BACKUP_DIR:-unknown} and reconcile manually" >&2
    fi
  fi
  mihomo_cleanup_known_hosts
  exit "$status"
}
trap on_exit EXIT

backup_output="$(ssh_remote bash -s -- "$LEGACY_APP_ID" <<'REMOTE'
set -euo pipefail
legacy_app_id="$1"
install -d -m 755 /run/lock
exec 9>/run/lock/clash-verge-deploy.lock
flock -n 9 || { echo "ERROR: another Clash-Verge deployment is active" >&2; exit 1; }
legacy_paths=(
  "/lzcsys/data/system/pkgm/apps/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/run/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/deploy.var/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/lpks/${legacy_app_id}.lpk"
  "/lzcsys/data/appcache/${legacy_app_id}"
  "/lzcsys/data/appvar/${legacy_app_id}"
  "/lzcsys/run/app/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/deploy.db"
)
python3 - <<'PY' "${legacy_paths[@]}"
import os
import stat
import sys
from pathlib import Path

for raw in sys.argv[1:]:
    path = Path(raw)
    if not path.is_absolute():
        raise SystemExit(f"unsafe non-absolute cleanup path: {path}")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            break
        except OSError as exc:
            raise SystemExit(f"cannot inspect cleanup path {current}: {exc}") from exc
        if stat.S_ISLNK(mode):
            raise SystemExit(f"refusing cleanup path with symlink ancestor: {current}")
PY
backup_root=/var/lib/mihomo/rollback
install -d -m 700 "$backup_root"
backup_dir="$(mktemp -d "$backup_root/legacy-dashboard.XXXXXX")"
install -d -m 700 "$backup_dir"
paths=(
  "/lzcsys/data/system/pkgm/apps/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/run/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/deploy.var/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/lpks/${legacy_app_id}.lpk"
  "/lzcsys/data/appcache/${legacy_app_id}"
  "/lzcsys/data/appvar/${legacy_app_id}"
  "/lzcsys/run/app/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/deploy.db"
)
target_digest() {
  local path="$1"
  if [[ -f "$path" ]]; then
    sha256sum -- "$path" | awk '{print $1}'
  elif [[ -d "$path" ]]; then
    tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
      -cf - -C / "${path#/}" | sha256sum | awk '{print $1}'
  else
    return 1
  fi
}
: > "$backup_dir/manifest.tsv"
index=0
for path in "${paths[@]}"; do
  index=$((index + 1))
  archive="target-${index}.tar.gz"
  if [[ ! -e "$path" ]]; then
    printf '%s\tpresent-no\t-\t0\t-\t-\t-\n' "$path" >> "$backup_dir/manifest.tsv"
    continue
  fi
  test ! -L "$path"
  if [[ -f "$path" ]]; then
    type=file
    size="$(stat -c '%s' -- "$path")"
  elif [[ -d "$path" ]]; then
    type=directory
    size=0
  else
    echo "ERROR: unsupported legacy target type: $path" >&2
    exit 1
  fi
  digest="$(target_digest "$path")"
  tar -czf "$backup_dir/$archive" -C / "${path#/}"
  test -s "$backup_dir/$archive"
  tar -tzf "$backup_dir/$archive" >/dev/null
  archive_digest="$(sha256sum -- "$backup_dir/$archive" | awk '{print $1}')"
  printf '%s\tpresent\t%s\t%s\t%s\t%s\t%s\n' \
    "$path" "$type" "$size" "$digest" "$archive" "$archive_digest" \
    >> "$backup_dir/manifest.tsv"
done
test -s "$backup_dir/manifest.tsv"
sha256sum -- "$backup_dir/manifest.tsv" > "$backup_dir/manifest.sha256"
active="$(systemctl is-active mihomo-verge-api.service 2>/dev/null || true)"
enabled="$(systemctl is-enabled mihomo-verge-api.service 2>/dev/null || true)"
case "$active" in active|inactive) ;; *) exit 1 ;; esac
case "$enabled" in enabled|disabled|static|masked) ;; *) exit 1 ;; esac
printf 'mihomo-verge-api.service\t%s\t%s\n' "$active" "$enabled" > "$backup_dir/service-state.tsv"
sha256sum -- "$backup_dir/service-state.tsv" > "$backup_dir/service-state.sha256"
printf 'backup_dir=%s\n' "$backup_dir"
REMOTE
)"
BACKUP_DIR="$(awk -F= '$1 == "backup_dir" {print substr($0, index($0, "=") + 1); exit}' <<<"$backup_output")"
[[ "$BACKUP_DIR" =~ ^/var/lib/mihomo/rollback/legacy-dashboard\.[A-Za-z0-9]+$ ]] || {
  echo "ERROR: backup did not return a private rollback directory" >&2
  exit 1
}

MUTATION_STARTED=1
lzc-cli app uninstall "$LEGACY_APP_ID" >/dev/null
app_status="$(lzc-cli app status "$LEGACY_APP_ID" 2>/dev/null || true)"
if grep -Eiq '(^|[^a-z])installed([^a-z]|$)|running|active' <<<"$app_status"; then
  echo "ERROR: legacy app uninstall did not produce an absent/stopped status" >&2
  exit 1
fi

ssh_remote bash -s -- "$LEGACY_APP_ID" <<'REMOTE'
set -euo pipefail
install -d -m 755 /run/lock
exec 9>/run/lock/clash-verge-deploy.lock
flock -n 9 || { echo "ERROR: another Clash-Verge deployment is active" >&2; exit 1; }

legacy_app_id="$1"
legacy_paths=(
  "/lzcsys/data/system/pkgm/apps/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/run/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/deploy.var/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/lpks/${legacy_app_id}.lpk"
  "/lzcsys/data/appcache/${legacy_app_id}"
  "/lzcsys/data/appvar/${legacy_app_id}"
  "/lzcsys/run/app/${legacy_app_id}"
)

python3 - <<'PY' "${legacy_paths[@]}"
import stat
import sys
from pathlib import Path

for raw in sys.argv[1:]:
    path = Path(raw)
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            break
        except OSError as exc:
            raise SystemExit(f"cannot inspect cleanup path {current}: {exc}") from exc
        if stat.S_ISLNK(mode):
            raise SystemExit(f"refusing cleanup path with symlink ancestor: {current}")
PY

for path in "${legacy_paths[@]}"; do
  rm -rf -- "$path"
done

python3 - <<'PY' "$legacy_app_id"
import sys
import os
import stat
from pathlib import Path

marker = sys.argv[1].encode("utf-8")
root = Path("/lzcsys/data/system/pkgm/deploy.db")

try:
    root_mode = root.lstat().st_mode
except OSError as exc:
    raise RuntimeError(f"cannot inspect deployment-record root {root}: {exc}") from exc
if not stat.S_ISDIR(root_mode):
    raise RuntimeError(f"deployment-record root is not a directory: {root}")


def fail_walk(exc: OSError) -> None:
    raise RuntimeError(f"cannot traverse deployment records: {exc}") from exc


def record_files():
    for directory, directories, filenames in os.walk(
        root, topdown=True, onerror=fail_walk, followlinks=False
    ):
        for child in directories:
            path = Path(directory) / child
            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                raise RuntimeError(f"cannot stat deployment-record directory {path}: {exc}") from exc
            if not stat.S_ISDIR(mode):
                raise RuntimeError(f"unexpected non-directory deployment-record entry: {path}")
        for filename in filenames:
            path = Path(directory) / filename
            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                raise RuntimeError(f"cannot stat deployment record {path}: {exc}") from exc
            if not stat.S_ISREG(mode):
                raise RuntimeError(f"unexpected non-regular deployment record: {path}")
            yield path


for path in record_files():
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"cannot read deployment record {path}: {exc}") from exc
    if marker in payload:
        path.unlink()

for path in record_files():
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"cannot verify deployment record {path}: {exc}") from exc
    if marker in payload:
        raise RuntimeError(f"legacy deployment record still exists: {path}")
PY

for path in "${legacy_paths[@]}"; do
  if [[ -e "$path" ]]; then
    echo "ERROR: legacy path still exists: $path" >&2
    exit 1
  fi
done

echo "Legacy dashboard cleanup complete: $legacy_app_id"
REMOTE
