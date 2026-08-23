#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> repository lint"
bash "$ROOT/scripts/lint.sh"

echo "==> microservice unit tests"
python3 -m unittest -v "$ROOT/infra/microserver/test_mihomo_verge_api.py"
