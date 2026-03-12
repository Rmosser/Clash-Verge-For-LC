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
MODE="${1:-enable}"

if [[ "$MODE" != "enable" && "$MODE" != "--disable" ]]; then
  echo "Usage: $0 [--disable]" >&2
  exit 1
fi

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" "$@"
}

if [[ "$MODE" == "--disable" ]]; then
  echo "Reverting resolver DNS from mihomo on $SSH_USER@$HOST ..."
else
  echo "Pointing resolver DNS to mihomo on $SSH_USER@$HOST ..."
fi

ssh_remote MODE="$MODE" bash -s <<'REMOTE'
set -euo pipefail

if ! command -v resolvectl >/dev/null 2>&1; then
  echo "ERROR: resolvectl not found on this microserver." >&2
  exit 2
fi

iface="$(ip route show default 2>/dev/null | awk '/default/ {print $5; exit}')"
if [[ -z "$iface" ]]; then
  echo "ERROR: unable to determine default route interface" >&2
  exit 3
fi

if [[ "$MODE" == "--disable" ]]; then
  resolvectl revert "$iface"
else
  resolvectl dns "$iface" 127.0.0.1:1053 192.168.1.1 fe80::1
fi

resolvectl flush-caches >/dev/null 2>&1 || true
echo "OK: resolver state updated"
echo "--- resolvectl status (DNS servers should now include 127.0.0.1)"
resolvectl status | head -n 20 || true
REMOTE
