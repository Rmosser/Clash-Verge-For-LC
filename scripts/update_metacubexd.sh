#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

APP_DIR="$ROOT/src/mihomo-dashboard-app"
DIST_DIR="$APP_DIR/dist"

VERSION="${METACUBEXD_VERSION:-latest}"

tmpdir="$(mktemp -d)"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

api_url="https://api.github.com/repos/MetaCubeX/metacubexd/releases/latest"
tgz_url_latest="https://github.com/MetaCubeX/metacubexd/releases/latest/download/compressed-dist.tgz"

tag=""
download_url=""
if [[ "$VERSION" == "latest" ]]; then
  # Best-effort: read tag from GitHub API, but still download from the stable "latest" URL.
  if command -v jq >/dev/null 2>&1; then
    tag="$(curl -fsSL "$api_url" | jq -r '.tag_name // empty' || true)"
  else
    tag="$(curl -fsSL "$api_url" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1 || true)"
  fi
  download_url="$tgz_url_latest"
else
  tag="$VERSION"
  download_url="https://github.com/MetaCubeX/metacubexd/releases/download/${VERSION}/compressed-dist.tgz"
fi

echo "Updating metacubexd dist (version=${tag:-unknown} url=$download_url) ..."

curl -fsSL -o "$tmpdir/metacubexd.tgz" "$download_url"

mkdir -p "$DIST_DIR"
# Preserve the tracked README.md; everything else is generated.
find "$DIST_DIR" -mindepth 1 -maxdepth 1 ! -name 'README.md' -exec rm -rf {} +

tar -xzf "$tmpdir/metacubexd.tgz" -C "$DIST_DIR"

cfg="$DIST_DIR/config.js"
if [[ ! -f "$cfg" ]]; then
  echo "ERROR: metacubexd dist missing config.js ($cfg)" >&2
  exit 1
fi

# Make metacubexd default to our proxied backend under the same origin.
python3 - "$cfg" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

def set_default_backend_url(src: str) -> str:
    # Prefer editing an existing defaultBackendURL entry.
    out = re.sub(r"(defaultBackendURL\s*:\s*)'[^']*'", r"\1'/api'", src)
    if out != src:
        return out
    out = re.sub(r'(defaultBackendURL\s*:\s*)"[^"]*"', r'\1"/api"', src)
    if out != src:
        return out

    # Fallback: insert into config object if missing.
    m = re.search(r"window\.__METACUBEXD_CONFIG__\s*=\s*\{\s*", src)
    if not m:
        raise SystemExit("config.js format unexpected: missing window.__METACUBEXD_CONFIG__ object")
    insert_at = m.end()
    return src[:insert_at] + "\n  defaultBackendURL: '/api'," + src[insert_at:]


new_text = set_default_backend_url(text)
if not new_text.endswith("\n"):
    new_text += "\n"
path.write_text(new_text, encoding="utf-8")
PY

if [[ -n "${tag:-}" ]]; then
  printf '%s\n' "$tag" >"$DIST_DIR/.metacubexd-version"
fi

echo "OK: metacubexd updated in $DIST_DIR"
