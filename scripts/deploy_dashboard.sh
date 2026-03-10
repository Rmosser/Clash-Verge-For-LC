#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_paths.sh"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

APP_DIR="$ROOT/src/mihomo-dashboard-app"
LPK="$APP_DIR/mihomo-dashboard.lpk"

cd "$APP_DIR"

echo "Building Clash Verge Rev web assets ..."
pnpm build >/dev/null

if [[ ! -f "$APP_DIR/dist/index.html" ]]; then
  echo "ERROR: missing dashboard assets under $APP_DIR/dist (pnpm build failed or produced no index.html)" >&2
  exit 1
fi

SECRET_LOCAL_FILE="$(lzc_resolve_path_from_root "$ROOT" "${MIHOMO_SECRET_FILE_LOCAL:-var/private/mihomo.secret}")"
VERGE_SECRET_LOCAL_FILE="$(lzc_resolve_path_from_root "$ROOT" "${VERGE_API_SECRET_FILE_LOCAL:-var/private/verge-api.secret}")"
if [[ -n "${MIHOMO_SECRET:-}" ]]; then
  secret="$MIHOMO_SECRET"
elif [[ -f "$SECRET_LOCAL_FILE" ]]; then
  secret="$(tr -d '\r\n' <"$SECRET_LOCAL_FILE")"
else
  secret=""
fi

if [[ -n "${VERGE_API_SECRET:-}" ]]; then
  verge_secret="$VERGE_API_SECRET"
elif [[ -f "$VERGE_SECRET_LOCAL_FILE" ]]; then
  verge_secret="$(tr -d '\r\n' <"$VERGE_SECRET_LOCAL_FILE")"
else
  verge_secret=""
fi

cat >"$APP_DIR/dist/lzcapp-config.js" <<EOF
(function () {
  var config = {
    secret: ${secret@Q},
    vergeApiSecret: ${verge_secret@Q},
    mihomoBaseUrl: "/api",
    vergeApiBaseUrl: "/verge-api",
    appVersion: "2.4.7-webport.0"
  };

  try {
    if (config.vergeApiSecret) {
      var request = new XMLHttpRequest();
      request.open(
        "GET",
        config.vergeApiBaseUrl +
          "/public-config?token=" +
          encodeURIComponent(config.vergeApiSecret),
        false
      );
      request.send(null);
      if (request.status >= 200 && request.status < 300) {
        var remote = JSON.parse(request.responseText || "{}");
        config.secret = remote.secret || config.secret;
        config.vergeApiSecret = remote.vergeApiSecret || config.vergeApiSecret;
        config.mihomoBaseUrl = remote.mihomoBaseUrl || config.mihomoBaseUrl;
        config.vergeApiBaseUrl = remote.vergeApiBaseUrl || config.vergeApiBaseUrl;
        config.appVersion = remote.appVersion || config.appVersion;
      }
    }
  } catch (_error) {}

  window.__LZCAPP_MIHOMO__ = config;
})();
EOF

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
