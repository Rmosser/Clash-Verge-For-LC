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
REMOTE_HELPER="$ROOT/scripts/lib/deploy_verge_api_readiness.sh"
CONTRACT_VALIDATOR="$ROOT/scripts/lib/validate_verge_api_contract.sh"

REMOTE_API="/usr/local/lib/lzc-mihomo/mihomo-verge-api.py"
REMOTE_UNIT="/etc/systemd/system/mihomo-verge-api.service"
REMOTE_CONTRACT="/usr/local/lib/lzc-mihomo/runtime-contract.json"
REMOTE_ROLLBACK_ROOT="/var/lib/mihomo/rollback/clash-verge-webport"

ACTION="deploy"
ROLLBACK_ID=""
CONFIRM_APPLY=0

usage() {
  cat <<'USAGE'
Usage: scripts/deploy_verge_api.sh [--rollback <opaque-backup-id>] --confirm

Deploys or restores the Verge API/runtime-contract pair on rainierdev only.
The script never reads .env, Mihomo config, subscriptions, nodes, or secrets.

Environment overrides:
  MICROSERVER_HOST       must remain rainierdev.heiyu.space
  MICROSERVER_SSH_USER   defaults to root
  MICROSERVER_SSH_KEY    defaults to ~/.ssh/id_ed25519
  The repository-reviewed host map supplies the SHA256 fingerprint; it is not
  caller configurable.
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
    --confirm)
      CONFIRM_APPLY=1
      shift
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
[[ "$SSH_USER" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]] || {
  echo "ERROR: invalid SSH user" >&2
  exit 1
}

command -v ssh >/dev/null 2>&1 || { echo "ERROR: ssh is required" >&2; exit 1; }
command -v scp >/dev/null 2>&1 || { echo "ERROR: scp is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required" >&2; exit 1; }
[[ -f "$REMOTE_HELPER" ]] || { echo "ERROR: missing Verge API deployment helper" >&2; exit 1; }

# Do this before uploading files or invoking the remote helper.  Rollback is a
# mutation too, so it uses the same explicit target/identity gate.
source "$ROOT/scripts/_lib_deploy_settings.sh"
MIHOMO_APPROVED_HOST="$TARGET_HOST"
mihomo_require_apply_confirmation "$HOST" "$SSH_USER" "$CONFIRM_APPLY" "deploy_verge_api"

ssh_args=(
  -i "$SSH_KEY"
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}"
)

if [[ "$ACTION" == "rollback" ]]; then
  [[ "$ROLLBACK_ID" =~ ^backup\.[A-Za-z0-9]{8}$ ]] || {
    echo "ERROR: invalid opaque backup id" >&2
    exit 1
  }

  ssh "${ssh_args[@]}" "$SSH_USER@$HOST" \
    ACTION="$ACTION" \
    REMOTE_ROLLBACK_ROOT="$REMOTE_ROLLBACK_ROOT" \
    ROLLBACK_ID="$ROLLBACK_ID" \
    REMOTE_API="$REMOTE_API" \
    REMOTE_UNIT="$REMOTE_UNIT" \
    REMOTE_CONTRACT="$REMOTE_CONTRACT" \
    bash -s < "$REMOTE_HELPER"
  exit 0
fi

command -v git >/dev/null 2>&1 || { echo "ERROR: git is required" >&2; exit 1; }
[[ -x "$CONTRACT_VALIDATOR" ]] || { echo "ERROR: missing local contract validator" >&2; exit 1; }
[[ -f "$API_LOCAL" && -f "$UNIT_LOCAL" && -f "$CONTRACT_LOCAL" ]] || {
  echo "ERROR: missing API/runtime-contract source files" >&2
  exit 1
}

python3 -m py_compile "$API_LOCAL"
read -r EXPECTED_BUILD_ID EXPECTED_GIT_COMMIT < <(
  "$CONTRACT_VALIDATOR" "$CONTRACT_LOCAL" "$ROOT"
)

[[ ${#EXPECTED_BUILD_ID} -le 128 &&
   "$EXPECTED_BUILD_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || {
  echo "ERROR: runtime contract buildId is not safe for remote transport" >&2
  exit 1
}
[[ "$EXPECTED_GIT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo "ERROR: runtime contract gitCommit is not safe for remote transport" >&2
  exit 1
}

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$BASHPID"
REMOTE_TMP_ROOT="/tmp/clash-verge-webport-$RUN_ID"
REMOTE_TMP_API="$REMOTE_TMP_ROOT/api.py"
REMOTE_TMP_UNIT="$REMOTE_TMP_ROOT/unit"
REMOTE_TMP_CONTRACT="$REMOTE_TMP_ROOT/runtime-contract.json"

cleanup_remote_tmp() {
  # REMOTE_TMP_ROOT is generated locally from a fixed prefix, UTC digits, and BASHPID.
  # shellcheck disable=SC2029
  ssh "${ssh_args[@]}" "$SSH_USER@$HOST" "rm -rf -- '$REMOTE_TMP_ROOT'" >/dev/null 2>&1 || true
}
trap cleanup_remote_tmp EXIT

# REMOTE_TMP_ROOT is generated locally and contains no remote-shell metacharacters.
# shellcheck disable=SC2029
ssh "${ssh_args[@]}" "$SSH_USER@$HOST" "install -d -m 700 '$REMOTE_TMP_ROOT'"
scp "${ssh_args[@]}" "$API_LOCAL" "$SSH_USER@$HOST:$REMOTE_TMP_API" >/dev/null
scp "${ssh_args[@]}" "$UNIT_LOCAL" "$SSH_USER@$HOST:$REMOTE_TMP_UNIT" >/dev/null
scp "${ssh_args[@]}" "$CONTRACT_LOCAL" "$SSH_USER@$HOST:$REMOTE_TMP_CONTRACT" >/dev/null

ssh "${ssh_args[@]}" "$SSH_USER@$HOST" \
  ACTION="$ACTION" \
  REMOTE_TMP_ROOT="$REMOTE_TMP_ROOT" \
  REMOTE_TMP_API="$REMOTE_TMP_API" \
  REMOTE_TMP_UNIT="$REMOTE_TMP_UNIT" \
  REMOTE_TMP_CONTRACT="$REMOTE_TMP_CONTRACT" \
  REMOTE_ROLLBACK_ROOT="$REMOTE_ROLLBACK_ROOT" \
  REMOTE_API="$REMOTE_API" \
  REMOTE_UNIT="$REMOTE_UNIT" \
  REMOTE_CONTRACT="$REMOTE_CONTRACT" \
  EXPECTED_BUILD_ID="$EXPECTED_BUILD_ID" \
  EXPECTED_GIT_COMMIT="$EXPECTED_GIT_COMMIT" \
  bash -s < "$REMOTE_HELPER"
