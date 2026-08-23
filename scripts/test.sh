#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> repository lint"
bash scripts/lint.sh

echo "==> microservice unit tests"
python3 -m unittest -v infra/microserver/test_mihomo_verge_api.py
