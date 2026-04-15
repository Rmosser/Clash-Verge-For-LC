#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

HOST="${MICROSERVER_HOST:-rainierdev.heiyu.space}"
SSH_USER="${MICROSERVER_SSH_USER:-root}"
SSH_KEY="${MICROSERVER_SSH_KEY:-$HOME/.ssh/id_ed25519}"
REMOTE_BOOTSTRAP_ROOT="${MIHOMO_BOOTSTRAP_REMOTE_ROOT:-/root/.config/lzc-mihomo-bootstrap}"
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
  MIHOMO_BOOTSTRAP_REMOTE_ROOT     defaults to /root/.config/lzc-mihomo-bootstrap
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

case "$HOST" in
  rainierdev.heiyu.space|*.rainierdev.heiyu.space|rainierspace.heiyu.space|*.rainierspace.heiyu.space)
    ;;
  *)
    echo "ERROR: this installer only supports rainierdev.* or rainierspace.*" >&2
    echo "Refusing to run against host: $HOST" >&2
    exit 1
    ;;
esac

ssh_remote() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" "$@"
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

ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  "$SSH_USER@$HOST" \
  REMOTE_BOOTSTRAP_ROOT="$REMOTE_BOOTSTRAP_ROOT" \
  REMOTE_USER_UNIT_DIR="$REMOTE_USER_UNIT_DIR" \
  REMOTE_BOOTSTRAP_SERVICE="$REMOTE_BOOTSTRAP_SERVICE" \
  REMOTE_BOOTSTRAP_SCRIPT="$REMOTE_BOOTSTRAP_SCRIPT" \
  REMOTE_BOOTSTRAP_LOG="$REMOTE_BOOTSTRAP_LOG" \
  bash -s <<'REMOTE'
set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date -Iseconds)" "$1"
}

snapshot_root="$REMOTE_BOOTSTRAP_ROOT/snapshot"
unit_path="$REMOTE_USER_UNIT_DIR/$REMOTE_BOOTSTRAP_SERVICE"
wants_dir="$REMOTE_USER_UNIT_DIR/default.target.wants"
state_file="$REMOTE_BOOTSTRAP_ROOT/bootstrap-state.env"

log "Preparing bootstrap snapshot under $REMOTE_BOOTSTRAP_ROOT"

install -d -m 700 "$REMOTE_BOOTSTRAP_ROOT"
rm -rf "$snapshot_root"
install -d -m 700 \
  "$snapshot_root/usr-local-bin" \
  "$snapshot_root/etc-mihomo" \
  "$snapshot_root/var-lib-mihomo" \
  "$snapshot_root/systemd" \
  "$snapshot_root/usr-local-lib-lzc-mihomo"

install -m 755 /usr/local/bin/mihomo "$snapshot_root/usr-local-bin/mihomo"
install -m 640 /etc/mihomo/config.yaml "$snapshot_root/etc-mihomo/config.yaml"
install -m 600 /etc/mihomo/verge-api.secret "$snapshot_root/etc-mihomo/verge-api.secret"
install -m 644 /etc/systemd/system/mihomo.service "$snapshot_root/systemd/mihomo.service"
install -m 644 /etc/systemd/system/mihomo-verge-api.service "$snapshot_root/systemd/mihomo-verge-api.service"
install -m 755 /usr/local/lib/lzc-mihomo/mihomo-verge-api.py \
  "$snapshot_root/usr-local-lib-lzc-mihomo/mihomo-verge-api.py"
install -m 644 /usr/local/lib/lzc-mihomo/runtime-contract.json \
  "$snapshot_root/usr-local-lib-lzc-mihomo/runtime-contract.json"

if [[ -f /etc/systemd/system/mihomo-container-proxy.socket ]]; then
  install -m 644 /etc/systemd/system/mihomo-container-proxy.socket \
    "$snapshot_root/systemd/mihomo-container-proxy.socket"
fi

if [[ -f /etc/systemd/system/mihomo-container-proxy.service ]]; then
  install -m 644 /etc/systemd/system/mihomo-container-proxy.service \
    "$snapshot_root/systemd/mihomo-container-proxy.service"
fi

