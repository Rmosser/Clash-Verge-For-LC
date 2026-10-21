#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_root="$(mktemp -d)"
cleanup() { rm -rf -- "$tmp_root"; }
trap cleanup EXIT

mkdir -p "$tmp_root/bin" "$tmp_root/state"
cat >"$tmp_root/bin/ip" <<'IP'
#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  "-4 route show default") printf 'default via 10.0.0.1 dev eth1 proto dhcp\n' ;;
  "link show dev eth1") exit 0 ;;
  "link show dev eth0") exit 1 ;;
  *) exit 1 ;;
esac
IP
cat >"$tmp_root/bin/resolvectl" <<'RESOLVECTL'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${RESOLVECTL_LOG:?}"
RESOLVECTL
chmod 755 "$tmp_root/bin/ip" "$tmp_root/bin/resolvectl"
printf 'eth0\n' >"$tmp_root/state/resolved-link.iface"

PATH="$tmp_root/bin:$PATH" \
MIHOMO_RESOLVED_STATE_DIR="$tmp_root/state" \
RESOLVECTL_LOG="$tmp_root/resolvectl.log" \
bash "$ROOT/infra/microserver/mihomo-resolved-sync.sh" apply

[[ "$(tr -d '\r\n' <"$tmp_root/state/resolved-link.iface")" == eth1 ]]
grep -q '^dns eth1 127.0.0.1:1053 ' "$tmp_root/resolvectl.log"
printf 'resolved sync interface re-probe passed\n'
