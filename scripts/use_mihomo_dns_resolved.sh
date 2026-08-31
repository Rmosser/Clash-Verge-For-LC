#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_paths.sh"
. "$ROOT/scripts/_lib_deploy_settings.sh"

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
MODE="enable"
CONFIRM_APPLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    enable) MODE="enable"; shift ;;
    --disable) MODE="--disable"; shift ;;
    --confirm) CONFIRM_APPLY=1; shift ;;
    -h|--help) echo "Usage: $0 [--disable] [--confirm]"; exit 0 ;;
    *) echo "Usage: $0 [--disable] [--confirm]" >&2; exit 2 ;;
  esac
done
if [[ "$CONFIRM_APPLY" != "1" ]]; then
  echo "Plan only: would set resolver mode '${MODE}' on ${SSH_USER}@${HOST}."
  exit 0
fi
mihomo_require_apply_confirmation "$HOST" "$SSH_USER" "$CONFIRM_APPLY" "use_mihomo_dns_resolved"

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$SSH_USER@$HOST" "$@"
}

if [[ "$MODE" == "--disable" ]]; then
  echo "Reverting resolver DNS from mihomo on $SSH_USER@$HOST ..."
else
  echo "Pointing resolver DNS to mihomo on $SSH_USER@$HOST ..."
fi

ssh_remote MODE="$MODE" bash -s <<'REMOTE'
set -euo pipefail

resolve_fallback_dns() {
  if [[ -n "${MIHOMO_RESOLVED_FALLBACK_DNS:-}" ]]; then
    read -r -a configured <<<"${MIHOMO_RESOLVED_FALLBACK_DNS}"
    printf '%s\n' "${configured[@]}"
    return 0
  fi

  ip route show default 2>/dev/null | awk '/default/ {print $3; exit}'
}

if ! command -v resolvectl >/dev/null 2>&1; then
  echo "ERROR: resolvectl not found on this microserver." >&2
  exit 2
fi

iface="$(ip route show default 2>/dev/null | awk '/default/ {print $5; exit}')"
mapfile -t fallback_dns < <(resolve_fallback_dns)
if [[ -z "$iface" ]]; then
  echo "ERROR: unable to determine default route interface" >&2
  exit 3
fi

if [[ "$MODE" == "--disable" ]]; then
  resolvectl revert "$iface"
else
  if [[ "${#fallback_dns[@]}" -gt 0 ]]; then
    resolvectl dns "$iface" 127.0.0.1:1053 "${fallback_dns[@]}"
  else
    resolvectl dns "$iface" 127.0.0.1:1053
  fi
fi

resolvectl flush-caches >/dev/null 2>&1 || true
echo "OK: resolver state updated"
echo "--- resolvectl status (DNS servers should now include 127.0.0.1)"
resolvectl status | head -n 20 || true
REMOTE
