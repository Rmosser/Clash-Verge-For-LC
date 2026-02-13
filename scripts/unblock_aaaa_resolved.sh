#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_paths.sh"

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

DROPIN_DIR="/etc/systemd/resolved.conf.d"
DROPIN_FILE="$DROPIN_DIR/90-lzc-no-aaaa.conf"

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" "$@"
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
