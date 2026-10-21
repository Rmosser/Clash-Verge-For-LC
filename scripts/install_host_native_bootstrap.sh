#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_deploy_settings.sh"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

HOST="${MICROSERVER_HOST:-rainierdev.heiyu.space}"
SSH_USER="${MICROSERVER_SSH_USER:-root}"
SSH_KEY="${MICROSERVER_SSH_KEY:-$HOME/.ssh/id_ed25519}"
# This path is part of the bootstrap contract.  It is deliberately not
# caller-controlled: changing it would make the installer write arbitrary
# root-owned paths on the remote host.
readonly REMOTE_BOOTSTRAP_ROOT="/root/.config/lzc-mihomo-bootstrap"
BRIDGE_WAIT_SECONDS="${MIHOMO_BOOTSTRAP_BRIDGE_WAIT_SECONDS:-180}"
REMOTE_USER_UNIT_DIR="/root/.config/systemd/user"
REMOTE_BOOTSTRAP_SERVICE="lzc-mihomo-bootstrap.service"
REMOTE_BOOTSTRAP_SCRIPT="$REMOTE_BOOTSTRAP_ROOT/bootstrap-apply.sh"
REMOTE_BOOTSTRAP_LOG="$REMOTE_BOOTSTRAP_ROOT/bootstrap.log"

usage() {
  cat <<'USAGE'
Usage: scripts/install_host_native_bootstrap.sh

Snapshots the current host-native Mihomo deployment on the target microserver
into root's persistent home, then installs a root user-systemd oneshot service
that reapplies that snapshot at boot.

Supported targets:
  - rainierdev.heiyu.space
  - rainierspace.heiyu.space

Environment overrides:
  MICROSERVER_HOST                 defaults to rainierdev.heiyu.space
  MICROSERVER_SSH_USER             defaults to root
  MICROSERVER_SSH_KEY              defaults to ~/.ssh/id_ed25519
  The bootstrap root is fixed at /root/.config/lzc-mihomo-bootstrap.
USAGE
}

CONFIRM_APPLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --confirm) CONFIRM_APPLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$CONFIRM_APPLY" != "1" ]]; then
  echo "Plan only: would snapshot and install the fixed bootstrap on $SSH_USER@$HOST. Re-run with --confirm."
  exit 0
fi

if [[ -n "${MIHOMO_BOOTSTRAP_REMOTE_ROOT:-}" && "${MIHOMO_BOOTSTRAP_REMOTE_ROOT}" != "$REMOTE_BOOTSTRAP_ROOT" ]]; then
  echo "ERROR: MIHOMO_BOOTSTRAP_REMOTE_ROOT is not configurable; refusing an arbitrary remote path." >&2
  exit 2
fi

mihomo_require_apply_confirmation "$HOST" "$SSH_USER" "$CONFIRM_APPLY" "install_host_native_bootstrap"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

case "$HOST" in
  rainierdev.heiyu.space|rainierspace.heiyu.space)
    ;;
  *)
    echo "ERROR: this installer only supports rainierdev.* or rainierspace.*" >&2
    echo "Refusing to run against host: $HOST" >&2
    exit 1
    ;;
esac

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
    "$SSH_USER@$HOST" "$@"
}

required_remote_paths=(
  /usr/local/bin/mihomo
  /etc/mihomo/config.yaml
  /etc/mihomo/verge-api.secret
  /etc/systemd/system/mihomo.service
  /etc/systemd/system/mihomo-verge-api.service
  /usr/local/lib/lzc-mihomo/mihomo-verge-api.py
  /usr/local/lib/lzc-mihomo/runtime-contract.json
)

for remote_path in "${required_remote_paths[@]}"; do
  if ! ssh_remote "test -e '$remote_path'"; then
    echo "ERROR: remote prerequisite missing: $remote_path" >&2
    echo "Hint: run deploy_microserver.sh first to seed a live host-native deployment." >&2
    exit 1
  fi
done

cat <<EOF >&2
Installing host-native bootstrap on $SSH_USER@$HOST
  bootstrap root: $REMOTE_BOOTSTRAP_ROOT
  user unit dir : $REMOTE_USER_UNIT_DIR
