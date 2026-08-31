#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_paths.sh"

# shellcheck source=/dev/null
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
APP_DIR="$ROOT/src/mihomo-dashboard-app"
LPK="$APP_DIR/mihomo-dashboard.lpk"
APP_ID="cloud.lazycat.app.clash-verge-for-lc"
readonly EXPECTED_URL="https://clash.rainierserver.heiyu.space"
if [[ -n "${MIHOMO_DASHBOARD_URL:-}" && "$MIHOMO_DASHBOARD_URL" != "$EXPECTED_URL" ]]; then
  echo "ERROR: MIHOMO_DASHBOARD_URL may only narrow to the reviewed URL ${EXPECTED_URL}" >&2
  exit 2
fi
[[ "$HOST" == "$EXPECTED_HOST" ]] || {
  echo "ERROR: dashboard deployment is reviewed only for ${EXPECTED_HOST}" >&2
  exit 2
}
EXPECTED_DOMAIN="${EXPECTED_URL#http://}"
EXPECTED_DOMAIN="${EXPECTED_DOMAIN#https://}"
EXPECTED_DOMAIN="${EXPECTED_DOMAIN%%/*}"
EXPECTED_SUBDOMAIN="${EXPECTED_DOMAIN%%.*}"
CLEAN_RESET=0
CONFIRM_APPLY=0
CLEAN_RESET_BACKUP_DIR=""
CLEAN_RESET_MUTATED=0

usage() {
  cat <<'USAGE'
Usage: scripts/deploy_dashboard.sh [options]

Options:
  --clean-reset  Reset only the current dashboard app and Verge local state before install
  --confirm      Confirm the approved host and SSH fingerprint before installing or resetting
  -h, --help     Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean-reset)
      CLEAN_RESET=1
      ;;
    --confirm)
      CONFIRM_APPLY=1
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
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$SSH_USER@$HOST" "$@"
}

