from __future__ import annotations

import copy
import importlib.util
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
                "+.heiyu.space": ["192.168.1.1", "fe80::1"],
                "+.baidu.com": ["192.168.1.1", "fe80::1"],
                "+.custom.internal": ["10.0.0.2"],
            },
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

    def test_apply_runtime_for_current_or_empty_state_uses_empty_runtime_log(self) -> None:
        with (
            patch.object(
                MODULE,
                "build_runtime_text_for_current_or_empty_state",
                return_value=("runtime-yaml", "secret", None),
            ),
            patch.object(MODULE, "apply_runtime_text") as apply_runtime_text,
        ):
            MODULE.apply_runtime_for_current_or_empty_state()

        apply_runtime_text.assert_called_once_with(
            "runtime-yaml",
            "applied empty runtime profile",
        )

    def test_apply_runtime_for_current_or_empty_state_preserves_profile_log(self) -> None:
        with (
            patch.object(
                MODULE,
                "build_runtime_text_for_current_or_empty_state",
                return_value=("runtime-yaml", "secret", {"uid": "demo-profile"}),
            ),
            patch.object(MODULE, "apply_runtime_text") as apply_runtime_text,
        ):
            MODULE.apply_runtime_for_current_or_empty_state()

        apply_runtime_text.assert_called_once_with(
            "runtime-yaml",
            "applied profile demo-profile",
        )

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
