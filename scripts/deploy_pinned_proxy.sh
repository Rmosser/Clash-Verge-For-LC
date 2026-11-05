#!/usr/bin/env bash
set -Eeuo pipefail

# Installs (or removes) only the pinned container proxy socket/service pair on the reviewed hosts.
# It never reads .env, the Mihomo config, subscriptions, nodes or secrets, and never restarts Mihomo:
# the listener it forwards to (127.0.0.1:7896) comes from the Verge API overlay key lzc-pinned-listeners.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
HOST="${MICROSERVER_HOST:-rainierdev.heiyu.space}"
readonly TARGET_HOST="$HOST"
SSH_USER="${MICROSERVER_SSH_USER:-root}"
SSH_KEY="${MICROSERVER_SSH_KEY:-$HOME/.ssh/id_ed25519}"

SOCKET_LOCAL="$ROOT/infra/microserver/mihomo-container-proxy-pinned.socket"
SERVICE_LOCAL="$ROOT/infra/microserver/mihomo-container-proxy-pinned.service"

ACTION="install"
CONFIRM_APPLY=0

usage() {
  cat <<'USAGE'
Usage: scripts/deploy_pinned_proxy.sh [--remove] --confirm

Installs and starts mihomo-container-proxy-pinned.{socket,service} (app bridges :17896 -> 127.0.0.1:7896)
on rainierdev or rainierspace; --remove disables and deletes them. Re-run
install_host_native_bootstrap.sh --confirm afterwards so the boot generation captures the change.

Environment overrides:
  MICROSERVER_HOST       rainierdev.heiyu.space or rainierspace.heiyu.space
  MICROSERVER_SSH_USER   defaults to root
  MICROSERVER_SSH_KEY    defaults to ~/.ssh/id_ed25519
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remove) ACTION="remove"; shift ;;
    --confirm) CONFIRM_APPLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$HOST" == "rainierdev.heiyu.space" || "$HOST" == "rainierspace.heiyu.space" ]] || {
  echo "ERROR: refusing unreviewed target: $HOST" >&2
  exit 1
}
[[ "$SSH_USER" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]] || { echo "ERROR: invalid SSH user" >&2; exit 1; }
[[ -f "$SOCKET_LOCAL" && -f "$SERVICE_LOCAL" ]] || { echo "ERROR: missing pinned proxy unit files" >&2; exit 1; }

source "$ROOT/scripts/_lib_deploy_settings.sh"
MIHOMO_APPROVED_HOST="$TARGET_HOST"
mihomo_require_apply_confirmation "$HOST" "$SSH_USER" "$CONFIRM_APPLY" "deploy_pinned_proxy"

ssh_args=(
  -i "$SSH_KEY"
  -o BatchMode=yes
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="${MIHOMO_KNOWN_HOSTS_FILE:?target identity was not prepared}"
)

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$BASHPID"
REMOTE_TMP_ROOT="/tmp/mihomo-pinned-proxy-$RUN_ID"
cleanup_remote_tmp() {
  # REMOTE_TMP_ROOT is generated locally from a fixed prefix, UTC digits, and BASHPID.
  # shellcheck disable=SC2029
  ssh "${ssh_args[@]}" "$SSH_USER@$HOST" "rm -rf -- '$REMOTE_TMP_ROOT'" >/dev/null 2>&1 || true
}
trap cleanup_remote_tmp EXIT

if [[ "$ACTION" == "install" ]]; then
  # shellcheck disable=SC2029
  ssh "${ssh_args[@]}" "$SSH_USER@$HOST" "install -d -m 700 '$REMOTE_TMP_ROOT'"
  scp "${ssh_args[@]}" "$SOCKET_LOCAL" "$SSH_USER@$HOST:$REMOTE_TMP_ROOT/socket" >/dev/null
  scp "${ssh_args[@]}" "$SERVICE_LOCAL" "$SSH_USER@$HOST:$REMOTE_TMP_ROOT/service" >/dev/null
fi

ssh "${ssh_args[@]}" "$SSH_USER@$HOST" ACTION="$ACTION" REMOTE_TMP_ROOT="$REMOTE_TMP_ROOT" bash -s <<'REMOTE'
set -Eeuo pipefail
socket_unit=/etc/systemd/system/mihomo-container-proxy-pinned.socket
service_unit=/etc/systemd/system/mihomo-container-proxy-pinned.service

if [[ "$ACTION" == "remove" ]]; then
  systemctl disable --now mihomo-container-proxy-pinned.socket >/dev/null 2>&1 || true
  systemctl stop mihomo-container-proxy-pinned.service >/dev/null 2>&1 || true
  rm -f -- "$socket_unit" "$service_unit"
  systemctl daemon-reload
  echo "pinned container proxy removed"
  exit 0
fi

[[ -x /lib/systemd/systemd-socket-proxyd ]] || { echo "ERROR: systemd-socket-proxyd is missing" >&2; exit 1; }
install -o root -g root -m 644 "$REMOTE_TMP_ROOT/socket" "$socket_unit"
install -o root -g root -m 644 "$REMOTE_TMP_ROOT/service" "$service_unit"
systemctl daemon-reload
systemctl enable mihomo-container-proxy-pinned.socket >/dev/null
systemctl reset-failed mihomo-container-proxy-pinned.socket >/dev/null 2>&1 || true
systemctl restart mihomo-container-proxy-pinned.socket
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if systemctl is-active mihomo-container-proxy-pinned.socket >/dev/null 2>&1 &&
     ss -lnt | grep -q '172\.18\.0\.1:17896'; then
    echo "pinned container proxy listening on 172.18.0.1:17896"
    exit 0
  fi
  sleep 1
done
echo "ERROR: mihomo-container-proxy-pinned.socket did not reach steady state" >&2
exit 1
REMOTE
