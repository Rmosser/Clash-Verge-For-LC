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

HOST="${MICROSERVER_HOST:-rainierserver.heiyu.space}"
SSH_USER="${MICROSERVER_SSH_USER:-root}"
SSH_KEY="${MICROSERVER_SSH_KEY:-$HOME/.ssh/id_ed25519}"
APP_DIR="$ROOT/src/mihomo-dashboard-app"
LPK="$APP_DIR/mihomo-dashboard.lpk"
APP_ID="cloud.lazycat.app.clash-verge-for-lc"
LEGACY_APP_ID="cloud.lazycat.app.mihomo-dashboard"
EXPECTED_URL="${MIHOMO_DASHBOARD_URL:-https://clash.rainierserver.heiyu.space}"
EXPECTED_DOMAIN="${EXPECTED_URL#http://}"
EXPECTED_DOMAIN="${EXPECTED_DOMAIN#https://}"
EXPECTED_DOMAIN="${EXPECTED_DOMAIN%%/*}"
EXPECTED_SUBDOMAIN="${EXPECTED_DOMAIN%%.*}"
CLEAN_RESET=0

usage() {
  cat <<'USAGE'
Usage: scripts/deploy_dashboard.sh [options]

Options:
  --clean-reset  Remove legacy dashboard residues and reset Verge local state before install
  -h, --help     Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean-reset)
      CLEAN_RESET=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" "$@"
}

clean_reset_remote() {
  echo "Running clean reset on $SSH_USER@$HOST ..."
  lzc-cli app uninstall "$LEGACY_APP_ID" >/dev/null 2>&1 || true
  lzc-cli app uninstall "$APP_ID" >/dev/null 2>&1 || true

  ssh_remote bash -s -- "$EXPECTED_SUBDOMAIN" <<'REMOTE'
set -euo pipefail

target_domain="$1"
legacy_app_id="cloud.lazycat.app.mihomo-dashboard"
current_app_id="cloud.lazycat.app.clash-verge-for-lc"
legacy_paths=(
  "/lzcsys/data/system/pkgm/apps/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/run/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/deploy.var/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/lpks/${legacy_app_id}.lpk"
  "/lzcsys/data/appcache/${legacy_app_id}"
  "/lzcsys/data/appvar/${legacy_app_id}"
)
current_paths=(
  "/lzcsys/data/system/pkgm/apps/${current_app_id}"
  "/lzcsys/data/system/pkgm/run/${current_app_id}"
  "/lzcsys/data/system/pkgm/deploy.var/${current_app_id}"
  "/lzcsys/data/system/pkgm/lpks/${current_app_id}.lpk"
  "/lzcsys/data/appcache/${current_app_id}"
  "/lzcsys/data/appvar/${current_app_id}"
  "/lzcsys/run/app/${current_app_id}"
)

for path in "${legacy_paths[@]}"; do
  rm -rf "$path"
done

for path in "${current_paths[@]}"; do
  rm -rf "$path"
done

orphan_cleanup_file="$(mktemp)"

python3 - <<'PY' "$target_domain" "$legacy_app_id" "$current_app_id" "$orphan_cleanup_file"
import json
import sys
from pathlib import Path

target_domain = sys.argv[1]
legacy_app_id = sys.argv[2]
current_app_id = sys.argv[3]
orphan_cleanup_file = Path(sys.argv[4])
markers = (
    legacy_app_id.encode("utf-8"),
    current_app_id.encode("utf-8"),
)
root = Path("/lzcsys/data/system/pkgm/deploy.db")
stale_domain_claimants = []
for path in root.rglob("*"):
    if not path.is_file():
        continue
    try:
        payload = path.read_bytes()
    except OSError:
        continue
    if any(marker in payload for marker in markers):
        path.unlink()
        continue
    if f'"domain":"{target_domain}"'.encode("utf-8") not in payload:
        continue
    start = payload.find(b"{")
    if start < 0:
        continue
    try:
        record = json.loads(payload[start:].decode("utf-8"))
    except Exception:
        continue
    pkg_id = record.get("pkg_id") or record.get("deploy_id")
    if not pkg_id:
        continue
    app_dir = Path("/lzcsys/data/system/pkgm/apps") / pkg_id
    if app_dir.exists():
        continue
    stale_domain_claimants.append(pkg_id)
    path.unlink()

orphan_cleanup_file.write_text("\n".join(sorted(set(stale_domain_claimants))), encoding="utf-8")
PY

while IFS= read -r stale_pkg_id; do
  [[ -n "$stale_pkg_id" ]] || continue
  rm -rf \
    "/lzcsys/data/system/pkgm/apps/${stale_pkg_id}" \
    "/lzcsys/data/system/pkgm/run/${stale_pkg_id}" \
    "/lzcsys/data/system/pkgm/deploy.var/${stale_pkg_id}" \
    "/lzcsys/data/system/pkgm/lpks/${stale_pkg_id}.lpk" \
    "/lzcsys/data/appcache/${stale_pkg_id}" \
    "/lzcsys/data/appvar/${stale_pkg_id}" \
    "/lzcsys/run/app/${stale_pkg_id}"
done <"$orphan_cleanup_file"
rm -f "$orphan_cleanup_file"

rm -rf /var/lib/mihomo/verge
install -d -m 750 /var/lib/mihomo
touch /var/lib/mihomo/.verge-clean-reset
chown mihomo:mihomo /var/lib/mihomo/.verge-clean-reset

systemctl restart mihomo-verge-api

for _ in 1 2 3 4 5; do
  if curl -fsS http://172.18.0.1:9091/healthz >/dev/null; then
    exit 0
  fi
  sleep 1
done

echo "ERROR: mihomo-verge-api did not become healthy after clean reset" >&2
exit 1
REMOTE
}

