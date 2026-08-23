#!/usr/bin/env bash
set -Eeuo pipefail

# This file is uploaded transiently by deploy_verge_api.sh and can also be
# executed with command fakes by the focused offline test. It owns only the
# Verge API/runtime-contract pair; it never restarts or mutates Mihomo.

: "${ACTION:?}"
: "${REMOTE_API:?}"
: "${REMOTE_UNIT:?}"
: "${REMOTE_CONTRACT:?}"
: "${REMOTE_ROLLBACK_ROOT:?}"

READINESS_TIMEOUT_SECONDS="${READINESS_TIMEOUT_SECONDS:-30}"
READINESS_POLL_INTERVAL_SECONDS="${READINESS_POLL_INTERVAL_SECONDS:-1}"
MIHOMO_BIN="${MIHOMO_BIN:-/usr/local/bin/mihomo}"
INSTALL_BIN="${INSTALL_BIN:-install}"
API_HEALTH_URL="${API_HEALTH_URL:-http://172.18.0.1:9091/healthz}"

if [[ ! "$READINESS_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] ||
   (( READINESS_TIMEOUT_SECONDS > 30 )); then
  printf 'ERROR: invalid readiness timeout\n' >&2
  exit 2
fi
if ! READINESS_POLL_INTERVAL_MS="$(python3 - "$READINESS_POLL_INTERVAL_SECONDS" <<'PY' 2>/dev/null
from decimal import Decimal, InvalidOperation
import sys

try:
    interval = Decimal(sys.argv[1])
except InvalidOperation:
    raise SystemExit(1)
if not interval.is_finite() or interval <= 0 or interval > 30:
    raise SystemExit(1)
milliseconds = int(interval * 1000)
if milliseconds < 1:
    raise SystemExit(1)
print(milliseconds)
PY
)"; then
  printf 'ERROR: invalid readiness poll interval\n' >&2
  exit 2
fi

backup_dir=""
backup_id="${ROLLBACK_ID:-}"
mihomo_before_timestamp=""
mihomo_before_version=""
mihomo_baseline_captured=0
mihomo_failure=""
readiness_failure=""
restore_failure=""
restore_health=0
runtime_probe=""

quiet_install() {
  "$INSTALL_BIN" "$@" >/dev/null 2>&1
}

capture_mihomo_state() {
  local timestamp version

  if ! timestamp="$(systemctl show mihomo.service -p ActiveEnterTimestampMonotonic --value 2>/dev/null)" ||
     [[ -z "$timestamp" ]]; then
    mihomo_failure="state_unavailable"
    return 1
  fi
  if ! version="$("$MIHOMO_BIN" -v 2>/dev/null | sed -n '1p')" ||
     [[ -z "$version" ]]; then
    mihomo_failure="state_unavailable"
    return 1
  fi

  mihomo_before_timestamp="$timestamp"
  mihomo_before_version="$version"
  mihomo_baseline_captured=1
  mihomo_failure=""
}

verify_mihomo_unchanged() {
  local timestamp version

  if (( mihomo_baseline_captured != 1 )); then
    mihomo_failure="state_unavailable"
    return 1
  fi

  if ! timestamp="$(systemctl show mihomo.service -p ActiveEnterTimestampMonotonic --value 2>/dev/null)" ||
     [[ -z "$timestamp" ]]; then
    mihomo_failure="state_unavailable"
    return 1
  fi
  if ! version="$("$MIHOMO_BIN" -v 2>/dev/null | sed -n '1p')" ||
     [[ -z "$version" ]]; then
    mihomo_failure="state_unavailable"
    return 1
  fi

  if [[ "$timestamp" != "$mihomo_before_timestamp" ||
        "$version" != "$mihomo_before_version" ]]; then
    mihomo_failure="drift"
    return 2
  fi
  mihomo_failure=""
}

read_api_state() {
  local state
  state="$(systemctl show mihomo-verge-api.service -p ActiveState --value 2>/dev/null)" || return 1
  [[ -n "$state" ]] || return 1
  printf '%s\n' "$state"
}

read_api_nrestarts() {
  local count
  count="$(systemctl show mihomo-verge-api.service -p NRestarts --value 2>/dev/null)" || return 1
  [[ "$count" =~ ^[0-9]+$ ]] || return 1
  printf '%s\n' "$count"
}

listener_ready() {
  ss -H -ltn 2>/dev/null |
    awk '$4 == "172.18.0.1:9091" { found=1 } END { exit(found ? 0 : 1) }'
}

monotonic_ms() {
  python3 - <<'PY'
import time

print(time.monotonic_ns() // 1_000_000)
PY
}

format_duration_ms() {
  awk -v milliseconds="$1" 'BEGIN { printf "%.3f", milliseconds / 1000 }'
}

api_health_probe() {
  local max_time="$1"
  # The response body is deliberately discarded. Readiness is listener-first
  # and performs only one health request after the exact listener is present.
  curl --silent --fail --max-time "$max_time" "$API_HEALTH_URL" >/dev/null 2>&1
}

verify_api_stable() {
  local expected_nrestarts="$1"
  local state nrestarts

  if ! state="$(read_api_state)"; then
    readiness_failure="service_state_unavailable"
    return 11
  fi
  if ! nrestarts="$(read_api_nrestarts)"; then
    readiness_failure="nrestarts_unavailable"
    return 12
  fi
  if [[ "$nrestarts" != "$expected_nrestarts" ]]; then
    readiness_failure="api_restart_storm"
    return 13
  fi
  if [[ "$state" != "active" ]] ||
     ! systemctl is-active mihomo-verge-api.service >/dev/null 2>&1; then
    readiness_failure="api_unstable"
    return 17
  fi
  if ! listener_ready; then
    readiness_failure="listener_missing"
    return 19
  fi
}

wait_for_api_ready() {
  local expected_nrestarts="$1"
  local started_ms deadline_ms now_ms remaining_ms sleep_ms health_budget_ms

  if ! started_ms="$(monotonic_ms)"; then
    readiness_failure="readiness_clock_unavailable"
    return 18
  fi
  deadline_ms=$((started_ms + READINESS_TIMEOUT_SECONDS * 1000))

  readiness_failure="readiness_timeout"
  while :; do
    local state nrestarts
    if ! state="$(read_api_state)"; then
      readiness_failure="service_state_unavailable"
      return 11
    fi
    if ! nrestarts="$(read_api_nrestarts)"; then
      readiness_failure="nrestarts_unavailable"
      return 12
    fi
    if [[ "$nrestarts" != "$expected_nrestarts" ]]; then
      readiness_failure="api_restart_storm"
      return 13
    fi
    if [[ "$state" == "failed" ]]; then
      readiness_failure="api_service_failed"
      return 14
    fi

    # Do not call health until systemd reports active and the exact host
    # listener is present. This avoids treating Type=simple as HTTP readiness.
    if [[ "$state" == "active" ]] &&
       systemctl is-active mihomo-verge-api.service >/dev/null 2>&1 &&
       listener_ready; then
      if ! now_ms="$(monotonic_ms)"; then
        readiness_failure="readiness_clock_unavailable"
        return 18
      fi
      remaining_ms=$((deadline_ms - now_ms))
      if (( remaining_ms <= 0 )); then
        readiness_failure="readiness_timeout"
        return 15
      fi
      health_budget_ms="$remaining_ms"
      if (( health_budget_ms > 8000 )); then
        health_budget_ms=8000
      fi
      if ! api_health_probe "$(format_duration_ms "$health_budget_ms")"; then
        readiness_failure="health_probe_failed"
        return 16
      fi
      if ! now_ms="$(monotonic_ms)"; then
        readiness_failure="readiness_clock_unavailable"
        return 18
      fi
      if (( now_ms > deadline_ms )); then
        readiness_failure="readiness_timeout"
        return 15
      fi
      verify_api_stable "$expected_nrestarts"
      return
    fi

    if ! now_ms="$(monotonic_ms)"; then
      readiness_failure="readiness_clock_unavailable"
      return 18
    fi
    remaining_ms=$((deadline_ms - now_ms))
    if (( remaining_ms <= 0 )); then
      readiness_failure="readiness_timeout"
      return 15
    fi
    sleep_ms="$READINESS_POLL_INTERVAL_MS"
    if (( sleep_ms > remaining_ms )); then
      sleep_ms="$remaining_ms"
    fi
    sleep "$(format_duration_ms "$sleep_ms")"
  done
}

restore_backup() {
  local restore_nrestarts
  local install_failed=0
  restore_failure=""
  restore_health=0

  if [[ ! -d "$backup_dir" ||
        ! -f "$backup_dir/api.py" ||
        ! -f "$backup_dir/unit" ||
        ! -f "$backup_dir/runtime-contract.json" ]]; then
    restore_failure="backup_incomplete"
    return 20
  fi

  quiet_install -o root -g root -m 755 "$backup_dir/api.py" "$REMOTE_API" || install_failed=1
  quiet_install -o root -g root -m 644 "$backup_dir/unit" "$REMOTE_UNIT" || install_failed=1
  quiet_install -o root -g root -m 644 "$backup_dir/runtime-contract.json" "$REMOTE_CONTRACT" || install_failed=1
  if (( install_failed )); then
    restore_failure="file_restore_failed"
    return 21
  fi
  if ! systemctl daemon-reload >/dev/null 2>&1; then
    restore_failure="daemon_reload_failed"
    return 22
  fi
  if ! restore_nrestarts="$(read_api_nrestarts)"; then
    restore_failure="nrestarts_unavailable"
    return 24
  fi
  if ! systemctl restart mihomo-verge-api.service >/dev/null 2>&1; then
    restore_failure="api_restart_failed"
    return 23
  fi
  # A manual restart must not absorb an automatic restart into a new baseline.
  # Capture NRestarts first, then require it to remain unchanged throughout.
  if ! wait_for_api_ready "$restore_nrestarts"; then
    restore_failure="${readiness_failure:-readiness_failed}"
    return 25
  fi
  restore_health=1
  if ! verify_mihomo_unchanged; then
    if [[ "$mihomo_failure" == "drift" ]]; then
      restore_failure="mihomo_drift"
      return 26
    fi
    restore_failure="mihomo_state_unavailable"
    return 27
  fi
  if ! verify_api_stable "$restore_nrestarts"; then
    restore_health=0
    restore_failure="${readiness_failure:-api_unstable}"
    return 28
  fi
}

report_candidate_failure() {
  local reason="$1"
  local initial_mihomo_failure=""
  local initial_mihomo_status=0
  local restore_status=0

  if verify_mihomo_unchanged; then
    :
  else
    initial_mihomo_status=$?
    initial_mihomo_failure="$mihomo_failure"
  fi

  if restore_backup; then
    :
  else
    restore_status=$?
  fi

  if [[ "$initial_mihomo_failure" == "drift" || "$restore_failure" == "mihomo_drift" ]]; then
    printf 'ERROR: candidate_failed reason=%s mihomo=drift api_pair_health=%s restore_failure=%s stop=1\n' \
      "$reason" "$restore_health" "${restore_failure:-none}" >&2
    return 3
  fi
  if (( initial_mihomo_status != 0 )); then
    printf 'ERROR: candidate_failed reason=%s mihomo=unverified api_pair_health=%s restore_failure=%s stop=1\n' \
      "$reason" "$restore_health" "${restore_failure:-none}" >&2
    return 3
  fi
  if (( restore_status != 0 )); then
    printf 'ERROR: candidate_failed reason=%s api_pair_restored=0 api_pair_health=%s mihomo_unchanged=1 restore_failure=%s stop=1\n' \
      "$reason" "$restore_health" "${restore_failure:-unknown}" >&2
    return 1
  fi
  printf 'ERROR: candidate_failed reason=%s api_pair_restored=1 api_pair_health=1 mihomo_unchanged=1\n' \
    "$reason" >&2
  return 1
}

validate_candidate_contract() {
  python3 - "$REMOTE_TMP_CONTRACT" <<'PY' >/dev/null 2>&1
import json
import os
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "appVersion": "2.5.2-webport.0",
    "apiSchemaVersion": "2026.08-lzc-v2",
    "uiSchemaVersion": "2026.08-lzc-v2",
    "packageFingerprint": "cloud.lazycat.app.clash-verge-for-lc/2.5.2-webport.0",
    "buildId": os.environ["EXPECTED_BUILD_ID"],
    "gitCommit": os.environ["EXPECTED_GIT_COMMIT"],
}
if any(payload.get(key) != value for key, value in expected.items()):
    raise SystemExit(1)
if payload.get("capabilities", {}).get("systemProxy", {}).get("mode") != "disabled":
    raise SystemExit(1)
PY
}

validate_runtime_probe() {
  python3 - "$1" <<'PY' >/dev/null 2>&1
import json
import os
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "appVersion": "2.5.2-webport.0",
    "apiSchemaVersion": "2026.08-lzc-v2",
    "uiSchemaVersion": "2026.08-lzc-v2",
    "packageFingerprint": "cloud.lazycat.app.clash-verge-for-lc/2.5.2-webport.0",
    "buildId": os.environ["EXPECTED_BUILD_ID"],
    "gitCommit": os.environ["EXPECTED_GIT_COMMIT"],
}
if any(payload.get(key) != value for key, value in expected.items()):
    raise SystemExit(1)
if payload.get("systemProxy", {}).get("mode") != "disabled":
    raise SystemExit(1)
PY
}

