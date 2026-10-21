from __future__ import annotations

import copy
import base64
import gzip
import importlib.util
import json
import ssl
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("mihomo-verge-api.py")
SPEC = importlib.util.spec_from_file_location("mihomo_verge_api", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load module from {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MihomoVergeApiTests(unittest.TestCase):
    def test_operation_log_redacts_credentials_from_urls_and_headers(self) -> None:
        message = (
            "GET /public-config?token=query-secret HTTP/1.1 "
            "Authorization: Bearer header-secret "
            "Cookie: HC-Auth-Token=cookie-secret "
            "https://user:password@sub.example.test/path?access_token=url-secret"
        )

        redacted = MODULE.sanitize_log_text(message)

        for secret in ("query-secret", "header-secret", "cookie-secret", "password", "url-secret"):
            self.assertNotIn(secret, redacted)
        self.assertIn("/public-config?token=<redacted>", redacted)
        self.assertIn("https://<redacted>@sub.example.test/path?access_token=<redacted>", redacted)

    def test_corrupt_json_state_is_logged_with_cause_without_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "profiles.json"
            path.write_text("{not-json", encoding="utf-8")
            log_path = root / "operations.log"
            with (
                patch.object(MODULE, "OPERATIONS_LOG_PATH", log_path),
                patch.object(MODULE, "ensure_dirs"),
            ):
                self.assertEqual(MODULE.load_json(path, {"current": ""}), {"current": ""})

            log = log_path.read_text(encoding="utf-8")

        self.assertIn("state load failed", log)
        self.assertIn("JSONDecodeError", log)
        self.assertNotIn("not-json", log)

    def test_operation_log_includes_request_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "operations.log"
            token = MODULE.LOG_CONTEXT.set(
                {
                    "request_id": "request-123",
                    "command": "update_profile",
                    "profile_uid": "profile-secret-uid",
                    "stage": "fetch",
                }
            )
            try:
                with (
                    patch.object(MODULE, "OPERATIONS_LOG_PATH", log_path),
                    patch.object(MODULE, "ensure_dirs"),
                ):
                    MODULE.append_operation_log("profile update failed")
            finally:
                MODULE.LOG_CONTEXT.reset(token)

            log = log_path.read_text(encoding="utf-8")

        self.assertIn("request_id=request-123", log)
        self.assertIn("command=update_profile", log)
        self.assertIn("profile_uid=uid_hash=", log)
        self.assertIn("stage=fetch", log)
        self.assertNotIn("profile-secret-uid", log)

    def test_filter_mihomo_journal_lines_keeps_only_core_logs(self) -> None:
        rows = MODULE.filter_mihomo_journal_lines(
            [
                'time="2026-03-12T15:16:32.190504926+08:00" level=info msg="line 1"',
                "Started mihomo.service - Mihomo (Clash Meta).",
                'time="2026-03-12T15:16:33.190504926+08:00" level=warning msg="line 2"',
                "",
            ]
        )

        self.assertEqual(
            rows,
            [
                'time="2026-03-12T15:16:32.190504926+08:00" level=info msg="line 1"',
                'time="2026-03-12T15:16:33.190504926+08:00" level=warning msg="line 2"',
            ],
        )

    def test_get_clash_logs_uses_filtered_journal_output(self) -> None:
        with (
            patch.object(MODULE, "ensure_state"),
            patch.object(
                MODULE,
                "run_command",
                return_value=CompletedProcess(
                    args=["journalctl"],
                    returncode=0,
                    stdout=(
                        'time="2026-03-12T15:16:32.190504926+08:00" level=info msg="line 1"\n'
                        "Started mihomo.service - Mihomo (Clash Meta).\n"
                        'time="2026-03-12T15:16:33.190504926+08:00" level=warning msg="line 2"\n'
                    ),
                    stderr="",
                ),
            ),
        ):
            result = MODULE.invoke_command("get_clash_logs", {})

        self.assertEqual(
            result,
            [
                'time="2026-03-12T15:16:32.190504926+08:00" level=info msg="line 1"',
                'time="2026-03-12T15:16:33.190504926+08:00" level=warning msg="line 2"',
            ],
        )

    def test_get_clash_logs_raises_api_error_when_journalctl_fails(self) -> None:
        with (
            patch.object(MODULE, "ensure_state"),
            patch.object(
                MODULE,
                "run_command",
                side_effect=CalledProcessError(
                    returncode=1,
                    cmd=["journalctl"],
                    stderr="permission denied",
                ),
            ),
            patch.object(MODULE, "append_operation_log") as append_operation_log,
        ):
            with self.assertRaises(MODULE.ApiError) as ctx:
                MODULE.invoke_command("get_clash_logs", {})

        self.assertEqual(ctx.exception.code, "GET_CLASH_LOGS_FAILED")
        append_operation_log.assert_called_once()

    def test_normalize_dns_config_prunes_legacy_direct_policy_keys(self) -> None:
        with patch.object(MODULE, "detect_direct_dns_servers", return_value=["192.168.8.1"]):
            normalized = MODULE.normalize_dns_config(
                {
                    "nameserver-policy": {
                        "+.lazycat.cloud": ["192.168.1.1", "fe80::1"],
                        "+.lazycat.cloud.lan": ["192.168.1.1", "fe80::1"],
                        "+.heiyu.space.lan": ["192.168.1.1", "fe80::1"],
                        "+.custom.internal": ["10.0.0.2"],
                    }
                },
                True,
            )

        self.assertEqual(
            normalized["nameserver-policy"],
            {
                "+.heiyu.space": ["192.168.8.1"],
                "+.lazycat.cloud": ["192.168.8.1"],
                "+.baidu.com": ["192.168.8.1"],
                "+.custom.internal": ["10.0.0.2"],
            },
        )

    def test_normalize_dns_config_replaces_legacy_bootstrap_resolvers(self) -> None:
        with patch.object(MODULE, "detect_direct_dns_servers", return_value=["192.168.8.1"]):
            normalized = MODULE.normalize_dns_config(
                {
                    "default-nameserver": ["192.168.1.1", "223.5.5.5", "119.29.29.29"],
                    "proxy-server-nameserver": ["192.168.1.1", "223.5.5.5", "119.29.29.29"],
                },
                True,
            )

        self.assertEqual(
            normalized["default-nameserver"],
            ["192.168.8.1", "223.5.5.5", "119.29.29.29"],
        )
        self.assertEqual(
            normalized["proxy-server-nameserver"],
            ["192.168.8.1", "223.5.5.5", "119.29.29.29"],
        )

    def test_build_default_dns_config_prefers_cn_reachable_doh_endpoints(self) -> None:
        with patch.object(MODULE, "detect_direct_dns_servers", return_value=["192.168.8.1"]):
            normalized = MODULE.build_default_dns_config()

        self.assertEqual(
            normalized["nameserver"],
            [
                "https://dns.alidns.com/dns-query",
                "https://doh.pub/dns-query",
            ],
        )
        self.assertEqual(
            normalized["nameserver-policy"],
            {
                "+.heiyu.space": ["192.168.8.1"],
                "+.lazycat.cloud": ["192.168.8.1"],
                "+.baidu.com": ["192.168.8.1"],
            },
        )

    def test_normalize_dns_config_replaces_legacy_cloudflare_doh_defaults(self) -> None:
        with patch.object(MODULE, "detect_direct_dns_servers", return_value=["192.168.8.1"]):
            normalized = MODULE.normalize_dns_config(
                {
                    "nameserver": [
                        "https://1.1.1.1/dns-query",
                        "https://1.0.0.1/dns-query",
                    ]
                },
                True,
            )

        self.assertEqual(
            normalized["nameserver"],
            [
                "https://dns.alidns.com/dns-query",
                "https://doh.pub/dns-query",
            ],
        )

    def test_normalize_tun_config_keeps_diagnostic_bypass_pool(self) -> None:
        normalized = MODULE.normalize_tun_config(
            {
                "route-exclude-address": [
                    "45.32.239.193/32",
                    "203.0.113.10/32",
                ]
            },
            True,
        )

        self.assertIn("45.63.83.38/32", normalized["route-exclude-address"])
        self.assertIn("45.32.130.255/32", normalized["route-exclude-address"])
        self.assertIn("107.172.76.12/32", normalized["route-exclude-address"])
        self.assertIn("203.0.113.10/32", normalized["route-exclude-address"])

    def test_runtime_info_payload_marks_empty_runtime_as_degraded(self) -> None:
        contract = copy.deepcopy(MODULE.DEFAULT_RUNTIME_CONTRACT)
        with (
            patch.object(MODULE, "load_runtime_contract", return_value=contract),
            patch.object(MODULE, "get_profiles_state", return_value={"current": "", "items": []}),
            patch.object(
                MODULE,
                "get_runtime_profile_health_state",
                return_value=copy.deepcopy(MODULE.DEFAULT_RUNTIME_PROFILE_HEALTH),
            ),
            patch.object(
                MODULE,
                "runtime_probe_health",
                return_value={"status": "ok", "checkedAt": "2026-03-12T00:00:00Z"},
            ),
        ):
            payload = MODULE.runtime_info_payload()

        self.assertEqual(payload["capabilities"]["runtimeProfile"]["mode"], "degraded")
        self.assertEqual(
            payload["capabilities"]["runtimeProfile"]["label"],
            "空配置运行态",
        )
        self.assertEqual(payload["profileHealth"]["status"], "ready")

    def test_runtime_info_payload_forces_system_proxy_disabled_even_with_contract_override(self) -> None:
        contract = copy.deepcopy(MODULE.DEFAULT_RUNTIME_CONTRACT)
        contract["capabilities"]["systemProxy"] = {
            "mode": "enabled",
            "reason": "incorrect override",
            "label": "override",
        }
        with (
            patch.object(MODULE, "load_runtime_contract", return_value=contract),
            patch.object(MODULE, "get_profiles_state", return_value={"current": "", "items": []}),
            patch.object(
                MODULE,
                "get_runtime_profile_health_state",
                return_value=copy.deepcopy(MODULE.DEFAULT_RUNTIME_PROFILE_HEALTH),
            ),
            patch.object(
                MODULE,
                "runtime_probe_health",
                return_value={"status": "ok", "checkedAt": "2026-03-12T00:00:00Z"},
            ),
        ):
            payload = MODULE.runtime_info_payload()

        self.assertEqual(
            payload["capabilities"]["systemProxy"],
            {
                "mode": "disabled",
                "reason": "LazyCat 微服 Web 版不支持接管宿主机系统代理，请使用虚拟网卡模式（TUN）或显式代理入口。",
            },
        )

    def test_runtime_info_payload_includes_profile_health(self) -> None:
        contract = copy.deepcopy(MODULE.DEFAULT_RUNTIME_CONTRACT)
        profile_health = {
            "status": "degraded",
            "activeProfileId": "demo",
            "lastGoodProfileId": "demo",
            "lastAppliedAt": "2026-03-31T01:44:24Z",
            "lastError": "订阅拉取超时（20s）",
            "providerCounts": {"high-premium": 7},
        }
        with (
            patch.object(MODULE, "load_runtime_contract", return_value=contract),
            patch.object(MODULE, "get_profiles_state", return_value={"current": "demo", "items": [{"uid": "demo"}]}),
            patch.object(MODULE, "get_runtime_profile_health_state", return_value=profile_health),
            patch.object(
                MODULE,
                "runtime_probe_health",
                return_value={"status": "ok", "checkedAt": "2026-03-12T00:00:00Z"},
            ),
        ):
            payload = MODULE.runtime_info_payload()

        self.assertEqual(payload["profileHealth"], profile_health)

    def test_alert_outbox_repairs_torn_tail_and_delivers_valid_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outbox = root / "alerts.jsonl"
            state = root / "alert-state.json"
            outbox.parent.mkdir(parents=True, exist_ok=True)
            outbox.write_bytes(b'{"id":"torn"')
            event = {
                "id": "valid-alert-1",
                "createdAt": "2026-09-02T00:00:00Z",
                "component": "controller",
                "status": "degraded",
                "details": "controller down",
                "delivery": "pending",
            }
            captures: list[tuple[str | None, bytes]] = []

            class Handler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:  # noqa: N802
                    length = int(self.headers.get("Content-Length", "0"))
                    captures.append(
                        (self.headers.get("Idempotency-Key"), self.rfile.read(length))
                    )
                    self.send_response(204)
                    self.end_headers()

                def log_message(self, *_args: object) -> None:
                    return

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with (
                    patch.object(MODULE, "ALERT_OUTBOX_PATH", outbox),
                    patch.object(MODULE, "ALERT_STATE_PATH", state),
                    patch.object(
                        MODULE,
                        "ALERT_WEBHOOK_URL",
                        f"http://127.0.0.1:{server.server_port}/alerts",
                    ),
                    patch.object(MODULE, "ensure_dirs"),
                    patch.object(MODULE, "append_operation_log"),
                ):
                    # This append is the old crash window: the repair must
                    # insert a newline before adding the next generation.
                    MODULE._append_alert_event(event)
                    MODULE.reconcile_alert_outbox()
                    MODULE.flush_alert_outbox()
                    MODULE.flush_alert_outbox()
                    alert_health = MODULE.alert_health_payload()

                rows = [
                    json.loads(line)
                    for line in outbox.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                corruption_rows = [
                    json.loads(line)
                    for line in outbox.with_name("alerts.jsonl.corrupt.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(len(captures), 1)
        self.assertEqual(captures[0][0], "valid-alert-1")
        self.assertEqual(json.loads(captures[0][1])["id"], "valid-alert-1")
        self.assertEqual(alert_health["status"], "degraded")
        self.assertEqual(alert_health["corruptionCount"], 1)
        self.assertEqual(sum(row.get("id") == "valid-alert-1" for row in rows), 1)
        self.assertEqual(
            [row.get("status") for row in rows if row.get("type") == "delivery"],
            ["attempting", "delivered"],
        )
        self.assertEqual(len(corruption_rows), 1)
        self.assertEqual(corruption_rows[0]["reason"], "unterminated-or-invalid-json")
        self.assertTrue(corruption_rows[0]["sha256"])

    def test_alert_outbox_keeps_valid_rows_after_a_corrupt_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outbox = root / "alerts.jsonl"
            state = root / "alert-state.json"
            outbox.parent.mkdir(parents=True, exist_ok=True)
            valid = {
                "id": "valid-after-corrupt-1",
                "createdAt": "2026-09-02T00:00:00Z",
                "component": "controller",
                "status": "degraded",
                "details": "controller down",
                "delivery": "pending",
            }
            outbox.write_bytes(b"{not-json}\n" + json.dumps(valid).encode() + b"\n")
            with (
                patch.object(MODULE, "ALERT_OUTBOX_PATH", outbox),
                patch.object(MODULE, "ALERT_STATE_PATH", state),
                patch.object(MODULE, "ensure_dirs"),
                patch.object(MODULE, "append_operation_log"),
            ):
                result = MODULE.reconcile_alert_outbox()
                rows = [
                    json.loads(line)
                    for line in outbox.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                corruption = [
                    json.loads(line)
                    for line in outbox.with_name("alerts.jsonl.corrupt.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]

        self.assertEqual(result["corruptions"], 1)
        self.assertEqual([row["id"] for row in rows], ["valid-after-corrupt-1"])
        self.assertEqual(len(corruption), 1)
        self.assertEqual(corruption[0]["reason"], "invalid-json")

    def test_alert_receipt_interruption_replays_with_same_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outbox = root / "alerts.jsonl"
            state = root / "alert-state.json"
            outbox.parent.mkdir(parents=True, exist_ok=True)
            event = {
                "id": "replay-alert-1",
                "createdAt": "2026-09-02T00:00:00Z",
                "component": "restore",
                "status": "degraded",
                "details": "restore interrupted",
                "delivery": "pending",
            }
            outbox.write_text(json.dumps(event) + "\n", encoding="utf-8")
            keys: list[str | None] = []

            class Handler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:  # noqa: N802
                    length = int(self.headers.get("Content-Length", "0"))
                    self.rfile.read(length)
                    keys.append(self.headers.get("Idempotency-Key"))
                    self.send_response(204)
                    self.end_headers()

                def log_message(self, *_args: object) -> None:
                    return

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            original_append = MODULE._append_alert_event
            interrupted = True

            def append_with_interruption(record: dict[str, object]) -> None:
                nonlocal interrupted
                if record.get("type") == "delivery" and record.get("status") == "delivered" and interrupted:
                    interrupted = False
                    raise OSError("simulated death before receipt")
                original_append(record)

            try:
                with (
                    patch.object(MODULE, "ALERT_OUTBOX_PATH", outbox),
                    patch.object(MODULE, "ALERT_STATE_PATH", state),
                    patch.object(
                        MODULE,
                        "ALERT_WEBHOOK_URL",
                        f"http://127.0.0.1:{server.server_port}/alerts",
                    ),
                    patch.object(MODULE, "ensure_dirs"),
                    patch.object(MODULE, "append_operation_log"),
                    patch.object(
                        MODULE,
                        "_append_alert_event",
                        side_effect=append_with_interruption,
                    ),
                ):
                    MODULE.flush_alert_outbox()
                with (
                    patch.object(MODULE, "ALERT_OUTBOX_PATH", outbox),
                    patch.object(MODULE, "ALERT_STATE_PATH", state),
                    patch.object(
                        MODULE,
                        "ALERT_WEBHOOK_URL",
                        f"http://127.0.0.1:{server.server_port}/alerts",
                    ),
                    patch.object(MODULE, "ensure_dirs"),
                    patch.object(MODULE, "append_operation_log"),
                ):
                    MODULE.flush_alert_outbox()
                rows = [
                    json.loads(line)
                    for line in outbox.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(keys, ["replay-alert-1", "replay-alert-1"])
        delivered = [
            row for row in rows if row.get("type") == "delivery" and row.get("status") == "delivered"
        ]
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0]["idempotencyKey"], "replay-alert-1")

    def test_alert_delivery_failures_stop_at_bounded_attempt_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outbox = root / "alerts.jsonl"
            state = root / "alert-state.json"
            outbox.parent.mkdir(parents=True, exist_ok=True)
            event = {
                "id": "bounded-alert-1",
                "createdAt": "2026-09-02T00:00:00Z",
                "component": "controller",
                "status": "degraded",
                "details": "controller unavailable",
                "delivery": "pending",
            }
            outbox.write_text(json.dumps(event) + "\n", encoding="utf-8")
            keys: list[str | None] = []

            class Handler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:  # noqa: N802
                    length = int(self.headers.get("Content-Length", "0"))
                    self.rfile.read(length)
                    keys.append(self.headers.get("Idempotency-Key"))
                    self.send_response(503)
                    self.end_headers()

                def log_message(self, *_args: object) -> None:
                    return

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with (
                    patch.object(MODULE, "ALERT_OUTBOX_PATH", outbox),
                    patch.object(MODULE, "ALERT_STATE_PATH", state),
                    patch.object(
                        MODULE,
                        "ALERT_WEBHOOK_URL",
                        f"http://127.0.0.1:{server.server_port}/alerts",
                    ),
                    patch.object(MODULE, "ALERT_MAX_ATTEMPTS", 2),
                    patch.object(MODULE, "ALERT_RETRY_BACKOFF_SECONDS", 0.0),
                    patch.object(MODULE, "ensure_dirs"),
                    patch.object(MODULE, "append_operation_log"),
                ):
                    for _ in range(4):
                        MODULE.flush_alert_outbox()
                    alert_health = MODULE.alert_health_payload()
                    rows = [
                        json.loads(line)
                        for line in outbox.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(keys, ["bounded-alert-1", "bounded-alert-1"])
        self.assertEqual(
            [row.get("status") for row in rows if row.get("type") == "delivery"],
            ["attempting", "failed", "attempting", "exhausted"],
        )
        self.assertEqual(alert_health["status"], "degraded")
        self.assertEqual(alert_health["exhausted"], 1)
        self.assertEqual(alert_health["pending"], 1)

    def test_alerting_health_is_degraded_when_unconfigured_or_attempts_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outbox = root / "alerts.jsonl"
            state = root / "alert-state.json"
            outbox.parent.mkdir(parents=True, exist_ok=True)
            event = {
                "id": "exhausted-alert-1",
                "createdAt": "2026-09-02T00:00:00Z",
                "component": "controller",
                "status": "degraded",
                "delivery": "pending",
            }
            receipt = {
                "type": "delivery",
                "alertId": "exhausted-alert-1",
                "status": "exhausted",
                "attempt": 5,
                "idempotencyKey": "exhausted-alert-1",
                "createdAt": "2026-09-02T00:00:01Z",
                "error": "connection refused",
            }
            outbox.write_text(
                "\n".join(json.dumps(row) for row in (event, receipt)) + "\n",
                encoding="utf-8",
            )
            with (
                patch.object(MODULE, "ALERT_OUTBOX_PATH", outbox),
                patch.object(MODULE, "ALERT_STATE_PATH", state),
                patch.object(MODULE, "ALERT_WEBHOOK_URL", ""),
                patch.object(MODULE, "ensure_dirs"),
                patch.object(MODULE, "append_operation_log"),
                patch.object(MODULE, "controller_request", return_value={"version": "1.0"}),
            ):
                payload = MODULE.healthz_payload()
                with (
                    patch.object(
                        MODULE,
                        "load_runtime_contract",
                        return_value=copy.deepcopy(MODULE.DEFAULT_RUNTIME_CONTRACT),
                    ),
                    patch.object(
                        MODULE,
                        "get_profiles_state",
                        return_value={"current": "alert-test", "items": [{"uid": "alert-test"}]},
                    ),
                    patch.object(
                        MODULE,
                        "get_runtime_profile_health_state",
                        return_value=copy.deepcopy(MODULE.DEFAULT_RUNTIME_PROFILE_HEALTH),
                    ),
                    patch.object(
                        MODULE,
                        "runtime_probe_health",
                        return_value={"status": "ok", "checkedAt": "2026-09-02T00:00:00Z"},
                    ),
                ):
                    runtime = MODULE.runtime_info_payload()

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["alerting"]["status"], "degraded")
        self.assertFalse(payload["alerting"]["ready"])
        self.assertIn("not configured", payload["alerting"]["detail"])
        self.assertEqual(runtime["alerting"]["status"], "degraded")
        self.assertFalse(runtime["alerting"]["ready"])

    def test_runtime_contract_probe_payload_contains_only_contract_fields(self) -> None:
        contract = copy.deepcopy(MODULE.DEFAULT_RUNTIME_CONTRACT)
        contract["capabilities"]["systemProxy"] = {
            "mode": "enabled",
            "reason": "incorrect override",
        }
        with patch.object(MODULE, "load_runtime_contract", return_value=contract):
            payload = MODULE.runtime_contract_probe_payload()

        self.assertEqual(payload["appVersion"], "2.5.2-webport.0")
        self.assertEqual(payload["apiSchemaVersion"], "2026.08-lzc-v2")
        self.assertEqual(payload["uiSchemaVersion"], "2026.08-lzc-v2")
        self.assertEqual(payload["systemProxy"], {"mode": "enabled"})
        self.assertNotIn("profileHealth", payload)
        self.assertNotIn("secret", payload)

    def test_check_unlock_status_runs_items_in_parallel(self) -> None:
        test_items = [
            {"name": "ChatGPT", "status": "Pending"},
            {"name": "Claude", "status": "Pending"},
        ]

        def slow_proxy_request(*_args, **_kwargs):
            time.sleep(0.2)
            return 200, b"ok"

        with (
            patch.object(MODULE, "DEFAULT_UNLOCK_ITEMS", test_items),
            patch.object(
                MODULE,
                "UNLOCK_TEST_URLS",
                {"ChatGPT": "https://chat.openai.com/", "Claude": "https://claude.ai/"},
            ),
            patch.object(MODULE, "current_region", return_value="US"),
            patch.object(MODULE, "proxy_request", side_effect=slow_proxy_request),
        ):
            started = time.monotonic()
            result = MODULE.check_unlock_status(timeout_seconds=3)
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.35)
        self.assertEqual(result["summary"]["total"], 2)
        self.assertEqual(result["summary"]["success"], 2)

    def test_run_unlock_probe_passes_timeout_budget_to_unlock_checks(self) -> None:
        with patch.object(
            MODULE,
            "check_unlock_status",
            return_value={
                "items": [],
                "summary": {"total": 0, "success": 0, "failed": 0, "timeout": 0},
            },
        ) as check_unlock_status:
            MODULE.run_unlock_probe(timeout_ms=3000)

        check_unlock_status.assert_called_once_with(None, timeout_seconds=3)

    def test_apply_runtime_for_current_or_empty_state_uses_empty_runtime_log(self) -> None:
        with (
            patch.object(
                MODULE,
                "build_runtime_text_for_current_or_empty_state",
                return_value=("runtime-yaml", "secret", None),
            ),
            patch.object(MODULE, "apply_runtime_text") as apply_runtime_text,
            patch.object(MODULE, "mark_runtime_profile_ready") as mark_runtime_profile_ready,
        ):
            MODULE.apply_runtime_for_current_or_empty_state()

        apply_runtime_text.assert_called_once_with(
            "runtime-yaml",
            "applied empty runtime profile",
        )
        mark_runtime_profile_ready.assert_called_once_with("")

    def test_apply_runtime_for_current_or_empty_state_preserves_profile_log(self) -> None:
        with (
            patch.object(
                MODULE,
                "build_runtime_text_for_current_or_empty_state",
                return_value=("runtime-yaml", "secret", {"uid": "demo-profile"}),
            ),
            patch.object(MODULE, "apply_runtime_text") as apply_runtime_text,
            patch.object(MODULE, "mark_runtime_profile_ready") as mark_runtime_profile_ready,
        ):
            MODULE.apply_runtime_for_current_or_empty_state()

        apply_runtime_text.assert_called_once_with(
            "runtime-yaml",
            f"applied profile profile_uid={MODULE.profile_uid_for_log('demo-profile')}",
        )
        mark_runtime_profile_ready.assert_called_once_with("demo-profile")

    def test_apply_current_profile_records_ready_profile_health(self) -> None:
        with (
            patch.object(MODULE, "current_profile_item", return_value={"uid": "demo-profile"}),
            patch.object(MODULE, "build_runtime_text", return_value=("runtime-yaml", "secret")),
            patch.object(MODULE, "apply_runtime_text"),
            patch.object(
                MODULE,
                "controller_request",
                return_value={
                    "providers": {
                        "high-premium": {"proxies": [1, 2, 3]},
                        "high-standard": {"proxies": [1]},
                    }
                },
            ),
            patch.object(
                MODULE,
                "get_runtime_profile_health_state",
                return_value=copy.deepcopy(MODULE.DEFAULT_RUNTIME_PROFILE_HEALTH),
            ),
            patch.object(MODULE, "save_runtime_profile_health_state") as save_state,
        ):
            MODULE.apply_current_profile()

        saved_state = save_state.call_args.args[0]
        self.assertEqual(saved_state["status"], "ready")
        self.assertEqual(saved_state["activeProfileId"], "demo-profile")
        self.assertEqual(saved_state["lastGoodProfileId"], "demo-profile")
        self.assertEqual(
            saved_state["providerCounts"],
            {"high-premium": 3, "high-standard": 1},
        )
        self.assertEqual(saved_state["lastError"], "")

    def test_apply_current_profile_marks_degraded_when_apply_fails(self) -> None:
        initial_state = {
            "status": "ready",
            "activeProfileId": "demo-profile",
            "lastGoodProfileId": "demo-profile",
            "lastAppliedAt": "2026-03-31T01:44:24Z",
            "lastError": "",
            "providerCounts": {"high-premium": 7},
        }
        with (
            patch.object(MODULE, "current_profile_item", return_value={"uid": "demo-profile"}),
            patch.object(MODULE, "build_runtime_text", return_value=("runtime-yaml", "secret")),
            patch.object(MODULE, "apply_runtime_text", side_effect=RuntimeError("boom")),
            patch.object(MODULE, "get_runtime_profile_health_state", return_value=copy.deepcopy(initial_state)),
            patch.object(MODULE, "save_runtime_profile_health_state") as save_state,
        ):
            with self.assertRaises(RuntimeError):
                MODULE.apply_current_profile()

        saved_state = save_state.call_args.args[0]
        self.assertEqual(saved_state["status"], "degraded")
        self.assertEqual(saved_state["activeProfileId"], "demo-profile")
        self.assertEqual(saved_state["lastGoodProfileId"], "demo-profile")
        self.assertIn("boom", saved_state["lastError"])

    def test_patch_profiles_config_keeps_last_good_runtime_for_transient_empty_state(self) -> None:
        with (
            patch.object(MODULE, "ensure_state"),
            patch.object(
                MODULE,
                "get_profiles_state",
                return_value={"current": "demo", "items": [{"uid": "demo"}]},
            ),
            patch.object(
                MODULE,
                "normalize_profiles_state",
                return_value=({"current": "", "items": []}, True),
            ),
            patch.object(MODULE, "save_profiles_state"),
            patch.object(MODULE, "apply_empty_profile_runtime") as apply_empty_profile_runtime,
            patch.object(MODULE, "mark_runtime_profile_degraded") as mark_runtime_profile_degraded,
            patch.object(MODULE, "append_operation_log") as append_operation_log,
        ):
            MODULE.invoke_command(
                "patch_profiles_config",
                {"profiles": {"current": ""}},
            )

        apply_empty_profile_runtime.assert_not_called()
        mark_runtime_profile_degraded.assert_called_once()
        append_operation_log.assert_called_once()

    def test_update_current_remote_profile_marks_runtime_degraded_on_fetch_timeout(self) -> None:
        timeout_error = MODULE.ApiError(
            "PROFILE_FETCH_TIMEOUT",
            "订阅拉取超时（20s）",
            status=504,
        )
        profiles = {
            "current": "demo",
            "items": [
                {
                    "uid": "demo",
                    "type": "remote",
                    "url": "https://example.com/sub.yaml",
                    "option": {},
                }
            ],
        }
        with (
            patch.object(MODULE, "ensure_state"),
            patch.object(MODULE, "get_profiles_state", return_value=profiles),
            patch.object(MODULE, "fetch_remote_profile", side_effect=timeout_error),
            patch.object(MODULE, "mark_runtime_profile_degraded") as mark_runtime_profile_degraded,
        ):
            with self.assertRaises(MODULE.ApiError):
                MODULE.invoke_command("update_profile", {"index": "demo"})

        mark_runtime_profile_degraded.assert_called_once()

    def test_patch_verge_config_forces_enable_system_proxy_false(self) -> None:
        verge_state = {
            "enable_system_proxy": False,
            "enable_tun_mode": True,
            "language": "zh",
        }
        with (
            patch.object(MODULE, "ensure_state"),
            patch.object(MODULE, "get_verge_config_state", return_value=verge_state),
            patch.object(MODULE, "save_verge_config_state") as save_verge_config_state,
            patch.object(MODULE, "append_operation_log") as append_operation_log,
            patch.object(MODULE, "apply_runtime_for_current_or_empty_state") as apply_runtime,
        ):
            MODULE.invoke_command(
                "patch_verge_config",
                {"payload": {"enable_system_proxy": True}},
            )

        saved_payload = save_verge_config_state.call_args.args[0]
        self.assertIs(saved_payload["enable_system_proxy"], False)
        append_operation_log.assert_called_once()
        apply_runtime.assert_not_called()

    def test_validate_remote_profile_payload_accepts_provider_profile(self) -> None:
        payload = """
proxy-providers:
  demo:
    type: http
    url: https://example.com/providers/demo.yaml
proxy-groups:
  - name: PROXY
    type: select
    use:
      - demo
rules:
  - MATCH,PROXY
"""
        summary = MODULE.validate_remote_profile_payload(
            payload,
            content_type="application/x-yaml",
            source_url="https://example.com/sub.yaml",
        )

        self.assertTrue(summary["hasProxyGroups"])
        self.assertTrue(summary["hasRules"])
        self.assertFalse(summary["hasProxies"])
        self.assertTrue(summary["hasProxyProviders"])

    def test_validate_remote_profile_payload_rejects_html_login_page(self) -> None:
        with self.assertRaises(MODULE.ApiError) as ctx:
            MODULE.validate_remote_profile_payload(
                "<html><body>Please login</body></html>",
                content_type="text/html; charset=utf-8",
                source_url="https://example.com/sub.yaml",
            )

        self.assertEqual(ctx.exception.code, "PROFILE_HTML_LOGIN_PAGE")

    def test_validate_remote_profile_payload_rejects_missing_required_sections(self) -> None:
        with self.assertRaises(MODULE.ApiError) as ctx:
            MODULE.validate_remote_profile_payload(
                "proxy-groups:\n  - name: PROXY\n    type: select\nrules: []\n",
                content_type="application/x-yaml",
                source_url="https://example.com/sub.yaml",
            )

        self.assertEqual(ctx.exception.code, "PROFILE_CONTENT_INVALID")

    def test_resolve_remote_profile_name_hint_prioritizes_profile_title(self) -> None:
        name = MODULE.resolve_remote_profile_name_hint(
            "https://example.com/clash.yaml",
            {
                "profile-title": "My LZC Profile",
                "content-disposition": 'attachment; filename="ignored.yaml"',
            },
        )
        self.assertEqual(name, "My LZC Profile")

    def test_fetch_remote_profile_maps_http_error(self) -> None:
        class FakeOpener:
            def open(self, *_args, **_kwargs):
                raise urllib.error.HTTPError(
                    "https://user:password@example.com/sub.yaml?token=synthetic",
                    403,
                    "Forbidden",
                    hdrs={},
                    fp=None,
                )

        with patch.object(MODULE.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaises(MODULE.ApiError) as ctx:
                MODULE.fetch_remote_profile(
                    "https://user:password@example.com/sub.yaml?token=synthetic",
                    {},
                )

        self.assertEqual(ctx.exception.code, "PROFILE_FETCH_HTTP_ERROR")
        self.assertEqual(ctx.exception.warning["url"], "https://example.com/sub.yaml")
        self.assertNotIn("synthetic", repr(ctx.exception.warning))
        self.assertNotIn("password", repr(ctx.exception.warning))

    def test_fetch_remote_profile_maps_timeout_error(self) -> None:
        class FakeOpener:
            def open(self, *_args, **_kwargs):
                raise TimeoutError("timed out")

        with patch.object(MODULE.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaises(MODULE.ApiError) as ctx:
                MODULE.fetch_remote_profile("https://example.com/sub.yaml", {})

        self.assertEqual(ctx.exception.code, "PROFILE_FETCH_TIMEOUT")

    def test_fetch_remote_profile_maps_timeout_urLError(self) -> None:
        class FakeOpener:
            def open(self, *_args, **_kwargs):
                raise urllib.error.URLError(TimeoutError("timed out"))

        with patch.object(MODULE.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaises(MODULE.ApiError) as ctx:
                MODULE.fetch_remote_profile("https://example.com/sub.yaml", {})

        self.assertEqual(ctx.exception.code, "PROFILE_FETCH_TIMEOUT")

    def test_fetch_remote_profile_maps_network_error(self) -> None:
        class FakeOpener:
            def open(self, *_args, **_kwargs):
                raise urllib.error.URLError("network down")

        with patch.object(MODULE.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaises(MODULE.ApiError) as ctx:
                MODULE.fetch_remote_profile("https://example.com/sub.yaml", {})

        self.assertEqual(ctx.exception.code, "PROFILE_FETCH_NETWORK_ERROR")

    def test_runtime_contract_is_v252_webport(self) -> None:
        self.assertEqual(MODULE.APP_VERSION, "2.5.2-webport.0")
        self.assertEqual(MODULE.DEFAULT_RUNTIME_CONTRACT["apiSchemaVersion"], "2026.08-lzc-v2")
        self.assertEqual(MODULE.DEFAULT_RUNTIME_CONTRACT["uiSchemaVersion"], "2026.08-lzc-v2")

    def test_get_clash_mode_prefers_overlay_and_group_order_uses_runtime_config(self) -> None:
        with patch.object(MODULE, "ensure_state"), patch.object(
            MODULE, "load_overlay", return_value={"mode": "global"}
        ):
            self.assertEqual(MODULE.invoke_command("get_clash_mode", {}), "global")

        with patch.object(MODULE, "ensure_state"), patch.object(
            MODULE,
            "controller_request",
            return_value={
                "proxy-groups": [
                    {"name": "PROXY"},
                    {"name": "fallback"},
                    {"name": "PROXY"},
                ]
            },
        ):
            self.assertEqual(
                MODULE.invoke_command("get_runtime_proxy_group_order", {}),
                ["PROXY", "fallback"],
            )

    def test_provider_delay_encodes_provider_proxy_and_query_separately(self) -> None:
        with patch.object(MODULE, "ensure_state"), patch.object(
            MODULE, "controller_request", return_value={"delay": 321}
        ) as controller_request:
            result = MODULE.invoke_command(
                "clash_api_get_provider_proxy_delay",
                {
                    "provider": "provider/one",
                    "name": "node / one",
                    "url": "https://example.test/p?q=a b",
                    "timeout": 3210,
                },
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["latencyMs"], 321)
        path = controller_request.call_args.args[1]
        self.assertIn("/providers/proxies/provider%2Fone/node%20%2F%20one/delay?", path)
        self.assertIn("url=https%3A%2F%2Fexample.test%2Fp%3Fq%3Da+b", path)

    def test_provider_delay_maps_controller_timeout(self) -> None:
        error = urllib.error.HTTPError(
            "http://controller.test",
            504,
            "Gateway Timeout",
            hdrs={},
            fp=None,
        )
        with patch.object(MODULE, "ensure_state"), patch.object(
            MODULE, "controller_request", side_effect=error
        ):
            result = MODULE.invoke_command(
                "clash_api_get_provider_proxy_delay",
                {"provider": "demo", "name": "node", "timeout": 1000},
            )

        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["errorCode"], "timeout")

    def test_fetch_remote_profile_decompresses_gzip_and_handles_empty_password_auth(self) -> None:
        profile = (
            "proxies:\n  - name: demo\n    type: direct\n"
            "proxy-groups:\n  - name: PROXY\n    type: select\n    proxies: [demo]\n"
            "rules:\n  - MATCH,PROXY\n"
        ).encode("utf-8")

        class FakeResponse:
            headers = {
                "Content-Encoding": "gzip",
                "Content-Type": "application/x-yaml",
                "subscription-userinfo": "",
            }
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def getcode(self):
                return self.status

            def read(self, _size=-1):
                return gzip.compress(profile)

        class FakeOpener:
            def __init__(self):
                self.request = None

            def open(self, request, timeout):
                self.request = request
                return FakeResponse()

        opener = FakeOpener()
        with patch.object(MODULE.urllib.request, "build_opener", return_value=opener):
            payload, _extra, metadata = MODULE.fetch_remote_profile(
                "https://user:@example.test/profile.yaml?token=synthetic",
                {},
            )

        self.assertIn("proxy-groups:", payload)
        self.assertEqual(metadata["url"], "https://example.test/profile.yaml")
        self.assertEqual(
            opener.request.full_url,
            "https://example.test/profile.yaml?token=synthetic",
        )
        self.assertEqual(
            opener.request.headers["Authorization"],
            "Basic " + base64.b64encode(b"user:").decode("ascii"),
        )

    def test_fetch_remote_profile_rejects_decompressed_payload_over_limit(self) -> None:
        max_bytes = 64
        compressed_payload = gzip.compress(b"x" * 256)
        self.assertLessEqual(len(compressed_payload), max_bytes + 1)

        class FakeResponse:
            headers = {"Content-Encoding": "gzip", "Content-Type": "application/x-yaml"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def getcode(self):
                return 200

            def read(self, size=-1):
                self.read_size = size
                return compressed_payload

        response = FakeResponse()

        class FakeOpener:
            def open(self, *_args, **_kwargs):
                return response

        with patch.object(MODULE, "PROFILE_MAX_BYTES", max_bytes), patch.object(
            MODULE.urllib.request, "build_opener", return_value=FakeOpener()
        ):
            with self.assertRaises(MODULE.ApiError) as ctx:
                MODULE.fetch_remote_profile("https://example.test/profile.yaml", {})

        self.assertEqual(ctx.exception.code, "PROFILE_CONTENT_TOO_LARGE")
        self.assertEqual(response.read_size, max_bytes + 1)

    def test_fetch_remote_profile_rejects_raw_payload_without_unbounded_read(self) -> None:
        class FakeResponse:
            headers = {"Content-Type": "application/x-yaml"}

            def __init__(self):
                self.read_sizes = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def getcode(self):
                return 200

            def read(self, size=-1):
                self.read_sizes.append(size)
                return b"x" * 9

        response = FakeResponse()

        class FakeOpener:
            def open(self, *_args, **_kwargs):
                return response

        with patch.object(MODULE, "PROFILE_MAX_BYTES", 8), patch.object(
            MODULE.urllib.request, "build_opener", return_value=FakeOpener()
        ):
            with self.assertRaises(MODULE.ApiError) as ctx:
                MODULE.fetch_remote_profile("https://example.test/profile.yaml", {})

        self.assertEqual(ctx.exception.code, "PROFILE_CONTENT_TOO_LARGE")
        self.assertEqual(response.read_sizes, [9])

    def test_profile_url_credentials_preserves_query_without_transport_userinfo(self) -> None:
        transport_url, username, password = MODULE.profile_url_credentials(
            "https://user:p%40ss@example.test/profile.yaml?token=synthetic&foo=a%2Bb"
        )

        self.assertEqual(
            transport_url,
            "https://example.test/profile.yaml?token=synthetic&foo=a%2Bb",
        )
        self.assertEqual(username, "user")
        self.assertEqual(password, "p@ss")

    def test_profile_redirect_handler_removes_authorization_across_origins(self) -> None:
        request = urllib.request.Request("https://example.test/profile.yaml")
        request.add_header("Authorization", "Basic synthetic")
        redirected = MODULE.ProfileRedirectHandler().redirect_request(
            request,
            None,
            302,
            "Found",
            {"location": "https://other.example/profile.yaml"},
            "https://other.example/profile.yaml",
        )

        self.assertIsNotNone(redirected)
        assert redirected is not None
        self.assertNotIn("Authorization", redirected.headers)
        self.assertNotIn("Authorization", redirected.unredirected_hdrs)

    def test_fetch_remote_profile_maps_tls_error_to_stable_code(self) -> None:
        class FakeOpener:
            def open(self, *_args, **_kwargs):
                raise urllib.error.URLError(ssl.SSLError("handshake failed"))

        with patch.object(MODULE.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaises(MODULE.ApiError) as ctx:
                MODULE.fetch_remote_profile("https://example.test/profile.yaml", {})

        self.assertEqual(ctx.exception.code, "PROFILE_FETCH_TLS_ERROR")
        self.assertNotIn("handshake failed", ctx.exception.message)

    def test_profile_validation_outcome_reports_busy_and_transient_empty(self) -> None:
        with patch.object(MODULE, "ensure_state"), patch.object(
            MODULE,
            "get_profiles_state",
            return_value={"current": "demo", "items": [{"uid": "demo"}]},
        ), patch.object(
            MODULE,
            "normalize_profiles_state",
            return_value=({"current": "", "items": []}, True),
        ), patch.object(MODULE, "save_profiles_state"), patch.object(
            MODULE, "mark_runtime_profile_degraded"
        ), patch.object(MODULE, "append_operation_log"):
            result = MODULE.invoke_command(
                "patch_profiles_config",
                {"profiles": {"current": ""}},
            )
        self.assertEqual(result, {"status": "skipped", "reason": "transient-empty-last-good"})

        self.assertTrue(MODULE.PROFILE_MUTATION_LOCK.acquire(blocking=False))
        try:
            with patch.object(MODULE, "ensure_state"):
                self.assertEqual(
                    MODULE.invoke_command("enhance_profiles", {}),
                    {"status": "busy"},
                )
        finally:
            MODULE.PROFILE_MUTATION_LOCK.release()

    def test_profile_validation_rolls_back_profile_state_on_apply_failure(self) -> None:
        before = {"current": "old", "items": [{"uid": "old"}]}
        after = {"current": "new", "items": [{"uid": "new"}]}
        with patch.object(MODULE, "ensure_state"), patch.object(
            MODULE, "get_profiles_state", return_value=before
        ), patch.object(
            MODULE, "normalize_profiles_state", return_value=(after, True)
        ), patch.object(MODULE, "save_profiles_state") as save_profiles_state, patch.object(
            MODULE, "apply_current_profile", side_effect=RuntimeError("synthetic apply failure")
        ), patch.object(MODULE, "append_operation_log"):
            result = MODULE.invoke_command(
                "patch_profiles_config",
                {"profiles": {"current": "new"}},
            )

        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["kind"], "PROFILE_APPLY_FAILED")
        self.assertEqual(save_profiles_state.call_args_list[-1].args[0], before)


if __name__ == "__main__":
    unittest.main()
