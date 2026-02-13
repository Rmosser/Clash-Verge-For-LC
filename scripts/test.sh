#!/usr/bin/env bash
set -euo pipefail

# This project doesn't have a test suite; keep a stable entrypoint for agents.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lint.sh" "$@"

