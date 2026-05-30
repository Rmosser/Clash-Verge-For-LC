#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT/src/mihomo-dashboard-app"
MANIFEST_FILE="$APP_DIR/lzc-manifest.yml"
OUTPUT_ROOT="${OUTPUT_ROOT:-$ROOT/output/release}"

usage() {
  cat <<'USAGE'
Usage: scripts/build_dashboard_release.sh [output-dir]

Builds a versioned LazyCat-installable LPK for the dashboard app, without
installing it to any box. The resulting directory is suitable for uploading to
网盘 / cloud disk for one-click install.

Arguments:
  output-dir   Optional release output root. Defaults to output/release
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 1 ]]; then
  echo "ERROR: too many arguments" >&2
  usage >&2
  exit 1
fi

if [[ $# -eq 1 ]]; then
  OUTPUT_ROOT="$1"
fi

case "$OUTPUT_ROOT" in
  /*) ;;
  *) OUTPUT_ROOT="$(pwd)/$OUTPUT_ROOT" ;;
esac

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: missing required command: $1" >&2
    exit 1
  fi
}

resolve_build_cmd() {
  if command -v pnpm >/dev/null 2>&1; then
    printf '%s\n' "pnpm build"
    return 0
  fi

  if command -v corepack >/dev/null 2>&1; then
    printf '%s\n' "corepack pnpm build"
    return 0
  fi

  if command -v npm >/dev/null 2>&1; then
    printf '%s\n' "npm run build"
    return 0
  fi

  echo "ERROR: missing a supported build command (pnpm, corepack pnpm, or npm)" >&2
  exit 1
}

read_manifest_field() {
  local key="$1"
  sed -n -E "s/^${key}:[[:space:]]*(.+)[[:space:]]*$/\\1/p" "$MANIFEST_FILE" | head -n 1
}

validate_dist_config() {
  local config_file="$APP_DIR/dist/lzcapp-config.js"

  python3 - <<'PY' "$config_file"
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
for key in ("secret", "vergeApiSecret"):
    match = re.search(rf"{key}:\s*\"([^\"]*)\"", text)
    if not match:
        raise SystemExit(f"ERROR: {path} missing {key} in lzcapp-config.js")
    if match.group(1):
        raise SystemExit(f"ERROR: {path} still embeds non-empty {key}")
print("Verified dist/lzcapp-config.js uses runtime bootstrap only.")
PY
}

write_sha256() {
  local file="$1"
  local out="$2"

  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$(basename "$file")" >"$out"
    return 0
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$(basename "$file")" >"$out"
    return 0
  fi

  echo "ERROR: missing checksum command (shasum or sha256sum)" >&2
  exit 1
}

require_cmd python3
require_cmd lzc-cli
BUILD_CMD="$(resolve_build_cmd)"

if [[ ! -f "$MANIFEST_FILE" ]]; then
  echo "ERROR: manifest file not found: $MANIFEST_FILE" >&2
  exit 1
fi

APP_NAME="$(read_manifest_field "name")"
APP_PACKAGE="$(read_manifest_field "package")"
APP_VERSION="$(read_manifest_field "version")"
APP_SUBDOMAIN="$(
  sed -n -E 's/^[[:space:]]*subdomain:[[:space:]]*(.+)[[:space:]]*$/\1/p' "$MANIFEST_FILE" | head -n 1
)"

if [[ -z "$APP_NAME" || -z "$APP_PACKAGE" || -z "$APP_VERSION" ]]; then
  echo "ERROR: failed to parse name/package/version from $MANIFEST_FILE" >&2
  exit 1
fi

RELEASE_DIR="$OUTPUT_ROOT/$APP_VERSION"
LPK_BASENAME="clash-verge-for-lc-${APP_VERSION}.lpk"
LPK_PATH="$RELEASE_DIR/$LPK_BASENAME"
SHA_PATH="$RELEASE_DIR/${LPK_BASENAME}.sha256"
README_PATH="$RELEASE_DIR/INSTALL.md"
BUILD_INFO_PATH="$RELEASE_DIR/build-info.txt"
BUILD_TIME_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

mkdir -p "$RELEASE_DIR"
rm -f "$LPK_PATH" "$SHA_PATH" "$README_PATH" "$BUILD_INFO_PATH"

echo "Building Clash Verge Rev web assets ..."
(
  cd "$APP_DIR"
  bash -lc "$BUILD_CMD" >/dev/null
)

if [[ ! -f "$APP_DIR/dist/index.html" ]]; then
  echo "ERROR: missing dashboard assets under $APP_DIR/dist" >&2
  exit 1
fi

validate_dist_config

echo "Building LazyCat installable LPK ..."
(
  cd "$APP_DIR"
  lzc-cli project build -f lzc-build.yml -o "$LPK_PATH" >/dev/null
)

if [[ ! -f "$LPK_PATH" ]]; then
  echo "ERROR: expected LPK was not created: $LPK_PATH" >&2
  exit 1
fi

(
  cd "$RELEASE_DIR"
  write_sha256 "$LPK_PATH" "$SHA_PATH"
)

cat >"$README_PATH" <<EOF
# Clash for LC 安装包

这是一个可直接上传到懒猫网盘分发的标准 LPK 安装包。

- 应用名: ${APP_NAME}
- 包名: ${APP_PACKAGE}
- 版本: ${APP_VERSION}
- 默认子域名: ${APP_SUBDOMAIN:-clash}
- 安装文件: ${LPK_BASENAME}

## 使用方式

1. 把 \`${LPK_BASENAME}\` 上传到懒猫网盘。
2. 在懒猫里打开这个文件，执行安装。
3. 安装完成后，从应用入口访问 Dashboard。

## 边界说明

这个安装包只负责安装懒猫应用侧的 Web Dashboard 与同源订阅抓取代理。
它不会自动在微服宿主机上安装或配置 \`mihomo\`、TUN、\`mihomo-verge-api\`。
如果宿主机侧运行时还没部署好，应用虽然能装上，但不会具备完整代理能力。

## 校验

同目录下的 \`$(basename "$SHA_PATH")\` 是 SHA-256 校验文件，上传或分发前可先核对。
EOF

cat >"$BUILD_INFO_PATH" <<EOF
name=${APP_NAME}
package=${APP_PACKAGE}
version=${APP_VERSION}
subdomain=${APP_SUBDOMAIN:-clash}
manifest=${MANIFEST_FILE}
artifact=${LPK_PATH}
sha256=${SHA_PATH}
built_at_utc=${BUILD_TIME_UTC}
EOF

echo "Release ready:"
echo "  $LPK_PATH"
echo "  $SHA_PATH"
echo "  $README_PATH"
