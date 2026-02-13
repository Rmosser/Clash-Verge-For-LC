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

TIMEOUT_MS="${TIMEOUT_MS:-8000}"
V4_TEST_URL="${V4_TEST_URL:-http://www.gstatic.com/generate_204}"
V6_TEST_URL="${V6_TEST_URL:-https://ipv6.google.com/}"
CONCURRENCY="${CONCURRENCY:-4}"

usage() {
  cat <<'USAGE'
Usage: scripts/audit_proxy_egress.sh [--json]

Runs on your dev machine; queries Mihomo controller via SSH on the microserver.

Output:
  - default: human-readable summary + a short table
  - --json:  prints full JSON (for piping into other tools)

Env (optional):
  MICROSERVER_HOST, MICROSERVER_SSH_USER, MICROSERVER_SSH_KEY
  MIHOMO_CONTROLLER_URL (default: http://172.18.0.1:9090)
  TIMEOUT_MS (default: 8000)
  V4_TEST_URL (default: http://www.gstatic.com/generate_204)
  V6_TEST_URL (default: https://ipv6.google.com/)
  CONCURRENCY (default: 4)
USAGE
}

JSON_ONLY=0
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "--json" ]]; then
  JSON_ONLY=1
fi

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" "$@"
}

# The controller secret never leaves the microserver: extracted remotely and only
# used as an in-memory env var for the audit process.
ssh_remote \
  CONTROLLER_URL="$CONTROLLER_URL" \
  TIMEOUT_MS="$TIMEOUT_MS" \
  V4_TEST_URL="$V4_TEST_URL" \
  V6_TEST_URL="$V6_TEST_URL" \
  CONCURRENCY="$CONCURRENCY" \
  bash -s <<'REMOTE'
set -euo pipefail

SECRET="$(
  grep -E '^[[:space:]]*secret:' /etc/mihomo/config.yaml | head -n1 \
    | sed -E 's/^[[:space:]]*secret:[[:space:]]*//' \
    | sed -E 's/^\x27(.*)\x27$|^\x22(.*)\x22$/\1\2/' \
    | tr -d '\r\n'
)"

export SECRET CONTROLLER_URL TIMEOUT_MS V4_TEST_URL V6_TEST_URL CONCURRENCY

python3 - <<'PY'
import concurrent.futures
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

controller = os.environ.get("CONTROLLER_URL", "http://172.18.0.1:9090").rstrip("/")
secret = os.environ.get("SECRET", "")
timeout_ms = int(os.environ.get("TIMEOUT_MS", "8000"))
test_v4 = os.environ.get("V4_TEST_URL", "http://www.gstatic.com/generate_204")
test_v6 = os.environ.get("V6_TEST_URL", "https://ipv6.google.com/")
concurrency = int(os.environ.get("CONCURRENCY", "4"))

hdr = {}
if secret:
    hdr["Authorization"] = f"Bearer {secret}"

ctx = ssl.create_default_context()


def _get_json(url: str, http_timeout_s: float = 10.0):
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=http_timeout_s, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))


def _delay(name: str, url: str):
    path = "/proxies/%s/delay" % urllib.parse.quote(name, safe="")
    qs = urllib.parse.urlencode({"timeout": str(timeout_ms), "url": url})
    full = f"{controller}{path}?{qs}"
    try:
        j = _get_json(full, http_timeout_s=max(3.0, (timeout_ms / 1000.0) + 2.0))
        d = j.get("delay")
        if isinstance(d, int) and d > 0:
            return d, ""
        return 0, str(j.get("message") or "no_delay")
    except urllib.error.HTTPError as e:
        return 0, f"HTTP {e.code}"
    except Exception as e:
        return 0, str(e)


def _classify(name: str):
    d4, e4 = _delay(name, test_v4)
    d6, e6 = _delay(name, test_v6)
    if d4 > 0 and d6 > 0:
        st = "V6_EGRESS_OK"
    elif d4 > 0 and d6 == 0:
        st = "V4_ONLY_EGRESS"
    else:
        st = "DEAD"
    return {
        "name": name,
        "d4": d4,
        "d6": d6,
        "status": st,
        "err_v4": e4,
        "err_v6": e6,
    }


px = _get_json(f"{controller}/proxies").get("proxies", {})
socks5 = [name for name, obj in px.items() if obj.get("type") == "Socks5"]
socks5.sort()

started = time.time()
results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
    for r in ex.map(_classify, socks5):
        results.append(r)
elapsed_ms = int((time.time() - started) * 1000)

counts = {}
for r in results:
    counts[r["status"]] = counts.get(r["status"], 0) + 1

print(
    json.dumps(
        {
            "meta": {
                "controller": controller,
                "timeout_ms": timeout_ms,
                "test_v4": test_v4,
                "test_v6": test_v6,
                "concurrency": concurrency,
                "elapsed_ms": elapsed_ms,
            },
            "counts": counts,
            "results": results,
        },
        ensure_ascii=False,
    )
)
PY
REMOTE