EOF

ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}" \
  "$SSH_USER@$HOST" \
  REMOTE_BOOTSTRAP_ROOT="$REMOTE_BOOTSTRAP_ROOT" \
  BRIDGE_WAIT_SECONDS="$BRIDGE_WAIT_SECONDS" \
  REMOTE_USER_UNIT_DIR="$REMOTE_USER_UNIT_DIR" \
  REMOTE_BOOTSTRAP_SERVICE="$REMOTE_BOOTSTRAP_SERVICE" \
  REMOTE_BOOTSTRAP_SCRIPT="$REMOTE_BOOTSTRAP_SCRIPT" \
  REMOTE_BOOTSTRAP_LOG="$REMOTE_BOOTSTRAP_LOG" \
  bash -s <<'REMOTE'
set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date -Iseconds)" "$1"
}

generations_root="$REMOTE_BOOTSTRAP_ROOT/generations"
state_dir="$REMOTE_BOOTSTRAP_ROOT/state"
unit_path="$REMOTE_USER_UNIT_DIR/$REMOTE_BOOTSTRAP_SERVICE"
wants_dir="$REMOTE_USER_UNIT_DIR/default.target.wants"
state_file="$REMOTE_BOOTSTRAP_ROOT/bootstrap-state.env"
current_generation_file="$REMOTE_BOOTSTRAP_ROOT/current-generation"
applied_generation_file="$REMOTE_BOOTSTRAP_ROOT/applied-generation"

log "Preparing immutable bootstrap generation under $REMOTE_BOOTSTRAP_ROOT"

install -d -m 700 "$REMOTE_BOOTSTRAP_ROOT" "$generations_root" "$state_dir"
generation_id="gen.$(date -u +%Y%m%dT%H%M%SZ).$$"
snapshot_root="$generations_root/$generation_id"
if [[ -e "$snapshot_root" || -L "$snapshot_root" ]]; then
  echo "ERROR: generated bootstrap generation already exists" >&2
  exit 1
fi
staging_root="$(mktemp -d "$generations_root/.staging.XXXXXX")"
cleanup_staging() {
  if [[ -d "$staging_root" ]]; then
    rm -rf -- "$staging_root"
  fi
}
trap cleanup_staging EXIT
install -d -m 700 \
  "$staging_root/usr-local-bin" \
  "$staging_root/etc-mihomo" \
  "$staging_root/var-lib-mihomo" \
  "$staging_root/systemd" \
  "$staging_root/usr-local-lib-lzc-mihomo"

copy_snapshot_file() {
  local source="$1" destination="$2" mode="$3"
  [[ -f "$source" && ! -L "$source" ]] || {
    echo "ERROR: snapshot source is not a regular file: $source" >&2
    exit 1
  }
  install -m "$mode" "$source" "$staging_root/$destination"
}

copy_snapshot_file /usr/local/bin/mihomo usr-local-bin/mihomo 755
copy_snapshot_file /etc/mihomo/config.yaml etc-mihomo/config.yaml 640
copy_snapshot_file /etc/mihomo/verge-api.secret etc-mihomo/verge-api.secret 600
copy_snapshot_file /etc/systemd/system/mihomo.service systemd/mihomo.service 644
copy_snapshot_file /etc/systemd/system/mihomo-verge-api.service systemd/mihomo-verge-api.service 644
copy_snapshot_file /usr/local/lib/lzc-mihomo/mihomo-verge-api.py \
  usr-local-lib-lzc-mihomo/mihomo-verge-api.py 755
copy_snapshot_file /usr/local/lib/lzc-mihomo/runtime-contract.json \
  usr-local-lib-lzc-mihomo/runtime-contract.json 644

for optional_file in \
  /etc/systemd/system/mihomo-container-proxy.socket \
  /etc/systemd/system/mihomo-container-proxy.service \
  /etc/systemd/system/mihomo-resolved-sync.service; do
  if [[ -f "$optional_file" ]]; then
    [[ ! -L "$optional_file" ]] || { echo "ERROR: snapshot source is a symlink: $optional_file" >&2; exit 1; }
    install -m 644 "$optional_file" "$staging_root/systemd/$(basename "$optional_file")"
  fi
done

