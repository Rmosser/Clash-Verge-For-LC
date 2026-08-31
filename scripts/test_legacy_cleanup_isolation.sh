#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY="$ROOT/scripts/deploy_dashboard.sh"
CLEANUP="$ROOT/scripts/cleanup_legacy_dashboard.sh"

grep -q 'Reset only the current dashboard app' "$DEPLOY"
if grep -q 'cloud.lazycat.app.mihomo-dashboard' "$DEPLOY"; then
  echo "deploy_dashboard.sh still carries the retired app ID" >&2
  exit 1
fi

grep -q 'LEGACY_APP_ID="cloud.lazycat.app.mihomo-dashboard"' "$CLEANUP"
grep -q 'No changes made' "$CLEANUP"
grep -q 'legacy path still exists' "$CLEANUP"
grep -q 'LAZYCAT_BOX may only narrow' "$CLEANUP"
grep -q 'cannot verify deployment record' "$CLEANUP"

output="$(bash "$CLEANUP")"
grep -q 'No changes made' <<<"$output"
