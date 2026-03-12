from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("mihomo-verge-api.py")
SPEC = importlib.util.spec_from_file_location("mihomo_verge_api", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load module from {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MihomoVergeApiTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