if [[ -f /usr/local/lib/lzc-mihomo/mihomo-resolved-sync.sh ]]; then
  copy_snapshot_file /usr/local/lib/lzc-mihomo/mihomo-resolved-sync.sh \
    usr-local-lib-lzc-mihomo/mihomo-resolved-sync.sh 755
fi

if [[ -f /var/lib/mihomo/Country.mmdb ]]; then
  copy_snapshot_file /var/lib/mihomo/Country.mmdb var-lib-mihomo/Country.mmdb 644
fi

if [[ -d /var/lib/mihomo/verge ]]; then
  if [[ -n "$(find /var/lib/mihomo/verge -type l -print -quit)" ]]; then
    echo "ERROR: /var/lib/mihomo/verge contains a symlink" >&2
    exit 1
  fi
  cp -a -- /var/lib/mihomo/verge "$staging_root/var-lib-mihomo/verge"
fi

container_proxy_enabled=0
resolved_sync_enabled=0

if systemctl is-enabled mihomo-container-proxy.socket >/dev/null 2>&1; then
  container_proxy_enabled=1
fi

if systemctl is-enabled mihomo-resolved-sync.service >/dev/null 2>&1; then
  resolved_sync_enabled=1
fi

cat >"$staging_root/metadata.env" <<STATE
GENERATION=$generation_id
CONTAINER_PROXY_ENABLED=$container_proxy_enabled
RESOLVED_SYNC_ENABLED=$resolved_sync_enabled
STATE
chmod 600 "$staging_root/metadata.env"
(
  cd "$staging_root"
  find . -type f ! -name manifest.sha256 -print0 |
    sort -z |
    while IFS= read -r -d '' path; do sha256sum -- "$path"; done
) >"$staging_root/manifest.sha256"
(
  cd "$staging_root"
  sha256sum -c manifest.sha256 >/dev/null
)
touch "$staging_root/COMPLETE"
chmod 600 "$staging_root/manifest.sha256" "$staging_root/COMPLETE"
mv -- "$staging_root" "$snapshot_root"
printf '%s\n' "$generation_id" >"$current_generation_file.tmp.$$"
chmod 600 "$current_generation_file.tmp.$$"
mv -- "$current_generation_file.tmp.$$" "$current_generation_file"

cat >"$state_file.tmp.$$" <<STATE
CONTAINER_PROXY_ENABLED=$container_proxy_enabled
RESOLVED_SYNC_ENABLED=$resolved_sync_enabled
STATE
chmod 600 "$state_file.tmp.$$"
mv -- "$state_file.tmp.$$" "$state_file"

cat >"$REMOTE_BOOTSTRAP_SCRIPT" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

bootstrap_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
generations_root="$bootstrap_root/generations"
state_dir="$bootstrap_root/state"
current_generation_file="$bootstrap_root/current-generation"
applied_generation_file="$bootstrap_root/applied-generation"
pending_transaction="$state_dir/pending.env"
log_file="$bootstrap_root/bootstrap.log"
bridge_wait_seconds="${BRIDGE_WAIT_SECONDS:-180}"
apply_stage=""

log() {
  printf '[%s] %s\n' "$(date -Iseconds)" "$1" | tee -a "$log_file" >&2
}

cleanup_apply_stage() {
  if [[ -n "$apply_stage" && -d "$apply_stage" ]]; then
    rm -rf -- "$apply_stage"
  fi
}
trap cleanup_apply_stage EXIT

read_value() {
  local path="$1" key="$2"
  [[ -f "$path" ]] || return 1
  awk -F= -v key="$key" '$1 == key {print substr($0, index($0, "=") + 1); exit}' "$path"
}

valid_generation_name() {
  [[ "$1" =~ ^gen\.[0-9]{8}T[0-9]{6}Z\.[0-9]+$ ]]
}

generation_path() {
  local generation="$1"
  valid_generation_name "$generation" || return 1
  printf '%s/%s\n' "$generations_root" "$generation"
}

