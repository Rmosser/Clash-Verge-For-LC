#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_paths.sh"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_deploy_settings.sh"

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
RESOLVED_DNS_PRIMARY_OVERRIDE="${MIHOMO_RESOLVED_DNS_PRIMARY:-}"
RESOLVED_FALLBACK_DNS_OVERRIDE="${MIHOMO_RESOLVED_FALLBACK_DNS:-}"

CFG_LOCAL="$(lzc_resolve_path_from_root "$ROOT" "${MIHOMO_CONFIG_LOCAL:-var/private/mihomo.config.yaml}")"
UNIT_LOCAL="$ROOT/infra/mihomo/mihomo.service"
CONTAINER_PROXY_SOCKET_LOCAL="$ROOT/infra/microserver/mihomo-container-proxy.socket"
CONTAINER_PROXY_SERVICE_LOCAL="$ROOT/infra/microserver/mihomo-container-proxy.service"
VERGE_API_LOCAL="$ROOT/infra/microserver/mihomo-verge-api.py"
CORE_UPDATER_LOCAL="$ROOT/infra/microserver/mihomo_core_updater.py"
VERGE_API_UNIT_LOCAL="$ROOT/infra/microserver/mihomo-verge-api.service"
RESOLVED_SYNC_LOCAL="$ROOT/infra/microserver/mihomo-resolved-sync.sh"
RESOLVED_SYNC_UNIT_LOCAL="$ROOT/infra/microserver/mihomo-resolved-sync.service"
RUNTIME_CONTRACT_LOCAL="$ROOT/src/mihomo-dashboard-app/runtime-contract.json"
MMDB_LOCAL="$(lzc_resolve_path_from_root "$ROOT" "${MIHOMO_COUNTRY_MMDB_LOCAL:-var/private/Country.mmdb}")"
SECRET_LOCAL_FILE="$(lzc_resolve_path_from_root "$ROOT" "${MIHOMO_SECRET_FILE_LOCAL:-var/private/mihomo.secret}")"
VERGE_SECRET_LOCAL_FILE="$(lzc_resolve_path_from_root "$ROOT" "${VERGE_API_SECRET_FILE_LOCAL:-var/private/verge-api.secret}")"
mihomo_resolve_deploy_settings
TUN_ENABLE="$MIHOMO_TUN_ENABLE"
DNS_ENABLE="$MIHOMO_DNS_ENABLE"
RESOLVED_VIA_MIHOMO="$MIHOMO_RESOLVED_VIA_MIHOMO"
AUTO_TEST_URL="${MIHOMO_AUTO_TEST_URL-https://api.openai.com/v1/models}"
DOH_PROXY_RULES_ENABLE="${MIHOMO_DOH_PROXY_RULES_ENABLE:-1}" # 1=enabled (default), 0=disabled
INSTALL_NET_SAFE_APPLY="${LZC_NET_SAFE_APPLY_INSTALL:-1}" # 1=install (default), 0=skip
CONTAINER_PROXY_ENABLE="${MIHOMO_CONTAINER_PROXY_ENABLE:-1}" # 1=enabled (default), 0=disabled
DEFAULT_CORE_VERSION="${MIHOMO_VERSION:-v1.19.30}"

UPGRADE_CORE=0
ONLY_CORE=0
NO_ROLLBACK=0
CORE_VERSION_ARG=""
CONFIRM_APPLY=0

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$SSH_USER@$HOST" "$@"
}

usage() {
  cat <<'USAGE'
Usage: scripts/deploy_microserver.sh [options]

Options:
  --upgrade-core            Upgrade mihomo core even if already installed
  --core-version <tag>      Upgrade/install exact release tag (default: v1.19.30)
  --only-core               Upgrade core only (skip config/unit/mmdb deploy)
  --no-rollback             Disable automatic rollback on upgrade failure
  --confirm                 Confirm the approved host and SSH fingerprint before mutating it
  -h, --help                Show this help

Notes:
  - Default behavior keeps backward compatibility: deploy config/unit and only install core if missing.
  - Host-native network defaults are conservative: TUN=0 and DNS=0; enabling either is explicit.
  - The default core release is pinned to v1.19.30; use --core-version to override it.
  - Use --upgrade-core --only-core --core-version <tag> for a core-only upgrade.
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
    --only-core)
      ONLY_CORE=1
      ;;
    --no-rollback)
      NO_ROLLBACK=1
      ;;
    --confirm)
      CONFIRM_APPLY=1
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

mihomo_require_apply_confirmation "$HOST" "$SSH_USER" "$CONFIRM_APPLY" "deploy_microserver"

TS="$(date +%Y%m%d-%H%M%S)"
TMPDIR_LOCAL="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR_LOCAL"; mihomo_cleanup_known_hosts; }
trap cleanup EXIT

PATCHED_CFG_LOCAL="$TMPDIR_LOCAL/mihomo.config.patched.$TS.yaml"
SECRET_OUT_LOCAL="$TMPDIR_LOCAL/mihomo.secret.$TS"
TMP_CFG="/tmp/mihomo.config.$TS.yaml"
TMP_UNIT="/tmp/mihomo.service.$TS"
TMP_CONTAINER_PROXY_SOCKET="/tmp/mihomo-container-proxy.socket.$TS"
TMP_CONTAINER_PROXY_SERVICE="/tmp/mihomo-container-proxy.service.$TS"
TMP_VERGE_API="/tmp/mihomo-verge-api.py.$TS"
TMP_CORE_UPDATER="/tmp/mihomo_core_updater.py.$TS"
TMP_VERGE_API_UNIT="/tmp/mihomo-verge-api.service.$TS"
TMP_RESOLVED_SYNC="/tmp/mihomo-resolved-sync.sh.$TS"
TMP_RESOLVED_SYNC_UNIT="/tmp/mihomo-resolved-sync.service.$TS"
TMP_RUNTIME_CONTRACT="/tmp/runtime-contract.json.$TS"
TMP_VERGE_SECRET="/tmp/verge-api.secret.$TS"

