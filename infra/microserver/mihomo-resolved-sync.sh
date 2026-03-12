#!/usr/bin/env bash
set -euo pipefail

PATH="/lzcsys/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

STATE_DIR="/var/lib/mihomo"
STATE_FILE="$STATE_DIR/resolved-link.iface"
PRIMARY_DNS="${MIHOMO_RESOLVED_DNS_PRIMARY:-127.0.0.1:1053}"
FALLBACK_DNS=(${MIHOMO_RESOLVED_FALLBACK_DNS:-192.168.1.1 fe80::1})

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

apply_dns() {
  local iface
  iface="$(resolve_iface)"
  if [[ -z "$iface" ]]; then
    echo "ERROR: unable to determine default route interface for resolvectl" >&2
    exit 1
  fi

  install -d -m 750 "$STATE_DIR"
  printf '%s\n' "$iface" >"$STATE_FILE"
  chmod 600 "$STATE_FILE" || true

  resolvectl dns "$iface" "$PRIMARY_DNS" "${FALLBACK_DNS[@]}"
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