validate_generation() {
  local generation="$1" source metadata container_proxy_enabled resolved_sync_enabled
  source="$(generation_path "$generation")"
  [[ -d "$source" && ! -L "$source" ]] || return 1
  [[ -f "$source/COMPLETE" && -f "$source/manifest.sha256" && -f "$source/metadata.env" ]] || return 1
  if [[ -n "$(find "$source" -type l -print -quit)" ]]; then
    return 1
  fi
  (
    cd "$source"
    sha256sum -c manifest.sha256 >/dev/null
  ) || return 1
  for required in \
    usr-local-bin/mihomo \
    etc-mihomo/config.yaml \
    etc-mihomo/verge-api.secret \
    systemd/mihomo.service \
    systemd/mihomo-verge-api.service \
    usr-local-lib-lzc-mihomo/mihomo-verge-api.py \
    usr-local-lib-lzc-mihomo/runtime-contract.json; do
    [[ -f "$source/$required" ]] || return 1
  done
  # Metadata is generated locally by the installer, but validate its values
  # before sourcing it in a root-owned bootstrap process.
  metadata="$source/metadata.env"
  container_proxy_enabled="$(read_value "$metadata" CONTAINER_PROXY_ENABLED || true)"
  resolved_sync_enabled="$(read_value "$metadata" RESOLVED_SYNC_ENABLED || true)"
  [[ "$container_proxy_enabled" == 0 || "$container_proxy_enabled" == 1 ]] || return 1
  [[ "$resolved_sync_enabled" == 0 || "$resolved_sync_enabled" == 1 ]] || return 1
  if [[ "$container_proxy_enabled" == 1 ]]; then
    [[ -f "$source/systemd/mihomo-container-proxy.socket" && -f "$source/systemd/mihomo-container-proxy.service" ]] || return 1
  fi
  if [[ "$resolved_sync_enabled" == 1 ]]; then
    [[ -f "$source/systemd/mihomo-resolved-sync.service" && -f "$source/usr-local-lib-lzc-mihomo/mihomo-resolved-sync.sh" ]] || return 1
  fi
}

write_pending() {
  local phase="$1" generation="$2" stage="$3" temporary
  temporary="$pending_transaction.tmp.$$"
  {
    printf 'PHASE=%s\n' "$phase"
    printf 'GENERATION=%s\n' "$generation"
    printf 'STAGE=%s\n' "$stage"
    printf 'UPDATED_AT=%s\n' "$(date -Iseconds)"
  } >"$temporary"
  chmod 600 "$temporary"
  mv -- "$temporary" "$pending_transaction"
}

clear_pending() {
  rm -f -- "$pending_transaction"
}

cleanup_stale_staging() {
  local active_stage=""
  if [[ -f "$pending_transaction" ]]; then
    active_stage="$(read_value "$pending_transaction" STAGE || true)"
  fi
  for candidate in "$bootstrap_root"/.restore-staging-* "$bootstrap_root"/.restore-staging.* \
    "$bootstrap_root"/.restore-live-* "$bootstrap_root"/.restore-live.*; do
    [[ -e "$candidate" || -L "$candidate" ]] || continue
    [[ "$candidate" == "$active_stage" ]] && continue
    rm -rf -- "$candidate"
  done
  # replace_directory stages live under /var/lib/mihomo because that is the
  # parent of the runtime directory.  They must not survive a SIGKILL into a
  # later generation application.
  for candidate in /var/lib/mihomo/.restore-live-* /var/lib/mihomo/.restore-live.* \
    /var/lib/mihomo/.restore-old-* /var/lib/mihomo/.restore-old.*; do
    [[ -e "$candidate" || -L "$candidate" ]] || continue
    rm -rf -- "$candidate"
  done
}

remove_bootstrap_stage() {
  local candidate="$1"
  case "$candidate" in
    "$bootstrap_root"/.restore-staging-*|"$bootstrap_root"/.restore-staging.*)
      [[ -e "$candidate" || -L "$candidate" ]] && rm -rf -- "$candidate"
      ;;
  esac
}

wait_for_bridge() {
  local deadline
  deadline=$((SECONDS + bridge_wait_seconds))

  while (( SECONDS < deadline )); do
    if ip -4 addr show | grep -q '172\.18\.0\.1/'; then
      return 0
    fi
    sleep 2
  done

  return 1
}