if [[ -f /etc/systemd/system/mihomo-resolved-sync.service ]]; then
  install -m 644 /etc/systemd/system/mihomo-resolved-sync.service \
    "$snapshot_root/systemd/mihomo-resolved-sync.service"
fi

if [[ -f /usr/local/lib/lzc-mihomo/mihomo-resolved-sync.sh ]]; then
  install -m 755 /usr/local/lib/lzc-mihomo/mihomo-resolved-sync.sh \
    "$snapshot_root/usr-local-lib-lzc-mihomo/mihomo-resolved-sync.sh"
fi

if [[ -f /var/lib/mihomo/Country.mmdb ]]; then
  install -m 644 /var/lib/mihomo/Country.mmdb "$snapshot_root/var-lib-mihomo/Country.mmdb"
fi

if [[ -d /var/lib/mihomo/verge ]]; then
  rm -rf "$snapshot_root/var-lib-mihomo/verge"
  cp -a /var/lib/mihomo/verge "$snapshot_root/var-lib-mihomo/verge"
fi

container_proxy_enabled=0
resolved_sync_enabled=0

if systemctl is-enabled mihomo-container-proxy.socket >/dev/null 2>&1; then
  container_proxy_enabled=1
fi

if systemctl is-enabled mihomo-resolved-sync.service >/dev/null 2>&1; then
  resolved_sync_enabled=1
fi

cat >"$state_file" <<STATE
CONTAINER_PROXY_ENABLED=$container_proxy_enabled
RESOLVED_SYNC_ENABLED=$resolved_sync_enabled
STATE
chmod 600 "$state_file"

cat >"$REMOTE_BOOTSTRAP_SCRIPT" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

bootstrap_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
snapshot_root="$bootstrap_root/snapshot"
state_file="$bootstrap_root/bootstrap-state.env"
log_file="$bootstrap_root/bootstrap.log"

log() {
  printf '[%s] %s\n' "$(date -Iseconds)" "$1" | tee -a "$log_file" >&2
}

if [[ ! -d "$snapshot_root" ]]; then
  log "snapshot missing: $snapshot_root"
  exit 1
fi

container_proxy_enabled=0
resolved_sync_enabled=0
if [[ -f "$state_file" ]]; then
  # shellcheck disable=SC1090
  . "$state_file"
  container_proxy_enabled="${CONTAINER_PROXY_ENABLED:-$container_proxy_enabled}"
  resolved_sync_enabled="${RESOLVED_SYNC_ENABLED:-$resolved_sync_enabled}"
fi

if ! id mihomo >/dev/null 2>&1; then
  useradd --system --home /var/lib/mihomo --shell /usr/sbin/nologin mihomo
fi

install -d -o root -g mihomo -m 750 /etc/mihomo
install -d -o mihomo -g mihomo -m 750 /var/lib/mihomo
install -d -m 755 /usr/local/lib/lzc-mihomo

install -o root -g root -m 755 \
  "$snapshot_root/usr-local-bin/mihomo" /usr/local/bin/mihomo
install -o root -g mihomo -m 640 \
  "$snapshot_root/etc-mihomo/config.yaml" /etc/mihomo/config.yaml
install -o root -g root -m 600 \
  "$snapshot_root/etc-mihomo/verge-api.secret" /etc/mihomo/verge-api.secret
install -o root -g root -m 644 \
  "$snapshot_root/systemd/mihomo.service" /etc/systemd/system/mihomo.service
install -o root -g root -m 644 \
  "$snapshot_root/systemd/mihomo-verge-api.service" /etc/systemd/system/mihomo-verge-api.service
install -o root -g root -m 755 \
  "$snapshot_root/usr-local-lib-lzc-mihomo/mihomo-verge-api.py" \
  /usr/local/lib/lzc-mihomo/mihomo-verge-api.py
install -o root -g root -m 644 \
  "$snapshot_root/usr-local-lib-lzc-mihomo/runtime-contract.json" \
  /usr/local/lib/lzc-mihomo/runtime-contract.json

if [[ -f "$snapshot_root/systemd/mihomo-container-proxy.socket" ]]; then
  install -o root -g root -m 644 \
    "$snapshot_root/systemd/mihomo-container-proxy.socket" \
    /etc/systemd/system/mihomo-container-proxy.socket
fi

