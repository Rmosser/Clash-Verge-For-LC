#!/usr/bin/env python3
"""Exercise the on-disk rollback contract without contacting a microserver.

The production snapshot/restore routines are embedded in remote shell heredocs,
so this fixture deliberately tests the same manifest grammar and destructive
ordering against a private temporary tree.  The source assertions below keep
the fixture tied to the three entry points instead of silently becoming an
independent backup implementation.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MICROSERVER = ROOT / "scripts" / "deploy_microserver.sh"
DASHBOARD = ROOT / "scripts" / "deploy_dashboard.sh"
LEGACY = ROOT / "scripts" / "cleanup_legacy_dashboard.sh"


def stream_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(path: Path) -> str:
    """Digest regular directory content and metadata in stable order."""

    digest = hashlib.sha256()
    entries = [path, *sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix())]
    for entry in entries:
        relative = "." if entry == path else entry.relative_to(path).as_posix()
        metadata = entry.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise AssertionError(f"fixture unexpectedly contains symlink: {entry}")
        kind = "d" if stat.S_ISDIR(metadata.st_mode) else "f"
        digest.update(f"{kind}\0{relative}\0{stat.S_IMODE(metadata.st_mode):o}\0".encode())
        if kind == "f":
            digest.update(stream_digest(entry).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def archive_directory(source: Path, archive: Path) -> None:
    with tarfile.open(archive, "w:gz") as output:
        output.add(source, arcname=source.name, recursive=True)


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def snapshot_target(path: Path, snapshot_dir: Path, index: int) -> list[str]:
    backup_name = f"target-{index}"
    if not path.exists() and not path.is_symlink():
        return [str(path), "missing", "-", "0", "-", "-", "-", "-", "-", "-"]
    if path.is_symlink():
        raise AssertionError(f"snapshot must reject symlink target: {path}")

    metadata = path.lstat()
    mode = format(stat.S_IMODE(metadata.st_mode), "o")
    uid = str(metadata.st_uid)
    gid = str(metadata.st_gid)
    if path.is_file():
        target_type = "file"
        size = str(metadata.st_size)
        digest = stream_digest(path)
        shutil.copy2(path, snapshot_dir / backup_name)
        backup = snapshot_dir / backup_name
    elif path.is_dir():
        target_type = "directory"
        size = "0"
        digest = tree_digest(path)
        backup_name += ".tar.gz"
        backup = snapshot_dir / backup_name
        archive_directory(path, backup)
    else:
        raise AssertionError(f"unsupported fixture target: {path}")

    archive_digest = stream_digest(backup)
    return [
        str(path),
        "present",
        target_type,
        size,
        digest,
        backup_name,
        archive_digest,
        mode,
        uid,
        gid,
    ]


def write_manifest(rows: list[list[str]], snapshot_dir: Path) -> Path:
    manifest = snapshot_dir / "manifest.tsv"
    manifest.write_text("\n".join("\t".join(row) for row in rows) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(rows: list[list[str]], snapshot_dir: Path, allowed: set[str]) -> None:
    for row in rows:
        if len(row) not in {7, 10}:
            raise AssertionError(f"manifest row has wrong field count: {row}")
        path, state, target_type, size, digest, backup_name, archive_digest = row[:7]
        metadata = row[7:]
        if path not in allowed:
            raise AssertionError(f"unapproved target in manifest: {path}")
        if state == "missing":
            expected = ["-", "0", "-", "-", "-"]
            if len(row) == 10:
                expected += ["-", "-", "-"]
            if row[2:] != expected:
                raise AssertionError(f"invalid missing sentinel: {row}")
            continue
        if state != "present" or target_type not in {"file", "directory"}:
            raise AssertionError(f"invalid present row: {row}")
        if not re.fullmatch(r"target-[0-9]+(?:\.tar\.gz)?", backup_name):
            raise AssertionError(f"invalid backup name: {backup_name}")
        backup = snapshot_dir / backup_name
        if backup.is_symlink() or not backup.is_file():
            raise AssertionError(f"backup is not a regular file: {backup}")
        if stream_digest(backup) != archive_digest:
            raise AssertionError(f"archive digest mismatch: {backup}")
        if target_type == "file":
            if backup_name.endswith(".tar.gz") or stream_digest(backup) != digest:
                raise AssertionError("file content and archive digest must match")
        elif not backup_name.endswith(".tar.gz"):
            raise AssertionError("directory backup must be an archive")
        if len(row) == 10:
            mode, uid, gid = metadata
            if not re.fullmatch(r"[0-7]{1,4}", mode) or not uid.isdigit() or not gid.isdigit():
                raise AssertionError(f"invalid permission metadata: {row}")


def restore(rows: list[list[str]], snapshot_dir: Path) -> None:
    unknown = snapshot_dir / "UNKNOWN"
    unknown.write_text("rollback_status=UNKNOWN\n", encoding="utf-8")
    try:
        for row in rows:
            path_text, state, target_type, _size, _digest, backup_name, _archive_digest = row[:7]
            mode = uid = gid = None
            if len(row) == 10:
                mode, uid, gid = row[7:]
            path = Path(path_text)
            if state == "missing":
                if path.exists() or path.is_symlink():
                    remove_path(path)
                continue
            if path.exists() or path.is_symlink():
                remove_path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if target_type == "file":
                shutil.copyfile(snapshot_dir / backup_name, path)
                if mode is not None:
                    os.chmod(path, int(mode, 8))
                    os.chown(path, int(uid), int(gid))
            elif target_type == "directory":
                with tarfile.open(snapshot_dir / backup_name, "r:gz") as archive:
                    members = archive.getmembers()
                    prefix = Path(members[0].name).parts[0] if members else ""
                    if not prefix or any(member.name.startswith("/") or ".." in Path(member.name).parts for member in members):
                        raise AssertionError("unsafe archive member")
                    archive.extractall(path.parent)
                if mode is not None:
                    os.chmod(path, int(mode, 8))
                    os.chown(path, int(uid), int(gid))
            else:
                raise AssertionError(f"unknown target type: {target_type}")
    except Exception:
        raise
    else:
        unknown.unlink()


def assert_service_state(active: str, enabled: str) -> None:
    if active not in {"active", "inactive"}:
        raise AssertionError(f"unreproducible active state accepted: {active}")
    if enabled not in {"enabled", "disabled", "static", "masked"}:
        raise AssertionError(f"unreproducible enabled state accepted: {enabled}")


def assert_absent_service_readback(
    active: str, load_state: str, enabled: str, unit_file_count: int
) -> None:
    """Mirror the fail-closed proof required after removing a new unit."""

    if active == "active":
        raise AssertionError("newly-created unit is still active")
    if active not in {"inactive", "failed", "unknown"}:
        raise AssertionError(f"unreadable active state: {active}")
    if load_state != "not-found":
        raise AssertionError(f"unit remains loaded: {load_state}")
    if enabled not in {"", "not-found"}:
        raise AssertionError(f"unit remains enabled: {enabled}")
    if unit_file_count != 0:
        raise AssertionError("unit file remains after absent restore")


def assert_source_contract(script: Path, restore_name: str) -> None:
    source = script.read_text(encoding="utf-8")
    if "approved_paths=(" not in source or "assert_approved_path" not in source:
        raise AssertionError(f"{script.name} lacks exact restore allowlist")
    if "present-no" not in source or "rm -rf -- \"$path\"" not in source:
        raise AssertionError(f"{script.name} does not remove a mutation-created missing target")
    body_start = source.index(f"{restore_name}()")
    body_end = source.find("\non_exit()", body_start)
    body = source[body_start:] if body_end < 0 else source[body_start:body_end]
    present = body.index('if [[ "$state" == present ]]')
    removed = body.index('rm -rf -- "$path"', present)
    extracted = body.index("tar -xzf", present)
    if removed > extracted:
        raise AssertionError(f"{script.name} extracts before clearing the existing target")
    if re.search(r"(?:inactive|active)\|(?:failed|unknown)|(?:failed|unknown)\) systemctl", body):
        raise AssertionError(f"{script.name} treats failed/unknown as restorable")


def run_dashboard_style_fixture(root: Path) -> None:
    """Cover the seven-column dashboard/legacy manifest contract."""

    snapshot_dir = root / "snapshot"
    snapshot_dir.mkdir()
    directory = root / "directory"
    directory.mkdir()
    (directory / "original.txt").write_text("original\n", encoding="utf-8")
    missing = root / "was-missing"
    full_rows = [snapshot_target(directory, snapshot_dir, 1), snapshot_target(missing, snapshot_dir, 2)]
    rows = [row[:7] for row in full_rows]
    write_manifest(rows, snapshot_dir)
    verify_manifest(rows, snapshot_dir, {str(directory), str(missing)})

    (directory / "new-residue.txt").write_text("must disappear", encoding="utf-8")
    missing.write_text("mutation-created", encoding="utf-8")
    restore(rows, snapshot_dir)
    if tree_digest(directory) != full_rows[0][4]:
        raise AssertionError("dashboard-style directory residue survived restore")
    if missing.exists() or missing.is_symlink():
        raise AssertionError("dashboard-style present-no target survived restore")
    if (snapshot_dir / "UNKNOWN").exists():
        raise AssertionError("dashboard-style restore left UNKNOWN marker")


def main() -> None:
    assert_source_contract(DASHBOARD, "restore_dashboard_reset")
    assert_source_contract(LEGACY, "restore_legacy_backup")
    microserver = MICROSERVER.read_text(encoding="utf-8")
    for required in (
        "archive_digest",
        '"$actual" == "$digest"',
        '"$mode"',
        '"$uid"',
        '"$gid"',
        "case \"$snapshot_active\" in active|inactive",
        'systemctl disable --now "$snapshot_service"',
        'systemctl stop "$snapshot_service"',
        'systemctl show "$snapshot_service" --property=LoadState --value',
        'systemctl list-unit-files --no-legend "$snapshot_service"',
        '[[ "$load_state" == not-found ]]',
        '[[ "$unit_file_count" == 0 ]]',
    ):
        if required not in microserver:
            raise AssertionError(f"deploy_microserver.sh missing snapshot invariant: {required}")

    for invalid in (("failed", "enabled"), ("active", "unknown"), ("unknown", "disabled")):
        try:
            assert_service_state(*invalid)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"invalid service state was accepted: {invalid}")
    assert_service_state("active", "enabled")
    assert_service_state("inactive", "disabled")
    assert_absent_service_readback("inactive", "not-found", "not-found", 0)
    assert_absent_service_readback("unknown", "not-found", "", 0)
    for invalid in (
        ("active", "not-found", "not-found", 0),
        ("inactive", "loaded", "not-found", 0),
        ("inactive", "not-found", "disabled", 0),
        ("inactive", "not-found", "not-found", 1),
    ):
        try:
            assert_absent_service_readback(*invalid)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"invalid absent service readback was accepted: {invalid}")

    with tempfile.TemporaryDirectory(prefix="clash-verge-snapshot-") as temporary:
        root = Path(temporary)
        snapshot_dir = root / "snapshot"
        snapshot_dir.mkdir()
        directory = root / "directory"
        directory.mkdir(mode=0o750)
        (directory / "nested").mkdir()
        (directory / "nested" / "original.txt").write_text("original\n", encoding="utf-8")
        file_path = root / "secret.bin"
        file_path.write_bytes(b"original-secret")
        file_path.chmod(0o640)
        missing = root / "was-missing"
        targets = [directory, file_path, missing]
        rows = [snapshot_target(path, snapshot_dir, index) for index, path in enumerate(targets, 1)]
        write_manifest(rows, snapshot_dir)
        verify_manifest(rows, snapshot_dir, {str(path) for path in targets})

        directory_row = rows[0]
        if directory_row[4] == directory_row[6]:
            raise AssertionError("directory content digest must be distinct from archive digest")
        if directory_row[2:] != [
            "directory",
            "0",
            directory_row[4],
            directory_row[5],
            directory_row[6],
            directory_row[7],
            directory_row[8],
            directory_row[9],
        ]:
            raise AssertionError("directory metadata fields were not persisted")
        if rows[2] != [str(missing), "missing", "-", "0", "-", "-", "-", "-", "-", "-"]:
            raise AssertionError("missing target sentinel is not explicit")

        # Simulate a failed deployment: overwrite the file, change its mode,
        # add a residue under the directory, and create the previously missing
        # path.  Restore must remove all mutation residue and preserve metadata.
        file_path.write_bytes(b"mutated")
        file_path.chmod(0o600)
        (directory / "new-residue.txt").write_text("must disappear", encoding="utf-8")
        missing.mkdir()
        (missing / "unexpected").write_text("must disappear", encoding="utf-8")
        restore(rows, snapshot_dir)

        if (snapshot_dir / "UNKNOWN").exists():
            raise AssertionError("successful restore left UNKNOWN marker")
        if tree_digest(directory) != directory_row[4]:
            raise AssertionError("directory content/readback digest mismatch after restore")
        if stream_digest(file_path) != rows[1][4] or stat.S_IMODE(file_path.stat().st_mode) != int(rows[1][7], 8):
            raise AssertionError("file content or mode was not restored")
        if file_path.stat().st_uid != int(rows[1][8]) or file_path.stat().st_gid != int(rows[1][9]):
            raise AssertionError("file uid/gid was not restored")
        if missing.exists() or missing.is_symlink():
            raise AssertionError("mutation-created missing target survived restore")

    for style in ("dashboard", "legacy"):
        with tempfile.TemporaryDirectory(prefix=f"clash-verge-{style}-snapshot-") as temporary:
            run_dashboard_style_fixture(Path(temporary))

    print("rollback snapshot contract fixture passed")


if __name__ == "__main__":
    main()
