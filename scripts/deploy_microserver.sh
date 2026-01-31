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
if ! grep -q '^external-controller: 172\.18\.0\.1:9090$' "$CFG_LOCAL"; then
  echo "ERROR: $CFG_LOCAL must contain: external-controller: 172.18.0.1:9090" >&2
  echo "(LazyCat ingress reaches host via host.lzcapp -> 172.18.0.1)" >&2
  exit 1
fi

TS="$(date +%Y%m%d-%H%M%S)"
TMP_CFG="/tmp/mihomo.config.$TS.yaml"
TMP_UNIT="/tmp/mihomo.service.$TS"

echo "Deploying to $SSH_USER@$HOST ..."

scp -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  "$CFG_LOCAL" "$SSH_USER@$HOST:$TMP_CFG" >/dev/null

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
ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" bash -lc "
set -euo pipefail

cfg=/etc/mihomo/config.yaml
unit=/etc/systemd/system/mihomo.service

bak_cfg=\"${cfg}.bak.$TS\"
bak_unit=\"${unit}.bak.$TS\"

# Backups
if [[ -f \"$cfg\" ]]; then cp -a \"$cfg\" \"$bak_cfg\"; fi
if [[ -f \"$unit\" ]]; then cp -a \"$unit\" \"$bak_unit\"; fi

# Ensure directories exist
id mihomo >/dev/null 2>&1 || useradd --system --home /var/lib/mihomo --shell /usr/sbin/nologin mihomo
install -d -o root -g mihomo -m 750 /etc/mihomo
install -d -o mihomo -g mihomo -m 750 /var/lib/mihomo

# Install config + unit
install -o root -g mihomo -m 640 \"$TMP_CFG\" \"$cfg\"
install -o root -g root -m 644 \"$TMP_UNIT\" \"$unit\"
rm -f \"$TMP_CFG\" \"$TMP_UNIT\"

# Optional mmdb
if [[ -f /tmp/Country.mmdb.$TS ]]; then
  install -o mihomo -g mihomo -m 644 /tmp/Country.mmdb.$TS /var/lib/mihomo/Country.mmdb
  rm -f /tmp/Country.mmdb.$TS
fi

# Validate config
/usr/local/bin/mihomo -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml >/dev/null

systemctl daemon-reload
systemctl enable mihomo >/dev/null
systemctl restart mihomo
sleep 2
systemctl is-active mihomo >/dev/null

echo \"OK: mihomo restarted. backups: $bak_cfg $bak_unit\"
"

echo "Done." 
