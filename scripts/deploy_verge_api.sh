#!/usr/bin/env bash
set -Eeuo pipefail

# This script deliberately does not source .env or any private configuration.
# It owns only the Verge API/runtime-contract pair on the development host.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly TARGET_HOST="rainierdev.heiyu.space"
HOST="${MICROSERVER_HOST:-$TARGET_HOST}"
SSH_USER="${MICROSERVER_SSH_USER:-root}"
SSH_KEY="${MICROSERVER_SSH_KEY:-$HOME/.ssh/id_ed25519}"

API_LOCAL="$ROOT/infra/microserver/mihomo-verge-api.py"
UNIT_LOCAL="$ROOT/infra/microserver/mihomo-verge-api.service"
CONTRACT_LOCAL="$ROOT/src/mihomo-dashboard-app/runtime-contract.json"

REMOTE_API="/usr/local/lib/lzc-mihomo/mihomo-verge-api.py"
REMOTE_UNIT="/etc/systemd/system/mihomo-verge-api.service"
REMOTE_CONTRACT="/usr/local/lib/lzc-mihomo/runtime-contract.json"
REMOTE_ROLLBACK_ROOT="/var/lib/mihomo/rollback/clash-verge-webport"

ACTION="deploy"
ROLLBACK_ID=""

