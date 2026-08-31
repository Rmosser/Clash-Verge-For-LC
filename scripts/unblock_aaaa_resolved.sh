#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_paths.sh"
. "$ROOT/scripts/_lib_deploy_settings.sh"

# Optional local env override
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

HOST="${MICROSERVER_HOST:-rainierserver.heiyu.space}"
SSH_USER="${MICROSERVER_SSH_USER:-root}"
SSH_KEY="${MICROSERVER_SSH_KEY:-$HOME/.ssh/id_ed25519}"
CONFIRM_APPLY=0

DROPIN_DIR="/etc/systemd/resolved.conf.d"
DROPIN_FILE="$DROPIN_DIR/90-lzc-no-aaaa.conf"

if [[ "${1:-}" == "--confirm" && "$#" -eq 1 ]]; then
  CONFIRM_APPLY=1
elif [[ "$#" -gt 0 ]]; then
  echo "Usage: scripts/unblock_aaaa_resolved.sh [--confirm]" >&2
  exit 2
fi
if [[ "$CONFIRM_APPLY" != "1" ]]; then
  echo "Plan only: would remove ${DROPIN_FILE} and restart systemd-resolved on ${SSH_USER}@${HOST}."
  exit 0
fi
mihomo_require_apply_confirmation "$HOST" "$SSH_USER" "$CONFIRM_APPLY" "unblock_aaaa_resolved"

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$SSH_USER@$HOST" "$@"
}

echo "Removing AAAA refusal drop-in on $SSH_USER@$HOST ..."

ssh_remote DROPIN_FILE="$DROPIN_FILE" bash -s <<'REMOTE'
set -euo pipefail
if ! systemctl list-unit-files --no-pager 2>/dev/null | awk '{print $1}' | grep -qx systemd-resolved.service; then
  echo "ERROR: systemd-resolved.service not found on this microserver." >&2
  exit 2
fi
rm -f "$DROPIN_FILE"
systemctl restart systemd-resolved
sleep 1
systemctl is-active systemd-resolved >/dev/null
echo "OK: systemd-resolved restarted"
echo "--- resolvectl query google.com (may include IPv6 again)"
resolvectl query google.com | head -n 25 || true
REMOTE