REMOTE_DIRECT_DNS_SERVERS=()
if [[ "$DNS_ENABLE" == "1" || "$RESOLVED_VIA_MIHOMO" == "1" ]]; then
  if [[ -n "${MIHOMO_DIRECT_DNS_SERVERS:-}" ]]; then
    read -r -a REMOTE_DIRECT_DNS_SERVERS <<< "${MIHOMO_DIRECT_DNS_SERVERS}"
  else
    detected_remote_ipv4_gateway="$(
      ssh_remote "ip route show default 2>/dev/null | awk '/default/ {print \$3; exit}'" \
        | tr -d '\r\n' || true
    )"
    if [[ -n "$detected_remote_ipv4_gateway" ]]; then
      REMOTE_DIRECT_DNS_SERVERS=("$detected_remote_ipv4_gateway")
    fi
  fi
fi

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
    for dns_server in "${REMOTE_DIRECT_DNS_SERVERS[@]}"; do
      PATCH_ARGS+=(--dns-direct-server "$dns_server")
    done
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

  if [[ -n "${VERGE_API_SECRET:-}" ]]; then
    VERGE_API_SECRET_EFFECTIVE="$VERGE_API_SECRET"
  elif [[ -f "$VERGE_SECRET_LOCAL_FILE" ]]; then
    VERGE_API_SECRET_EFFECTIVE="$(tr -d '\r\n' <"$VERGE_SECRET_LOCAL_FILE")"
  else
    VERGE_API_SECRET_EFFECTIVE="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(16))
PY
)"
    mkdir -p "$(dirname "$VERGE_SECRET_LOCAL_FILE")"
    printf '%s\n' "$VERGE_API_SECRET_EFFECTIVE" >"$VERGE_SECRET_LOCAL_FILE"
    chmod 600 "$VERGE_SECRET_LOCAL_FILE" 2>/dev/null || true
    echo "VERGE_API_SECRET generated and saved to: $VERGE_SECRET_LOCAL_FILE" >&2
  fi
fi

echo "Deploying to $SSH_USER@$HOST ..."

# Compute the exact Mihomo asset and digest for the remote architecture.
REMOTE_UNAME="$(ssh_remote uname -m)"

MIHOMO_TAG="$CORE_VERSION_ARG"
if [[ -z "$MIHOMO_TAG" ]]; then
  MIHOMO_TAG="$DEFAULT_CORE_VERSION"
fi
if [[ "$MIHOMO_TAG" == "latest" || -z "$MIHOMO_TAG" ]]; then
  echo "ERROR: Mihomo core version must resolve to an exact release tag; use --core-version v1.19.30." >&2
  exit 1
fi
if [[ "$MIHOMO_TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  MIHOMO_TAG="v$MIHOMO_TAG"
fi
if [[ ! "$MIHOMO_TAG" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "ERROR: Mihomo core version contains unsupported characters: $MIHOMO_TAG" >&2
  exit 1
fi

case "$REMOTE_UNAME" in
  x86_64)
    MIHOMO_ASSET_ARCH="amd64-compatible"
    ;;
  aarch64|arm64)
    MIHOMO_ASSET_ARCH="arm64"
    ;;
  armv7l|armv7*)
    MIHOMO_ASSET_ARCH="armv7"
    ;;
  i386|i686)
    MIHOMO_ASSET_ARCH="386"
    ;;
  *)
    echo "ERROR: unsupported remote arch from uname -m: $REMOTE_UNAME" >&2
    exit 1
    ;;
esac

if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl is required to resolve Mihomo release metadata" >&2
  exit 1
fi
MIHOMO_METADATA="$(
  curl --retry 3 --retry-delay 1 --retry-all-errors --connect-timeout 10 --max-time 60 -fsSL \
    "https://api.github.com/repos/MetaCubeX/mihomo/releases/tags/${MIHOMO_TAG}" |
    python3 -c '
import json
import re
import sys

asset_arch = sys.argv[1]
payload = json.load(sys.stdin)
assets = payload.get("assets") if isinstance(payload, dict) else None
prefix = f"mihomo-linux-{asset_arch}-"
candidates = [
    asset
    for asset in assets or []
    if isinstance(asset, dict)
    and isinstance(asset.get("name"), str)
    and asset["name"].startswith(prefix)
    and asset["name"].endswith(".gz")
    and isinstance(asset.get("browser_download_url"), str)
    and asset["browser_download_url"]
]
if len(candidates) != 1:
    raise SystemExit(f"release has {len(candidates)} metadata assets for {asset_arch}")
asset = candidates[0]
asset_name = asset["name"]
asset_url = asset["browser_download_url"]
digest = str(asset.get("digest") or "")
if digest.startswith("sha256:"):
    digest = digest.split(":", 1)[1]
if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
    raise SystemExit(f"asset {asset_name} has no valid SHA256 digest")
print(f"{asset_name}\t{asset_url}\t{digest.lower()}")
' "$MIHOMO_ASSET_ARCH"
)"
if [[ "$(printf '%s\n' "$MIHOMO_METADATA" | wc -l | tr -d ' ')" != "1" ]]; then
  echo "ERROR: unexpected Mihomo metadata selection output" >&2
  exit 1
fi
IFS=$'\t' read -r MIHOMO_ASSET MIHOMO_URL MIHOMO_SHA256 <<<"$MIHOMO_METADATA"
if [[ -z "$MIHOMO_ASSET" || -z "$MIHOMO_URL" || -z "$MIHOMO_SHA256" ]]; then
  echo "ERROR: incomplete Mihomo release metadata" >&2
  exit 1
fi
MMDB_URL="https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/country.mmdb"
echo "Selected Mihomo ${MIHOMO_TAG}: ${MIHOMO_ASSET} sha256=${MIHOMO_SHA256}"

