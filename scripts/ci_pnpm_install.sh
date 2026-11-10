#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
pnpm_version=11.3.0
project_dir=src/mihomo-dashboard-app
cache_registry=http://172.18.0.1:17893
public_registry=https://registry.npmjs.org

# Both Corepack and pnpm use the pinned EB Fast IPv4 listener on a cache miss.
export HTTP_PROXY=http://172.18.0.1:17896 HTTPS_PROXY=http://172.18.0.1:17896
export NO_PROXY=127.0.0.1,localhost,172.18.0.1
export http_proxy="$HTTP_PROXY" https_proxy="$HTTPS_PROXY" no_proxy="$NO_PROXY"
export COREPACK_DEFAULT_TO_LATEST=0 COREPACK_ENABLE_DOWNLOAD_PROMPT=0

install_from_registry() {
  local registry=$1 deadline=$2 actual_version
  actual_version=$(COREPACK_NPM_REGISTRY="$registry" \
    timeout --kill-after=5s 60s corepack "pnpm@$pnpm_version" --version) || return
  if [[ "$actual_version" != "$pnpm_version" ]]; then
    echo "Unexpected pnpm version: $actual_version" >&2
    return 1
  fi
  timeout --kill-after=5s "$deadline" \
    corepack "pnpm@$pnpm_version" --dir "$project_dir" install --frozen-lockfile \
    --registry="$registry" --fetch-retries=1 --fetch-timeout=30000 \
    --fetch-retry-mintimeout=1000 --fetch-retry-maxtimeout=2000
}

started_at=$(date +%s)
if curl --fail --silent --show-error --noproxy '*' --connect-timeout 2 --max-time 5 \
  "$cache_registry/-/ping" >/dev/null && install_from_registry "$cache_registry" 180s; then
  printf 'CI_NPM_INSTALL mode=proxy duration_s=%s\n' "$(( $(date +%s) - started_at ))"
  exit 0
fi

echo 'CI_NPM_INSTALL mode=fallback registry=https://registry.npmjs.org' >&2
install_from_registry "$public_registry" 600s
printf 'CI_NPM_INSTALL mode=public duration_s=%s\n' "$(( $(date +%s) - started_at ))"
