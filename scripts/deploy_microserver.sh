#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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

CFG_LOCAL="${MIHOMO_CONFIG_LOCAL:-$ROOT/var/private/mihomo.config.yaml}"
UNIT_LOCAL="$ROOT/infra/mihomo/mihomo.service"
MMDB_LOCAL="${MIHOMO_COUNTRY_MMDB_LOCAL:-$ROOT/var/private/Country.mmdb}"
SECRET_LOCAL_FILE="${MIHOMO_SECRET_FILE_LOCAL:-$ROOT/var/private/mihomo.secret}"
TUN_ENABLE="${MIHOMO_TUN_ENABLE:-1}" # 1=enabled (default), 0=disabled

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
if ! grep -Eq '^[[:space:]]*external-controller:[[:space:]]*172\\.18\\.0\\.1:9090[[:space:]]*$' "$CFG_LOCAL"; then
  echo "ERROR: $CFG_LOCAL must contain: external-controller: 172.18.0.1:9090" >&2
  echo "(LazyCat ingress reaches host via host.lzcapp -> 172.18.0.1)" >&2
  exit 1
fi

TS="$(date +%Y%m%d-%H%M%S)"
TMPDIR_LOCAL="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR_LOCAL"; }
trap cleanup EXIT

PATCHED_CFG_LOCAL="$TMPDIR_LOCAL/mihomo.config.patched.$TS.yaml"
SECRET_OUT_LOCAL="$TMPDIR_LOCAL/mihomo.secret.$TS"

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

TMP_CFG="/tmp/mihomo.config.$TS.yaml"
TMP_UNIT="/tmp/mihomo.service.$TS"

echo "Deploying to $SSH_USER@$HOST ..."

# Compute mihomo download URL for the remote architecture (best-effort).
REMOTE_UNAME="$(ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" uname -m)"
MIHOMO_TAG="${MIHOMO_VERSION:-}"
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

echo "Applying on microserver ..."
ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  "$SSH_USER@$HOST" TS="$TS" TMP_CFG="$TMP_CFG" TMP_UNIT="$TMP_UNIT" MIHOMO_URL="$MIHOMO_URL" MMDB_URL="$MMDB_URL" bash -s <<'REMOTE'
set -euo pipefail

cfg=/etc/mihomo/config.yaml
unit=/etc/systemd/system/mihomo.service
mihomo_bin=/usr/local/bin/mihomo

command -v curl >/dev/null 2>&1 || { echo "ERROR: curl not found on microserver" >&2; exit 1; }
command -v gzip >/dev/null 2>&1 || { echo "ERROR: gzip not found on microserver" >&2; exit 1; }

bak_cfg="${cfg}.bak.${TS}"
bak_unit="${unit}.bak.${TS}"

# Install mihomo binary if missing.
if [[ ! -x "$mihomo_bin" ]]; then
  echo "Installing mihomo from: $MIHOMO_URL" >&2
  tmp_gz="/tmp/mihomo.${TS}.gz"
  tmp_bin="/tmp/mihomo.${TS}"
  curl -fsSL "$MIHOMO_URL" -o "$tmp_gz"
  gzip -d -c "$tmp_gz" >"$tmp_bin"
  install -o root -g root -m 755 "$tmp_bin" "$mihomo_bin"
  rm -f "$tmp_gz" "$tmp_bin"
fi

# Backups
if [[ -f "$cfg" ]]; then cp -a "$cfg" "$bak_cfg"; fi
if [[ -f "$unit" ]]; then cp -a "$unit" "$bak_unit"; fi

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
  echo "Downloading Country.mmdb from: $MMDB_URL" >&2
  tmp_mmdb="/tmp/Country.mmdb.${TS}"
  curl -fsSL "$MMDB_URL" -o "$tmp_mmdb"
  install -o mihomo -g mihomo -m 644 "$tmp_mmdb" /var/lib/mihomo/Country.mmdb
  rm -f "$tmp_mmdb"
fi

# Validate config
"$mihomo_bin" -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml >/dev/null

systemctl daemon-reload
systemctl enable mihomo >/dev/null
systemctl restart mihomo
sleep 2
systemctl is-active mihomo >/dev/null

echo "OK: mihomo restarted. backups: $bak_cfg $bak_unit"
REMOTE

echo "Done."
