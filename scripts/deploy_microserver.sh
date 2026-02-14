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
UNIT_LOCAL="$ROOT/infra/mihomo/mihomo.service"
CONTAINER_PROXY_SOCKET_LOCAL="$ROOT/infra/microserver/mihomo-container-proxy.socket"
CONTAINER_PROXY_SERVICE_LOCAL="$ROOT/infra/microserver/mihomo-container-proxy.service"
MMDB_LOCAL="$(lzc_resolve_path_from_root "$ROOT" "${MIHOMO_COUNTRY_MMDB_LOCAL:-var/private/Country.mmdb}")"
SECRET_LOCAL_FILE="$(lzc_resolve_path_from_root "$ROOT" "${MIHOMO_SECRET_FILE_LOCAL:-var/private/mihomo.secret}")"
TUN_ENABLE="${MIHOMO_TUN_ENABLE:-1}" # 1=enabled (default), 0=disabled
DNS_ENABLE="${MIHOMO_DNS_ENABLE:-1}" # 1=enabled (default), 0=disabled
AUTO_TEST_URL="${MIHOMO_AUTO_TEST_URL-https://api.openai.com/v1/models}"
DOH_PROXY_RULES_ENABLE="${MIHOMO_DOH_PROXY_RULES_ENABLE:-1}" # 1=enabled (default), 0=disabled
INSTALL_NET_SAFE_APPLY="${LZC_NET_SAFE_APPLY_INSTALL:-1}" # 1=install (default), 0=skip
CONTAINER_PROXY_ENABLE="${MIHOMO_CONTAINER_PROXY_ENABLE:-1}" # 1=enabled (default), 0=disabled

UPGRADE_CORE=0
ONLY_CORE=0
NO_ROLLBACK=0
CORE_VERSION_ARG=""
FORCE_LATEST_STABLE=0

usage() {
  cat <<'USAGE'
Usage: scripts/deploy_microserver.sh [options]

Options:
  --upgrade-core            Upgrade mihomo core even if already installed
  --core-version <tag>      Upgrade/install specific version (e.g. v1.19.20, Prerelease-Alpha)
  --latest-stable           Force GitHub stable latest tag
  --only-core               Upgrade core only (skip config/unit/mmdb deploy)
  --no-rollback             Disable automatic rollback on upgrade failure
  -h, --help                Show this help

Notes:
  - Default behavior keeps backward compatibility: deploy config/unit and only install core if missing.
  - Use --upgrade-core --only-core for one-click in-place core upgrade.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --upgrade-core)
      UPGRADE_CORE=1
      ;;
    --core-version)
      shift
      if [[ $# -eq 0 ]]; then
        echo "ERROR: --core-version requires a tag value" >&2
        exit 1
      fi
      CORE_VERSION_ARG="$1"
      ;;
    --latest-stable)
      FORCE_LATEST_STABLE=1
      ;;
    --only-core)
      ONLY_CORE=1
      ;;
    --no-rollback)
      NO_ROLLBACK=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if [[ "$ONLY_CORE" == "1" && "$UPGRADE_CORE" != "1" ]]; then
  echo "ERROR: --only-core requires --upgrade-core" >&2
  exit 1
fi

TS="$(date +%Y%m%d-%H%M%S)"
TMPDIR_LOCAL="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR_LOCAL"; }
trap cleanup EXIT

PATCHED_CFG_LOCAL="$TMPDIR_LOCAL/mihomo.config.patched.$TS.yaml"
SECRET_OUT_LOCAL="$TMPDIR_LOCAL/mihomo.secret.$TS"
TMP_CFG="/tmp/mihomo.config.$TS.yaml"
TMP_UNIT="/tmp/mihomo.service.$TS"
TMP_CONTAINER_PROXY_SOCKET="/tmp/mihomo-container-proxy.socket.$TS"
TMP_CONTAINER_PROXY_SERVICE="/tmp/mihomo-container-proxy.service.$TS"

