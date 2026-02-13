#!/usr/bin/env bash
set -euo pipefail

# Resolve a path that may be absolute, ~-prefixed, or repo-root relative.
# This makes `.env` safe even if scripts are invoked from a different CWD.
lzc_resolve_path_from_root() {
  local root="$1"
  local p="${2:-}"

  if [[ -z "$p" ]]; then
    printf '%s' ""
    return 0
  fi

  case "$p" in
    /*)
      printf '%s' "$p"
      return 0
      ;;
    "~/"*)
      printf '%s' "$HOME/${p#~/}"
      return 0
      ;;
  esac

  printf '%s' "$root/$p"
}

