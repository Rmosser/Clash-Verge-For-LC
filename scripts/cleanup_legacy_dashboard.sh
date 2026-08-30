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
LAZYCAT_BOX="${LAZYCAT_BOX:-}"
LEGACY_APP_ID="cloud.lazycat.app.mihomo-dashboard"

if [[ "${1:-}" != "--execute" ]]; then
  echo "One-time cleanup for legacy app ID: $LEGACY_APP_ID"
  echo "Target: $SSH_USER@$HOST"
  echo "LazyCat box: ${LAZYCAT_BOX:-not set (required for --execute)}"
  echo "No changes made. Re-run with --execute after reviewing the exact target."
  exit 0
fi
if [[ $# -ne 1 ]]; then
  echo "ERROR: usage: scripts/cleanup_legacy_dashboard.sh [--execute]" >&2
  exit 2
fi

if [[ -z "$LAZYCAT_BOX" ]]; then
  echo "ERROR: LAZYCAT_BOX is required to bind lzc-cli to the reviewed target" >&2
  exit 2
fi
current_box="$(lzc-cli box default)"
if [[ "$current_box" != "$LAZYCAT_BOX" ]]; then
  echo "ERROR: lzc-cli default box '$current_box' does not match reviewed LAZYCAT_BOX '$LAZYCAT_BOX'" >&2
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
import os
import stat
from pathlib import Path

marker = sys.argv[1].encode("utf-8")
root = Path("/lzcsys/data/system/pkgm/deploy.db")

try:
    root_mode = root.lstat().st_mode
except OSError as exc:
    raise RuntimeError(f"cannot inspect deployment-record root {root}: {exc}") from exc
if not stat.S_ISDIR(root_mode):
    raise RuntimeError(f"deployment-record root is not a directory: {root}")


def fail_walk(exc: OSError) -> None:
    raise RuntimeError(f"cannot traverse deployment records: {exc}") from exc


def record_files():
    for directory, directories, filenames in os.walk(
        root, topdown=True, onerror=fail_walk, followlinks=False
    ):
        for child in directories:
            path = Path(directory) / child
            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                raise RuntimeError(f"cannot stat deployment-record directory {path}: {exc}") from exc
            if not stat.S_ISDIR(mode):
                raise RuntimeError(f"unexpected non-directory deployment-record entry: {path}")
        for filename in filenames:
            path = Path(directory) / filename
            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                raise RuntimeError(f"cannot stat deployment record {path}: {exc}") from exc
            if not stat.S_ISREG(mode):
                raise RuntimeError(f"unexpected non-regular deployment record: {path}")
            yield path


for path in record_files():
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"cannot read deployment record {path}: {exc}") from exc
    if marker in payload:
        path.unlink()

for path in record_files():
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"cannot verify deployment record {path}: {exc}") from exc
    if marker in payload:
        raise RuntimeError(f"legacy deployment record still exists: {path}")
PY

for path in "${legacy_paths[@]}"; do
  if [[ -e "$path" ]]; then
    echo "ERROR: legacy path still exists: $path" >&2
    exit 1
  fi
done

echo "Legacy dashboard cleanup complete: $legacy_app_id"
REMOTE