if [[ "$ONLY_CORE" != "1" ]]; then
  if [[ ! -f "$CFG_LOCAL" ]]; then
    echo "ERROR: missing config file: $CFG_LOCAL" >&2
    echo "Hint: keep your real config (with proxy creds) under var/private/ and do NOT commit it." >&2
    exit 1
  fi

  if [[ ! -f "$UNIT_LOCAL" ]]; then
    echo "ERROR: missing unit file: $UNIT_LOCAL" >&2
    exit 1
  fi

  # Guardrails: avoid accidentally breaking dashboard access.
  if ! grep -Eq '^[[:space:]]*external-controller:[[:space:]]*172\.18\.0\.1:9090[[:space:]]*$' "$CFG_LOCAL"; then
    echo "ERROR: $CFG_LOCAL must contain: external-controller: 172.18.0.1:9090" >&2
    echo "(LazyCat ingress reaches host via host.lzcapp -> 172.18.0.1)" >&2
    exit 1
  fi

  PATCH_ARGS=(
    --in "$CFG_LOCAL"
    --out "$PATCHED_CFG_LOCAL"
    --secret-out "$SECRET_OUT_LOCAL"
  )

  if [[ -n "${MIHOMO_SECRET:-}" ]]; then
    PATCH_ARGS+=(--set-secret "$MIHOMO_SECRET")
  else
    PATCH_ARGS+=(--ensure-secret)
  fi

  if [[ "$TUN_ENABLE" == "0" ]]; then
    PATCH_ARGS+=(--set-tun-enabled false)
  else
    PATCH_ARGS+=(--set-tun-enabled true --ensure-tun-excludes)
  fi

  if [[ "$DNS_ENABLE" == "1" ]]; then
    PATCH_ARGS+=(--ensure-dns)
    if [[ "$DOH_PROXY_RULES_ENABLE" == "1" ]]; then
      PATCH_ARGS+=(--ensure-doh-proxy-rules)
    fi
  fi

  if [[ -n "$AUTO_TEST_URL" ]]; then
    PATCH_ARGS+=(--set-auto-test-url "$AUTO_TEST_URL")
  fi

  python3 "$ROOT/scripts/patch_remote_mihomo_config.py" "${PATCH_ARGS[@]}" >/dev/null

  MIHOMO_SECRET_EFFECTIVE="$(cat "$SECRET_OUT_LOCAL" | tr -d '\r\n')"
  if [[ -z "$MIHOMO_SECRET_EFFECTIVE" ]]; then
    echo "ERROR: failed to determine mihomo secret (empty)" >&2
    exit 1
  fi

  if [[ -z "${MIHOMO_SECRET:-}" ]]; then
    mkdir -p "$(dirname "$SECRET_LOCAL_FILE")"
    printf '%s\n' "$MIHOMO_SECRET_EFFECTIVE" >"$SECRET_LOCAL_FILE"
    chmod 600 "$SECRET_LOCAL_FILE" 2>/dev/null || true
    echo "MIHOMO_SECRET generated and saved to: $SECRET_LOCAL_FILE" >&2
  fi
fi

echo "Deploying to $SSH_USER@$HOST ..."

# Compute mihomo download URL for the remote architecture.
REMOTE_UNAME="$(ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" uname -m)"

MIHOMO_TAG="$CORE_VERSION_ARG"
if [[ -z "$MIHOMO_TAG" ]]; then
  MIHOMO_TAG="${MIHOMO_VERSION:-}"
fi
if [[ "$FORCE_LATEST_STABLE" == "1" ]]; then
  MIHOMO_TAG=""
fi
if [[ -z "$MIHOMO_TAG" || "$MIHOMO_TAG" == "latest" ]]; then
  if command -v jq >/dev/null 2>&1; then
    MIHOMO_TAG="$(curl -fsSL https://api.github.com/repos/MetaCubeX/mihomo/releases/latest | jq -r '.tag_name')"
  else
    MIHOMO_TAG="$(curl -fsSL https://api.github.com/repos/MetaCubeX/mihomo/releases/latest | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
  fi
fi

case "$REMOTE_UNAME" in
  x86_64)
    MIHOMO_ASSET="mihomo-linux-amd64-compatible-${MIHOMO_TAG}.gz"
    ;;
  aarch64|arm64)
    MIHOMO_ASSET="mihomo-linux-arm64-${MIHOMO_TAG}.gz"
    ;;
  armv7l|armv7*)
    MIHOMO_ASSET="mihomo-linux-armv7-${MIHOMO_TAG}.gz"
    ;;
  i386|i686)
    MIHOMO_ASSET="mihomo-linux-386-${MIHOMO_TAG}.gz"
    ;;
  *)
    echo "ERROR: unsupported remote arch from uname -m: $REMOTE_UNAME" >&2
    exit 1
    ;;