if [[ ! -f "$CORE_UPDATER_LOCAL" || ! -f "$VERGE_API_LOCAL" ]]; then
  echo "ERROR: missing core updater or Verge API source:" >&2
  echo "  - $CORE_UPDATER_LOCAL" >&2
  echo "  - $VERGE_API_LOCAL" >&2
  exit 1
fi
scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
  "$CORE_UPDATER_LOCAL" "$SSH_USER@$HOST:$TMP_CORE_UPDATER" >/dev/null
scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
  "$VERGE_API_LOCAL" "$SSH_USER@$HOST:$TMP_VERGE_API" >/dev/null

if [[ "$ONLY_CORE" != "1" ]]; then
scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$PATCHED_CFG_LOCAL" "$SSH_USER@$HOST:$TMP_CFG" >/dev/null

scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$UNIT_LOCAL" "$SSH_USER@$HOST:$TMP_UNIT" >/dev/null

  if [[ ! -f "$VERGE_API_LOCAL" || ! -f "$VERGE_API_UNIT_LOCAL" || ! -f "$RUNTIME_CONTRACT_LOCAL" ]]; then
    echo "ERROR: missing verge api files:" >&2
    echo "  - $VERGE_API_LOCAL" >&2
    echo "  - $VERGE_API_UNIT_LOCAL" >&2
    echo "  - $RUNTIME_CONTRACT_LOCAL" >&2
    exit 1
  fi

  if [[ ! -f "$RESOLVED_SYNC_LOCAL" || ! -f "$RESOLVED_SYNC_UNIT_LOCAL" ]]; then
    echo "ERROR: missing resolved sync files:" >&2
    echo "  - $RESOLVED_SYNC_LOCAL" >&2
    echo "  - $RESOLVED_SYNC_UNIT_LOCAL" >&2
    exit 1
  fi

scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$VERGE_API_UNIT_LOCAL" "$SSH_USER@$HOST:$TMP_VERGE_API_UNIT" >/dev/null
scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$RESOLVED_SYNC_LOCAL" "$SSH_USER@$HOST:$TMP_RESOLVED_SYNC" >/dev/null
scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$RESOLVED_SYNC_UNIT_LOCAL" "$SSH_USER@$HOST:$TMP_RESOLVED_SYNC_UNIT" >/dev/null
scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$RUNTIME_CONTRACT_LOCAL" "$SSH_USER@$HOST:$TMP_RUNTIME_CONTRACT" >/dev/null
  printf '%s\n' "$VERGE_API_SECRET_EFFECTIVE" | \
    ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
      "$SSH_USER@$HOST" "cat > '$TMP_VERGE_SECRET'"

  # Optional: sync Country.mmdb if present locally.
  if [[ -f "$MMDB_LOCAL" ]]; then
    echo "Uploading Country.mmdb ..."
scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
      "$MMDB_LOCAL" "$SSH_USER@$HOST:/tmp/Country.mmdb.$TS" >/dev/null
  else
    echo "NOTE: $MMDB_LOCAL not found; skipping Country.mmdb upload." >&2
  fi

  # Optional: install the DNS change safety tool (no execution by default).
  if [[ "$INSTALL_NET_SAFE_APPLY" == "1" && -f "$ROOT/infra/microserver/lzc-net-safe-apply" ]]; then
    echo "Installing lzc-net-safe-apply ..."
scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
      "$ROOT/infra/microserver/lzc-net-safe-apply" "$SSH_USER@$HOST:/tmp/lzc-net-safe-apply.$TS" >/dev/null
    ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
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

if [[ "$CONTAINER_PROXY_ENABLE" == "1" && "$ONLY_CORE" != "1" ]]; then
  if [[ ! -f "$CONTAINER_PROXY_SOCKET_LOCAL" || ! -f "$CONTAINER_PROXY_SERVICE_LOCAL" ]]; then
    echo "ERROR: missing container proxy unit(s):" >&2
    echo "  - $CONTAINER_PROXY_SOCKET_LOCAL" >&2
    echo "  - $CONTAINER_PROXY_SERVICE_LOCAL" >&2
    exit 1
  fi

  echo "Uploading mihomo-container-proxy units ..."
scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$CONTAINER_PROXY_SOCKET_LOCAL" "$SSH_USER@$HOST:$TMP_CONTAINER_PROXY_SOCKET" >/dev/null
scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$CONTAINER_PROXY_SERVICE_LOCAL" "$SSH_USER@$HOST:$TMP_CONTAINER_PROXY_SERVICE" >/dev/null
fi

echo "Applying on microserver ..."
    ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
  "$SSH_USER@$HOST" \
  TS="$TS" \
  TMP_CFG="$TMP_CFG" \
  TMP_UNIT="$TMP_UNIT" \
  TMP_CONTAINER_PROXY_SOCKET="$TMP_CONTAINER_PROXY_SOCKET" \
  TMP_CONTAINER_PROXY_SERVICE="$TMP_CONTAINER_PROXY_SERVICE" \
  TMP_VERGE_API="$TMP_VERGE_API" \
  TMP_CORE_UPDATER="$TMP_CORE_UPDATER" \
  TMP_VERGE_API_UNIT="$TMP_VERGE_API_UNIT" \
  TMP_RESOLVED_SYNC="$TMP_RESOLVED_SYNC" \
  TMP_RESOLVED_SYNC_UNIT="$TMP_RESOLVED_SYNC_UNIT" \
  TMP_RUNTIME_CONTRACT="$TMP_RUNTIME_CONTRACT" \
  TMP_VERGE_SECRET="$TMP_VERGE_SECRET" \
  MIHOMO_URL="$MIHOMO_URL" \
  MIHOMO_SHA256="$MIHOMO_SHA256" \
  MIHOMO_TAG="$MIHOMO_TAG" \
  MMDB_URL="$MMDB_URL" \
  UPGRADE_CORE="$UPGRADE_CORE" \
  ONLY_CORE="$ONLY_CORE" \
  NO_ROLLBACK="$NO_ROLLBACK" \
  CONTAINER_PROXY_ENABLE="$CONTAINER_PROXY_ENABLE" \
  DNS_ENABLE="$DNS_ENABLE" \
  RESOLVED_VIA_MIHOMO="$RESOLVED_VIA_MIHOMO" \
  RESOLVED_DNS_PRIMARY_OVERRIDE="$RESOLVED_DNS_PRIMARY_OVERRIDE" \
  RESOLVED_FALLBACK_DNS_OVERRIDE="$RESOLVED_FALLBACK_DNS_OVERRIDE" \
  bash -s <<'REMOTE'