report_rollback_failure() {
  local reason="$1"
  local health="${2:-0}"
  local mihomo_status=0

  if verify_mihomo_unchanged; then
    :
  else
    mihomo_status=$?
  fi
  if [[ "$mihomo_failure" == "drift" ]]; then
    printf 'ERROR: rollback_failed reason=%s mihomo=drift api_pair_health=%s stop=1\n' \
      "$reason" "$health" >&2
    return 3
  fi
  if (( mihomo_status != 0 )); then
    printf 'ERROR: rollback_failed reason=%s mihomo=unverified api_pair_health=%s stop=1\n' \
      "$reason" "$health" >&2
    return 3
  fi
  printf 'ERROR: rollback_failed reason=%s mihomo_unchanged=1 api_pair_health=%s stop=1\n' \
    "$reason" "$health" >&2
  return 1
}

run_rollback() {
  [[ "$backup_id" =~ ^backup\.[A-Za-z0-9]{8}$ ]] || {
    printf 'ERROR: invalid opaque backup id\n' >&2
    return 2
  }
  backup_dir="$REMOTE_ROLLBACK_ROOT/$backup_id"
  [[ -d "$backup_dir" && -f "$backup_dir/api.py" && -f "$backup_dir/unit" &&
     -f "$backup_dir/runtime-contract.json" ]] || {
    printf 'ERROR: requested backup is incomplete\n' >&2
    return 1
  }
  if ! capture_mihomo_state; then
    printf 'ERROR: rollback_failed reason=mihomo_baseline_unavailable stop=1\n' >&2
    return 3
  fi

  local expected_nrestarts
  local install_failed=0
  quiet_install -o root -g root -m 755 "$backup_dir/api.py" "$REMOTE_API" || install_failed=1
  quiet_install -o root -g root -m 644 "$backup_dir/unit" "$REMOTE_UNIT" || install_failed=1
  quiet_install -o root -g root -m 644 "$backup_dir/runtime-contract.json" "$REMOTE_CONTRACT" || install_failed=1
  if (( install_failed )); then
    report_rollback_failure "file_restore_failed"
  fi
  if ! systemctl daemon-reload >/dev/null 2>&1; then
    report_rollback_failure "daemon_reload_failed"
  fi
  if ! expected_nrestarts="$(read_api_nrestarts)"; then
    report_rollback_failure "nrestarts_unavailable"
  fi
  if ! systemctl restart mihomo-verge-api.service >/dev/null 2>&1; then
    report_rollback_failure "api_restart_failed"
  fi
  if ! wait_for_api_ready "$expected_nrestarts"; then
    report_rollback_failure "${readiness_failure:-readiness_failed}"
  fi
  if ! verify_mihomo_unchanged; then
    printf 'ERROR: rollback_failed reason=mihomo_%s api_pair_health=1 stop=1\n' \
      "${mihomo_failure:-state_unavailable}" >&2
    return 3
  fi
  if ! verify_api_stable "$expected_nrestarts"; then
    report_rollback_failure "${readiness_failure:-api_unstable}" 1
  fi
  printf 'rollback_ok backup_id=%s api_pair_health=1 mihomo_unchanged=1\n' "$backup_id"
}