esac

MIHOMO_URL="https://github.com/MetaCubeX/mihomo/releases/download/${MIHOMO_TAG}/${MIHOMO_ASSET}"
MMDB_URL="https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/country.mmdb"

if [[ "$ONLY_CORE" != "1" ]]; then
  scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "$PATCHED_CFG_LOCAL" "$SSH_USER@$HOST:$TMP_CFG" >/dev/null

  scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "$UNIT_LOCAL" "$SSH_USER@$HOST:$TMP_UNIT" >/dev/null

  # Optional: sync Country.mmdb if present locally.
  if [[ -f "$MMDB_LOCAL" ]]; then
    echo "Uploading Country.mmdb ..."
    scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
      "$MMDB_LOCAL" "$SSH_USER@$HOST:/tmp/Country.mmdb.$TS" >/dev/null
  else
    echo "NOTE: $MMDB_LOCAL not found; skipping Country.mmdb upload." >&2
  fi

  # Optional: install the DNS change safety tool (no execution by default).
  if [[ "$INSTALL_NET_SAFE_APPLY" == "1" && -f "$ROOT/infra/microserver/lzc-net-safe-apply" ]]; then
    echo "Installing lzc-net-safe-apply ..."
    scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
      "$ROOT/infra/microserver/lzc-net-safe-apply" "$SSH_USER@$HOST:/tmp/lzc-net-safe-apply.$TS" >/dev/null
    ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
      "$SSH_USER@$HOST" \
      TS="$TS" \
      bash -s <<'NETSAFE'
set -euo pipefail
install -d -m 755 /usr/local/sbin
install -m 755 "/tmp/lzc-net-safe-apply.${TS}" /usr/local/sbin/lzc-net-safe-apply
rm -f "/tmp/lzc-net-safe-apply.${TS}" || true
NETSAFE
  fi
fi

if [[ "$CONTAINER_PROXY_ENABLE" == "1" ]]; then
  if [[ ! -f "$CONTAINER_PROXY_SOCKET_LOCAL" || ! -f "$CONTAINER_PROXY_SERVICE_LOCAL" ]]; then
    echo "ERROR: missing container proxy unit(s):" >&2
    echo "  - $CONTAINER_PROXY_SOCKET_LOCAL" >&2
    echo "  - $CONTAINER_PROXY_SERVICE_LOCAL" >&2
    exit 1
  fi

  echo "Uploading mihomo-container-proxy units ..."
  scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "$CONTAINER_PROXY_SOCKET_LOCAL" "$SSH_USER@$HOST:$TMP_CONTAINER_PROXY_SOCKET" >/dev/null
  scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "$CONTAINER_PROXY_SERVICE_LOCAL" "$SSH_USER@$HOST:$TMP_CONTAINER_PROXY_SERVICE" >/dev/null
fi

echo "Applying on microserver ..."
ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  "$SSH_USER@$HOST" \
  TS="$TS" \
  TMP_CFG="$TMP_CFG" \
  TMP_UNIT="$TMP_UNIT" \
  TMP_CONTAINER_PROXY_SOCKET="$TMP_CONTAINER_PROXY_SOCKET" \
  TMP_CONTAINER_PROXY_SERVICE="$TMP_CONTAINER_PROXY_SERVICE" \
  MIHOMO_URL="$MIHOMO_URL" \
  MIHOMO_TAG="$MIHOMO_TAG" \
  MMDB_URL="$MMDB_URL" \
  UPGRADE_CORE="$UPGRADE_CORE" \
  ONLY_CORE="$ONLY_CORE" \
  NO_ROLLBACK="$NO_ROLLBACK" \
  CONTAINER_PROXY_ENABLE="$CONTAINER_PROXY_ENABLE" \
  bash -s <<'REMOTE'
set -euo pipefail