resolve_app_container() {
  local name
  local attempt

  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    name="$(
      lzc-cli docker -- ps --format '{{.Names}}' \
        | grep -E '^cloudlazycatappclash-verge-for-lc-app-[0-9]+$' \
        | head -n 1 || true
    )"
    if [[ -n "$name" ]]; then
      printf '%s\n' "$name"
      return 0
    fi
    sleep 1
  done

  return 1
}

expected_route_reachable() {
  local headers
  local status

  headers="$(curl -kIsS --max-time 15 "$EXPECTED_URL" || true)"
  status="$(
    printf '%s\n' "$headers" \
      | sed -n 's/^HTTP\/[0-9.]* \([0-9][0-9][0-9]\).*/\1/p' \
      | head -n 1
  )"

  [[ "$status" =~ ^(200|30[1278])$ ]]
}

validate_actual_domain() {
  local container_name
  local actual_domain

  if ! container_name="$(resolve_app_container)"; then
    echo "ERROR: failed to locate dashboard app container for $APP_ID" >&2
    exit 1
  fi

  actual_domain="$(
    lzc-cli docker -- inspect "$container_name" \
      | python3 -c 'import json, sys; payload=json.load(sys.stdin); env=payload[0]["Config"]["Env"]; print(next((item.split("=", 1)[1] for item in env if item.startswith("LAZYCAT_APP_DOMAIN=")), ""))'
  )"

  if [[ -z "$actual_domain" ]]; then
    echo "ERROR: dashboard app container has no LAZYCAT_APP_DOMAIN" >&2
    exit 1
  fi

  echo "Resolved dashboard domain: $actual_domain"

  if [[ "$actual_domain" != "$EXPECTED_DOMAIN" ]]; then
    if expected_route_reachable; then
      echo "WARNING: expected public route $EXPECTED_URL is reachable, but LAZYCAT_APP_DOMAIN remains $actual_domain" >&2
      echo "WARNING: treating public ingress as source of truth and continuing; this looks like LazyCat metadata drift." >&2
      return 0
    fi

    echo "ERROR: expected dashboard domain $EXPECTED_DOMAIN but platform assigned $actual_domain and $EXPECTED_URL is not reachable" >&2
    ssh_remote bash -s -- "$EXPECTED_SUBDOMAIN" "$APP_ID" <<'REMOTE' >&2 || true
set -euo pipefail

target_domain="$1"
current_app_id="$2"

python3 - <<'PY' "$target_domain" "$current_app_id"
import json
import sys
from pathlib import Path

target_domain = sys.argv[1]
current_app_id = sys.argv[2]
hits = []
for path in Path("/lzcsys/data/system/pkgm/deploy.db").rglob("*"):
    if not path.is_file():
        continue
    try:
        payload = path.read_text("utf-8", errors="ignore")
    except OSError:
        continue
    if f'"domain":"{target_domain}"' not in payload:
        continue
    start = payload.find("{")
    if start < 0:
        continue
    try:
        record = json.loads(payload[start:])
    except json.JSONDecodeError:
        continue
    hits.append((str(path), record))

if hits:
    print("Domain claim(s) currently recorded in LazyCat deploy.db:")
    for path, record in hits:
        marker = " (current app)" if record.get("deploy_id") == current_app_id else ""
        print(f"- {record.get('deploy_id')} -> domain={record.get('domain')} file={path}{marker}")
else:
    print("No deploy.db claim found for the requested subdomain; fallback may come from another platform layer.")
PY
REMOTE
    echo "Hint: this usually means a leftover app or subdomain conflict still occupies the requested route." >&2
    exit 1
  fi
}

if [[ "$CLEAN_RESET" == "1" ]]; then
  clean_reset_remote
fi

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

validate_actual_domain