controller_health() {
  local secret="${CONTROLLER_SECRET:-}" response
  if [[ -z "$secret" && -f /etc/mihomo/config.yaml ]]; then
    secret="$(awk -F: '/^[[:space:]]*secret:/ {sub(/^[[:space:]]+/, "", $2); gsub(/[[:space:]]+$/, "", $2); print $2; exit}' /etc/mihomo/config.yaml)"
    secret="${secret#\"}"
    secret="${secret%\"}"
    secret="${secret#\'}"
    secret="${secret%\'}"
  fi
  if [[ -n "$secret" ]]; then
    response="$(curl --max-time 5 -fsS -H "Authorization: Bearer ${secret}" http://172.18.0.1:9090/version)"
  else
    response="$(curl --max-time 5 -fsS http://172.18.0.1:9090/version)"
  fi
  [[ "$response" == *'"version"'* ]]
}

verge_api_health() {
  curl --max-time 5 -fsS http://172.18.0.1:9091/healthz >/dev/null
}

wait_for_runtime_health() {
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if controller_health && verge_api_health; then
      return 0
    fi
    sleep 1
  done
  return 1
}

runtime_services_healthy() {
  systemctl is-active mihomo.service >/dev/null 2>&1 &&
    systemctl is-active mihomo-verge-api.service >/dev/null 2>&1 &&
    controller_health && verge_api_health
}

stop_runtime_services() {
  for service in mihomo-resolved-sync.service mihomo-container-proxy.service \
    mihomo-container-proxy.socket mihomo-verge-api.service mihomo.service; do
    systemctl stop "$service" >/dev/null 2>&1 || true
  done
}

install_optional_file() {
  local source="$1" destination="$2" owner="$3" group="$4" mode="$5"
  if [[ -f "$source" ]]; then
    install -o "$owner" -g "$group" -m "$mode" "$source" "$destination"
  else
    rm -f -- "$destination"
  fi
}

replace_directory() {
  local source="$1" destination="$2" temporary
  if [[ -d "$source" ]]; then
    temporary="$(mktemp -d "$(dirname "$destination")/.restore-live.XXXXXX")"
    rm -rf -- "$temporary"
    cp -a -- "$source" "$temporary"
    rm -rf -- "$destination"
    mv -- "$temporary" "$destination"
  else
    rm -rf -- "$destination"
  fi
}

start_container_proxy() {
  local socket_ok=0
  systemctl enable mihomo-container-proxy.socket >/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ! ip -4 addr show | grep -q '172\.18\.0\.1/'; then
      sleep 1
      continue
    fi
    systemctl reset-failed mihomo-container-proxy.socket >/dev/null 2>&1 || true
    systemctl start mihomo-container-proxy.socket >/dev/null
    if systemctl is-active mihomo-container-proxy.socket >/dev/null 2>&1 \
      && ss -lnt | grep -q '172\.18\.0\.1:17890'; then
      socket_ok=1
      break
    fi
    sleep 1
  done
  [[ "$socket_ok" == 1 ]] || {
    log "container proxy socket failed to reach steady state"
    return 1
  }
}

restart_live_runtime() {
  [[ -f /etc/mihomo/config.yaml && -f /etc/systemd/system/mihomo.service && \
    -f /etc/systemd/system/mihomo-verge-api.service ]] || return 1
  /usr/local/bin/mihomo -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml >/dev/null || return 1
  wait_for_bridge || return 1
  systemctl daemon-reload
  systemctl restart mihomo.service
  systemctl restart mihomo-verge-api.service
  systemctl is-active mihomo.service >/dev/null
  systemctl is-active mihomo-verge-api.service >/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if controller_health && verge_api_health; then
      break
    fi
    sleep 1
  done
  controller_health && verge_api_health || return 1
  if systemctl is-enabled mihomo-container-proxy.socket >/dev/null 2>&1; then
    start_container_proxy
  fi
  if systemctl is-enabled mihomo-resolved-sync.service >/dev/null 2>&1; then
    systemctl enable --now mihomo-resolved-sync.service >/dev/null
  fi
}

