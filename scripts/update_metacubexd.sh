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

# Patch metacubexd's setup page to support auto-connect via
# `?url=<full_url>&secret=<secret>` (upstream supports only hostname/http/https/port).
python3 - "$DIST_DIR" <<'PY'
import sys
from pathlib import Path

dist_dir = Path(sys.argv[1])
nuxt_dir = dist_dir / "_nuxt"
if not nuxt_dir.is_dir():
    raise SystemExit(f"dist missing _nuxt dir: {nuxt_dir}")

targets = []
for p in nuxt_dir.glob("*.js"):
    try:
        s = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    if "setupDescription" in s and "endpointURL" in s and "defaultBackendURL" in s and "window.location.search" in s:
        targets.append(p)

if not targets:
    raise SystemExit("unable to locate metacubexd setup chunk to patch (query url/secret support)")
if len(targets) > 2:
    # Avoid patching multiple unrelated chunks accidentally.
    raise SystemExit(f"found multiple candidates for setup chunk: {[p.name for p in targets]}")

patched_any = False
for p in targets:
    s = p.read_text(encoding="utf-8", errors="replace")
    if "let t=e.url;" in s and "F.url=t" in s:
        patched_any = True
        continue

    anchor = "if(e&&typeof e==`object`){let t=e.hostname;"
    idx = s.find(anchor)
    if idx == -1:
        raise SystemExit(f"unexpected setup chunk format in {p.name}: missing hostname anchor")

    inject = (
        "if(e&&typeof e==`object`){"
        "let t=e.url;"
        "if(t){F.url=t,F.secret=e.secret||``,await $();return}"
        "let t2=e.hostname;"
    )
    s2 = s.replace(anchor, inject, 1)
    if s2 == s:
        raise SystemExit(f"failed to patch {p.name}")
    p.write_text(s2, encoding="utf-8")
    patched_any = True

if not patched_any:
    raise SystemExit("failed to patch any setup chunk")
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
    # Prefer full URL so we can include /api path behind the LazyCat app.
    'if(!u.searchParams.get(\"url\")){u.searchParams.set(\"url\",new URL(\"/api\",window.location.origin).toString());}'
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
