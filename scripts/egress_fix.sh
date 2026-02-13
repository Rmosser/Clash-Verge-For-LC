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

CFG_LOCAL="$(lzc_resolve_path_from_root "$ROOT" "${MIHOMO_CONFIG_LOCAL:-var/private/mihomo.config.yaml}")"

usage() {
  cat <<'USAGE'
Usage: scripts/egress_fix.sh

1) Audits each Socks5 proxy's IPv4 + IPv6 egress (via Mihomo delay API).
2) If any proxies are V6_EGRESS_OK:
   - pins proxy-groups.AUTO.proxies to only those proxies
   - deploys to microserver via scripts/deploy_microserver.sh
   - runs acceptance curls (30x github + cloudflare via 127.0.0.1:7890)

Notes:
  - This does NOT print the Mihomo controller secret.
  - This only mutates your local ignored config under var/private/ and then deploys.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "$CFG_LOCAL" ]]; then
  echo "ERROR: missing config file: $CFG_LOCAL" >&2
  exit 1
fi

TS="$(date +%Y%m%d-%H%M%S)"
TMPDIR_LOCAL="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR_LOCAL"; }
trap cleanup EXIT

mkdir -p "$ROOT/tmp"
AUDIT_JSON_PERSIST="$ROOT/tmp/egress-audit.$TS.json"
AUDIT_JSON_TMP="$TMPDIR_LOCAL/egress-audit.$TS.json"

echo "1) Auditing proxy egress on $SSH_USER@$HOST ..."
"$ROOT/scripts/audit_proxy_egress.sh" --json >"$AUDIT_JSON_TMP"
cp -a "$AUDIT_JSON_TMP" "$AUDIT_JSON_PERSIST"
echo "audit_json=$AUDIT_JSON_PERSIST"

echo "2) Parsing audit results ..."
V6_OK_CSV="$(
  python3 - <<'PY' "$AUDIT_JSON_TMP"
import json,sys
p=sys.argv[1]
j=json.load(open(p,"r",encoding="utf-8"))
ok=[r["name"] for r in j.get("results",[]) if r.get("status")=="V6_EGRESS_OK"]
print(",".join(ok))
PY
)"

V4_OK_CSV="$(
  python3 - <<'PY' "$AUDIT_JSON_TMP"
import json,sys
p=sys.argv[1]
j=json.load(open(p,"r",encoding="utf-8"))
ok=[r["name"] for r in j.get("results",[]) if r.get("status")=="V4_ONLY_EGRESS"]
print(",".join(ok))
PY
)"

python3 - <<'PY' "$AUDIT_JSON_TMP"
import json,sys
j=json.load(open(sys.argv[1],"r",encoding="utf-8"))
print("counts=", j.get("counts",{}))
meta=j.get("meta",{})
print("controller=", meta.get("controller"))
print("elapsed_ms=", meta.get("elapsed_ms"))
PY

if [[ -z "$V6_OK_CSV" ]]; then
  if [[ -z "$V4_OK_CSV" ]]; then
    echo
    echo "No working proxies found (neither V6_EGRESS_OK nor V4_ONLY_EGRESS)."
    echo
    cat <<'TXT'
Action required (subscription/node provider):
1) Provide at least one stable node with IPv4 egress (must reach http://www.gstatic.com/generate_204).
2) Preferably also IPv6 egress (must reach https://ipv6.google.com/), otherwise IPv6 destinations may stall under TUN.
TXT
    exit 2
  fi

  echo
  echo "No V6_EGRESS_OK proxies found, but some proxies are V4_ONLY_EGRESS."
  echo "Applying IPv4-preference workaround and pinning AUTO to V4-only egress proxies."
  echo

  "$ROOT/scripts/prefer_ipv4_gai.sh" >/dev/null
  # Prevent long stalls on IPv6 destinations when egress is V4-only.
  python3 "$ROOT/scripts/ensure_ipv6_reject_rule.py" --in "$CFG_LOCAL" --backup >/dev/null

  V6_OK_CSV="$V4_OK_CSV"
fi

echo
V6_OK_COUNT="$(python3 -c 'import sys; print(len([x for x in sys.argv[1].split(",") if x]))' "$V6_OK_CSV")"
echo "3) Pinning AUTO group to selected proxies (count=$V6_OK_COUNT) ..."
python3 "$ROOT/scripts/patch_auto_group.py" --in "$CFG_LOCAL" --backup --proxies "$V6_OK_CSV" >/dev/null

echo "4) Deploying config to microserver ..."
"$ROOT/scripts/deploy_microserver.sh" >/dev/null

echo "5) Acceptance checks (30x curls via 127.0.0.1:7890) ..."
ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" bash -s <<'REMOTE'
set -euo pipefail

proxy=http://127.0.0.1:7890
max_time=8

run_loop() {
  local url="$1"
  local ok=0
  local fail=0
  local sum=0
  local n=30
  for i in $(seq 1 "$n"); do
    out="$(curl -sS -o /dev/null -x "$proxy" -m "$max_time" -w 'code=%{http_code} total=%{time_total}\n' "$url" 2>/dev/null || true)"
    code="$(echo "$out" | awk '{print $1}' | sed 's/code=//')"
    total="$(echo "$out" | awk '{print $2}' | sed 's/total=//')"
    if [[ "$code" =~ ^(2|3) ]]; then
      ok=$((ok+1))
      # total is float; keep as ms-ish integer via awk.
      ms="$(awk -v t="$total" 'BEGIN{printf("%d", t*1000)}')"
      sum=$((sum+ms))
    else
      fail=$((fail+1))
    fi
  done
  avg_ms=0
  if [[ "$ok" -gt 0 ]]; then
    avg_ms=$((sum/ok))
  fi
  echo "url=$url ok=$ok fail=$fail avg_ms=$avg_ms max_time_s=$max_time"
}

run_loop "https://github.com/"
run_loop "https://www.cloudflare.com/cdn-cgi/trace"
REMOTE

echo
echo "OK"