clean_reset_remote() {
  echo "Running clean reset on $SSH_USER@$HOST ..."
  local backup_output

  # Capture a verified rollback artifact before touching the app or its state.
  # A clean reset without a complete snapshot is refused.
backup_output="$(ssh_remote bash -s <<'REMOTE'
set -euo pipefail
install -d -m 755 /run/lock
exec 9>/run/lock/clash-verge-deploy.lock
flock -n 9 || { echo "ERROR: another Clash-Verge deployment is active" >&2; exit 1; }
backup_root="/var/lib/mihomo/rollback/dashboard-reset"
install -d -m 700 "$backup_root"
backup_dir="$(mktemp -d "$backup_root/dashboard-reset.XXXXXX")"
install -d -m 700 "$backup_dir"
paths=(
  "/lzcsys/data/system/pkgm/apps/cloud.lazycat.app.clash-verge-for-lc"
  "/lzcsys/data/system/pkgm/run/cloud.lazycat.app.clash-verge-for-lc"
  "/lzcsys/data/system/pkgm/deploy.var/cloud.lazycat.app.clash-verge-for-lc"
  "/lzcsys/data/system/pkgm/lpks/cloud.lazycat.app.clash-verge-for-lc.lpk"
  "/lzcsys/data/appcache/cloud.lazycat.app.clash-verge-for-lc"
  "/lzcsys/data/appvar/cloud.lazycat.app.clash-verge-for-lc"
    "/lzcsys/run/app/cloud.lazycat.app.clash-verge-for-lc"
    "/lzcsys/data/system/pkgm/deploy.db"
    "/var/lib/mihomo/verge"
  )
python3 - <<'PY' "${paths[@]}"
import stat
import sys
from pathlib import Path

for raw in sys.argv[1:]:
    path = Path(raw)
    if not path.is_absolute():
        raise SystemExit(f"unsafe non-absolute clean-reset path: {path}")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            break
        except OSError as exc:
            raise SystemExit(f"cannot inspect clean-reset path {current}: {exc}") from exc
        if stat.S_ISLNK(mode):
            raise SystemExit(f"refusing clean-reset path with symlink ancestor: {current}")
PY
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
    echo "ERROR: unsupported clean-reset target type: $path" >&2
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
test -s "$backup_dir/manifest.tsv" || {
  echo "ERROR: clean reset snapshot is empty" >&2
  exit 1
}
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
  CLEAN_RESET_BACKUP_DIR="$(awk -F= '$1 == "backup_dir" {print substr($0, index($0, "=") + 1); exit}' <<<"$backup_output")"
  [[ "$CLEAN_RESET_BACKUP_DIR" == /var/lib/mihomo/rollback/dashboard-reset/* ]] || {
    echo "ERROR: clean reset did not return a private rollback directory" >&2
    return 1
  }

  CLEAN_RESET_MUTATED=1
  lzc-cli app uninstall "$APP_ID" >/dev/null
  local app_status
  app_status="$(lzc-cli app status "$APP_ID" 2>/dev/null || true)"
  if grep -Eiq '(^|[^a-z])installed([^a-z]|$)|running|active' <<<"$app_status"; then
    echo "ERROR: app uninstall did not produce a stopped/absent status; refusing state deletion" >&2
    return 1
  fi

  ssh_remote bash -s <<'REMOTE'
set -euo pipefail
install -d -m 755 /run/lock
exec 9>/run/lock/clash-verge-deploy.lock
flock -n 9 || { echo "ERROR: another Clash-Verge deployment is active" >&2; exit 1; }

current_app_id="cloud.lazycat.app.clash-verge-for-lc"
current_paths=(
  "/lzcsys/data/system/pkgm/apps/${current_app_id}"
  "/lzcsys/data/system/pkgm/run/${current_app_id}"
  "/lzcsys/data/system/pkgm/deploy.var/${current_app_id}"
  "/lzcsys/data/system/pkgm/lpks/${current_app_id}.lpk"
  "/lzcsys/data/appcache/${current_app_id}"
  "/lzcsys/data/appvar/${current_app_id}"
  "/lzcsys/run/app/${current_app_id}"
)

python3 - <<'PY' "${current_paths[@]}" "/var/lib/mihomo/verge"
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
            raise SystemExit(f"cannot inspect clean-reset path {current}: {exc}") from exc
        if stat.S_ISLNK(mode):
            raise SystemExit(f"refusing clean-reset path with symlink ancestor: {current}")
PY

for path in "${current_paths[@]}"; do
  rm -rf -- "$path"
  test ! -e "$path" || { echo "ERROR: failed to remove $path" >&2; exit 1; }
done

python3 - <<'PY' "$current_app_id"
from pathlib import Path

import sys

current_app_id = sys.argv[1]
markers = (current_app_id.encode("utf-8"),)
root = Path("/lzcsys/data/system/pkgm/deploy.db")
for path in root.rglob("*"):
    if not path.is_file():
        continue
    try:
        payload = path.read_bytes()
    except OSError:
        continue
    if any(marker in payload for marker in markers):
        path.unlink()
PY

rm -rf -- /var/lib/mihomo/verge
test ! -e /var/lib/mihomo/verge
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

restore_dashboard_reset() {
  [[ -n "$CLEAN_RESET_BACKUP_DIR" ]] || return 0
  echo "Restoring dashboard clean-reset backup: $CLEAN_RESET_BACKUP_DIR" >&2
  ssh_remote BACKUP_DIR="$CLEAN_RESET_BACKUP_DIR" bash -s <<'REMOTE'
set -euo pipefail
backup_dir="$BACKUP_DIR"
unknown_marker="$backup_dir/UNKNOWN"
install -d -m 755 /run/lock
exec 9>/run/lock/clash-verge-deploy.lock
flock -n 9 || { echo "ERROR: another Clash-Verge deployment is active" >&2; exit 1; }
[[ "$backup_dir" =~ ^/var/lib/mihomo/rollback/dashboard-reset/dashboard-reset\.[A-Za-z0-9]+$ ]] || exit 1
[[ -d "$backup_dir" && -f "$backup_dir/manifest.tsv" && -f "$backup_dir/manifest.sha256" &&
   -f "$backup_dir/service-state.tsv" && -f "$backup_dir/service-state.sha256" ]] || exit 1
printf 'rollback_status=UNKNOWN\n' > "$unknown_marker"
sha256sum -c "$backup_dir/manifest.sha256" >/dev/null
sha256sum -c "$backup_dir/service-state.sha256" >/dev/null
while IFS=$'\t' read -r unit active enabled; do
  [[ "$unit" == mihomo-verge-api.service ]] || exit 1
  case "$active" in active|inactive) ;; *) exit 1 ;; esac
  case "$enabled" in enabled|disabled|static|masked) ;; *) exit 1 ;; esac
done < "$backup_dir/service-state.tsv"
approved_paths=(
  "/lzcsys/data/system/pkgm/apps/cloud.lazycat.app.clash-verge-for-lc"
  "/lzcsys/data/system/pkgm/run/cloud.lazycat.app.clash-verge-for-lc"
  "/lzcsys/data/system/pkgm/deploy.var/cloud.lazycat.app.clash-verge-for-lc"
  "/lzcsys/data/system/pkgm/lpks/cloud.lazycat.app.clash-verge-for-lc.lpk"
  "/lzcsys/data/appcache/cloud.lazycat.app.clash-verge-for-lc"
  "/lzcsys/data/appvar/cloud.lazycat.app.clash-verge-for-lc"
  "/lzcsys/run/app/cloud.lazycat.app.clash-verge-for-lc"
  "/lzcsys/data/system/pkgm/deploy.db"
  "/var/lib/mihomo/verge"
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
    enabled) systemctl unmask "$unit" >/dev/null 2>&1 || true; systemctl enable "$unit" >/dev/null ;;
    disabled) systemctl unmask "$unit" >/dev/null 2>&1 || true; systemctl disable "$unit" >/dev/null 2>&1 || true ;;
    static) systemctl unmask "$unit" >/dev/null 2>&1 || true ;;
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
echo "dashboard clean-reset rollback readback: manifest=ok service_state=ok"
REMOTE
}

on_exit() {
  local status=$?
  trap - EXIT
  set +e
  if [[ "$CLEAN_RESET_MUTATED" == "1" && "$status" != "0" ]]; then
    restore_dashboard_reset || echo "ERROR: dashboard clean-reset rollback failed; preserve ${CLEAN_RESET_BACKUP_DIR:-unknown}" >&2
  fi
  mihomo_cleanup_known_hosts
  exit "$status"
}
trap on_exit EXIT

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
    echo "ERROR: expected dashboard domain $EXPECTED_DOMAIN but platform assigned $actual_domain" >&2
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

validate_dist_config() {
  local config_file="$APP_DIR/dist/lzcapp-config.js"

  python3 - <<'PY' "$config_file"
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
for key in ("secret", "vergeApiSecret"):
    match = re.search(rf"{key}:\s*\"([^\"]*)\"", text)
    if not match:
        raise SystemExit(f"ERROR: {path} missing {key} in lzcapp-config.js")
    if match.group(1):
        raise SystemExit(f"ERROR: {path} still embeds non-empty {key}")
print("Verified dist/lzcapp-config.js uses runtime bootstrap only.")
PY
}

validate_remote_runtime_apis() {
  echo "Validating remote verge-api/controller chain ..."
  ssh_remote CONTROLLER_URL="http://172.18.0.1:9090" VERGE_API_URL="http://172.18.0.1:9091" bash -s <<'REMOTE'
set -euo pipefail

controller_secret="$(
  grep -E '^[[:space:]]*secret:' /etc/mihomo/config.yaml \
    | head -n 1 \
    | sed -E "s/^[[:space:]]*secret:[[:space:]]*//" \
    | sed -E "s/^'(.*)'\$|^\"(.*)\"\$/\\1\\2/" \
    | tr -d '\r\n'
)"
verge_secret="$(tr -d '\r\n' </etc/mihomo/verge-api.secret)"

if [[ -z "$controller_secret" ]]; then
  echo "ERROR: missing controller secret on remote microserver" >&2
  exit 1
fi

if [[ -z "$verge_secret" ]]; then
  echo "ERROR: missing verge-api secret on remote microserver" >&2
  exit 1
fi

curl -fsS "${VERGE_API_URL%/}/healthz" >/dev/null
public_config="$(curl -fsS "${VERGE_API_URL%/}/public-config?token=${verge_secret}")"
python3 - <<'PY' "$public_config"
import json
import sys

payload = json.loads(sys.argv[1])
if not payload.get("secret"):
    raise SystemExit("ERROR: /public-config did not return controller secret")
if payload.get("mihomoBaseUrl") != "/api":
    raise SystemExit(f"ERROR: unexpected mihomoBaseUrl: {payload.get('mihomoBaseUrl')!r}")
if payload.get("vergeApiBaseUrl") != "/verge-api":
    raise SystemExit(f"ERROR: unexpected vergeApiBaseUrl: {payload.get('vergeApiBaseUrl')!r}")
PY

curl -fsS -H "Authorization: Bearer ${controller_secret}" "${CONTROLLER_URL%/}/version" >/dev/null
curl -fsS -H "Authorization: Bearer ${controller_secret}" "${CONTROLLER_URL%/}/configs" >/dev/null
curl -fsS -H "Authorization: Bearer ${controller_secret}" "${CONTROLLER_URL%/}/proxies" >/dev/null

python3 - <<'PY' "$CONTROLLER_URL" "$controller_secret" "/traffic"
import base64
import hashlib
import os
import socket
import sys
from urllib.parse import urlparse

url, secret, path = sys.argv[1:]
parsed = urlparse(url)
host = parsed.hostname or "127.0.0.1"
port = parsed.port or (443 if parsed.scheme == "https" else 80)
key = base64.b64encode(os.urandom(16)).decode("ascii")
request = (
    f"GET {path} HTTP/1.1\r\n"
    f"Host: {host}:{port}\r\n"
    "Upgrade: websocket\r\n"
    "Connection: Upgrade\r\n"
    f"Sec-WebSocket-Key: {key}\r\n"
    "Sec-WebSocket-Version: 13\r\n"
    f"Authorization: Bearer {secret}\r\n"
    "\r\n"
)
expected_accept = base64.b64encode(
    hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
).decode("ascii")

with socket.create_connection((host, port), timeout=5) as conn:
    conn.sendall(request.encode("ascii"))
    response = conn.recv(4096).decode("utf-8", errors="replace")

if "101" not in response.splitlines()[0]:
    raise SystemExit(f"ERROR: websocket handshake failed for {path}: {response.splitlines()[0]}")
if f"sec-websocket-accept: {expected_accept}".lower() not in response.lower():
    raise SystemExit(f"ERROR: websocket accept mismatch for {path}")
PY

python3 - <<'PY' "$CONTROLLER_URL" "$controller_secret" "/memory"
import base64
import hashlib
import os
import socket
import sys
from urllib.parse import urlparse

url, secret, path = sys.argv[1:]
parsed = urlparse(url)
host = parsed.hostname or "127.0.0.1"
port = parsed.port or (443 if parsed.scheme == "https" else 80)
key = base64.b64encode(os.urandom(16)).decode("ascii")
request = (
    f"GET {path} HTTP/1.1\r\n"
    f"Host: {host}:{port}\r\n"
    "Upgrade: websocket\r\n"
    "Connection: Upgrade\r\n"
    f"Sec-WebSocket-Key: {key}\r\n"
    "Sec-WebSocket-Version: 13\r\n"
    f"Authorization: Bearer {secret}\r\n"
    "\r\n"
)
expected_accept = base64.b64encode(
    hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
).decode("ascii")

with socket.create_connection((host, port), timeout=5) as conn:
    conn.sendall(request.encode("ascii"))
    response = conn.recv(4096).decode("utf-8", errors="replace")

if "101" not in response.splitlines()[0]:
    raise SystemExit(f"ERROR: websocket handshake failed for {path}: {response.splitlines()[0]}")
if f"sec-websocket-accept: {expected_accept}".lower() not in response.lower():
    raise SystemExit(f"ERROR: websocket accept mismatch for {path}")
PY
REMOTE
}

if [[ "${LAZYCAT_BOX:-}" != "" && "${LAZYCAT_BOX}" != "$EXPECTED_BOX" ]]; then
  echo "ERROR: LAZYCAT_BOX must narrow to ${EXPECTED_BOX}" >&2
  exit 2
fi

# Bind the CLI plane before any uninstall/reset.  This deployment is
# intentionally fail-closed rather than silently switching a user's global
# default box; the operator must select the reviewed box explicitly.
lzc-cli box list >/dev/null
CURRENT_BOX="$(lzc-cli box default 2>/dev/null || true)"
[[ "$CURRENT_BOX" == "$EXPECTED_BOX" ]] || {
  echo "ERROR: lzc-cli default box '${CURRENT_BOX:-unknown}' is not ${EXPECTED_BOX}; refusing remote mutation" >&2
  exit 2
}

# The SSH identity gate must precede every remote read/write, including a
# destructive clean reset.
mihomo_require_apply_confirmation "$HOST" "$SSH_USER" "$CONFIRM_APPLY" "deploy_dashboard"

if [[ "$CLEAN_RESET" == "1" ]]; then
  clean_reset_remote
fi

cd "$APP_DIR"

echo "Building Clash Verge Rev web assets ..."
npm exec --yes --package=pnpm@11.3.0 -- pnpm build >/dev/null

if [[ ! -f "$APP_DIR/dist/index.html" ]]; then
  echo "ERROR: missing dashboard assets under $APP_DIR/dist (pnpm build failed or produced no index.html)" >&2
  exit 1
fi
validate_dist_config

echo "Building dashboard LPK ..."
lzc-cli project build -f lzc-build.yml -o "$LPK" >/dev/null

echo "Installing dashboard app ..."
lzc-cli app install "$LPK"

validate_actual_domain
validate_remote_runtime_apis

# The reset snapshot remains on the target for manual rollback.  Only after
# install, identity, and runtime health readbacks succeed is it safe to keep
# the new state instead of restoring the pre-reset state in the EXIT trap.
CLEAN_RESET_MUTATED=0
