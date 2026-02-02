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

# Optional: embed controller secret into the dashboard package so users don't
# have to paste it manually (still protected by LazyCat login).
SECRET_LOCAL_FILE="${MIHOMO_SECRET_FILE_LOCAL:-$ROOT/var/private/mihomo.secret}"
if [[ -n "${MIHOMO_SECRET:-}" ]]; then
  secret="$MIHOMO_SECRET"
elif [[ -f "$SECRET_LOCAL_FILE" ]]; then
  secret="$(tr -d '\r\n' <"$SECRET_LOCAL_FILE")"
else
  secret=""
fi

if [[ -n "$secret" ]]; then
  cat >"$APP_DIR/dist/lzcapp-config.js" <<EOF
window.__LZCAPP_MIHOMO__ = { secret: ${secret@Q} };
EOF
else
  # Keep the file absent if we don't have a secret.
  rm -f "$APP_DIR/dist/lzcapp-config.js" 2>/dev/null || true
  echo "NOTE: mihomo secret not found; metacubexd will ask user to enter URL/secret." >&2
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
