#!/usr/bin/env python3
"""Safe, version-pinned Mihomo core upgrades for the host-native runtime."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import gzip
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator


REPOSITORY = "MetaCubeX/mihomo"
RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases"
DOWNLOAD_BASE = f"https://github.com/{REPOSITORY}/releases/download"
USER_AGENT = "Clash-Verge-For-LC-mihomo-updater/1.0"
DEFAULT_STABLE_TAG = os.environ.get("MIHOMO_CORE_VERSION", "v1.19.30")
DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_TIMEOUT = 120

DEFAULT_BINARY = Path("/usr/local/bin/mihomo")
DEFAULT_STATE_DIR = Path("/var/lib/mihomo")
DEFAULT_CONFIG = Path("/etc/mihomo/config.yaml")
DEFAULT_SERVICE = "mihomo"
DEFAULT_CONTROLLER_URL = "http://172.18.0.1:9090"
DEFAULT_LOCK_PATH = Path("/var/lock/mihomo-core-upgrade.lock")

ASSET_ARCHES = {
    "x86_64": "amd64-compatible",
    "amd64": "amd64-compatible",
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv7l": "armv7",
    "armv7": "armv7",
    "i386": "386",
    "i686": "386",
}
OUTPUT_ARCHES = {
    "amd64-compatible": "amd64",
    "arm64": "arm64",
    "armv7": "arm",
    "386": "386",
}
VERSION_PATTERN = re.compile(r"Mihomo Meta\s+(?P<version>[^\s]+)", re.IGNORECASE)
SECRET_PATTERN = re.compile(r"^\s*secret\s*:\s*(?P<value>.*?)\s*$")
TAG_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class CoreUpdateError(RuntimeError):
    """Raised when a core upgrade cannot be completed safely."""


def run_command(
    args: list[str],
    *,
    check: bool = True,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def normalize_tag(tag: str) -> str:
    value = str(tag or "").strip()
    if not value:
        raise CoreUpdateError("Mihomo release tag is empty")
    if not TAG_PATTERN.fullmatch(value):
        raise CoreUpdateError("Mihomo release tag contains unsupported characters")
    if not value.startswith("v") and re.fullmatch(r"\d+\.\d+\.\d+", value):
        value = f"v{value}"
    return value


def asset_arch_for_machine(machine: str | None = None) -> str:
    value = (machine or platform.machine()).strip().lower()
    try:
        return ASSET_ARCHES[value]
    except KeyError as exc:
        raise CoreUpdateError(f"unsupported architecture: {value}") from exc


def asset_name_prefix(asset_arch: str) -> str:
    """Return the metadata-controlled prefix for a Linux release asset."""
    return f"mihomo-linux-{asset_arch}-"


def asset_version(
    asset_name: str, asset_arch: str, fallback: str
) -> str:
    """Extract the binary version from the metadata-selected asset name.

    Stable releases use a semver tag in the filename, while the prerelease
    channel currently publishes names such as ``...-alpha-65287f0.gz`` under
    the label ``Prerelease-Alpha``.  The release tag is therefore not always
    the version reported by ``mihomo -v``.
    """
    prefix = asset_name_prefix(asset_arch)
    if asset_name.startswith(prefix) and asset_name.endswith(".gz"):
        candidate = asset_name[len(prefix) : -len(".gz")]
        if candidate:
            return normalize_tag(candidate)
    return normalize_tag(fallback)


def normalize_digest(value: str) -> str:
    digest = str(value or "").strip().lower()
    if digest.startswith("sha256:"):
        digest = digest.split(":", 1)[1]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise CoreUpdateError("release asset does not provide a valid SHA256 digest")
    return digest


def request_json(url: str, *, timeout: int = 20) -> dict[str, Any] | list[Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise CoreUpdateError(f"unable to read Mihomo release metadata: {exc}") from exc


def resolve_release_tag(channel: str = "stable", tag: str | None = None) -> str:
    if tag:
        return normalize_tag(tag)
    if channel == "stable":
        return normalize_tag(DEFAULT_STABLE_TAG)
    if channel != "alpha":
        raise CoreUpdateError(f"unsupported Mihomo release channel: {channel}")

    payload = request_json(f"{RELEASE_API}?per_page=30")
    if not isinstance(payload, list):
        raise CoreUpdateError("Mihomo release list has an unexpected shape")
    for release in payload:
        if isinstance(release, dict) and release.get("prerelease") and not release.get("draft"):
            return normalize_tag(str(release.get("tag_name") or ""))
    raise CoreUpdateError("no prerelease Mihomo release found")


def release_metadata(tag: str) -> dict[str, Any]:
    normalized = normalize_tag(tag)
    payload = request_json(f"{RELEASE_API}/tags/{normalized}")
    if not isinstance(payload, dict):
        raise CoreUpdateError("Mihomo release metadata has an unexpected shape")
    if payload.get("draft"):
        raise CoreUpdateError(f"Mihomo release {normalized} is a draft")
    return payload


def resolve_asset(
    tag: str,
    *,
    machine: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    normalized = normalize_tag(tag)
    asset_arch = asset_arch_for_machine(machine)
    payload = metadata if metadata is not None else release_metadata(normalized)
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise CoreUpdateError("Mihomo release has no asset list")
    prefix = asset_name_prefix(asset_arch)
    candidates = [
        item
        for item in assets
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and item["name"].startswith(prefix)
        and item["name"].endswith(".gz")
    ]
    if len(candidates) != 1:
        raise CoreUpdateError(
            f"Mihomo release {normalized} has {len(candidates)} metadata assets for {prefix}"
        )
    selected = candidates[0]

    name = str(selected.get("name") or "")
    digest = normalize_digest(str(selected.get("digest") or ""))
    url = str(selected.get("browser_download_url") or "")
    if not url:
        raise CoreUpdateError(f"Mihomo release asset {name} has no download URL")
    return name, url, digest


def extract_version(binary: Path) -> str:
    try:
        result = run_command([str(binary), "-v"], check=False, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CoreUpdateError(f"unable to execute Mihomo binary: {exc}") from exc
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    match = VERSION_PATTERN.search(output)
    if result.returncode != 0 or not match:
        raise CoreUpdateError("downloaded file is not a usable Mihomo binary")
    return normalize_tag(match.group("version"))


def expected_output_arch(asset_arch: str) -> str:
    try:
        return OUTPUT_ARCHES[asset_arch]
    except KeyError as exc:
        raise CoreUpdateError(f"unsupported Mihomo asset architecture: {asset_arch}") from exc


def verify_binary_version(binary: Path, tag: str, asset_arch: str) -> str:
    version = extract_version(binary)
    expected = normalize_tag(tag)
    if version != expected:
        raise CoreUpdateError(f"Mihomo version mismatch: expected {expected}, got {version}")

    try:
        result = run_command([str(binary), "-v"], check=False, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CoreUpdateError(f"unable to inspect Mihomo binary architecture: {exc}") from exc
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    expected_arch = expected_output_arch(asset_arch)
    if expected_arch not in output:
        raise CoreUpdateError(
            f"Mihomo architecture mismatch: expected {expected_arch}, got {output.splitlines()[0] if output else 'unknown'}"
        )
    return version


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_asset(url: str, destination: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            destination.unlink(missing_ok=True)
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response, destination.open(
                "wb"
            ) as handle:
                shutil.copyfileobj(response, handle)
            return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            destination.unlink(missing_ok=True)
            if attempt < DOWNLOAD_ATTEMPTS:
                time.sleep(attempt)
    raise CoreUpdateError(f"unable to download Mihomo asset after {DOWNLOAD_ATTEMPTS} attempts: {last_error}") from last_error


def extract_asset(source: Path, destination: Path) -> None:
    try:
        with gzip.open(source, "rb") as compressed, destination.open("wb") as binary:
            shutil.copyfileobj(compressed, binary)
    except (OSError, EOFError) as exc:
        raise CoreUpdateError(f"unable to decompress Mihomo asset: {exc}") from exc
    os.chmod(destination, 0o755)


def config_test(binary: Path, state_dir: Path, config: Path) -> None:
    try:
        result = run_command(
            [str(binary), "-t", "-d", str(state_dir), "-f", str(config)],
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CoreUpdateError(f"unable to run Mihomo config test: {exc}") from exc
    if result.returncode != 0:
        detail = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        raise CoreUpdateError(f"Mihomo config test failed: {detail or result.returncode}")


def read_controller_secret(config: Path) -> str:
    if not config.exists():
        return ""
    for line in config.read_text(encoding="utf-8").splitlines():
        match = SECRET_PATTERN.match(line)
        if not match:
            continue
        value = match.group("value").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value
    return ""


def probe_controller(url: str, config: Path, *, timeout: int = 12) -> None:
    secret = read_controller_secret(config)
    headers = {"User-Agent": USER_AGENT}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    endpoint = f"{url.rstrip('/')}/version"
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        request = urllib.request.Request(endpoint, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                if 200 <= response.status < 300:
                    return
                last_error = CoreUpdateError(f"controller returned HTTP {response.status}")
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
        time.sleep(1)
    raise CoreUpdateError(f"Mihomo controller probe failed: {last_error}")


def atomic_replace(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)
    os.chmod(destination, 0o755)


def metadata_path(state_dir: Path) -> Path:
    return state_dir / "rollback" / "latest.env"


def read_metadata(path: Path) -> dict[str, str]:
    if not path.exists():
        raise CoreUpdateError(f"rollback metadata not found: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = raw_line.partition("=")
        if separator and re.fullmatch(r"[A-Z0-9_]+", key):
            values[key] = value
    return values


def write_metadata(path: Path, values: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z0-9_]+", key):
            continue
        text = str(value or "").replace("\n", " ")
        lines.append(f"{key}={text}")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=str(path.parent)
    ) as handle:
        handle.write("\n".join(lines) + "\n")
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


@contextlib.contextmanager
def upgrade_lock(path: Path = DEFAULT_LOCK_PATH) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CoreUpdateError("another Mihomo core upgrade is already running") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def restart_and_probe(
    *,
    service: str,
    controller_url: str,
    config: Path,
) -> None:
    run_command(["systemctl", "restart", service], timeout=60)
    run_command(["systemctl", "is-active", "--quiet", service], timeout=30)
    probe_controller(controller_url, config)


def _backup_binary(binary: Path, rollback_dir: Path, version: str) -> Path:
    rollback_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    backup = rollback_dir / f"mihomo.{timestamp}.{version or 'unknown'}.bak"
    shutil.copy2(binary, backup)
    os.chmod(backup, 0o700)
    return backup


def upgrade_core(
    *,
    tag: str | None = None,
    channel: str = "stable",
    asset_url: str | None = None,
    expected_sha256: str | None = None,
    binary: Path = DEFAULT_BINARY,
    state_dir: Path = DEFAULT_STATE_DIR,
    config: Path = DEFAULT_CONFIG,
    service: str = DEFAULT_SERVICE,
    controller_url: str = DEFAULT_CONTROLLER_URL,
    lock_path: Path = DEFAULT_LOCK_PATH,
    auto_rollback: bool = True,
) -> dict[str, str]:
    release_tag = resolve_release_tag(channel, tag)
    asset_arch = asset_arch_for_machine()
    if asset_url and expected_sha256:
        # Explicit operator overrides are still accepted, but use a fixed
        # architecture-only temporary filename. Release assets are resolved
        # from GitHub metadata below, never from a tag-derived filename.
        release_asset = f"mihomo-linux-{asset_arch}.gz"
        verified_url = asset_url
        verified_sha256 = normalize_digest(expected_sha256)
        url_name = Path(urllib.parse.urlparse(asset_url).path).name
        expected_binary_version = asset_version(url_name, asset_arch, release_tag)
    else:
        release_asset, verified_url, verified_sha256 = resolve_asset(release_tag)
        expected_binary_version = asset_version(
            release_asset, asset_arch, release_tag
        )

    rollback_dir = state_dir / "rollback"
    meta_file = metadata_path(state_dir)
    with upgrade_lock(lock_path):
        previous_version = extract_version(binary) if binary.exists() else ""
        if previous_version == expected_binary_version:
            config_test(binary, state_dir, config)
            probe_controller(controller_url, config)
            result = {
                "STATUS": "already_current",
                "PREV_VERSION": previous_version,
                "TARGET_VERSION": release_tag,
                "ASSET": release_asset,
                "ASSET_SHA256": verified_sha256,
                "CURRENT_VERSION": previous_version,
            }
            existing = read_metadata(meta_file) if meta_file.exists() else {}
            preserved_backup = existing.get("BACKUP_BIN", "")
            if existing.get("TARGET_VERSION") == release_tag and preserved_backup and Path(
                preserved_backup
            ).is_file():
                result["BACKUP_BIN"] = preserved_backup
                if existing.get("STATUS") != "success":
                    write_metadata(
                        meta_file,
                        {
                            **existing,
                            **result,
                            "STATUS": "success",
                        },
                    )
            else:
                write_metadata(meta_file, result)
            return result

        state_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mihomo-core-", dir=str(state_dir)) as temp_dir:
            temporary_dir = Path(temp_dir)
            compressed = temporary_dir / release_asset
            candidate = temporary_dir / "mihomo"
            download_asset(verified_url, compressed)
            actual_sha256 = sha256_file(compressed)
            if actual_sha256 != verified_sha256:
                raise CoreUpdateError(
                    f"Mihomo asset checksum mismatch: expected {verified_sha256}, got {actual_sha256}"
                )
            extract_asset(compressed, candidate)
            verify_binary_version(candidate, expected_binary_version, asset_arch)
            config_test(candidate, state_dir, config)

            backup = _backup_binary(binary, rollback_dir, previous_version) if binary.exists() else None
            pending = {
                "PREV_VERSION": previous_version,
                "TARGET_VERSION": release_tag,
                "BACKUP_BIN": str(backup) if backup else "",
                "ASSET": release_asset,
                "ASSET_URL": verified_url,
                "ASSET_SHA256": verified_sha256,
                "UPGRADE_AT": time.strftime("%Y%m%d-%H%M%S", time.gmtime()),
                "STATUS": "pending",
            }
            write_metadata(meta_file, pending)
            atomic_replace(candidate, binary)

        try:
            restart_and_probe(
                service=service,
                controller_url=controller_url,
                config=config,
            )
        except Exception as exc:
            if backup and backup.exists() and auto_rollback:
                rollback_candidate = binary.parent / f".mihomo.rollback.{os.getpid()}"
                shutil.copy2(backup, rollback_candidate)
                os.chmod(rollback_candidate, 0o755)
                atomic_replace(rollback_candidate, binary)
                try:
                    restart_and_probe(
                        service=service,
                        controller_url=controller_url,
                        config=config,
                    )
                except Exception as rollback_exc:
                    write_metadata(
                        meta_file,
                        {
                            **pending,
                            "STATUS": "rollback_failed",
                            "ROLLBACK_ERROR": str(rollback_exc),
                        },
                    )
                    raise CoreUpdateError(
                        f"Mihomo upgrade failed and rollback failed: {rollback_exc}"
                    ) from exc
                write_metadata(meta_file, {**pending, "STATUS": "rolled_back"})
            else:
                write_metadata(
                    meta_file,
                    {
                        **pending,
                        "STATUS": "failed",
                        "ROLLBACK_SKIPPED": "true" if backup else "false",
                    },
                )
            raise CoreUpdateError(f"Mihomo upgrade health check failed: {exc}") from exc

        result = {
            **pending,
            "STATUS": "success",
            "CURRENT_VERSION": extract_version(binary),
        }
        write_metadata(meta_file, result)
        return result


def rollback_core(
    *,
    target: str = "latest",
    binary: Path = DEFAULT_BINARY,
    state_dir: Path = DEFAULT_STATE_DIR,
    config: Path = DEFAULT_CONFIG,
    service: str = DEFAULT_SERVICE,
    controller_url: str = DEFAULT_CONTROLLER_URL,
    lock_path: Path = DEFAULT_LOCK_PATH,
) -> dict[str, str]:
    meta_file = metadata_path(state_dir)
    with upgrade_lock(lock_path):
        if target == "latest":
            target = read_metadata(meta_file).get("BACKUP_BIN", "")
        restore_path = Path(target)
        if not restore_path.is_file():
            raise CoreUpdateError(f"rollback backup not found: {restore_path}")
        restore_version = extract_version(restore_path)
        config_test(restore_path, state_dir, config)
        current_version = extract_version(binary) if binary.exists() else ""
        temporary = state_dir / f".mihomo.rollback.{os.getpid()}"
        if binary.exists():
            shutil.copy2(binary, temporary)
            os.chmod(temporary, 0o700)
        try:
            with tempfile.NamedTemporaryFile(delete=False, dir=str(binary.parent)) as handle:
                temporary_restore = Path(handle.name)
            shutil.copy2(restore_path, temporary_restore)
            os.chmod(temporary_restore, 0o755)
            atomic_replace(temporary_restore, binary)
            restart_and_probe(
                service=service,
                controller_url=controller_url,
                config=config,
            )
        except Exception:
            if temporary.exists():
                atomic_replace(temporary, binary)
                try:
                    restart_and_probe(
                        service=service,
                        controller_url=controller_url,
                        config=config,
                    )
                except Exception:
                    pass
            raise
        finally:
            temporary.unlink(missing_ok=True)

        result = {
            "PREV_VERSION": current_version,
            "TARGET_VERSION": restore_version,
            "BACKUP_BIN": str(restore_path),
            "UPGRADE_AT": time.strftime("%Y%m%d-%H%M%S", time.gmtime()),
            "STATUS": "rolled_back",
        }
        write_metadata(meta_file, result)
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    upgrade = subparsers.add_parser("upgrade")
    upgrade.add_argument("--tag")
    upgrade.add_argument("--channel", choices=("stable", "alpha"), default="stable")
    upgrade.add_argument("--asset-url")
    upgrade.add_argument("--asset-sha256")
    upgrade.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    upgrade.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    upgrade.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    upgrade.add_argument("--service", default=DEFAULT_SERVICE)
    upgrade.add_argument("--controller-url", default=DEFAULT_CONTROLLER_URL)
    upgrade.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK_PATH)
    upgrade.add_argument("--no-rollback", action="store_true")

    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("--target", default="latest")
    rollback.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    rollback.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    rollback.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    rollback.add_argument("--service", default=DEFAULT_SERVICE)
    rollback.add_argument("--controller-url", default=DEFAULT_CONTROLLER_URL)
    rollback.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "upgrade":
            if bool(args.asset_url) != bool(args.asset_sha256):
                raise CoreUpdateError("--asset-url and --asset-sha256 must be provided together")
            result = upgrade_core(
                tag=args.tag,
                channel=args.channel,
                asset_url=args.asset_url,
                expected_sha256=args.asset_sha256,
                binary=args.binary,
                state_dir=args.state_dir,
                config=args.config,
                service=args.service,
                controller_url=args.controller_url,
                lock_path=args.lock_path,
                auto_rollback=not args.no_rollback,
            )
        else:
            result = rollback_core(
                target=args.target,
                binary=args.binary,
                state_dir=args.state_dir,
                config=args.config,
                service=args.service,
                controller_url=args.controller_url,
                lock_path=args.lock_path,
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except CoreUpdateError as exc:
        print(f"ERROR: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
