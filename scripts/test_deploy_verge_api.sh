#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
HELPER="$ROOT/scripts/lib/deploy_verge_api_readiness.sh"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/clash-verge-webport-readiness.XXXXXX")"
FAKE_BIN="$TEST_ROOT/bin"
mkdir -p "$FAKE_BIN"
cleanup_test_root() {
  if [[ "${KEEP_TEST_ROOT:-0}" == 1 ]]; then
    printf 'test root: %s\n' "$TEST_ROOT" >&2
  else
    rm -rf -- "$TEST_ROOT"
  fi
}
trap cleanup_test_root EXIT

cat >"$FAKE_BIN/install" <<'FAKE_INSTALL'
#!/usr/bin/env bash
set -Eeuo pipefail
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|-g)
      shift 2
      ;;
    *)
      args+=("$1")
      shift
      ;;
  esac
done
exec /usr/bin/install "${args[@]}"
FAKE_INSTALL

cat >"$FAKE_BIN/systemctl" <<'FAKE_SYSTEMCTL'
#!/usr/bin/env bash
set -Eeuo pipefail
state="${FAKE_STATE:?}"
command_name="${1:-}"
unit="${2:-}"
property="${4:-}"

case "$command_name" in
  show)
    case "$unit:$property" in
      mihomo.service:ActiveEnterTimestampMonotonic)
        cat "$state/mihomo_timestamp"
        ;;
      mihomo-verge-api.service:ActiveState)
        cat "$state/api_state"
        ;;
      mihomo-verge-api.service:NRestarts)
        cat "$state/api_nrestarts"
        ;;
      *)
        exit 1
        ;;
    esac
    ;;
  is-active)
    [[ "$unit" == mihomo-verge-api.service ]] || exit 1
    [[ "$(<"$state/api_state")" == active ]]
    ;;
  daemon-reload)
    printf '%s\n' daemon-reload >>"$state/systemctl.log"
    [[ ! -f "$state/daemon_reload_fail" ]]
    ;;
  restart)
    printf 'restart %s\n' "$unit" >>"$state/systemctl.log"
    if [[ "$unit" != mihomo-verge-api.service ]]; then
      exit 1
    fi
    calls=$(( $(<"$state/api_restart_calls") + 1 ))
    printf '%s\n' "$calls" >"$state/api_restart_calls"
    mode="$(<"$state/mode")"
    if [[ "$mode" == service_failure && "$calls" == 1 ]]; then
      printf '%s\n' failed >"$state/api_state"
    else
      printf '%s\n' active >"$state/api_state"
    fi
    if [[ "$mode" == nrestarts && "$calls" == 1 ]] ||
       [[ "$mode" == explicit_nrestarts && "$calls" == 1 ]] ||
       [[ "$mode" == restore_nrestarts && "$calls" == 2 ]]; then
      printf '%s\n' 1 >"$state/api_nrestarts"
    fi
    if [[ "$mode" == mihomo_drift ]]; then
      printf '%s\n' "$(( $(<"$state/mihomo_timestamp") + 1 ))" >"$state/mihomo_timestamp"
    fi
    ;;
  *)
    exit 1
    ;;
esac
FAKE_SYSTEMCTL

cat >"$FAKE_BIN/ss" <<'FAKE_SS'
#!/usr/bin/env bash
set -Eeuo pipefail
state="${FAKE_STATE:?}"
attempts=$(( $(<"$state/ss_attempts") + 1 ))
printf '%s\n' "$attempts" >"$state/ss_attempts"
mode="$(<"$state/mode")"
calls="$(<"$state/api_restart_calls")"

ready=0
case "$mode" in
  delayed|explicit_delayed|explicit_nrestarts|final_nrestarts|mihomo_drift|slow_health)
    (( attempts >= 2 )) && ready=1
    ;;
  timeout|rollback_failure)
    ready=0
    ;;
  timeout_then_rollback|restore_nrestarts)
    (( calls >= 2 )) && ready=1
    ;;
  service_failure|nrestarts)
    if (( calls >= 2 )) || [[ "$mode" == nrestarts ]]; then
      ready=1
    fi
    ;;
esac

if (( ready )); then
  printf '%s\n' ready >"$state/listener_seen"
  printf 'LISTEN 0 128 172.18.0.1:9091 0.0.0.0:*\n'
fi
exit $(( ready ? 0 : 1 ))
FAKE_SS

cat >"$FAKE_BIN/curl" <<'FAKE_CURL'
#!/usr/bin/env bash
set -Eeuo pipefail
state="${FAKE_STATE:?}"
url="${!#}"
max_time=""
previous=""
for argument in "$@"; do
  if [[ "$previous" == --max-time ]]; then
    max_time="$argument"
  fi
  previous="$argument"
