from __future__ import annotations

import copy
import importlib.util
import time
import unittest
import urllib.error
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
            "applied profile demo-profile",
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
                    "https://example.com/sub.yaml",
                    403,
                    "Forbidden",
                    hdrs={},
                    fp=None,
                )

        with patch.object(MODULE.urllib.request, "build_opener", return_value=FakeOpener()):
            with self.assertRaises(MODULE.ApiError) as ctx:
                MODULE.fetch_remote_profile("https://example.com/sub.yaml", {})

        self.assertEqual(ctx.exception.code, "PROFILE_FETCH_HTTP_ERROR")

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


if __name__ == "__main__":
    unittest.main()
