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

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" "$@"
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