set -euo pipefail

cfg=/etc/mihomo/config.yaml
unit=/etc/systemd/system/mihomo.service
container_proxy_socket=/etc/systemd/system/mihomo-container-proxy.socket
container_proxy_service=/etc/systemd/system/mihomo-container-proxy.service
verge_api_service=/etc/systemd/system/mihomo-verge-api.service
verge_api_secret=/etc/mihomo/verge-api.secret
verge_api_bin=/usr/local/lib/lzc-mihomo/mihomo-verge-api.py
core_updater=/usr/local/lib/lzc-mihomo/mihomo_core_updater.py
resolved_sync_service=/etc/systemd/system/mihomo-resolved-sync.service
resolved_sync_bin=/usr/local/lib/lzc-mihomo/mihomo-resolved-sync.sh
resolved_sync_dropin_dir=/etc/systemd/system/mihomo-resolved-sync.service.d
resolved_sync_override_file=$resolved_sync_dropin_dir/override.conf
runtime_contract=/usr/local/lib/lzc-mihomo/runtime-contract.json
mihomo_bin=/usr/local/bin/mihomo
rollback_dir=/var/lib/mihomo/rollback
log_file="$rollback_dir/upgrade-${TS}.log"

bak_cfg=""
bak_unit=""
verge_api_backup=""
prev_version=""
new_version=""
core_attempted=0
core_changed=0
mutation_started=0

command -v curl >/dev/null 2>&1 || { echo "ERROR: curl not found on microserver" >&2; exit 1; }
command -v gzip >/dev/null 2>&1 || { echo "ERROR: gzip not found on microserver" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found on microserver" >&2; exit 1; }

install -d -o root -g root -m 755 /run/lock
exec 9>/run/lock/clash-verge-deploy.lock
flock -n 9 || { echo "ERROR: another Clash-Verge deployment is active" >&2; exit 1; }

assert_no_symlink_components() {
  python3 - "$@" <<'PY'
import stat
import sys
from pathlib import Path

for raw in sys.argv[1:]:
    path = Path(raw)
    if not path.is_absolute():
        raise SystemExit(f"unsafe non-absolute path: {path}")
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            break
        if stat.S_ISLNK(mode):
            raise SystemExit(f"refusing symlink path component: {current}")
PY
}

snapshot_dir="$rollback_dir/full-deploy-${TS}"
assert_no_symlink_components "$rollback_dir" "$snapshot_dir"
install -d -o root -g root -m 700 "$rollback_dir"
if [[ -e "$snapshot_dir" || -L "$snapshot_dir" ]]; then
  echo "ERROR: snapshot path already exists; refusing to mix deployments" >&2
  exit 1
fi
install -d -o root -g root -m 700 "$snapshot_dir"
snapshot_manifest="$snapshot_dir/manifest.tsv"
snapshot_service_state="$snapshot_dir/service-state.tsv"
: > "$snapshot_manifest"
: > "$snapshot_service_state"

snapshot_target() {
  local path="$1" index backup type size digest archive_digest mode uid gid
  assert_no_symlink_components "$path"
  index=$((snapshot_index + 1))
  snapshot_index="$index"
  backup="target-${index}"
  if [[ ! -e "$path" ]]; then
    printf '%s\tmissing\t-\t0\t-\t-\t-\t-\t-\t-\n' "$path" >> "$snapshot_manifest"
    return 0
  fi
  [[ ! -L "$path" ]] || return 1
  mode="$(stat -c '%a' -- "$path")"
  uid="$(stat -c '%u' -- "$path")"
  gid="$(stat -c '%g' -- "$path")"
  if [[ -f "$path" ]]; then
    type=file
    size="$(stat -c '%s' -- "$path")"
    cp -a -- "$path" "$snapshot_dir/$backup"
  elif [[ -d "$path" ]]; then
    type=directory
    size=0
    digest="$(tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
      -cf - -C / "${path#/}" | sha256sum | awk '{print $1}')"
    tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
      -czf "$snapshot_dir/$backup.tar.gz" -C / "${path#/}"
    backup="$backup.tar.gz"
  else
    echo "ERROR: unsupported snapshot target type: $path" >&2
    return 1
  fi
  if [[ "$type" == file ]]; then
    digest="$(sha256sum -- "$path" | awk '{print $1}')"
  fi
  archive_digest="$(sha256sum -- "$snapshot_dir/$backup" | awk '{print $1}')"
  [[ "$archive_digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  printf '%s\tpresent\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$path" "$type" "$size" "$digest" "$backup" "$archive_digest" "$mode" "$uid" "$gid" \
    >> "$snapshot_manifest"
}

snapshot_index=0
snapshot_targets=(
  "$cfg" "$unit" "$container_proxy_socket" "$container_proxy_service"
  "$verge_api_service" "$verge_api_secret" "$verge_api_bin"
  "$resolved_sync_service" "$resolved_sync_bin" "$resolved_sync_dropin_dir"
  "$runtime_contract" "/var/lib/mihomo/Country.mmdb" "/var/lib/mihomo/verge"
)
for snapshot_path in "${snapshot_targets[@]}"; do
  snapshot_target "$snapshot_path"
done
snapshot_services=(mihomo.service mihomo-verge-api.service mihomo-container-proxy.socket mihomo-resolved-sync.service)
for snapshot_service in "${snapshot_services[@]}"; do
  service_exists=0
  if systemctl cat "$snapshot_service" >/dev/null 2>&1 ||
     systemctl list-unit-files --no-legend "$snapshot_service" 2>/dev/null |
       awk -v unit="$snapshot_service" '$1 == unit {found = 1} END {exit !found}'; then
    service_exists=1
  fi
  if [[ "$service_exists" == "1" ]]; then
    snapshot_active="$(systemctl is-active "$snapshot_service" 2>/dev/null || true)"
    snapshot_enabled="$(systemctl is-enabled "$snapshot_service" 2>/dev/null || true)"
    # Failed/unknown states cannot be recreated deterministically. Refuse the
    # deployment before any target mutation rather than claiming a rollback.
    case "$snapshot_active" in active|inactive) ;; *) exit 1 ;; esac
    case "$snapshot_enabled" in enabled|disabled|static|masked) ;; *) exit 1 ;; esac
    printf '%s\t%s\t%s\n' "$snapshot_service" "$snapshot_active" "$snapshot_enabled" >> "$snapshot_service_state"
  else
    printf '%s\tabsent\tabsent\n' "$snapshot_service" >> "$snapshot_service_state"
  fi