cfg=/etc/mihomo/config.yaml
unit=/etc/systemd/system/mihomo.service
container_proxy_socket=/etc/systemd/system/mihomo-container-proxy.socket
container_proxy_service=/etc/systemd/system/mihomo-container-proxy.service
mihomo_bin=/usr/local/bin/mihomo
rollback_dir=/var/lib/mihomo/rollback
log_file="$rollback_dir/upgrade-${TS}.log"
latest_meta="$rollback_dir/latest.env"

bak_cfg=""
bak_unit=""
backup_bin=""
prev_version=""
new_version=""
status="pending"
core_attempted=0
core_changed=0

command -v curl >/dev/null 2>&1 || { echo "ERROR: curl not found on microserver" >&2; exit 1; }
command -v gzip >/dev/null 2>&1 || { echo "ERROR: gzip not found on microserver" >&2; exit 1; }

install -d -o root -g root -m 755 "$rollback_dir"

touch "$log_file"
chmod 600 "$log_file" || true

log() {
  local msg="$1"
  printf '[%s] %s\n' "$(date -Iseconds)" "$msg" | tee -a "$log_file" >&2
}

extract_version() {
  local bin="$1"
  "$bin" -v 2>/dev/null | head -n 1 | sed -E 's/^Mihomo Meta[[:space:]]+([^[:space:]]+).*/\1/'
}

write_meta() {
  cat >"$latest_meta" <<META
PREV_VERSION=${prev_version}
TARGET_VERSION=${MIHOMO_TAG}
BACKUP_BIN=${backup_bin}
UPGRADE_AT=${TS}
STATUS=${status}
META
  chmod 600 "$latest_meta" || true
}

rollback_core() {
  if [[ "$NO_ROLLBACK" == "1" ]]; then
    status="failed"
    write_meta
    log "Rollback skipped because --no-rollback is enabled."
    return
  fi

  if [[ -n "$backup_bin" && -f "$backup_bin" ]]; then
    log "Rolling back core using backup: $backup_bin"
    install -o root -g root -m 755 "$backup_bin" "$mihomo_bin"
    systemctl daemon-reload || true
    systemctl restart mihomo || true
    status="rolled_back"
    write_meta
    log "Rollback finished."
  else
    status="failed"
    write_meta
    log "Rollback unavailable: backup binary missing."
  fi
}

err_handler() {
  local rc=$?
  local line="$1"
  trap - ERR
  log "ERROR at line $line (exit=$rc)."
  if [[ "$core_attempted" == "1" ]]; then
    if [[ "$core_changed" == "1" ]]; then
      rollback_core
    else
      status="rolled_back"
      write_meta
      log "Core was not switched before failure; keeping previous binary."
    fi
  fi
  exit "$rc"
}
trap 'err_handler "$LINENO"' ERR

if [[ -x "$mihomo_bin" ]]; then
  prev_version="$(extract_version "$mihomo_bin" || true)"
fi

if [[ "$UPGRADE_CORE" == "1" || ! -x "$mihomo_bin" ]]; then
  core_attempted=1
  log "Downloading mihomo: $MIHOMO_URL"
  tmp_gz="/tmp/mihomo.${TS}.gz"
  tmp_new="/tmp/mihomo.${TS}.new"
  curl --retry 3 --retry-delay 1 --retry-all-errors --connect-timeout 10 --max-time 300 -fsSL "$MIHOMO_URL" -o "$tmp_gz"
  gzip -d -c "$tmp_gz" >"$tmp_new"
  chmod 755 "$tmp_new"

  log "Verifying downloaded binary executable"
  "$tmp_new" -v >/dev/null

  if [[ -x "$mihomo_bin" ]]; then
    backup_bin="$rollback_dir/mihomo.${TS}.bak"
    cp -a "$mihomo_bin" "$backup_bin"
    chmod 700 "$backup_bin" || true
    log "Backup created: $backup_bin"
  fi

  install -o root -g root -m 755 "$tmp_new" "$mihomo_bin"
  rm -f "$tmp_gz" "$tmp_new"
  core_changed=1
  new_version="$(extract_version "$mihomo_bin" || true)"
  log "Core switched to: ${new_version:-unknown}"
else
  new_version="$prev_version"
  log "Core upgrade skipped (existing binary retained)."
fi