done
if [[ "$url" == *runtime-info* ]]; then
  mode="$(<"$state/mode")"
  [[ "$mode" != runtime_failure ]] || exit 1
  if [[ "$mode" == final_nrestarts && ! -f "$state/final_nrestarts_set" ]]; then
    printf '%s\n' 1 >"$state/api_nrestarts"
    : >"$state/final_nrestarts_set"
  fi
  printf '{"appVersion":"2.5.2-webport.0","apiSchemaVersion":"2026.08-lzc-v2","uiSchemaVersion":"2026.08-lzc-v2","packageFingerprint":"cloud.lazycat.app.clash-verge-for-lc/2.5.2-webport.0","buildId":"%s","gitCommit":"%s","systemProxy":{"mode":"disabled"}}\n' \
    "$EXPECTED_BUILD_ID" "$EXPECTED_GIT_COMMIT"
  exit 0
fi
if [[ "$url" == *healthz* ]]; then
  if [[ ! -f "$state/listener_seen" ]]; then
    printf '%s\n' health_before_listener >"$state/health_before_listener"
    exit 1
  fi
  mode="$(<"$state/mode")"
  if [[ "$mode" == slow_health && "$(<"$state/api_restart_calls")" == 1 ]]; then
    printf '%s\n' "$max_time" >"$state/health_max_time"
    python3 - "$max_time" <<'PY'
import sys
import time

time.sleep(float(sys.argv[1]) + 0.2)
PY
    exit 0
  fi
  [[ "$mode" != health_failure ]] || exit 1
  exit 0
fi
exit 1
FAKE_CURL

cat >"$FAKE_BIN/mihomo" <<'FAKE_MIHOMO'
#!/usr/bin/env bash
set -Eeuo pipefail
[[ "${1:-}" == -v ]] || exit 1
cat "${FAKE_STATE:?}/mihomo_version"
FAKE_MIHOMO