done
sha256sum -- "$snapshot_manifest" > "$snapshot_dir/manifest.sha256"
sha256sum -- "$snapshot_service_state" > "$snapshot_dir/service-state.sha256"

snapshot_target_digest() {
  local path="$1"
  if [[ -f "$path" ]]; then
    sha256sum -- "$path" | awk '{print $1}'
  elif [[ -d "$path" ]]; then
    tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
      -cf - -C / "${path#/}" | sha256sum | awk '{print $1}'
  else
    return 1
  fi
}

verify_snapshot() {
  local path state type size digest backup archive_digest mode uid gid actual
  local snapshot_service snapshot_active snapshot_enabled
  [[ -f "$snapshot_manifest" && -f "$snapshot_dir/manifest.sha256" &&
     -f "$snapshot_service_state" && -f "$snapshot_dir/service-state.sha256" ]] || return 1
  sha256sum -c "$snapshot_dir/manifest.sha256" >/dev/null || return 1
  sha256sum -c "$snapshot_dir/service-state.sha256" >/dev/null || return 1
  while IFS=$'\t' read -r snapshot_service snapshot_active snapshot_enabled; do
    [[ -n "$snapshot_service" ]] || continue
    case "$snapshot_service" in
      mihomo.service|mihomo-verge-api.service|mihomo-container-proxy.socket|mihomo-resolved-sync.service) ;;
      *) return 1 ;;
    esac
    if [[ "$snapshot_active" == absent ]]; then
      [[ "$snapshot_enabled" == absent ]] || return 1
    else
      case "$snapshot_active" in active|inactive) ;; *) return 1 ;; esac
      case "$snapshot_enabled" in enabled|disabled|static|masked) ;; *) return 1 ;; esac
    fi
  done < "$snapshot_service_state"
  while IFS=$'\t' read -r path state type size digest backup archive_digest mode uid gid; do
    [[ "$path" == "$cfg" || "$path" == "$unit" || "$path" == "$container_proxy_socket" ||
       "$path" == "$container_proxy_service" || "$path" == "$verge_api_service" ||
       "$path" == "$verge_api_secret" || "$path" == "$verge_api_bin" ||
       "$path" == "$resolved_sync_service" || "$path" == "$resolved_sync_bin" ||
       "$path" == "$resolved_sync_dropin_dir" || "$path" == "$runtime_contract" ||
       "$path" == /var/lib/mihomo/Country.mmdb || "$path" == /var/lib/mihomo/verge ]] || return 1
    assert_no_symlink_components "$path"
   if [[ "$state" == present ]]; then
      [[ "$type" == file || "$type" == directory ]] || return 1
      [[ "$backup" =~ ^target-[0-9]+(\.tar\.gz)?$ && "$digest" =~ ^[0-9a-f]{64}$ &&
         "$archive_digest" =~ ^[0-9a-f]{64}$ && "$mode" =~ ^[0-7]{1,4}$ &&
         "$uid" =~ ^[0-9]+$ && "$gid" =~ ^[0-9]+$ ]] || return 1
     [[ -e "$snapshot_dir/$backup" && ! -L "$snapshot_dir/$backup" ]] || return 1
      actual="$(sha256sum -- "$snapshot_dir/$backup" | awk '{print $1}')"
      [[ "$actual" == "$archive_digest" ]] || return 1
      if [[ "$type" == file ]]; then
        [[ "$size" =~ ^[0-9]+$ && ! "$backup" =~ \.tar\.gz$ && "$actual" == "$digest" ]] || return 1
      else
        [[ "$size" =~ ^[0-9]+$ && "$backup" =~ \.tar\.gz$ ]] || return 1
        tar -tzf "$snapshot_dir/$backup" >/dev/null || return 1
      fi
    elif [[ "$state" != missing || "$type" != - || "$size" != 0 || "$digest" != - ||
             "$backup" != - || "$archive_digest" != - || "$mode" != - || "$uid" != - || "$gid" != - ]]; then
     return 1
   fi
  done < "$snapshot_manifest"
}

