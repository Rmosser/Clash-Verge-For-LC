#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_deploy_settings.sh"

fail() {
  printf 'test_deploy_settings: %s\n' "$*" >&2
  exit 1
}

unset MIHOMO_TUN_ENABLE MIHOMO_DNS_ENABLE MIHOMO_RESOLVED_VIA_MIHOMO
mihomo_resolve_deploy_settings
[[ "$MIHOMO_TUN_ENABLE" == "0" ]] || fail "TUN must default to disabled"
[[ "$MIHOMO_DNS_ENABLE" == "0" ]] || fail "DNS must default to disabled"
[[ "$MIHOMO_RESOLVED_VIA_MIHOMO" == "0" ]] || fail "resolved sync must follow disabled DNS"

MIHOMO_TUN_ENABLE=1
MIHOMO_DNS_ENABLE=1
unset MIHOMO_RESOLVED_VIA_MIHOMO
mihomo_resolve_deploy_settings
[[ "$MIHOMO_TUN_ENABLE" == "1" ]] || fail "explicit TUN opt-in was not preserved"
[[ "$MIHOMO_DNS_ENABLE" == "1" ]] || fail "explicit DNS opt-in was not preserved"
[[ "$MIHOMO_RESOLVED_VIA_MIHOMO" == "1" ]] || fail "resolved sync must follow enabled DNS"

MIHOMO_TUN_ENABLE=invalid
if mihomo_resolve_deploy_settings 2>/dev/null; then
  fail "invalid binary settings must fail closed"
fi

printf 'Deployment setting tests passed.\n'
