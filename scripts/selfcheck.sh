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
CONTROLLER_URL="${MIHOMO_CONTROLLER_URL:-http://172.18.0.1:9090}"
VERGE_API_URL="${MIHOMO_VERGE_API_URL:-http://172.18.0.1:9091}"

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" "$@"
}

get_secret_remote() {
  ssh_remote "set -euo pipefail; grep -E '^[[:space:]]*secret:' /etc/mihomo/config.yaml | head -n 1 | sed -E \"s/^[[:space:]]*secret:[[:space:]]*//\" | sed -E \"s/^'(.*)'\\$|^\\\"(.*)\\\"\\$/\\1\\2/\" | tr -d '\r\n'"
}

get_verge_secret_remote() {
  ssh_remote "set -euo pipefail; tr -d '\r\n' </etc/mihomo/verge-api.secret"
}

detect_mode() {
  if ssh_remote "systemctl list-unit-files --no-pager 2>/dev/null | awk '{print \$1}' | grep -qx mihomo.service"; then
    echo "systemd"
    return 0
  fi
  if ssh_remote "command -v docker >/dev/null 2>&1 && docker ps -a --format '{{.Names}}' | grep -qx mihomo"; then
    echo "docker"
    return 0
  fi
  echo "unknown"
}

mode="$(detect_mode)"
echo "== Selfcheck =="
echo "host=$HOST mode=$mode"

echo "== Status =="
if [[ "$mode" == "systemd" ]]; then
  ssh_remote "systemctl is-active mihomo && systemctl status mihomo --no-pager | head -n 20"
elif [[ "$mode" == "docker" ]]; then
  ssh_remote "docker ps -a --filter name=^/mihomo$ --format 'table {{.Names}}\\t{{.Status}}\\t{{.Image}}'"
else
  echo "WARN: could not detect deployment mode (systemd/docker)" >&2
fi

echo "== Config test (if host binary exists) =="
ssh_remote "set -euo pipefail; if [[ -x /usr/local/bin/mihomo ]]; then /usr/local/bin/mihomo -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml >/dev/null; echo OK; else echo SKIP: /usr/local/bin/mihomo not found; fi"

echo "== Controller API (/version) =="
secret="$(get_secret_remote)"
if [[ -z "$secret" ]]; then
  echo "ERROR: missing controller secret on remote microserver" >&2
  exit 1
fi
ssh_remote SECRET="$secret" CONTROLLER_URL="$CONTROLLER_URL" bash -s <<'REMOTE'
set -euo pipefail
url="${CONTROLLER_URL%/}/version"
curl -fsS -H "Authorization: Bearer ${SECRET}" "$url"
REMOTE
echo

echo "== Verge API (/public-config) =="
verge_secret="$(get_verge_secret_remote)"
if [[ -z "$verge_secret" ]]; then
  echo "ERROR: missing verge-api secret on remote microserver" >&2
  exit 1
fi
ssh_remote VERGE_SECRET="$verge_secret" VERGE_API_URL="$VERGE_API_URL" bash -s <<'REMOTE'
set -euo pipefail
url="${VERGE_API_URL%/}/public-config?token=${VERGE_SECRET}"
curl -fsS "$url"
REMOTE
echo

echo "== TUN bypass probes (manual review) =="
ssh_remote "set -euo pipefail; ip route get 6.6.6.6 || true; ip -6 route get 2000::6666 || true; ip -6 route get fc03:1136:3800::1 || true"

echo "OK: selfcheck finished"
