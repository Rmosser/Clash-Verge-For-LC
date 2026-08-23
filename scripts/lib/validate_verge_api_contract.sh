#!/usr/bin/env bash
set -Eeuo pipefail

# Validate the local candidate identity before deploy_verge_api.sh uploads
# anything. The git object check is deliberately local-only: this must not
# turn a deployment into a network-dependent ref lookup.

CONTRACT_PATH="${1:-}"
REPOSITORY_ROOT="${2:-}"

if [[ -z "$CONTRACT_PATH" || -z "$REPOSITORY_ROOT" ]]; then
  printf 'ERROR: usage: validate_verge_api_contract.sh <contract> <repository-root>\n' >&2
  exit 2
fi
if [[ ! -f "$CONTRACT_PATH" ]]; then
  printf 'ERROR: runtime contract file is missing\n' >&2
  exit 1
fi
if [[ ! -d "$REPOSITORY_ROOT/.git" && ! -f "$REPOSITORY_ROOT/.git" ]]; then
  printf 'ERROR: local repository root is unavailable\n' >&2
  exit 1
fi
command -v git >/dev/null 2>&1 || {
  printf 'ERROR: git is required for local runtime contract identity validation\n' >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  printf 'ERROR: python3 is required for runtime contract validation\n' >&2
  exit 1
}

read -r EXPECTED_BUILD_ID EXPECTED_GIT_COMMIT < <(
  python3 - "$CONTRACT_PATH" <<'PY'
import json
import re
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
required = {
    "appVersion": "2.5.2-webport.0",
    "apiSchemaVersion": "2026.08-lzc-v2",
    "uiSchemaVersion": "2026.08-lzc-v2",
    "packageFingerprint": "cloud.lazycat.app.clash-verge-for-lc/2.5.2-webport.0",
}
for key, expected in required.items():
    if payload.get(key) != expected:
        raise SystemExit(f"ERROR: runtime contract {key} is not the v2.5.2 WebPort value")
if payload.get("capabilities", {}).get("systemProxy", {}).get("mode") != "disabled":
    raise SystemExit("ERROR: runtime contract must keep systemProxy disabled")
git_commit = str(payload.get("gitCommit") or "")
if not re.fullmatch(r"[0-9a-f]{40}", git_commit):
    raise SystemExit("ERROR: runtime contract must bind an exact candidate gitCommit")
print(payload.get("buildId", ""), git_commit)
PY
)

[[ -n "$EXPECTED_BUILD_ID" ]] || {
  printf 'ERROR: runtime contract buildId is missing\n' >&2
  exit 1
}
[[ "$EXPECTED_GIT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  printf 'ERROR: runtime contract must bind an exact candidate gitCommit\n' >&2
  exit 1
}
if ! git -C "$REPOSITORY_ROOT" cat-file -e "${EXPECTED_GIT_COMMIT}^{commit}" >/dev/null 2>&1; then
  printf 'ERROR: runtime contract gitCommit object is not present in the local repository\n' >&2
  exit 1
fi

printf '%s %s\n' "$EXPECTED_BUILD_ID" "$EXPECTED_GIT_COMMIT"