apply_generation() {
  local generation="$1" reason="$2" source metadata previous_stage=""
  if [[ -f "$pending_transaction" ]]; then
    previous_stage="$(read_value "$pending_transaction" STAGE || true)"
  fi
  validate_generation "$generation" || {
    log "generation validation failed: $generation"
    return 1
  }
  source="$(generation_path "$generation")"
  apply_stage="$(mktemp -d "$bootstrap_root/.restore-staging.XXXXXX")"
  cp -a -- "$source/." "$apply_stage/"
  (
    cd "$apply_stage"
    sha256sum -c manifest.sha256 >/dev/null
  )
  metadata="$apply_stage/metadata.env"
  # Read only the two validated flags; never source generation-controlled
  # shell text as root.
  CONTAINER_PROXY_ENABLED="$(read_value "$metadata" CONTAINER_PROXY_ENABLED)"
  RESOLVED_SYNC_ENABLED="$(read_value "$metadata" RESOLVED_SYNC_ENABLED)"
  write_pending prepared "$generation" "$apply_stage"
  if [[ -n "$previous_stage" && "$previous_stage" != "$apply_stage" ]]; then
    remove_bootstrap_stage "$previous_stage"
  fi
  stop_runtime_services
  write_pending applying "$generation" "$apply_stage"

  if ! id mihomo >/dev/null 2>&1; then
    useradd --system --home /var/lib/mihomo --shell /usr/sbin/nologin mihomo
  fi
  install -d -o root -g mihomo -m 750 /etc/mihomo
  install -d -o mihomo -g mihomo -m 750 /var/lib/mihomo
  install -d -m 755 /usr/local/lib/lzc-mihomo

  install_optional_file "$apply_stage/usr-local-bin/mihomo" /usr/local/bin/mihomo root root 755
  install_optional_file "$apply_stage/etc-mihomo/config.yaml" /etc/mihomo/config.yaml root mihomo 640
  install_optional_file "$apply_stage/etc-mihomo/verge-api.secret" /etc/mihomo/verge-api.secret root root 600
  install_optional_file "$apply_stage/systemd/mihomo.service" /etc/systemd/system/mihomo.service root root 644
  install_optional_file "$apply_stage/systemd/mihomo-verge-api.service" /etc/systemd/system/mihomo-verge-api.service root root 644
  install_optional_file "$apply_stage/usr-local-lib-lzc-mihomo/mihomo-verge-api.py" \
    /usr/local/lib/lzc-mihomo/mihomo-verge-api.py root root 755
  install_optional_file "$apply_stage/usr-local-lib-lzc-mihomo/runtime-contract.json" \
    /usr/local/lib/lzc-mihomo/runtime-contract.json root root 644
  install_optional_file "$apply_stage/usr-local-lib-lzc-mihomo/mihomo-resolved-sync.sh" \
    /usr/local/lib/lzc-mihomo/mihomo-resolved-sync.sh root root 755
  install_optional_file "$apply_stage/systemd/mihomo-container-proxy.socket" \
    /etc/systemd/system/mihomo-container-proxy.socket root root 644
  install_optional_file "$apply_stage/systemd/mihomo-container-proxy.service" \
    /etc/systemd/system/mihomo-container-proxy.service root root 644
  install_optional_file "$apply_stage/systemd/mihomo-resolved-sync.service" \
    /etc/systemd/system/mihomo-resolved-sync.service root root 644
  install_optional_file "$apply_stage/var-lib-mihomo/Country.mmdb" \
    /var/lib/mihomo/Country.mmdb mihomo mihomo 644
  replace_directory "$apply_stage/var-lib-mihomo/verge" /var/lib/mihomo/verge
  chown -R mihomo:mihomo /var/lib/mihomo

  /usr/local/bin/mihomo -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml >/dev/null
  wait_for_bridge || {
    log "container bridge address 172.18.0.1 did not appear within ${bridge_wait_seconds}s"
    return 1
  }
  systemctl daemon-reload
  systemctl enable mihomo.service >/dev/null
  systemctl restart mihomo.service
  systemctl enable mihomo-verge-api.service >/dev/null
  systemctl restart mihomo-verge-api.service

  if [[ "$CONTAINER_PROXY_ENABLED" == 1 && -f /etc/systemd/system/mihomo-container-proxy.socket ]]; then
    start_container_proxy
  else
    systemctl disable --now mihomo-container-proxy.socket >/dev/null 2>&1 || true
    systemctl disable --now mihomo-container-proxy.service >/dev/null 2>&1 || true
  fi
  if [[ "$RESOLVED_SYNC_ENABLED" == 1 && -f /etc/systemd/system/mihomo-resolved-sync.service ]]; then
    systemctl enable --now mihomo-resolved-sync.service >/dev/null
  else
    systemctl disable --now mihomo-resolved-sync.service >/dev/null 2>&1 || true
  fi
  systemctl is-active mihomo.service >/dev/null
  systemctl is-active mihomo-verge-api.service >/dev/null
  wait_for_runtime_health
  if [[ "$CONTAINER_PROXY_ENABLED" == 1 ]]; then
    systemctl is-active mihomo-container-proxy.socket >/dev/null
  fi

  printf '%s\n' "$generation" >"$applied_generation_file.tmp.$$"
  chmod 600 "$applied_generation_file.tmp.$$"
  mv -- "$applied_generation_file.tmp.$$" "$applied_generation_file"
  clear_pending
  log "bootstrap generation applied: generation=$generation reason=$reason mihomo=$(systemctl is-active mihomo.service) verge-api=$(systemctl is-active mihomo-verge-api.service)"
}

