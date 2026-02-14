#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_paths.sh"

# Optional local env override (same pattern as other helper scripts).
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
DROPIN_FILE="$DROPIN_DIR/90-lzc-mihomo-dns.conf"

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" "$@"
}

echo "Pointing systemd-resolved DNS to mihomo on $SSH_USER@$HOST ..."

ssh_remote DROPIN_DIR="$DROPIN_DIR" DROPIN_FILE="$DROPIN_FILE" bash -s <<'REMOTE'
set -euo pipefail

if ! systemctl list-unit-files --no-pager 2>/dev/null | awk '{print $1}' | grep -qx systemd-resolved.service; then
  echo "ERROR: systemd-resolved.service not found on this microserver (LazyCat base OS may provide DNS differently)." >&2
  echo "Hint: edit /etc/resolv.conf to point at 127.0.0.1 and restart the service that owns it." >&2
  exit 2
fi

install -d -o root -g root -m 755 "$DROPIN_DIR"

cat >"$DROPIN_FILE" <<'CONF'
[Resolve]
# Forward all queries to mihomo so the DoH+respect-rules chain resolves AI/Telegram IPs cleanly.
DNS=127.0.0.1
# Keep the LazyCat router/link-local DNS as fallbacks so control-plane domains stay direct if mihomo stops.
FallbackDNS=192.168.1.1 fe80::1
CONF

systemctl restart systemd-resolved
sleep 1
systemctl is-active systemd-resolved >/dev/null

echo "OK: systemd-resolved restarted"
echo "--- resolvectl status (DNS servers should now include 127.0.0.1)"
resolvectl status | head -n 20 || true
REMOTE
