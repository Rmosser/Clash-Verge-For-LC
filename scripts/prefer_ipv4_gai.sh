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

if [[ "${1:-}" == "--confirm" && "$#" -eq 1 ]]; then
  CONFIRM_APPLY=1
elif [[ "$#" -gt 0 ]]; then
  echo "Usage: scripts/prefer_ipv4_gai.sh [--confirm]" >&2
  exit 2
fi
if [[ "$CONFIRM_APPLY" != "1" ]]; then
  echo "Plan only: would edit /etc/gai.conf on ${SSH_USER}@${HOST}."
  exit 0
fi
mihomo_require_apply_confirmation "$HOST" "$SSH_USER" "$CONFIRM_APPLY" "prefer_ipv4_gai"

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$SSH_USER@$HOST" "$@"
}

echo "Configuring /etc/gai.conf to prefer IPv4 destinations on $SSH_USER@$HOST ..."

ssh_remote bash -s <<'REMOTE'
set -euo pipefail

cfg=/etc/gai.conf
ts="$(date +%Y%m%d-%H%M%S)"
bk="/etc/gai.conf.bak.${ts}"

cp -a "$cfg" "$bk"

if grep -Eq '^[[:space:]]*precedence[[:space:]]+::ffff:0:0/96[[:space:]]+100[[:space:]]*$' "$cfg"; then
  echo "OK: already prefers IPv4 (line present)"
  exit 0
fi

cat >>"$cfg" <<'EOF'

# lzc-clash_mihome workaround: prefer IPv4 destinations (avoid stalls when proxy is V4-only egress).
precedence ::ffff:0:0/96  100
EOF
echo "OK: appended precedence ::ffff:0:0/96 100"

echo "--- effective line:"
grep -nE 'precedence[[:space:]]+::ffff:0:0/96' "$cfg" | tail -n 3 || true
echo "--- backup:"
echo "$bk"
REMOTE