usage() {
  cat <<'USAGE'
Usage: scripts/deploy_verge_api.sh [--rollback <opaque-backup-id>]

Deploys or restores the Verge API/runtime-contract pair on rainierdev only.
The script never reads .env, Mihomo config, subscriptions, nodes, or secrets.

Environment overrides:
  MICROSERVER_HOST       must remain rainierdev.heiyu.space
  MICROSERVER_SSH_USER   defaults to root
  MICROSERVER_SSH_KEY    defaults to ~/.ssh/id_ed25519
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rollback)
      [[ $# -ge 2 ]] || { echo "ERROR: --rollback requires an opaque backup id" >&2; exit 2; }
      ACTION="rollback"
      ROLLBACK_ID="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ "$HOST" == "$TARGET_HOST" ]] || {
  echo "ERROR: refusing non-development target: $HOST" >&2
  echo "Only $TARGET_HOST is allowed for this migration." >&2
  exit 1
}

command -v ssh >/dev/null 2>&1 || { echo "ERROR: ssh is required" >&2; exit 1; }
command -v scp >/dev/null 2>&1 || { echo "ERROR: scp is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required" >&2; exit 1; }

ssh_args=(
  -i "$SSH_KEY"
  -o BatchMode=yes
  -o StrictHostKeyChecking=accept-new
)

if [[ "$ACTION" == "rollback" ]]; then
  [[ "$ROLLBACK_ID" =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "ERROR: invalid opaque backup id" >&2
    exit 1
  }

  ssh "${ssh_args[@]}" "$SSH_USER@$HOST" \
    ROLLBACK_ROOT="$REMOTE_ROLLBACK_ROOT" \
    ROLLBACK_ID="$ROLLBACK_ID" \
    REMOTE_API="$REMOTE_API" \
    REMOTE_UNIT="$REMOTE_UNIT" \
    REMOTE_CONTRACT="$REMOTE_CONTRACT" \
    bash -s <<'REMOTE'
set -Eeuo pipefail

backup_dir="$ROLLBACK_ROOT/$ROLLBACK_ID"
[[ -d "$backup_dir" ]] || { echo "ERROR: requested backup is not available" >&2; exit 1; }
[[ -f "$backup_dir/api.py" && -f "$backup_dir/unit" && -f "$backup_dir/runtime-contract.json" ]] || {
  echo "ERROR: requested backup is incomplete" >&2
  exit 1
}

install -o root -g root -m 755 "$backup_dir/api.py" "$REMOTE_API"
install -o root -g root -m 644 "$backup_dir/unit" "$REMOTE_UNIT"
install -o root -g root -m 644 "$backup_dir/runtime-contract.json" "$REMOTE_CONTRACT"
systemctl daemon-reload
systemctl restart mihomo-verge-api.service
systemctl is-active mihomo-verge-api.service >/dev/null
curl --silent --show-error --fail --max-time 8 http://172.18.0.1:9091/healthz >/dev/null
printf 'rollback_ok backup_id=%s\n' "$ROLLBACK_ID"
REMOTE
  exit 0
fi

[[ -f "$API_LOCAL" && -f "$UNIT_LOCAL" && -f "$CONTRACT_LOCAL" ]] || {
  echo "ERROR: missing API/runtime-contract source files" >&2
  exit 1
}

python3 -m py_compile "$API_LOCAL"
python3 - "$CONTRACT_LOCAL" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
required = {
    "appVersion": "2.5.2-webport.0",
    "apiSchemaVersion": "2026.08-lzc-v2",
    "uiSchemaVersion": "2026.08-lzc-v2",
    "packageFingerprint": "cloud.lazycat.app.clash-verge-for-lc/2.5.2-webport.0",
}
for key, expected in required.items():
    if payload.get(key) != expected:
        raise SystemExit(f"ERROR: runtime contract {key} is not the v2.5.2 WebPort value")
if payload.get("capabilities", {}).get("systemProxy", {}).get("mode") != "disabled":
    raise SystemExit("ERROR: runtime contract must keep systemProxy disabled")
PY

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$BASHPID"
REMOTE_TMP_ROOT="/tmp/clash-verge-webport-$RUN_ID"
REMOTE_TMP_API="$REMOTE_TMP_ROOT/api.py"
REMOTE_TMP_UNIT="$REMOTE_TMP_ROOT/unit"
REMOTE_TMP_CONTRACT="$REMOTE_TMP_ROOT/runtime-contract.json"

cleanup_remote_tmp() {
  ssh "${ssh_args[@]}" "$SSH_USER@$HOST" "rm -rf -- '$REMOTE_TMP_ROOT'" >/dev/null 2>&1 || true
}
trap cleanup_remote_tmp EXIT

ssh "${ssh_args[@]}" "$SSH_USER@$HOST" "install -d -m 700 '$REMOTE_TMP_ROOT'"
scp "${ssh_args[@]}" "$API_LOCAL" "$SSH_USER@$HOST:$REMOTE_TMP_API" >/dev/null
scp "${ssh_args[@]}" "$UNIT_LOCAL" "$SSH_USER@$HOST:$REMOTE_TMP_UNIT" >/dev/null
scp "${ssh_args[@]}" "$CONTRACT_LOCAL" "$SSH_USER@$HOST:$REMOTE_TMP_CONTRACT" >/dev/null

ssh "${ssh_args[@]}" "$SSH_USER@$HOST" \
  REMOTE_TMP_ROOT="$REMOTE_TMP_ROOT" \
  REMOTE_TMP_API="$REMOTE_TMP_API" \
  REMOTE_TMP_UNIT="$REMOTE_TMP_UNIT" \
  REMOTE_TMP_CONTRACT="$REMOTE_TMP_CONTRACT" \
  REMOTE_ROLLBACK_ROOT="$REMOTE_ROLLBACK_ROOT" \
  REMOTE_API="$REMOTE_API" \
  REMOTE_UNIT="$REMOTE_UNIT" \
  REMOTE_CONTRACT="$REMOTE_CONTRACT" \
  bash -s <<'REMOTE'
set -Eeuo pipefail

backup_dir=""
restore_backup() {
  [[ -n "$backup_dir" && -d "$backup_dir" ]] || return 0
  install -o root -g root -m 755 "$backup_dir/api.py" "$REMOTE_API" || true
  install -o root -g root -m 644 "$backup_dir/unit" "$REMOTE_UNIT" || true
  install -o root -g root -m 644 "$backup_dir/runtime-contract.json" "$REMOTE_CONTRACT" || true
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl restart mihomo-verge-api.service >/dev/null 2>&1 || true
}

install -d -o root -g root -m 700 "$REMOTE_ROLLBACK_ROOT"
backup_dir="$(mktemp -d "$REMOTE_ROLLBACK_ROOT/backup.XXXXXXXX")"
backup_id="${backup_dir##*/}"

install -o root -g root -m 755 "$REMOTE_API" "$backup_dir/api.py"
install -o root -g root -m 644 "$REMOTE_UNIT" "$backup_dir/unit"
install -o root -g root -m 644 "$REMOTE_CONTRACT" "$backup_dir/runtime-contract.json"
chmod 700 "$backup_dir"

if ! python3 -m py_compile "$REMOTE_TMP_API"; then
  restore_backup
  echo "ERROR: remote API syntax validation failed" >&2
  exit 1
fi

if ! python3 - "$REMOTE_TMP_CONTRACT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("appVersion") != "2.5.2-webport.0":
    raise SystemExit(1)
if payload.get("apiSchemaVersion") != "2026.08-lzc-v2":
    raise SystemExit(1)
if payload.get("uiSchemaVersion") != "2026.08-lzc-v2":
    raise SystemExit(1)
if payload.get("packageFingerprint") != "cloud.lazycat.app.clash-verge-for-lc/2.5.2-webport.0":
    raise SystemExit(1)
if payload.get("capabilities", {}).get("systemProxy", {}).get("mode") != "disabled":
    raise SystemExit(1)
PY
then
  restore_backup
  echo "ERROR: remote runtime contract validation failed" >&2
  exit 1
fi

mihomo_before="$(systemctl show mihomo.service -p ActiveEnterTimestampMonotonic --value)"
mihomo_version_before="$(/usr/local/bin/mihomo -v 2>/dev/null | head -n 1)"

if ! install -o root -g root -m 755 "$REMOTE_TMP_API" "$REMOTE_API" ||
   ! install -o root -g root -m 644 "$REMOTE_TMP_UNIT" "$REMOTE_UNIT" ||
   ! install -o root -g root -m 644 "$REMOTE_TMP_CONTRACT" "$REMOTE_CONTRACT"; then
  restore_backup
  echo "ERROR: API/runtime-contract installation failed" >&2
  exit 1
fi

if ! systemctl daemon-reload ||
   ! systemctl restart mihomo-verge-api.service ||
   ! systemctl is-active mihomo-verge-api.service >/dev/null ||
   ! curl --silent --show-error --fail --max-time 8 http://172.18.0.1:9091/healthz >/dev/null; then
  restore_backup
  echo "ERROR: Verge API health validation failed; previous pair restored" >&2
  exit 1
fi

runtime_probe="/tmp/clash-verge-webport-runtime-info-$BASHPID.json"
if ! curl --silent --show-error --fail --max-time 8 \
  'http://172.18.0.1:9091/runtime-info?scope=contract' >"$runtime_probe" ||
   ! python3 - "$runtime_probe" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "appVersion": "2.5.2-webport.0",
    "apiSchemaVersion": "2026.08-lzc-v2",
    "uiSchemaVersion": "2026.08-lzc-v2",
    "packageFingerprint": "cloud.lazycat.app.clash-verge-for-lc/2.5.2-webport.0",
}
if any(payload.get(key) != value for key, value in expected.items()):
    raise SystemExit(1)
if payload.get("systemProxy", {}).get("mode") != "disabled":
    raise SystemExit(1)
PY
then
  rm -f "$runtime_probe"
  restore_backup
  echo "ERROR: runtime-info contract validation failed; previous pair restored" >&2
  exit 1
fi
rm -f "$runtime_probe"

mihomo_after="$(systemctl show mihomo.service -p ActiveEnterTimestampMonotonic --value)"
mihomo_version_after="$(/usr/local/bin/mihomo -v 2>/dev/null | head -n 1)"
if [[ "$mihomo_before" != "$mihomo_after" || "$mihomo_version_before" != "$mihomo_version_after" ]]; then
  restore_backup
  echo "ERROR: Mihomo service or binary changed during Verge API deployment" >&2
  exit 1
fi

printf 'deploy_ok backup_id=%s mihomo=%s\n' "$backup_id" "$mihomo_version_after"
REMOTE
