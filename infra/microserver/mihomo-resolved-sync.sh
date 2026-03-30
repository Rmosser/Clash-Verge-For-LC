#!/usr/bin/env bash
set -euo pipefail

PATH="/lzcsys/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

STATE_DIR="/var/lib/mihomo"
STATE_FILE="$STATE_DIR/resolved-link.iface"
PRIMARY_DNS="${MIHOMO_RESOLVED_DNS_PRIMARY:-127.0.0.1:1053}"

need_bin() {
  local bin="$1"
  command -v "$bin" >/dev/null 2>&1 || {
    echo "ERROR: missing required binary: $bin" >&2
    exit 1
  }
}

detect_default_iface() {
  ip route show default 2>/dev/null | awk '/default/ {print $5; exit}'
}

detect_default_gateway_v4() {
  ip route show default 2>/dev/null | awk '/default/ {print $3; exit}'
}

resolve_iface() {
  if [[ -n "${MIHOMO_RESOLVED_IFACE:-}" ]]; then
    printf '%s\n' "$MIHOMO_RESOLVED_IFACE"
    return 0
  fi
  if [[ -f "$STATE_FILE" ]]; then
    local stored
    stored="$(tr -d '\r\n' <"$STATE_FILE" 2>/dev/null || true)"
    if [[ -n "$stored" ]]; then
      printf '%s\n' "$stored"
      return 0
    fi
  fi
  detect_default_iface
}

resolve_fallback_dns() {
  if [[ -n "${MIHOMO_RESOLVED_FALLBACK_DNS:-}" ]]; then
    read -r -a configured <<<"${MIHOMO_RESOLVED_FALLBACK_DNS}"
    printf '%s\n' "${configured[@]}"
    return 0
  fi

  local gateway_v4
  gateway_v4="$(detect_default_gateway_v4)"
  if [[ -n "$gateway_v4" ]]; then
    printf '%s\n' "$gateway_v4"
  fi
}

apply_dns() {
  local iface
  local fallback_dns=()
  iface="$(resolve_iface)"
  if [[ -z "$iface" ]]; then
    echo "ERROR: unable to determine default route interface for resolvectl" >&2
    exit 1
  fi

  mapfile -t fallback_dns < <(resolve_fallback_dns)

  install -d -m 750 "$STATE_DIR"
  printf '%s\n' "$iface" >"$STATE_FILE"
  chmod 600 "$STATE_FILE" || true

  if [[ "${#fallback_dns[@]}" -gt 0 ]]; then
    resolvectl dns "$iface" "$PRIMARY_DNS" "${fallback_dns[@]}"
  else
    resolvectl dns "$iface" "$PRIMARY_DNS"
  fi
  resolvectl flush-caches >/dev/null 2>&1 || true
}

revert_dns() {
  local iface
  iface="$(resolve_iface)"
  if [[ -z "$iface" ]]; then
    exit 0
  fi

  resolvectl revert "$iface" || true
  resolvectl flush-caches >/dev/null 2>&1 || true
}

main() {
  need_bin ip
  need_bin resolvectl

  case "${1:-apply}" in
    apply)
      apply_dns
      ;;
    revert)
      revert_dns
      ;;
    *)
      echo "Usage: $0 [apply|revert]" >&2
      exit 1
      ;;
  esac
}

main "$@"
