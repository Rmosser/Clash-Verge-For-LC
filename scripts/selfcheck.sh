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
ssh_remote CONTROLLER_URL="$CONTROLLER_URL" bash -s <<'REMOTE'
set -euo pipefail
python3 - "$CONTROLLER_URL" <<'PY'
from pathlib import Path
import sys
import urllib.request

url = sys.argv[1].rstrip("/") + "/version"
secret = ""
for line in Path("/etc/mihomo/config.yaml").read_text(encoding="utf-8").splitlines():
    if line.lstrip().startswith("secret:"):
        secret = line.split(":", 1)[1].strip().strip("'\"")
        break
if not secret:
    raise SystemExit("missing controller secret on remote microserver")
request = urllib.request.Request(url, headers={"Authorization": f"Bearer {secret}"})
with urllib.request.urlopen(request, timeout=10) as response:
    sys.stdout.buffer.write(response.read())
    sys.stdout.write("\n")
PY
REMOTE

echo "== Verge API (/public-config) =="
ssh_remote VERGE_API_URL="$VERGE_API_URL" bash -s <<'REMOTE'
set -euo pipefail
python3 - "$VERGE_API_URL" <<'PY'
from pathlib import Path
import sys
import urllib.parse
import urllib.request

token = Path("/etc/mihomo/verge-api.secret").read_text(encoding="utf-8").strip()
if not token:
    raise SystemExit("missing verge-api secret on remote microserver")
url = sys.argv[1].rstrip("/") + "/public-config?token=" + urllib.parse.quote(token, safe="")
with urllib.request.urlopen(url, timeout=10) as response:
    print(f"HTTP {response.status}")
PY
REMOTE

echo "== TUN bypass probes (manual review) =="
ssh_remote "set -euo pipefail; ip route get 6.6.6.6 || true; ip -6 route get 2000::6666 || true; ip -6 route get fc03:1136:3800::1 || true"

echo "== Protocol probes (use these instead of ping) =="
ssh_remote CONTROLLER_URL="$CONTROLLER_URL" bash -s <<'REMOTE'
set -euo pipefail

run_check() {
  local label="$1"
  shift
  echo "-- $label"
  if "$@"; then
    echo "OK: $label"
  else
    echo "WARN: $label failed"
  fi
  echo
}

run_check "DNS lookup google.com" timeout 10 getent ahostsv4 google.com
run_check "TCP connect google.com:443" timeout 10 bash -lc 'exec 3<>/dev/tcp/google.com/443'
run_check "HTTPS via TUN https://www.gstatic.com/generate_204" curl -fsSI --max-time 10 https://www.gstatic.com/generate_204
run_check "HTTPS via mixed-port https://api.ipify.org" curl -fsS --max-time 15 --proxy http://127.0.0.1:7890 https://api.ipify.org

controller_health() {
  python3 - "$CONTROLLER_URL" <<'PY'
from pathlib import Path
import sys
import urllib.request

secret = ""
for line in Path("/etc/mihomo/config.yaml").read_text(encoding="utf-8").splitlines():
    if line.lstrip().startswith("secret:"):
        secret = line.split(":", 1)[1].strip().strip("'\"")
        break
request = urllib.request.Request(
    sys.argv[1].rstrip("/") + "/version",
    headers={"Authorization": f"Bearer {secret}"},
)
with urllib.request.urlopen(request, timeout=5) as response:
    response.read()
PY
}

run_check "Controller health /version" controller_health

cat <<'EOF'
NOTE:
  ping/ICMP is intentionally not part of this selfcheck.
  In the current Mihomo + TUN + upstream SOCKS5 setup, daily traffic validation
  should rely on DNS/TCP/HTTPS checks rather than ICMP echo replies.
EOF
REMOTE

echo "OK: selfcheck finished"