restore_full_snapshot() {
  local unknown_marker="$snapshot_dir/UNKNOWN"
  local path state type size digest backup archive_digest mode uid gid
  local snapshot_service snapshot_active snapshot_enabled actual_active actual_enabled load_state unit_file_count
  verify_snapshot || return 1
  printf 'rollback_status=UNKNOWN\n' > "$unknown_marker"
  while IFS=$'\t' read -r path state type size digest backup archive_digest mode uid gid; do
    assert_no_symlink_components "$path"
    if [[ "$state" == present ]]; then
      if [[ "$type" == file ]]; then
        install -d -o root -g root -m 755 "$(dirname "$path")"
        install -o "$uid" -g "$gid" -m "$mode" "$snapshot_dir/$backup" "$path"
      elif [[ "$type" == directory ]]; then
        rm -rf -- "$path"
        install -d -o root -g root -m 755 "$(dirname "$path")"
        tar -xzf "$snapshot_dir/$backup" -C /
        chmod "$mode" "$path"
        chown "$uid:$gid" "$path"
      else
        return 1
      fi
    else
      rm -rf -- "$path"
    fi
  done < "$snapshot_manifest"
  while IFS=$'\t' read -r snapshot_service snapshot_active snapshot_enabled; do
    if [[ "$snapshot_active" == absent ]]; then
      # A unit file can have been removed while systemd still keeps the unit
      # loaded/running.  Stop and disable it before daemon-reload; otherwise a
      # rollback that only removes the file leaves a newly-created service
      # active while reporting success.
      systemctl disable --now "$snapshot_service" >/dev/null 2>&1 || true
      systemctl stop "$snapshot_service" >/dev/null 2>&1 || true
    fi
  done < "$snapshot_service_state"
  systemctl daemon-reload
  while IFS=$'\t' read -r snapshot_service snapshot_active snapshot_enabled; do
    [[ "$snapshot_active" == absent ]] && continue
    case "$snapshot_enabled" in
      enabled) systemctl unmask "$snapshot_service" >/dev/null 2>&1 || true; systemctl enable "$snapshot_service" >/dev/null ;;
      disabled) systemctl unmask "$snapshot_service" >/dev/null 2>&1 || true; systemctl disable "$snapshot_service" >/dev/null 2>&1 || true ;;
      static) systemctl unmask "$snapshot_service" >/dev/null 2>&1 || true ;;
      masked) systemctl mask "$snapshot_service" >/dev/null ;;
      *) return 1 ;;
    esac
    case "$snapshot_active" in
      active) systemctl start "$snapshot_service" >/dev/null ;;
      inactive) systemctl stop "$snapshot_service" >/dev/null 2>&1 || true ;;
      *) return 1 ;;
    esac
  done < "$snapshot_service_state"
  while IFS=$'\t' read -r path state type size digest backup archive_digest mode uid gid; do
    if [[ "$state" == present ]]; then
      [[ -e "$path" && ! -L "$path" ]] || return 1
      [[ "$(snapshot_target_digest "$path")" == "$digest" ]] || return 1
      [[ "$(stat -c '%a' -- "$path")" == "$mode" &&
         "$(stat -c '%u' -- "$path")" == "$uid" &&
         "$(stat -c '%g' -- "$path")" == "$gid" ]] || return 1
    else
      [[ ! -e "$path" && ! -L "$path" ]] || return 1
    fi
  done < "$snapshot_manifest"
  while IFS=$'\t' read -r snapshot_service snapshot_active snapshot_enabled; do
    if [[ "$snapshot_active" == absent ]]; then
      actual_active="$(systemctl is-active "$snapshot_service" 2>/dev/null || true)"
      actual_enabled="$(systemctl is-enabled "$snapshot_service" 2>/dev/null || true)"
      load_state="$(systemctl show "$snapshot_service" --property=LoadState --value 2>/dev/null || true)"
      unit_file_count="$(systemctl list-unit-files --no-legend "$snapshot_service" 2>/dev/null |
        awk -v unit="$snapshot_service" '$1 == unit {count += 1} END {print count + 0}')"
      case "$actual_active" in
        active) return 1 ;;
        inactive|failed|unknown) ;;
        *) return 1 ;;
      esac
      [[ "$load_state" == not-found ]] || return 1
      [[ "$actual_enabled" == not-found || -z "$actual_enabled" ]] || return 1
      [[ "$unit_file_count" == 0 ]] || return 1
      continue
    fi
    [[ "$(systemctl is-active "$snapshot_service" 2>/dev/null || true)" == "$snapshot_active" ]] || return 1
    [[ "$(systemctl is-enabled "$snapshot_service" 2>/dev/null || true)" == "$snapshot_enabled" ]] || return 1
  done < "$snapshot_service_state"
  rm -f -- "$unknown_marker"
  [[ ! -e "$unknown_marker" ]]
}

if [[ -f "$verge_api_bin" ]]; then
  verge_api_backup="$snapshot_dir/target-7"
  [[ -f "$verge_api_backup" ]] || verge_api_backup=""
fi

log() {
  local msg="$1"
  printf '[%s] %s\n' "$(date -Iseconds)" "$msg" | tee -a "$log_file" >&2
}

ensure_systemd_resolved_present() {
  if ! systemctl list-unit-files --no-pager 2>/dev/null | awk '{print $1}' | grep -qx systemd-resolved.service; then
    log "ERROR: systemd-resolved.service not found on this microserver."
    return 1
  fi
}

ensure_mihomo_dns_ready() {
  local ready=0
  for _ in 1 2 3 4 5; do
    if ss -lun | grep -q '127.0.0.1:1053'; then
      ready=1
      break
    fi
    sleep 1
  done
  if [[ "$ready" != "1" ]]; then
    log "Mihomo DNS 127.0.0.1:1053 is not listening after restart"
    return 1
  fi
}

configure_resolved_via_mihomo() {
  if ! command -v resolvectl >/dev/null 2>&1; then
    log "ERROR: resolvectl not found on this microserver."
    return 1
  fi
  systemctl enable --now mihomo-resolved-sync.service >/dev/null
  systemctl is-active mihomo-resolved-sync.service >/dev/null
}

disable_resolved_via_mihomo() {
  if systemctl list-unit-files --no-pager 2>/dev/null | awk '{print $1}' | grep -qx mihomo-resolved-sync.service; then
    systemctl disable --now mihomo-resolved-sync.service >/dev/null || true
    log "Disabled mihomo-resolved-sync.service"
  fi
}

