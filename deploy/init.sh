#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CFG="$DIR/config.yaml"
CFG_EXAMPLE="$DIR/config.yaml.example"
SECRET_FILE="$DIR/secret.txt"

TUN_ENABLE="${MIHOMO_TUN_ENABLE:-1}" # 1=enabled (default), 0=disabled

if [[ ! -f "$CFG" ]]; then
  cp "$CFG_EXAMPLE" "$CFG"
  echo "Created: $CFG" >&2
fi

if ! grep -Eq '^[[:space:]]*external-controller:[[:space:]]*172\\.18\\.0\\.1:9090[[:space:]]*$' "$CFG"; then
  echo "ERROR: $CFG must contain: external-controller: 172.18.0.1:9090" >&2
  echo "(LazyCat ingress reaches host via host.lzcapp -> 172.18.0.1)" >&2
  exit 1
fi

if grep -Eq "^[[:space:]]*secret:[[:space:]]*(''|\"\"|null)?[[:space:]]*$" "$CFG"; then
  secret="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
  sed -i.bak -E "s|^[[:space:]]*secret:.*$|secret: '${secret}'|g" "$CFG"
  printf '%s\n' "$secret" >"$SECRET_FILE"
  chmod 600 "$SECRET_FILE" 2>/dev/null || true
  echo "Generated MIHOMO_SECRET and saved to: $SECRET_FILE" >&2
fi

if [[ "$TUN_ENABLE" == "0" ]]; then
  # Disable TUN explicitly.
  if grep -Eq "^[[:space:]]*tun:[[:space:]]*$" "$CFG"; then
    if grep -Eq "^[[:space:]]{2}enable:[[:space:]]*true[[:space:]]*$" "$CFG"; then
      sed -i.bak -E "s|^[[:space:]]{2}enable:[[:space:]]*true[[:space:]]*$|  enable: false|g" "$CFG"
      echo "Set tun.enable=false in $CFG" >&2
    fi
  fi
fi

mkdir -p "$DIR/data"
echo "OK: init complete (config=$CFG)" >&2

