#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export MICROSERVER_HOST="${MICROSERVER_HOST:-rainierdev.heiyu.space}"

exec "$ROOT/scripts/install_host_native_bootstrap.sh" "$@"
