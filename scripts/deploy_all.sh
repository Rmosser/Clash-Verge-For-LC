#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" != "--confirm" || "$#" -ne 1 ]]; then
  echo "Usage: scripts/deploy_all.sh --confirm" >&2
  echo "--confirm is required; each child also verifies the approved SSH fingerprint." >&2
  exit 2
fi

"$ROOT/scripts/deploy_microserver.sh" --confirm
"$ROOT/scripts/deploy_dashboard.sh" --confirm
