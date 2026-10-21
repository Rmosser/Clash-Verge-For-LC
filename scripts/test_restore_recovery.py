#!/usr/bin/env python3
"""Local restore transaction and controller-health drills.

The fixture uses only temporary files and patched controller calls.  It models
the kill window by committing one target from a staged generation, then
starting the process again through ``reconcile_restore_transaction``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "infra" / "microserver" / "mihomo-verge-api.py"
SPEC = importlib.util.spec_from_file_location("mihomo_restore_recovery", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load module from {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RestoreRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="mihomo-restore-drill-")
        root = Path(self.temporary.name)
        data = root / "data"
        etc = root / "etc"
        paths = {
            "DATA_ROOT": data,
            "PROFILES_DIR": data / "profiles",
            "BACKUPS_DIR": data / "backups",
            "ICONS_DIR": data / "icons",
            "LOGS_DIR": data / "logs",
            "VERGE_CONFIG_PATH": data / "verge.json",
            "PROFILES_CONFIG_PATH": data / "profiles.json",
            "OVERLAY_JSON_PATH": data / "system-overlay.json",
            "OVERLAY_YAML_PATH": data / "system-overlay.yaml",
            "DNS_CONFIG_PATH": data / "dns-config.json",
            "PROXY_CHAIN_PATH": data / "proxy-chain.json",
            "OPERATIONS_LOG_PATH": data / "logs" / "operations.log",
            "MIHOMO_CONFIG_PATH": etc / "config.yaml",
            "VERGE_API_SECRET_PATH": etc / "verge-api.secret",
            "RESTORE_TRANSACTION_PATH": data / "restore-transaction.json",
            "ALERT_OUTBOX_PATH": data / "logs" / "alerts.jsonl",
            "ALERT_STATE_PATH": data / "logs" / "alert-state.json",
            "MIHOMO_BIN": root / "missing-mihomo",
        }
        for name, value in paths.items():
            setattr(MODULE, name, value)
        MODULE.RESTORE_FILE_TARGETS = (
            ("verge.json", MODULE.VERGE_CONFIG_PATH),
            ("profiles.json", MODULE.PROFILES_CONFIG_PATH),
            ("system-overlay.json", MODULE.OVERLAY_JSON_PATH),
            ("system-overlay.yaml", MODULE.OVERLAY_YAML_PATH),
            ("dns-config.json", MODULE.DNS_CONFIG_PATH),
            ("config.yaml", MODULE.MIHOMO_CONFIG_PATH),
            ("verge-api.secret", MODULE.VERGE_API_SECRET_PATH),
        )
        MODULE.RESTORE_DIRECTORY_TARGETS = (
            ("profiles", MODULE.PROFILES_DIR),
            ("icons", MODULE.ICONS_DIR),
        )
        MODULE.ALERT_WEBHOOK_URL = ""
        MODULE.ALERT_COOLDOWN_SECONDS = 300
        MODULE.ensure_dirs()
        for name, content in (
            ("verge.json", {"language": "zh"}),
            ("profiles.json", {"current": "old", "items": [{"uid": "old"}]}),
            ("system-overlay.json", {}),
            ("dns-config.json", {}),
        ):
            path = MODULE.DATA_ROOT / name
            path.write_text(json.dumps(content), encoding="utf-8")
        MODULE.OVERLAY_YAML_PATH.write_text("mode: rule\n", encoding="utf-8")
        MODULE.MIHOMO_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        MODULE.MIHOMO_CONFIG_PATH.write_text("mixed-port: 7890\n", encoding="utf-8")
        MODULE.VERGE_API_SECRET_PATH.write_text("old-secret\n", encoding="utf-8")
        MODULE.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        (MODULE.PROFILES_DIR / "old.yaml").write_text("old\n", encoding="utf-8")
        MODULE.ICONS_DIR.mkdir(parents=True, exist_ok=True)
        (MODULE.ICONS_DIR / "old.png").write_bytes(b"old")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_new_archive(self) -> Path:
        archive_path = Path(self.temporary.name) / "new.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            values = {
                "verge.json": '{"language":"en"}',
                "profiles.json": '{"current":"new","items":[{"uid":"new"}]}',
                "system-overlay.json": "{}",
                "system-overlay.yaml": "mode: global\n",
                "dns-config.json": "{}",
                "config.yaml": "mixed-port: 7891\n",
                "verge-api.secret": "new-secret\n",
                "profiles/new.yaml": "new\n",
                "icons/new.png": "new",
            }
            for name, content in values.items():
                archive.writestr(name, content)
        return archive_path

    def test_kill_mid_restore_is_reconciled_to_one_previous_generation(self) -> None:
        if not hasattr(os, "fork"):
            self.skipTest("the kill-window drill requires os.fork")
        archive_path = self.write_new_archive()
        child_pid = os.fork()
        if child_pid == 0:
            try:
                stage = MODULE._prepare_restore_stage(archive_path)
                previous = MODULE._capture_restore_snapshot(".restore-previous-")
                MODULE._write_restore_transaction(
                    {
                        "version": 1,
                        "generation": "kill-mid-restore",
                        "phase": "applying",
                        "stage": str(stage),
                        "previous": str(previous),
                    }
                )
                # Model SIGKILL after the first atomic target replacement.  No
                # finally path runs, so the durable transaction is all restart
                # reconciliation has to identify the mixed-generation window.
                MODULE._replace_restore_file(
                    stage / "payload" / "verge.json",
                    MODULE.VERGE_CONFIG_PATH,
                )
            except BaseException:
                os._exit(97)
            os.kill(os.getpid(), signal.SIGKILL)
        _, wait_status = os.waitpid(child_pid, 0)
        self.assertTrue(os.WIFSIGNALED(wait_status))
        self.assertEqual(os.WTERMSIG(wait_status), signal.SIGKILL)
        self.assertTrue(MODULE.RESTORE_TRANSACTION_PATH.exists())
        self.assertEqual(json.loads(MODULE.VERGE_CONFIG_PATH.read_text())["language"], "en")
        self.assertEqual(
            json.loads(MODULE.PROFILES_CONFIG_PATH.read_text())["current"],
            "old",
        )

        # Exercise the same startup path used by a restarted API process.
        with patch.object(MODULE, "apply_runtime_for_current_or_empty_state"):
            MODULE.ensure_state()
        self.assertEqual(json.loads(MODULE.VERGE_CONFIG_PATH.read_text())["language"], "zh")
        self.assertEqual(
            json.loads(MODULE.PROFILES_CONFIG_PATH.read_text())["current"],
            "old",
        )
        self.assertEqual(
            sorted(path.name for path in MODULE.PROFILES_DIR.iterdir()),
            ["old.yaml"],
        )
        self.assertFalse(MODULE.RESTORE_TRANSACTION_PATH.exists())
        self.assertFalse(list(MODULE.DATA_ROOT.glob(".restore-*")))

    def test_restore_uses_new_staging_and_removes_directory_residue(self) -> None:
        archive_path = self.write_new_archive()
        with patch.object(MODULE, "apply_runtime_for_current_or_empty_state"):
            MODULE.restore_backup_archive(archive_path)

        self.assertEqual(
            json.loads(MODULE.PROFILES_CONFIG_PATH.read_text())["current"],
            "new",
        )
        self.assertEqual(
            sorted(path.name for path in MODULE.PROFILES_DIR.iterdir()),
            ["new.yaml"],
        )
        self.assertEqual(
            sorted(path.name for path in MODULE.ICONS_DIR.iterdir()),
            ["new.png"],
        )
        self.assertFalse((MODULE.DATA_ROOT / "_restore_tmp").exists())
        self.assertFalse(MODULE.RESTORE_TRANSACTION_PATH.exists())

    def test_healthz_is_degraded_when_controller_probe_fails(self) -> None:
        with patch.object(MODULE, "controller_request", side_effect=RuntimeError("down")):
            payload = MODULE.healthz_payload()

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["controller"]["status"], "degraded")
        events = MODULE.ALERT_OUTBOX_PATH.read_text(encoding="utf-8")
        self.assertIn('"component": "controller"', events)


if __name__ == "__main__":
    unittest.main()
