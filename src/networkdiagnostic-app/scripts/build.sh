#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_DIR="$ROOT_DIR/bundle"
DIST_DIR="$ROOT_DIR/upstream-dist"

rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR/dist"

cp "$ROOT_DIR/server.mjs" "$BUNDLE_DIR/server.mjs"
cp -R "$DIST_DIR/." "$BUNDLE_DIR/dist/"