configure_resolved_sync_override() {
  if [[ -z "${RESOLVED_DNS_PRIMARY_OVERRIDE:-}" && -z "${RESOLVED_FALLBACK_DNS_OVERRIDE:-}" ]]; then
    rm -f "$resolved_sync_override_file" || true
    rmdir "$resolved_sync_dropin_dir" >/dev/null 2>&1 || true
    return
  fi

  install -d -o root -g root -m 755 "$resolved_sync_dropin_dir"
  {
    echo "[Service]"
    if [[ -n "${RESOLVED_DNS_PRIMARY_OVERRIDE:-}" ]]; then
      printf 'Environment=MIHOMO_RESOLVED_DNS_PRIMARY=%q\n' "$RESOLVED_DNS_PRIMARY_OVERRIDE"
    fi
    if [[ -n "${RESOLVED_FALLBACK_DNS_OVERRIDE:-}" ]]; then
      printf 'Environment=MIHOMO_RESOLVED_FALLBACK_DNS=%q\n' "$RESOLVED_FALLBACK_DNS_OVERRIDE"
    fi
  } >"$resolved_sync_override_file"
}

run_dns_validation() {
  local txt_via_mihomo
  local txt_via_stub
  local a_via_mihomo
  local aaaa_baidu_via_mihomo
  local resolved_status

  if ! command -v dig >/dev/null 2>&1; then
    log "ERROR: dig not found on microserver; cannot run special TXT DNS validation"
    return 1
  fi
  if ! command -v resolvectl >/dev/null 2>&1; then
    log "ERROR: resolvectl not found on microserver; cannot validate systemd-resolved state"
    return 1
  fi

  txt_via_mihomo="$(dig +time=5 +tries=1 TXT _dnsaddr.origin.lazycat.cloud @127.0.0.1 -p 1053 2>&1 || true)"
  printf '%s\n' "$txt_via_mihomo" | tee -a "$log_file" >/dev/null
  if ! grep -q 'status: NOERROR' <<<"$txt_via_mihomo"; then
    log "Special TXT lookup via mihomo DNS failed"
    return 1
  fi

  txt_via_stub="$(dig +time=5 +tries=1 TXT _dnsaddr.origin.lazycat.cloud @127.0.0.53 2>&1 || true)"
  printf '%s\n' "$txt_via_stub" | tee -a "$log_file" >/dev/null
  if ! grep -q 'status: NOERROR' <<<"$txt_via_stub"; then
    log "Special TXT lookup via systemd-resolved stub failed"
    return 1
  fi

  a_via_mihomo="$(dig +time=5 +tries=1 A origin.lazycat.cloud @127.0.0.1 -p 1053 2>&1 || true)"
  printf '%s\n' "$a_via_mihomo" | tee -a "$log_file" >/dev/null
  if ! grep -q 'status: NOERROR' <<<"$a_via_mihomo"; then
    log "origin.lazycat.cloud A lookup via mihomo DNS failed"
    return 1
  fi

  aaaa_baidu_via_mihomo="$(dig +time=5 +tries=1 AAAA www.baidu.com @127.0.0.1 -p 1053 2>&1 || true)"
  printf '%s\n' "$aaaa_baidu_via_mihomo" | tee -a "$log_file" >/dev/null
  if ! grep -q 'IN[[:space:]]\+AAAA' <<<"$aaaa_baidu_via_mihomo"; then
    log "www.baidu.com AAAA lookup via mihomo DNS failed"
    return 1
  fi

  resolved_status="$(resolvectl status 2>&1 || true)"
  printf '%s\n' "$resolved_status" | tee -a "$log_file" >/dev/null
  if ! grep -q '127.0.0.1:1053' <<<"$resolved_status"; then
    log "system resolver is not pointing at 127.0.0.1:1053"
    return 1
  fi
}

run_verge_api_validation() {
  if [[ ! -f "$verge_api_service" || ! -f "$verge_api_secret" ]]; then
    return 0
  fi
  local verge_secret
  local verge_ok=0
  verge_secret="$(tr -d '\r\n' <"$verge_api_secret" 2>/dev/null || true)"
  for _ in $(seq 1 30); do
    if [[ -n "$verge_secret" ]] && curl -fsS \
      -H "Authorization: Bearer ${verge_secret}" \
      "http://172.18.0.1:9091/healthz" >/dev/null 2>&1; then
      verge_ok=1
      break
    fi
    sleep 1
  done
  if [[ "$verge_ok" != "1" ]]; then
    log "Verge API /healthz probe failed after restart"
    return 1
  fi
}

extract_version() {
  local bin="$1"
  "$bin" -v 2>/dev/null | head -n 1 | sed -E 's/^Mihomo Meta[[:space:]]+([^[:space:]]+).*/\1/'
}

rollback_core() {
  if [[ "$NO_ROLLBACK" == "1" ]]; then
    log "Rollback skipped because --no-rollback is enabled."
    return
  fi
  log "Rolling back core through the shared updater."
  if ! python3 "$core_updater" rollback \
      --target latest \
      --binary "$mihomo_bin" \
      --state-dir /var/lib/mihomo \
      --config "$cfg" \
      --service mihomo \
      --controller-url http://172.18.0.1:9090; then
    log "ERROR: shared Mihomo core rollback failed"
    return 1
  fi
}

restore_verge_api_if_needed() {
  if [[ "$ONLY_CORE" != "1" || -z "$verge_api_backup" || ! -f "$verge_api_backup" ]]; then
    return 0
  fi
  install -o root -g root -m 755 "$verge_api_backup" "$verge_api_bin"
  systemctl restart mihomo-verge-api >/dev/null 2>&1 || true
  log "Restored previous Verge API after core-only failure."
}

