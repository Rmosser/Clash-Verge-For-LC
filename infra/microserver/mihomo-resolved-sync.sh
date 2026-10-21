#!/usr/bin/env bash
set -euo pipefail

PATH="/lzcsys/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

STATE_DIR="${MIHOMO_RESOLVED_STATE_DIR:-/var/lib/mihomo}"
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
  ip -4 route show default 2>/dev/null | awk '/default/ {print $5; exit}'
}

detect_default_gateway_v4() {
  ip -4 route show default 2>/dev/null | awk '/default/ {print $3; exit}'
}

interface_exists() {
  local iface="$1"
  [[ -n "$iface" ]] && ip link show dev "$iface" >/dev/null 2>&1
}

read_stored_iface() {
  if [[ -f "$STATE_FILE" ]]; then
    tr -d '\r\n' <"$STATE_FILE" 2>/dev/null || true
  fi
}

resolve_apply_iface() {
  local detected
  if [[ -n "${MIHOMO_RESOLVED_IFACE:-}" ]]; then
    if interface_exists "$MIHOMO_RESOLVED_IFACE"; then
      printf '%s\n' "$MIHOMO_RESOLVED_IFACE"
      return
    fi
    echo "WARN: configured resolver interface is absent; re-detecting default route" >&2
  fi
  detected="$(detect_default_iface)"
  if interface_exists "$detected"; then
    printf '%s\n' "$detected"
    return
  fi
  return 1
}

resolve_iface() {
  local detected stored
  if detected="$(resolve_apply_iface)"; then
    printf '%s\n' "$detected"
    return 0
  fi
  # Revert may run while the default route is temporarily absent.  Only use
  # the persisted interface after checking that the link still exists; stale
  # state must never drive a new DNS assignment.
  stored="$(read_stored_iface)"
  if interface_exists "$stored"; then
    printf '%s\n' "$stored"
    return 0
  fi
  return 1
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
  if ! iface="$(resolve_apply_iface)"; then
    echo "ERROR: unable to determine a live default route interface for resolvectl" >&2
    exit 1
  fi
  if [[ -z "$iface" ]]; then
    echo "ERROR: unable to determine a live default route interface for resolvectl" >&2
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
  local iface stored
  stored="$(read_stored_iface)"
  iface="$(resolve_apply_iface 2>/dev/null || true)"
  for candidate in "$stored" "$iface"; do
    [[ -n "$candidate" ]] || continue
    interface_exists "$candidate" || continue
    resolvectl revert "$candidate" || true
  done
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