if [[ -f "$snapshot_root/systemd/mihomo-container-proxy.service" ]]; then
  install -o root -g root -m 644 \
    "$snapshot_root/systemd/mihomo-container-proxy.service" \
    /etc/systemd/system/mihomo-container-proxy.service
fi

if [[ -f "$snapshot_root/systemd/mihomo-resolved-sync.service" ]]; then
  install -o root -g root -m 644 \
    "$snapshot_root/systemd/mihomo-resolved-sync.service" \
    /etc/systemd/system/mihomo-resolved-sync.service
fi

if [[ -f "$snapshot_root/usr-local-lib-lzc-mihomo/mihomo-resolved-sync.sh" ]]; then
  install -o root -g root -m 755 \
    "$snapshot_root/usr-local-lib-lzc-mihomo/mihomo-resolved-sync.sh" \
    /usr/local/lib/lzc-mihomo/mihomo-resolved-sync.sh
fi

if [[ -f "$snapshot_root/var-lib-mihomo/Country.mmdb" ]]; then
  install -o mihomo -g mihomo -m 644 \
    "$snapshot_root/var-lib-mihomo/Country.mmdb" /var/lib/mihomo/Country.mmdb
fi

if [[ -d "$snapshot_root/var-lib-mihomo/verge" ]]; then
  rm -rf /var/lib/mihomo/verge
  cp -a "$snapshot_root/var-lib-mihomo/verge" /var/lib/mihomo/verge
fi

chown -R mihomo:mihomo /var/lib/mihomo

/usr/local/bin/mihomo -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml >/dev/null

bridge_ready=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if ip -4 addr show | grep -q '172\.18\.0\.1/'; then
    bridge_ready=1
    break
  fi
  sleep 1
done
if [[ "$bridge_ready" != "1" ]]; then
  log "container bridge address 172.18.0.1 did not appear in time"
  exit 1
fi

systemctl daemon-reload
systemctl enable mihomo.service >/dev/null
systemctl restart mihomo.service
systemctl enable mihomo-verge-api.service >/dev/null
systemctl restart mihomo-verge-api.service

if [[ "$container_proxy_enabled" == "1" && -f /etc/systemd/system/mihomo-container-proxy.socket ]]; then
  systemctl enable mihomo-container-proxy.socket >/dev/null
  socket_ok=0
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ! ip -4 addr show | grep -q '172\.18\.0\.1/'; then
      sleep 1
      continue
    fi
    systemctl reset-failed mihomo-container-proxy.socket >/dev/null 2>&1 || true
    systemctl stop mihomo-container-proxy.socket >/dev/null 2>&1 || true
    systemctl start mihomo-container-proxy.socket >/dev/null
    if systemctl is-active mihomo-container-proxy.socket >/dev/null 2>&1 \
      && ss -lnt | grep -q '172\.18\.0\.1:17890'; then
      socket_ok=1
      break
    fi
    sleep 1
  done
  if [[ "$socket_ok" != "1" ]]; then
    log "container proxy socket failed to reach steady state"
    exit 1
  fi
fi

if [[ "$resolved_sync_enabled" == "1" && -f /etc/systemd/system/mihomo-resolved-sync.service ]]; then
  systemctl enable --now mihomo-resolved-sync.service >/dev/null
fi

systemctl is-active mihomo.service >/dev/null
systemctl is-active mihomo-verge-api.service >/dev/null
if [[ "$container_proxy_enabled" == "1" && -f /etc/systemd/system/mihomo-container-proxy.socket ]]; then
  systemctl is-active mihomo-container-proxy.socket >/dev/null
fi

log "bootstrap applied: mihomo=$(systemctl is-active mihomo.service) verge-api=$(systemctl is-active mihomo-verge-api.service)"
SCRIPT
chmod 700 "$REMOTE_BOOTSTRAP_SCRIPT"

install -d -m 755 "$REMOTE_USER_UNIT_DIR" "$wants_dir"

cat >"$unit_path" <<UNIT
[Unit]
Description=LazyCat Mihomo Host-Native Bootstrap
After=default.target

[Service]
Type=oneshot
ExecStart=$REMOTE_BOOTSTRAP_SCRIPT
RemainAfterExit=yes

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