chmod 755 "$FAKE_BIN"/*

write_fixture() {
  local case_root="$1"
  local mode="$2"
  local state="$case_root/state"
  mkdir -p "$state" "$case_root/remote" "$case_root/candidate" "$state/backups"
  printf '%s\n' "$mode" >"$state/mode"
  printf '%s\n' 100 >"$state/mihomo_timestamp"
  printf '%s\n' 'Mihomo v1.19.30-test' >"$state/mihomo_version"
  printf '%s\n' active >"$state/api_state"
  printf '%s\n' 0 >"$state/api_nrestarts"
  printf '%s\n' 0 >"$state/api_restart_calls"
  printf '%s\n' 0 >"$state/ss_attempts"
  : >"$state/systemctl.log"
  printf '%s\n' baseline >"$case_root/remote/api.py"
  printf '%s\n' baseline-unit >"$case_root/remote/unit"
  printf '%s\n' baseline-contract >"$case_root/remote/runtime-contract.json"
  printf '%s\n' 'print("candidate")' >"$case_root/candidate/api.py"
  printf '%s\n' candidate-unit >"$case_root/candidate/unit"
  printf '%s\n' '{"appVersion":"2.5.2-webport.0","apiSchemaVersion":"2026.08-lzc-v2","uiSchemaVersion":"2026.08-lzc-v2","packageFingerprint":"cloud.lazycat.app.clash-verge-for-lc/2.5.2-webport.0","buildId":"test-build","gitCommit":"0123456789012345678901234567890123456789","capabilities":{"systemProxy":{"mode":"disabled"}}}' >"$case_root/candidate/runtime-contract.json"
}

run_candidate() {
  local case_root="$1"
  local output="$case_root/output"
  local status=0
  set +e
  env PATH="$FAKE_BIN:$PATH" \
    FAKE_STATE="$case_root/state" \
    ACTION=deploy \
    REMOTE_API="$case_root/remote/api.py" \
    REMOTE_UNIT="$case_root/remote/unit" \
    REMOTE_CONTRACT="$case_root/remote/runtime-contract.json" \
    REMOTE_ROLLBACK_ROOT="$case_root/state/backups" \
    REMOTE_TMP_API="$case_root/candidate/api.py" \
    REMOTE_TMP_UNIT="$case_root/candidate/unit" \
    REMOTE_TMP_CONTRACT="$case_root/candidate/runtime-contract.json" \
    EXPECTED_BUILD_ID=test-build \
    EXPECTED_GIT_COMMIT=0123456789012345678901234567890123456789 \
    READINESS_TIMEOUT_SECONDS="${TEST_READINESS_TIMEOUT_SECONDS:-1}" \
    READINESS_POLL_INTERVAL_SECONDS="${TEST_READINESS_POLL_INTERVAL_SECONDS:-0.1}" \
    MIHOMO_BIN="$FAKE_BIN/mihomo" \
    INSTALL_BIN="$FAKE_BIN/install" \
    bash "$HELPER" >"$output.out" 2>"$output.err"
  status=$?
  set -e
  printf '%s\n' "$status" >"$output.status"
}

run_rollback() {
  local case_root="$1"
  local backup_id="$2"
  local output="$case_root/rollback-output"
  local status=0
  set +e
  env PATH="$FAKE_BIN:$PATH" \
    FAKE_STATE="$case_root/state" \
    ACTION=rollback \
    ROLLBACK_ID="$backup_id" \
    REMOTE_API="$case_root/remote/api.py" \
    REMOTE_UNIT="$case_root/remote/unit" \
    REMOTE_CONTRACT="$case_root/remote/runtime-contract.json" \
    REMOTE_ROLLBACK_ROOT="$case_root/state/backups" \
    READINESS_TIMEOUT_SECONDS="${TEST_READINESS_TIMEOUT_SECONDS:-1}" \
    READINESS_POLL_INTERVAL_SECONDS="${TEST_READINESS_POLL_INTERVAL_SECONDS:-0.1}" \
    MIHOMO_BIN="$FAKE_BIN/mihomo" \
    INSTALL_BIN="$FAKE_BIN/install" \
    bash "$HELPER" >"$output.out" 2>"$output.err"
  status=$?
  set -e
  printf '%s\n' "$status" >"$output.status"
}

assert_output() {
  local file="$1"
  local pattern="$2"
  rg -q -- "$pattern" "$file" || {
    printf 'ASSERTION FAILED: %s missing from %s\n' "$pattern" "$file" >&2
    sed -n '1,120p' "$file" >&2
    return 1
  }
}

assert_not_output() {
  local file="$1"
  local pattern="$2"
  if rg -q -- "$pattern" "$file"; then
    printf 'ASSERTION FAILED: unexpected %s in %s\n' "$pattern" "$file" >&2
    sed -n '1,120p' "$file" >&2
    return 1
  fi
}

case_root="$TEST_ROOT/delayed"
write_fixture "$case_root" delayed
run_candidate "$case_root"
[[ "$(<"$case_root/output.status")" == 0 ]]
assert_output "$case_root/output.out" 'deploy_ok backup_id='
assert_output "$case_root/output.out" 'api_pair_health=1 mihomo_unchanged=1'
[[ ! -f "$case_root/state/health_before_listener" ]]

case_root="$TEST_ROOT/explicit_rollback"
write_fixture "$case_root" explicit_delayed
mkdir -p "$case_root/state/backups/backup.A1b2C3d4"
cp "$case_root/remote/api.py" "$case_root/state/backups/backup.A1b2C3d4/api.py"
cp "$case_root/remote/unit" "$case_root/state/backups/backup.A1b2C3d4/unit"
cp "$case_root/remote/runtime-contract.json" "$case_root/state/backups/backup.A1b2C3d4/runtime-contract.json"
run_rollback "$case_root" backup.A1b2C3d4
[[ "$(<"$case_root/rollback-output.status")" == 0 ]]
assert_output "$case_root/rollback-output.out" 'rollback_ok backup_id=backup.A1b2C3d4 api_pair_health=1 mihomo_unchanged=1'
[[ ! -f "$case_root/state/health_before_listener" ]]

case_root="$TEST_ROOT/rollback_path_traversal"
write_fixture "$case_root" explicit_delayed
run_rollback "$case_root" ..
[[ "$(<"$case_root/rollback-output.status")" != 0 ]]
assert_output "$case_root/rollback-output.err" 'invalid opaque backup id'

case_root="$TEST_ROOT/explicit_nrestarts"
write_fixture "$case_root" explicit_nrestarts
mkdir -p "$case_root/state/backups/backup.E5f6G7h8"
cp "$case_root/remote/api.py" "$case_root/state/backups/backup.E5f6G7h8/api.py"
cp "$case_root/remote/unit" "$case_root/state/backups/backup.E5f6G7h8/unit"
cp "$case_root/remote/runtime-contract.json" "$case_root/state/backups/backup.E5f6G7h8/runtime-contract.json"
run_rollback "$case_root" backup.E5f6G7h8
[[ "$(<"$case_root/rollback-output.status")" != 0 ]]
assert_output "$case_root/rollback-output.err" 'reason=api_restart_storm'

case_root="$TEST_ROOT/timeout_then_rollback"
write_fixture "$case_root" timeout_then_rollback
run_candidate "$case_root"
[[ "$(<"$case_root/output.status")" != 0 ]]
assert_output "$case_root/output.err" 'reason=api_readiness_timeout'
assert_output "$case_root/output.err" 'api_pair_restored=1 api_pair_health=1 mihomo_unchanged=1'
[[ "$(<"$case_root/remote/api.py")" == baseline ]]

case_root="$TEST_ROOT/rollback_failure"
write_fixture "$case_root" rollback_failure
run_candidate "$case_root"
[[ "$(<"$case_root/output.status")" != 0 ]]
assert_output "$case_root/output.err" 'api_pair_restored=0'
assert_output "$case_root/output.err" 'restore_failure=readiness_timeout'
assert_output "$case_root/output.err" 'mihomo_unchanged=1'
assert_not_output "$case_root/output.err" 'api_pair_restored=1'

case_root="$TEST_ROOT/explicit_rollback_failure"
write_fixture "$case_root" rollback_failure
mkdir -p "$case_root/state/backups/backup.I9j0K1l2"
cp "$case_root/remote/api.py" "$case_root/state/backups/backup.I9j0K1l2/api.py"
cp "$case_root/remote/unit" "$case_root/state/backups/backup.I9j0K1l2/unit"
cp "$case_root/remote/runtime-contract.json" "$case_root/state/backups/backup.I9j0K1l2/runtime-contract.json"
run_rollback "$case_root" backup.I9j0K1l2
[[ "$(<"$case_root/rollback-output.status")" != 0 ]]
assert_output "$case_root/rollback-output.err" 'reason=readiness_timeout'
assert_output "$case_root/rollback-output.err" 'mihomo_unchanged=1 api_pair_health=0'

case_root="$TEST_ROOT/service_failure"
write_fixture "$case_root" service_failure
run_candidate "$case_root"
[[ "$(<"$case_root/output.status")" != 0 ]]
assert_output "$case_root/output.err" 'reason=api_api_service_failed'
assert_output "$case_root/output.err" 'api_pair_restored=1 api_pair_health=1'

case_root="$TEST_ROOT/nrestarts"
write_fixture "$case_root" nrestarts
run_candidate "$case_root"
[[ "$(<"$case_root/output.status")" != 0 ]]
assert_output "$case_root/output.err" 'reason=api_api_restart_storm'
assert_output "$case_root/output.err" 'api_pair_restored=1 api_pair_health=1'

case_root="$TEST_ROOT/restore_nrestarts"
write_fixture "$case_root" restore_nrestarts
run_candidate "$case_root"
[[ "$(<"$case_root/output.status")" != 0 ]]
assert_output "$case_root/output.err" 'api_pair_restored=0'
assert_output "$case_root/output.err" 'restore_failure=api_restart_storm'

case_root="$TEST_ROOT/final_nrestarts"
write_fixture "$case_root" final_nrestarts
run_candidate "$case_root"
[[ "$(<"$case_root/output.status")" != 0 ]]
assert_output "$case_root/output.err" 'reason=api_api_restart_storm'
assert_output "$case_root/output.err" 'api_pair_restored=1 api_pair_health=1'

case_root="$TEST_ROOT/slow_health"
write_fixture "$case_root" slow_health
run_candidate "$case_root"
[[ "$(<"$case_root/output.status")" != 0 ]]
assert_output "$case_root/output.err" 'reason=api_readiness_timeout'
python3 - "$case_root/state/health_max_time" <<'PY'
import sys
from pathlib import Path

budget = float(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not 0 < budget <= 1:
    raise SystemExit(f"unexpected health budget: {budget}")
PY

case_root="$TEST_ROOT/invalid_poll_interval"
write_fixture "$case_root" delayed
TEST_READINESS_POLL_INTERVAL_SECONDS=60 run_candidate "$case_root"
[[ "$(<"$case_root/output.status")" == 2 ]]
assert_output "$case_root/output.err" 'invalid readiness poll interval'

case_root="$TEST_ROOT/mihomo_drift"
write_fixture "$case_root" mihomo_drift
run_candidate "$case_root"
[[ "$(<"$case_root/output.status")" != 0 ]]
assert_output "$case_root/output.err" 'mihomo=drift'
assert_output "$case_root/output.err" 'stop=1'
assert_output "$case_root/output.err" 'api_pair_health=1'
assert_not_output "$case_root/state/systemctl.log" 'restart mihomo.service'

printf 'deploy_verge_api readiness tests passed\n'
