from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("mihomo_core_updater.py")
SPEC = importlib.util.spec_from_file_location("mihomo_core_updater_tests", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load module from {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MihomoCoreUpdaterTests(unittest.TestCase):
    def test_release_tag_rejects_unsafe_characters(self) -> None:
        with self.assertRaises(MODULE.CoreUpdateError):
            MODULE.normalize_tag("v1.19.30; touch /tmp/unexpected")

    def test_resolve_asset_requires_verified_sha256_digest(self) -> None:
        metadata = {
            "assets": [
                {
                    "name": "mihomo-linux-amd64-compatible-v1.19.30.gz",
                    "browser_download_url": "https://example.test/mihomo.gz",
                    "digest": "sha256:" + "a" * 64,
                }
            ]
        }

        result = MODULE.resolve_asset(
            "v1.19.30",
            machine="x86_64",
            metadata=metadata,
        )

        self.assertEqual(result[0], "mihomo-linux-amd64-compatible-v1.19.30.gz")
        self.assertEqual(result[1], "https://example.test/mihomo.gz")
        self.assertEqual(result[2], "a" * 64)

        metadata["assets"][0]["digest"] = ""
        with self.assertRaises(MODULE.CoreUpdateError):
            MODULE.resolve_asset("v1.19.30", machine="x86_64", metadata=metadata)

    def test_resolve_asset_uses_release_metadata_for_alpha_build_suffix(self) -> None:
        metadata = {
            "assets": [
                {
                    "name": "mihomo-linux-amd64-compatible-alpha-65287f0.gz",
                    "browser_download_url": "https://example.test/alpha.gz",
                    "digest": "sha256:" + "b" * 64,
                },
                {
                    "name": "mihomo-linux-amd64-compatible-alpha-65287f0.gz.sha256",
                    "browser_download_url": "https://example.test/alpha.gz.sha256",
                    "digest": None,
                },
            ]
        }

        result = MODULE.resolve_asset(
            "Prerelease-Alpha",
            machine="x86_64",
            metadata=metadata,
        )

        self.assertEqual(result, (
            "mihomo-linux-amd64-compatible-alpha-65287f0.gz",
            "https://example.test/alpha.gz",
            "b" * 64,
        ))

    def test_resolve_asset_rejects_ambiguous_metadata_assets(self) -> None:
        metadata = {
            "assets": [
                {
                    "name": "mihomo-linux-amd64-compatible-alpha-one.gz",
                    "browser_download_url": "https://example.test/one.gz",
                    "digest": "sha256:" + "c" * 64,
                },
                {
                    "name": "mihomo-linux-amd64-compatible-alpha-two.gz",
                    "browser_download_url": "https://example.test/two.gz",
                    "digest": "sha256:" + "d" * 64,
                },
            ]
        }

        with self.assertRaises(MODULE.CoreUpdateError):
            MODULE.resolve_asset("Prerelease-Alpha", machine="x86_64", metadata=metadata)

    def test_asset_version_uses_metadata_suffix_for_prerelease(self) -> None:
        self.assertEqual(
            MODULE.asset_version(
                "mihomo-linux-amd64-compatible-alpha-65287f0.gz",
                "amd64-compatible",
                "Prerelease-Alpha",
            ),
            "alpha-65287f0",
        )

    def test_asset_version_keeps_release_tag_for_unrecognised_override_url(self) -> None:
        self.assertEqual(
            MODULE.asset_version(
                "mihomo.gz",
                "amd64-compatible",
                "v1.19.30",
            ),
            "v1.19.30",
        )

    def test_upgrade_rejects_checksum_mismatch_before_switching_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary = root / "mihomo"
            binary.write_bytes(b"old-core")
            binary.chmod(0o755)
            state_dir = root / "state"
            config = root / "config.yaml"
            config.write_text("secret: test-secret\n", encoding="utf-8")
            lock_path = root / "upgrade.lock"

            with (
                patch.object(MODULE.platform, "machine", return_value="x86_64"),
                patch.object(MODULE, "extract_version", return_value="v1.19.23"),
                patch.object(
                    MODULE,
                    "download_asset",
                    side_effect=lambda _url, destination: destination.write_bytes(b"not-gzip"),
                ),
            ):
                with self.assertRaises(MODULE.CoreUpdateError) as context:
                    MODULE.upgrade_core(
                        tag="v1.19.30",
                        asset_url="https://example.test/mihomo.gz",
                        expected_sha256="b" * 64,
                        binary=binary,
                        state_dir=state_dir,
                        config=config,
                        lock_path=lock_path,
                    )

            self.assertIn("checksum mismatch", str(context.exception))
            self.assertEqual(binary.read_bytes(), b"old-core")
            self.assertFalse((state_dir / "rollback" / "latest.env").exists())

    def test_upgrade_rejects_version_mismatch_before_switching_binary(self) -> None:
        candidate_payload = b"candidate-core"
        candidate_digest = hashlib.sha256(gzip.compress(candidate_payload)).hexdigest()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary = root / "mihomo"
            binary.write_bytes(b"old-core")
            binary.chmod(0o755)
            state_dir = root / "state"
            config = root / "config.yaml"
            config.write_text("secret: test-secret\n", encoding="utf-8")
            lock_path = root / "upgrade.lock"

            with (
                patch.object(MODULE.platform, "machine", return_value="x86_64"),
                patch.object(MODULE, "extract_version", return_value="v1.19.23"),
                patch.object(
                    MODULE,
                    "download_asset",
                    side_effect=lambda _url, destination: destination.write_bytes(
                        gzip.compress(candidate_payload)
                    ),
                ),
                patch.object(
                    MODULE,
                    "verify_binary_version",
                    side_effect=MODULE.CoreUpdateError(
                        "Mihomo version mismatch: expected v1.19.30, got v1.19.29"
                    ),
                ),
            ):
                with self.assertRaises(MODULE.CoreUpdateError) as context:
                    MODULE.upgrade_core(
                        tag="v1.19.30",
                        asset_url="https://example.test/mihomo.gz",
                        expected_sha256=candidate_digest,
                        binary=binary,
                        state_dir=state_dir,
                        config=config,
                        lock_path=lock_path,
                    )

            self.assertIn("version mismatch", str(context.exception))
            self.assertEqual(binary.read_bytes(), b"old-core")
            self.assertFalse((state_dir / "rollback" / "latest.env").exists())

    def test_upgrade_rejects_config_failure_before_switching_binary(self) -> None:
        candidate_payload = b"candidate-core"
        candidate_digest = hashlib.sha256(gzip.compress(candidate_payload)).hexdigest()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary = root / "mihomo"
            binary.write_bytes(b"old-core")
            binary.chmod(0o755)
            state_dir = root / "state"
            config = root / "config.yaml"
            config.write_text("secret: test-secret\n", encoding="utf-8")
            lock_path = root / "upgrade.lock"

            with (
                patch.object(MODULE.platform, "machine", return_value="x86_64"),
                patch.object(MODULE, "extract_version", return_value="v1.19.23"),
                patch.object(
                    MODULE,
                    "download_asset",
                    side_effect=lambda _url, destination: destination.write_bytes(
                        gzip.compress(candidate_payload)
                    ),
                ),
                patch.object(MODULE, "verify_binary_version", return_value="v1.19.30"),
                patch.object(
                    MODULE,
                    "config_test",
                    side_effect=MODULE.CoreUpdateError("Mihomo config test failed"),
                ),
            ):
                with self.assertRaises(MODULE.CoreUpdateError) as context:
                    MODULE.upgrade_core(
                        tag="v1.19.30",
                        asset_url="https://example.test/mihomo.gz",
                        expected_sha256=candidate_digest,
                        binary=binary,
                        state_dir=state_dir,
                        config=config,
                        lock_path=lock_path,
                    )

            self.assertIn("config test failed", str(context.exception))
            self.assertEqual(binary.read_bytes(), b"old-core")
            self.assertFalse((state_dir / "rollback" / "latest.env").exists())

    def test_download_retries_transient_connection_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "mihomo.gz"
            with (
                patch.object(
                    MODULE.urllib.request,
                    "urlopen",
                    side_effect=[MODULE.urllib.error.URLError("connection closed"), io.BytesIO(b"asset")],
                ) as urlopen,
                patch.object(MODULE.time, "sleep"),
            ):
                MODULE.download_asset("https://example.test/mihomo.gz", destination)

            self.assertEqual(destination.read_bytes(), b"asset")
            self.assertEqual(urlopen.call_count, 2)

    def test_upgrade_switches_atomically_and_records_release_receipt(self) -> None:
        candidate_payload = b"candidate-core"
        candidate_digest = hashlib.sha256(gzip.compress(candidate_payload)).hexdigest()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary = root / "mihomo"
            binary.write_bytes(b"old-core")
            state_dir = root / "state"
            config = root / "config.yaml"
            config.write_text("secret: test-secret\n", encoding="utf-8")
            lock_path = root / "upgrade.lock"

            def fake_run(args: list[str], **_kwargs: object) -> CompletedProcess[str]:
                if args[0] == "systemctl":
                    return CompletedProcess(args, 0, "", "")
                if "-t" in args:
                    return CompletedProcess(args, 0, "configuration OK", "")
                if args[0] == str(binary) and binary.read_bytes() == b"old-core":
                    return CompletedProcess(args, 0, "Mihomo Meta v1.19.23 linux amd64\n", "")
                return CompletedProcess(args, 0, "Mihomo Meta v1.19.30 linux amd64\n", "")

            with (
                patch.object(MODULE.platform, "machine", return_value="x86_64"),
                patch.object(MODULE, "run_command", side_effect=fake_run),
                patch.object(MODULE, "probe_controller"),
                patch.object(
                    MODULE,
                    "download_asset",
                    side_effect=lambda _url, destination: destination.write_bytes(
                        gzip.compress(candidate_payload)
                    ),
                ),
            ):
                result = MODULE.upgrade_core(
                    tag="v1.19.30",
                    asset_url="https://example.test/mihomo.gz",
                    expected_sha256=candidate_digest,
                    binary=binary,
                    state_dir=state_dir,
                    config=config,
                    lock_path=lock_path,
                )

            self.assertEqual(result["STATUS"], "success")
            self.assertEqual(result["TARGET_VERSION"], "v1.19.30")
            self.assertEqual(result["ASSET_SHA256"], candidate_digest)
            json.dumps(result)
            self.assertEqual(binary.read_bytes(), candidate_payload)
            backup = Path(result["BACKUP_BIN"])
            self.assertTrue(backup.is_file())
            receipt = (state_dir / "rollback" / "latest.env").read_text(encoding="utf-8")
            self.assertIn("STATUS=success", receipt)
            self.assertIn(f"ASSET_SHA256={candidate_digest}", receipt)

    def test_upgrade_restores_backup_when_health_probe_fails(self) -> None:
        candidate_payload = b"candidate-core"
        candidate_digest = hashlib.sha256(gzip.compress(candidate_payload)).hexdigest()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary = root / "mihomo"
            binary.write_bytes(b"old-core")
            state_dir = root / "state"
            config = root / "config.yaml"
            config.write_text("secret: test-secret\n", encoding="utf-8")
            lock_path = root / "upgrade.lock"

            with (
                patch.object(MODULE.platform, "machine", return_value="x86_64"),
                patch.object(
                    MODULE,
                    "extract_version",
                    side_effect=["v1.19.23", "v1.19.30", "v1.19.23"],
                ),
                patch.object(MODULE, "config_test"),
                patch.object(
                    MODULE,
                    "download_asset",
                    side_effect=lambda _url, destination: destination.write_bytes(
                        gzip.compress(candidate_payload)
                    ),
                ),
                patch.object(
                    MODULE,
                    "run_command",
                    return_value=CompletedProcess(
                        args=["mihomo"],
                        returncode=0,
                        stdout="Mihomo Meta v1.19.30 linux amd64\n",
                        stderr="",
                    ),
                ),
                patch.object(
                    MODULE,
                    "restart_and_probe",
                    side_effect=[
                        MODULE.CoreUpdateError("controller unavailable"),
                        None,
                    ],
                ),
            ):
                with self.assertRaises(MODULE.CoreUpdateError) as context:
                    MODULE.upgrade_core(
                        tag="v1.19.30",
                        asset_url="https://example.test/mihomo.gz",
                        expected_sha256=candidate_digest,
                        binary=binary,
                        state_dir=state_dir,
                        config=config,
                        lock_path=lock_path,
                    )

            self.assertIn("health check failed", str(context.exception))
            self.assertEqual(binary.read_bytes(), b"old-core")
            receipt = (state_dir / "rollback" / "latest.env").read_text(encoding="utf-8")
            self.assertIn("STATUS=rolled_back", receipt)

    def test_already_current_preserves_previous_rollback_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary = root / "mihomo"
            binary.write_bytes(b"current-core")
            state_dir = root / "state"
            config = root / "config.yaml"
            config.write_text("secret: test-secret\n", encoding="utf-8")
            lock_path = root / "upgrade.lock"
            rollback_dir = state_dir / "rollback"
            rollback_dir.mkdir(parents=True)
            backup = rollback_dir / "mihomo.previous.v1.19.23.bak"
            backup.write_bytes(b"old-core")
            receipt = rollback_dir / "latest.env"
            receipt.write_text(
                "\n".join(
                    [
                        "PREV_VERSION=v1.19.23",
                        "TARGET_VERSION=v1.19.30",
                        f"BACKUP_BIN={backup}",
                        "STATUS=pending",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                patch.object(MODULE.platform, "machine", return_value="x86_64"),
                patch.object(MODULE, "extract_version", return_value="v1.19.30"),
                patch.object(MODULE, "config_test"),
                patch.object(MODULE, "probe_controller"),
            ):
                result = MODULE.upgrade_core(
                    tag="v1.19.30",
                    asset_url="https://example.test/mihomo.gz",
                    expected_sha256="a" * 64,
                    binary=binary,
                    state_dir=state_dir,
                    config=config,
                    lock_path=lock_path,
                )

            self.assertEqual(result["STATUS"], "already_current")
            self.assertEqual(result["BACKUP_BIN"], str(backup))
            self.assertIn(f"BACKUP_BIN={backup}", receipt.read_text(encoding="utf-8"))
            self.assertIn("STATUS=success", receipt.read_text(encoding="utf-8"))

    def test_upgrade_lock_rejects_concurrent_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "upgrade.lock"
            with MODULE.upgrade_lock(lock_path):
                with self.assertRaises(MODULE.CoreUpdateError):
                    with MODULE.upgrade_lock(lock_path):
                        pass


if __name__ == "__main__":
    unittest.main()