err_handler() {
  local rc=$?
  local line="$1"
  local rollback_failed=0
  trap - ERR
  log "ERROR at line $line (exit=$rc)."
  if [[ "$core_attempted" == "1" ]]; then
    if [[ "$core_changed" == "1" ]]; then
      rollback_core || rollback_failed=1
    else
      log "Core was not switched before failure; keeping previous binary."
    fi
  fi
  if [[ "$ONLY_CORE" == "1" ]]; then
    restore_verge_api_if_needed || rollback_failed=1
  elif [[ "$mutation_started" == "1" ]]; then
    if ! restore_full_snapshot; then
      rollback_failed=1
      log "ERROR: full deployment rollback failed; preserve $snapshot_dir/UNKNOWN and reconcile manually"
    fi
  fi
  if [[ "$rollback_failed" == "1" ]]; then
    log "ERROR: deployment failed with rollback status UNKNOWN"
  fi
  exit "$rc"
}
trap 'err_handler "$LINENO"' ERR

touch "$log_file"
chmod 600 "$log_file" || true
mutation_started=1
install -d -o root -g root -m 755 "$(dirname "$core_updater")"
install -o root -g root -m 755 "$TMP_CORE_UPDATER" "$core_updater"
if [[ -n "$verge_api_backup" ]]; then
  chmod 700 "$verge_api_backup"
fi
install -o root -g root -m 755 "$TMP_VERGE_API" "$verge_api_bin"
rm -f "$TMP_CORE_UPDATER" "$TMP_VERGE_API"

if [[ -x "$mihomo_bin" ]]; then
  prev_version="$(extract_version "$mihomo_bin" || true)"
fi

if [[ "$UPGRADE_CORE" == "1" || ! -x "$mihomo_bin" ]]; then
  core_attempted=1
  log "Upgrading mihomo through the shared updater: $MIHOMO_TAG"
  core_upgrade_args=(
    python3 "$core_updater" upgrade
    --tag "$MIHOMO_TAG"
    --asset-url "$MIHOMO_URL"
    --asset-sha256 "$MIHOMO_SHA256"
    --binary "$mihomo_bin"
    --state-dir /var/lib/mihomo
    --config "$cfg"
    --service mihomo
    --controller-url http://172.18.0.1:9090
  )
  if [[ "$NO_ROLLBACK" == "1" ]]; then
    core_upgrade_args+=(--no-rollback)
  fi
  "${core_upgrade_args[@]}" \
    | tee -a "$log_file"
  core_changed=1
  new_version="$(extract_version "$mihomo_bin" || true)"
  if [[ -n "$prev_version" && "$prev_version" == "$new_version" ]]; then
    core_changed=0
  fi
  log "Core switched to: ${new_version:-unknown}"
else
  new_version="$prev_version"
  log "Core upgrade skipped (existing binary retained)."
fi

if [[ "$ONLY_CORE" == "1" ]]; then
  if [[ -f "$verge_api_service" ]]; then
    systemctl restart mihomo-verge-api
    systemctl is-active mihomo-verge-api >/dev/null
    run_verge_api_validation
  fi
  trap - ERR
  log "OK: Mihomo core-only upgrade completed without changing config, units, TUN, DNS, or container proxy."
  exit 0
fi

if [[ "$ONLY_CORE" != "1" ]]; then
  # The immutable snapshot was captured before any target write.  Keep its
  # exact entries in the receipt instead of creating ad-hoc basename backups.
  bak_cfg="$snapshot_dir/target-1"
  bak_unit="$snapshot_dir/target-2"

  # Ensure directories exist
  id mihomo >/dev/null 2>&1 || useradd --system --home /var/lib/mihomo --shell /usr/sbin/nologin mihomo
  install -d -o root -g mihomo -m 750 /etc/mihomo
  install -d -o mihomo -g mihomo -m 750 /var/lib/mihomo
  install -d -o root -g root -m 755 /usr/local/lib/lzc-mihomo

  # Install config + unit
  install -o root -g mihomo -m 640 "$TMP_CFG" "$cfg"
  install -o root -g root -m 644 "$TMP_UNIT" "$unit"
  install -o root -g root -m 644 "$TMP_VERGE_API_UNIT" "$verge_api_service"
  install -o root -g root -m 755 "$TMP_RESOLVED_SYNC" "$resolved_sync_bin"
  install -o root -g root -m 644 "$TMP_RESOLVED_SYNC_UNIT" "$resolved_sync_service"
  install -o root -g root -m 644 "$TMP_RUNTIME_CONTRACT" "$runtime_contract"
  install -o root -g root -m 600 "$TMP_VERGE_SECRET" "$verge_api_secret"
  rm -f "$TMP_CFG" "$TMP_UNIT" "$TMP_VERGE_API_UNIT" "$TMP_RESOLVED_SYNC" "$TMP_RESOLVED_SYNC_UNIT" "$TMP_RUNTIME_CONTRACT" "$TMP_VERGE_SECRET"

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

configure_resolved_sync_override

# Validate config with the current core before restart.
"$mihomo_bin" -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml >/dev/null

systemctl daemon-reload
systemctl enable mihomo >/dev/null
systemctl restart mihomo
if [[ -f "$verge_api_service" ]]; then
  systemctl enable mihomo-verge-api >/dev/null
  systemctl restart mihomo-verge-api
fi
sleep 2
systemctl is-active mihomo >/dev/null
if [[ -f "$verge_api_service" ]]; then
  systemctl is-active mihomo-verge-api >/dev/null
fi

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

run_verge_api_validation

if [[ "$DNS_ENABLE" == "1" && "$RESOLVED_VIA_MIHOMO" == "1" ]]; then
  ensure_mihomo_dns_ready
  configure_resolved_via_mihomo
  run_dns_validation
else
  disable_resolved_via_mihomo
fi

trap - ERR
log "OK: mihomo restarted. cfg_backup=${bak_cfg:-none} unit_backup=${bak_unit:-none}"
if [[ "$core_attempted" == "1" ]]; then
  log "Core result: prev=${prev_version:-none} target=${MIHOMO_TAG} current=${new_version:-unknown}"
fi
REMOTE

echo "Done."
