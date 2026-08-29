#!/usr/bin/env bash

# Canonical host-native network defaults. Keep these conservative: callers that
# intentionally enable TUN or DNS must opt in explicitly.
mihomo_resolve_deploy_settings() {
  MIHOMO_TUN_ENABLE="${MIHOMO_TUN_ENABLE:-0}"
  MIHOMO_DNS_ENABLE="${MIHOMO_DNS_ENABLE:-0}"
  MIHOMO_RESOLVED_VIA_MIHOMO="${MIHOMO_RESOLVED_VIA_MIHOMO:-$MIHOMO_DNS_ENABLE}"

  local name value
  for name in MIHOMO_TUN_ENABLE MIHOMO_DNS_ENABLE MIHOMO_RESOLVED_VIA_MIHOMO; do
    value="${!name}"
    if [[ "$value" != "0" && "$value" != "1" ]]; then
      printf 'ERROR: %s must be 0 or 1, got %q\n' "$name" "$value" >&2
      return 1
    fi
  done
}
