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

SECRET_LOCAL_FILE="$(lzc_resolve_path_from_root "$ROOT" "${MIHOMO_SECRET_FILE_LOCAL:-var/private/mihomo.secret}")"
CONTROLLER_URL="${MIHOMO_CONTROLLER_URL:-http://172.18.0.1:9090}"

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" "$@"
}

get_secret_local() {
  if [[ -n "${MIHOMO_SECRET:-}" ]]; then
    printf '%s' "$MIHOMO_SECRET"
    return 0
  fi
  if [[ -f "$SECRET_LOCAL_FILE" ]]; then
    tr -d '\r\n' <"$SECRET_LOCAL_FILE"
    return 0
  fi
  printf ''
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
secret="$(get_secret_local)"
if [[ -z "$secret" ]]; then
  echo "WARN: missing secret (set MIHOMO_SECRET or create $SECRET_LOCAL_FILE); skipping /version check" >&2
else
  ssh_remote SECRET="$secret" CONTROLLER_URL="$CONTROLLER_URL" bash -s <<'REMOTE'
set -euo pipefail
url="${CONTROLLER_URL%/}/version"
curl -fsS -H "Authorization: Bearer ${SECRET}" "$url"
REMOTE
  echo
fi

echo "== TUN bypass probes (manual review) =="
ssh_remote "set -euo pipefail; ip route get 6.6.6.6 || true; ip -6 route get 2000::6666 || true; ip -6 route get fc03:1136:3800::1 || true"

echo "OK: selfcheck finished"
