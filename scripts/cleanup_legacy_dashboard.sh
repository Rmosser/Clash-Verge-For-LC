#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=/dev/null
. "$ROOT/scripts/_lib_paths.sh"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

HOST="${MICROSERVER_HOST:-rainierserver.heiyu.space}"
SSH_USER="${MICROSERVER_SSH_USER:-root}"
SSH_KEY="${MICROSERVER_SSH_KEY:-$HOME/.ssh/id_ed25519}"
LEGACY_APP_ID="cloud.lazycat.app.mihomo-dashboard"

if [[ "${1:-}" != "--execute" ]]; then
  echo "One-time cleanup for legacy app ID: $LEGACY_APP_ID"
  echo "Target: $SSH_USER@$HOST"
  echo "No changes made. Re-run with --execute after reviewing the exact target."
  exit 0
fi
if [[ $# -ne 1 ]]; then
  echo "ERROR: usage: scripts/cleanup_legacy_dashboard.sh [--execute]" >&2
  exit 2
fi

lzc-cli app uninstall "$LEGACY_APP_ID" >/dev/null 2>&1 || true

ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST" \
  bash -s -- "$LEGACY_APP_ID" <<'REMOTE'
set -euo pipefail

legacy_app_id="$1"
legacy_paths=(
  "/lzcsys/data/system/pkgm/apps/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/run/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/deploy.var/${legacy_app_id}"
  "/lzcsys/data/system/pkgm/lpks/${legacy_app_id}.lpk"
  "/lzcsys/data/appcache/${legacy_app_id}"
  "/lzcsys/data/appvar/${legacy_app_id}"
  "/lzcsys/run/app/${legacy_app_id}"
)

for path in "${legacy_paths[@]}"; do
  rm -rf -- "$path"
done

python3 - <<'PY' "$legacy_app_id"
import sys
from pathlib import Path

marker = sys.argv[1].encode("utf-8")
root = Path("/lzcsys/data/system/pkgm/deploy.db")
for path in root.rglob("*"):
    if not path.is_file():
        continue
    try:
        payload = path.read_bytes()
    except OSError:
        continue
    if marker in payload:
        path.unlink()
PY

for path in "${legacy_paths[@]}"; do
  if [[ -e "$path" ]]; then
    echo "ERROR: legacy path still exists: $path" >&2
    exit 1
  fi
done

if grep -RIl --fixed-strings "$legacy_app_id" /lzcsys/data/system/pkgm/deploy.db 2>/dev/null | grep -q .; then
  echo "ERROR: legacy deployment record still exists" >&2
  exit 1
fi

echo "Legacy dashboard cleanup complete: $legacy_app_id"
REMOTE