mkdir -p "$state_dir" "$generations_root"
cleanup_stale_staging
current_generation="$(tr -d '\r\n' <"$current_generation_file" 2>/dev/null || true)"
pending_generation=""
if [[ -f "$pending_transaction" ]]; then
  pending_generation="$(read_value "$pending_transaction" GENERATION || true)"
fi
if [[ -n "$pending_generation" ]]; then
  log "reconciling pending bootstrap generation: $pending_generation"
  apply_generation "$pending_generation" startup-reconcile
else
  [[ -n "$current_generation" ]] || { log "current bootstrap generation is missing"; exit 1; }
  applied_generation="$(tr -d '\r\n' <"$applied_generation_file" 2>/dev/null || true)"
  # A successful bootstrap must not overwrite a configuration changed after
  # the snapshot was captured.  Restart the live files first; only fall back
  # to the immutable generation when they are absent or invalid.
  if restart_live_runtime; then
    printf '%s\n' "$current_generation" >"$applied_generation_file.tmp.$$"
    chmod 600 "$applied_generation_file.tmp.$$"
    mv -- "$applied_generation_file.tmp.$$" "$applied_generation_file"
    log "bootstrap preserved live runtime files after restart: $current_generation"
  else
    apply_generation "$current_generation" startup-reconcile
  fi
fi
SCRIPT
chmod 700 "$REMOTE_BOOTSTRAP_SCRIPT"

install -d -m 755 "$REMOTE_USER_UNIT_DIR" "$wants_dir"

cat >"$unit_path" <<UNIT
[Unit]
Description=LazyCat Mihomo Host-Native Bootstrap
Wants=network-online.target
After=default.target network-online.target
StartLimitIntervalSec=0

[Service]
Type=oneshot
Environment=BRIDGE_WAIT_SECONDS=$BRIDGE_WAIT_SECONDS
ExecStart=$REMOTE_BOOTSTRAP_SCRIPT
RemainAfterExit=yes
Restart=on-failure
RestartSec=15s

[Install]
WantedBy=default.target
UNIT

chmod 644 "$unit_path"

log "Enabling linger + root user-systemd bootstrap service"
loginctl enable-linger root >/dev/null
systemctl start user@0.service >/dev/null 2>&1 || true
export XDG_RUNTIME_DIR=/run/user/0
systemctl --user daemon-reload
systemctl --user enable "$REMOTE_BOOTSTRAP_SERVICE" >/dev/null
systemctl --user restart "$REMOTE_BOOTSTRAP_SERVICE"

log "Bootstrap service enabled:"
systemctl --user status "$REMOTE_BOOTSTRAP_SERVICE" --no-pager -l | sed -n '1,120p'

log "Bootstrap log tail:"
tail -n 40 "$REMOTE_BOOTSTRAP_LOG" 2>/dev/null || true
REMOTE

echo "OK: installed host-native bootstrap on $HOST" >&2
