#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

APP_DIR="$ROOT/src/mihomo-dashboard-app"
LPK="$APP_DIR/mihomo-dashboard.lpk"

cd "$APP_DIR"

# Ensure the dashboard assets are metacubexd (defaults to latest release).
if [[ "${METACUBEXD_SKIP_UPDATE:-}" != "1" ]]; then
  "$ROOT/scripts/update_metacubexd.sh"
fi

if [[ ! -f "$APP_DIR/dist/index.html" ]]; then
  echo "ERROR: missing dashboard assets under $APP_DIR/dist (run scripts/update_metacubexd.sh)" >&2
  exit 1
fi

# Ensure lzc-cli connected.
lzc-cli box list >/dev/null

# Optional: ensure using the expected box.
if [[ -n "${LAZYCAT_BOX:-}" ]]; then
  cur_box="$(lzc-cli box default || true)"
  if [[ "$cur_box" != "$LAZYCAT_BOX" ]]; then
    echo "Switching box: $cur_box -> $LAZYCAT_BOX" >&2
    lzc-cli box switch "$LAZYCAT_BOX" >/dev/null
  fi
fi

echo "Building dashboard LPK ..."
lzc-cli project build -f lzc-build.yml -o "$LPK" >/dev/null

echo "Installing dashboard app ..."
lzc-cli app install "$LPK"
