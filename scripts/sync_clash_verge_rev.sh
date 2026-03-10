#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/src/mihomo-dashboard-app"
VENDOR_DIR="$APP_DIR/vendor/clash-verge-rev"
UPSTREAM_URL="${CLASH_VERGE_REV_UPSTREAM:-https://github.com/clash-verge-rev/clash-verge-rev.git}"
UPSTREAM_REF="${CLASH_VERGE_REV_REF:-v2.4.7}"

tmpdir="$(mktemp -d)"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

echo "Syncing Clash Verge Rev from $UPSTREAM_URL @ $UPSTREAM_REF"
git clone --depth 1 --branch "$UPSTREAM_REF" "$UPSTREAM_URL" "$tmpdir/repo" >/dev/null

rm -rf "$VENDOR_DIR"
mkdir -p "$VENDOR_DIR"

cp -R "$tmpdir/repo/src" "$VENDOR_DIR/src"

if [[ -f "$tmpdir/repo/LICENSE" ]]; then
  cp "$tmpdir/repo/LICENSE" "$VENDOR_DIR/LICENSE"
fi

if [[ -f "$tmpdir/repo/README.md" ]]; then
  cp "$tmpdir/repo/README.md" "$VENDOR_DIR/README.upstream.md"
fi

cat >"$VENDOR_DIR/README.local.txt" <<EOF
Vendored Clash Verge Rev frontend source. Sync via scripts/sync_clash_verge_rev.sh.
EOF

printf '%s\n' "$UPSTREAM_REF" >"$VENDOR_DIR/UPSTREAM_VERSION"

echo "Vendor tree refreshed in $VENDOR_DIR"
