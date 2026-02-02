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
# Use an absolute URL (metacubexd's connect screen validates URL format).
python3 - "$cfg" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

replacement = "defaultBackendURL: new URL('/api', location.href).toString(),"

def patch(src: str) -> str:
    # Replace an existing defaultBackendURL line (string or expression).
    out = re.sub(r"^\s*defaultBackendURL\s*:\s*.*?,\s*$", f"  {replacement}", src, flags=re.M)
    if out != src:
        return out

    # Insert into config object.
    m = re.search(r"window\.__METACUBEXD_CONFIG__\s*=\s*\{\s*", src)
    if not m:
        raise SystemExit("config.js format unexpected: missing window.__METACUBEXD_CONFIG__ object")
    insert_at = m.end()
    return src[:insert_at] + f"\n  {replacement}\n" + src[insert_at:]


new_text = patch(text)
if not new_text.endswith("\n"):
    new_text += "\n"
path.write_text(new_text, encoding="utf-8")
PY

# Inject a small bootstrap that auto-connects on first load by passing
# `?url=<origin>/api&secret=<secret>` (secret provided at build time).
index_html="$DIST_DIR/index.html"
if [[ -f "$index_html" ]]; then
  python3 - "$index_html" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
html = path.read_text(encoding="utf-8", errors="replace")

marker = '<script type="module" src="./_nuxt/'
if marker not in html:
    raise SystemExit("index.html format unexpected: missing nuxt module script marker")

if "lzcapp-config.js" in html and "__LZCAPP_MIHOMO__" in html:
    # Already injected.
    sys.exit(0)

inject = (
    '<script src="lzcapp-config.js"></script>'
    '<script>(function(){'
    'var c=window.__LZCAPP_MIHOMO__||{};'
    'if(!c.secret){return;}'
    'var u=new URL(window.location.href);'
    'if(!u.searchParams.get(\"url\")){u.searchParams.set(\"url\",new URL(\"/api\",u).toString());}'
    'if(!u.searchParams.get(\"secret\")){u.searchParams.set(\"secret\",c.secret);}'
    'var next=u.toString();'
    'if(next!==window.location.href){window.location.replace(next);}'
    '})();</script>'
)

pos = html.index(marker)
html = html[:pos] + inject + html[pos:]
path.write_text(html, encoding="utf-8")
PY
fi

if [[ -n "${tag:-}" ]]; then
  printf '%s\n' "$tag" >"$DIST_DIR/.metacubexd-version"
fi

echo "OK: metacubexd updated in $DIST_DIR"
