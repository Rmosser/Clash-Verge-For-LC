#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail=0

# Basic shell syntax check for repository .sh files (works without shellcheck).
while IFS= read -r -d '' f; do
  if ! bash -n "$f"; then
    fail=1
  fi
done < <(
  find "$ROOT" \
    -path "$ROOT/.git" -prune -o \
    -path "$ROOT/.codex-tmp" -prune -o \
    -path "$ROOT/output" -prune -o \
    -path "$ROOT/src/mihomo-dashboard-app/node_modules" -prune -o \
    -path "$ROOT/src/mihomo-dashboard-app/dist" -prune -o \
    -path "$ROOT/src/mihomo-dashboard-app/.pnpm-store" -prune -o \
    -type f -name '*.sh' -print0
)

# Fast Python syntax check.
if command -v python3 >/dev/null 2>&1; then
  python3 -m compileall -q "$ROOT" >/dev/null 2>&1 || fail=1
fi

exit "$fail"
