#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
This repository is deploy/ops oriented (no local "run" mode).

Entry points:
  - Deploy:     bash scripts/deploy_all.sh --confirm
  - Selfcheck:  bash scripts/selfcheck.sh

See README.md for details.
EOF
