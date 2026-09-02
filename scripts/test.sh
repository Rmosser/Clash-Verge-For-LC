#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> repository lint"
bash scripts/lint.sh

echo "==> microservice unit tests"
python3 -m unittest -v infra/microserver/test_mihomo_verge_api.py
python3 -m unittest -v infra/microserver/test_mihomo_core_updater.py

echo "==> Verge API deployment readiness tests"
bash scripts/test_deploy_verge_api.sh

echo "==> host-native deployment setting tests"
bash scripts/test_deploy_settings.sh

echo "==> legacy cleanup isolation tests"
bash scripts/test_legacy_cleanup_isolation.sh

echo "==> rollback snapshot contract fixture"
python3 -B scripts/test_rollback_snapshot_contract.py

echo "==> runtime restore and health recovery drill"
python3 -B scripts/test_restore_recovery.py

echo "==> resolved interface re-probe drill"
bash scripts/test_resolved_sync_reprobe.sh