if [[ "$ONLY_CORE" != "1" ]]; then
  # Backups
  if [[ -f "$cfg" ]]; then
    bak_cfg="${cfg}.bak.${TS}"
    cp -a "$cfg" "$bak_cfg"
  fi
  if [[ -f "$unit" ]]; then
    bak_unit="${unit}.bak.${TS}"
    cp -a "$unit" "$bak_unit"
  fi

  # Ensure directories exist
  id mihomo >/dev/null 2>&1 || useradd --system --home /var/lib/mihomo --shell /usr/sbin/nologin mihomo
  install -d -o root -g mihomo -m 750 /etc/mihomo
  install -d -o mihomo -g mihomo -m 750 /var/lib/mihomo

  # Install config + unit
  install -o root -g mihomo -m 640 "$TMP_CFG" "$cfg"
  install -o root -g root -m 644 "$TMP_UNIT" "$unit"
  rm -f "$TMP_CFG" "$TMP_UNIT"

  # Optional mmdb
  if [[ -f "/tmp/Country.mmdb.${TS}" ]]; then
    install -o mihomo -g mihomo -m 644 "/tmp/Country.mmdb.${TS}" /var/lib/mihomo/Country.mmdb
    rm -f "/tmp/Country.mmdb.${TS}"
  elif [[ ! -f /var/lib/mihomo/Country.mmdb ]]; then
    log "Downloading Country.mmdb from: $MMDB_URL"
    tmp_mmdb="/tmp/Country.mmdb.${TS}"
    curl --retry 3 --retry-delay 1 --retry-all-errors --connect-timeout 10 --max-time 180 -fsSL "$MMDB_URL" -o "$tmp_mmdb"
    install -o mihomo -g mihomo -m 644 "$tmp_mmdb" /var/lib/mihomo/Country.mmdb
    rm -f "$tmp_mmdb"
  fi
fi

if [[ "${CONTAINER_PROXY_ENABLE}" == "1" ]]; then
  if [[ -x /lib/systemd/systemd-socket-proxyd && -f "${TMP_CONTAINER_PROXY_SOCKET}" && -f "${TMP_CONTAINER_PROXY_SERVICE}" ]]; then
    install -o root -g root -m 644 "${TMP_CONTAINER_PROXY_SOCKET}" "${container_proxy_socket}"
    install -o root -g root -m 644 "${TMP_CONTAINER_PROXY_SERVICE}" "${container_proxy_service}"
    rm -f "${TMP_CONTAINER_PROXY_SOCKET}" "${TMP_CONTAINER_PROXY_SERVICE}" || true
    systemctl daemon-reload
    systemctl enable --now mihomo-container-proxy.socket >/dev/null || log "WARN: failed to enable mihomo-container-proxy.socket"
  else
    log "NOTE: container proxy socket/service not installed (missing tmp files or systemd-socket-proxyd)."
  fi
fi

# Validate config with the current core before restart.
"$mihomo_bin" -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml >/dev/null

systemctl daemon-reload
systemctl enable mihomo >/dev/null
systemctl restart mihomo
sleep 2
systemctl is-active mihomo >/dev/null

secret="$(grep -E '^[[:space:]]*secret:' "$cfg" | head -n 1 | sed -E 's/^[[:space:]]*secret:[[:space:]]*//' | sed -E "s/^'(.*)'$|^\"(.*)\"$/\1\2/" | tr -d '\r\n')"
version_ok=0
for _ in 1 2 3 4 5; do
  if [[ -n "$secret" ]]; then
    if curl -fsS -H "Authorization: Bearer ${secret}" "http://172.18.0.1:9090/version" >/dev/null; then
      version_ok=1
      break
    fi
  else
    if curl -fsS "http://172.18.0.1:9090/version" >/dev/null; then
      version_ok=1
      break
    fi
  fi
  sleep 1
done
if [[ "$version_ok" != "1" ]]; then
  log "Controller /version probe failed after restart"
  false
fi

if [[ "$core_attempted" == "1" ]]; then
  status="success"
  write_meta
fi

trap - ERR
log "OK: mihomo restarted. cfg_backup=${bak_cfg:-none} unit_backup=${bak_unit:-none}"
if [[ "$core_attempted" == "1" ]]; then
  log "Core result: prev=${prev_version:-none} target=${MIHOMO_TAG} current=${new_version:-unknown}"
fi
REMOTE

echo "Done."