run_deploy() {
  : "${REMOTE_TMP_API:?}"
  : "${REMOTE_TMP_UNIT:?}"
  : "${REMOTE_TMP_CONTRACT:?}"
  : "${EXPECTED_BUILD_ID:?}"
  : "${EXPECTED_GIT_COMMIT:?}"

  if ! "$INSTALL_BIN" -d -o root -g root -m 700 "$REMOTE_ROLLBACK_ROOT" >/dev/null 2>&1; then
    printf 'ERROR: candidate_failed reason=rollback_root_unavailable api_pair_restored=0 stop=1\n' >&2
    return 1
  fi
  if ! backup_dir="$(mktemp -d "$REMOTE_ROLLBACK_ROOT/backup.XXXXXXXX")"; then
    printf 'ERROR: candidate_failed reason=backup_create_failed api_pair_restored=0 stop=1\n' >&2
    return 1
  fi
  backup_id="${backup_dir##*/}"
  if ! quiet_install -o root -g root -m 755 "$REMOTE_API" "$backup_dir/api.py" ||
     ! quiet_install -o root -g root -m 644 "$REMOTE_UNIT" "$backup_dir/unit" ||
     ! quiet_install -o root -g root -m 644 "$REMOTE_CONTRACT" "$backup_dir/runtime-contract.json"; then
    printf 'ERROR: candidate_failed reason=backup_capture_failed api_pair_restored=0 stop=1\n' >&2
    return 1
  fi
  chmod 700 "$backup_dir" >/dev/null 2>&1 || {
    printf 'ERROR: candidate_failed reason=backup_permission_failed api_pair_restored=0 stop=1\n' >&2
    return 1
  }

  if ! capture_mihomo_state; then
    report_candidate_failure "mihomo_baseline_unavailable"
  fi
  if ! python3 -m py_compile "$REMOTE_TMP_API" >/dev/null 2>&1; then
    report_candidate_failure "candidate_api_syntax"
  fi
  if ! validate_candidate_contract; then
    report_candidate_failure "candidate_runtime_contract"
  fi

  local expected_nrestarts
  if ! expected_nrestarts="$(read_api_nrestarts)"; then
    report_candidate_failure "nrestarts_unavailable"
  fi
  if ! quiet_install -o root -g root -m 755 "$REMOTE_TMP_API" "$REMOTE_API" ||
     ! quiet_install -o root -g root -m 644 "$REMOTE_TMP_UNIT" "$REMOTE_UNIT" ||
     ! quiet_install -o root -g root -m 644 "$REMOTE_TMP_CONTRACT" "$REMOTE_CONTRACT"; then
    report_candidate_failure "candidate_install"
  fi
  if ! systemctl daemon-reload >/dev/null 2>&1; then
    report_candidate_failure "daemon_reload"
  fi
  if ! systemctl restart mihomo-verge-api.service >/dev/null 2>&1; then
    report_candidate_failure "api_restart"
  fi
  if ! wait_for_api_ready "$expected_nrestarts"; then
    report_candidate_failure "api_${readiness_failure:-readiness_failed}"
  fi

  runtime_probe="/tmp/clash-verge-webport-runtime-info-$BASHPID.json"
  trap 'rm -f -- "${runtime_probe:-}" >/dev/null 2>&1 || true' EXIT
  if ! curl --silent --fail --max-time 8 \
      'http://172.18.0.1:9091/runtime-info?scope=contract' >"$runtime_probe" 2>/dev/null ||
     ! validate_runtime_probe "$runtime_probe"; then
    report_candidate_failure "runtime_info_contract"
  fi
  rm -f -- "$runtime_probe" >/dev/null 2>&1 || true
  trap - EXIT

  if ! verify_mihomo_unchanged; then
    report_candidate_failure "mihomo_${mihomo_failure:-state_unavailable}"
  fi
  if ! verify_api_stable "$expected_nrestarts"; then
    report_candidate_failure "api_${readiness_failure:-api_unstable}"
  fi
  printf 'deploy_ok backup_id=%s api_pair_health=1 mihomo_unchanged=1\n' "$backup_id"
}

case "$ACTION" in
  deploy)
    run_deploy
    ;;
  rollback)
    run_rollback
    ;;
  *)
    printf 'ERROR: unsupported action\n' >&2
    exit 2
    ;;
esac
