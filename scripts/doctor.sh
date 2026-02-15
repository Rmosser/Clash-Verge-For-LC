#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
N/A: deploy/ops repo; no long-running local daemon.

Local Runtime Contract v2 (stub):
  - scripts/doctor.sh exists for interface consistency across projects.
  - No /healthz /readyz /diagnostics /metrics endpoints here.

Try:
  - bash scripts/deploy_all.sh
  - bash scripts/selfcheck.sh
EOF

exit 0
