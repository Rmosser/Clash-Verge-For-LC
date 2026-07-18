#!/usr/bin/env python3
from __future__ import annotations

# HARNESS_WRAPPER_CHECK_DOCS_V2

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import selectors
import shlex
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from types import ModuleType

CHECKER_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("HARNESS_REPO_ROOT", CHECKER_ROOT)).expanduser().resolve()
TRUSTED_ROOT = Path(
    os.environ.get("HARNESS_TRUSTED_REPO_ROOT", CHECKER_ROOT)
).expanduser().resolve()
MAX_GOVERNANCE_TEXT_BYTES = 1024 * 1024
STANDALONE_BASE_ENV = "HARNESS_STANDALONE_BASE_SHA"
ZERO_COMMIT_SHA = "0" * 40
YAML_MAPPING_KEY_RE = re.compile(
    r"^(?P<indent> *)(?P<key>[A-Za-z0-9_.-]+):(?P<value>.*)$"
)


def exact_docs_root_at(root: Path, label: str) -> Path:
    candidates = [
        child for child in root.iterdir() if child.name in {"docs", "Docs"}
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"expected exactly one real docs/ or Docs/ governance root in {label}"
        )
    docs_root = candidates[0]
    if docs_root.is_symlink() or not docs_root.is_dir():
        raise RuntimeError(
            f"docs/ or Docs/ governance root in {label} must be a real directory"
        )
    return docs_root


DOCS_ROOT = exact_docs_root_at(ROOT, "validation target")
TRUSTED_DOCS_ROOT = exact_docs_root_at(TRUSTED_ROOT, "trusted verifier checkout")
ACTIVE_PLAN_DIR = DOCS_ROOT / "exec-plans" / "active"
COMPLETED_PLAN_DIR = DOCS_ROOT / "exec-plans" / "completed"
ACTIVE_PLAN_SENTINEL = ACTIVE_PLAN_DIR / ".gitkeep"
PROJECT_CHECK = TRUSTED_ROOT / "scripts" / "check_docs_project.py"
INLINE_LINK_RE = re.compile(
    r"!?\[[^\]]*\]\(\s*(?:<([^>\r\n]+)>|([^\s)]+))"
)
REFERENCE_LINK_RE = re.compile(
    r"^[ \t]{0,3}\[[^\]\r\n]+\]:[ \t]*(?:<([^>\r\n]+)>|([^\s]+))",
    re.MULTILINE,
)
FIELD_RE_TEMPLATE = r"^[ \t]*-[ \t]*{field}[ \t]*[:：][ \t]*(.*)$"
PENDING_VALUES = {"", "-", "n/a", "na", "none", "pending", "unknown", "`pending`", "`unknown`"}
TRUE_VALUES = {"yes", "true", "used"}
FALSE_VALUES = {"no", "false", "not used", "none", "n/a", "na", "-"}
COMPLETED_TRANSITION_VALUES = {"satisfied/closed"}
DEFERRED_ROLLOUT_CLOSURE_VALUES = {"deferred-to-rollout-closure"}
PLAN_LIFECYCLE_FIELDS = (
    "Status",
    "Main synced",
    "Active Plan archived",
    "Transition invariant",
    "Local branch deleted",
    "Heartbeat closed",
)
COMPLETED_LIFECYCLE_CONTRACT = {
    "Status": {"completed"},
    "Main synced": {"completed"},
    "Active Plan archived": {"completed"},
    "Transition invariant": COMPLETED_TRANSITION_VALUES,
    "Local branch deleted": DEFERRED_ROLLOUT_CLOSURE_VALUES,
    "Heartbeat closed": DEFERRED_ROLLOUT_CLOSURE_VALUES,
}
VALID_TASK_CLASSES = {"trivial", "standard", "critical"}
GITHUB_ACTIONS_APP_ID = 15368
VALID_REASONING_BUDGETS = {"low", "medium", "high"}
VALID_DELEGATION_ROUTES = {
    "single-agent",
    "main+subagent",
    "main+work-thread",
    "main+parallel-subagents",
    "no-subagent-fallback",
}
EXPECTED_BUDGET = {
    "trivial": "low",
    "standard": "medium",
    "critical": "high",
}
ALLOWED_ROUTES = {
    "trivial": {"single-agent"},
    "standard": {"main+subagent", "main+work-thread", "no-subagent-fallback"},
    "critical": {
        "main+subagent",
        "main+work-thread",
        "main+parallel-subagents",
        "no-subagent-fallback",
    },
}
REQUIRED_EVIDENCE_SECTIONS = [
    "Task class",
    "Reasoning budget",
    "Delegation route",
    "## Scope",
    "## Checkpoint 证据",
    "Context Claim",
    "Scope Claim",
    "Change Claim",
    "Validation Claim",
    "## Agent Delegation",
    "Delegation decision",
    "Used subagent",
    "No-subagent fallback reason",
    "Delegated scope",
    "Forbidden scope",
    "Subagent result",
    "Main agent review",
    "Rework requested",
    "Final accepted diff",
    "## Codex Review",
    "Requested by",
    "Requested at",
    "Completed review head",
    "Current review target pointer",
    "Heartbeat required",
    "Heartbeat interval",
    "Heartbeat stop condition",
    "Review result",
    "## Review Repair Policy",
    "Start tier",
    "Current tier",
    "Max attempts per tier",
    "Attempts at current tier",
    "Total repair attempts",
    "Escalation path",
    "Stop condition",
    "Last repeated finding",
    "Human intervention required",
    "## Repair Ledger",
    "## Post-Merge Cleanup",
    "Main synced",
    "Local branch deleted",
    "Heartbeat closed",
]
TASK_CLASSIFICATION_HEADING_RE = re.compile(
    r"^##\s+(?:Task Classification(?:\s*/\s*任务分类)?|"
    r"任务分类(?:\s*/\s*Task Classification)?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
DOCUMENTATION_IMPACT_HEADING_RE = re.compile(
    r"^##\s+(?:Documentation Impact(?:\s*/\s*文档影响)?|"
    r"文档影响(?:\s*/\s*Documentation Impact)?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
FULL_SHA_RE = re.compile(r"[0-9a-f]{40}", re.IGNORECASE)
OUT_OF_REPO_SCOPE_RE = re.compile(
    r"(?:^|[\s`(,;])(?:\.\.(?:/|\\)[^\s`,;)]*|/[^\s`,;)]+|"
    r"~(?:/|\\)[^\s`,;)]+|[A-Za-z]:[\\/][^\s`,;)]+)"
)
CURRENT_HEAD_REVIEW_HEADING = "## Current-Head Codex Review\n\n"
CURRENT_HEAD_REVIEW_SHA256 = (
    "ecc90681230b537ca89c66d8f623ce526aeac6fd949963bd7bf9810df6cf0f12"
)
TRUSTED_CONTROL_FILES = (
    f"{DOCS_ROOT.name}/doc-sync-rules.json",
    ".harness/repo-contract.json",
    ".github/workflows/codex-review-gate.yml",
    ".github/workflows/codex-review-heartbeat.yml",
    "scripts/check_codex_review.py",
    "scripts/check_docs.py",
    "scripts/check_loop_checkpoints.py",
) + (
    ("scripts/check_docs_project.py",)
    if PROJECT_CHECK.is_file() and not PROJECT_CHECK.is_symlink()
    else ()
)


def load_json(path: Path, errors: list[str], label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(
            f"Cannot read {label} {path.relative_to(ROOT).as_posix()}: {exc}"
        )
        return {}
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid {label}: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"Invalid {label}: top-level value must be an object")
        return {}
    return payload


def load_trusted_manifest(errors: list[str]) -> dict[str, object]:
    path = TRUSTED_DOCS_ROOT / "doc-sync-rules.json"
    if path.is_symlink():
        errors.append("trusted doc sync rules must be a regular file, not a symlink")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Invalid trusted doc sync rules: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append("Invalid trusted doc sync rules: top-level value must be an object")
        return {}
    return payload


def required_paths_from(
    manifest: dict[str, object], errors: list[str], label: str
) -> list[str]:
    value = manifest.get("required_paths", [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{label} required_paths must be a list of strings")
        return []
    return value


def forbidden_paths_from(
    manifest: dict[str, object], errors: list[str], label: str
) -> list[str]:
    value = manifest.get("forbidden_paths", [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{label} forbidden_paths must be a list of strings")
        return []
    return value


def check_trusted_forbidden_paths(
    manifest: dict[str, object],
    trusted_manifest: dict[str, object],
    errors: list[str],
) -> None:
    target_forbidden = set(
        forbidden_paths_from(manifest, errors, "doc-sync-rules")
    )
    trusted_forbidden = forbidden_paths_from(
        trusted_manifest, errors, "trusted doc-sync-rules"
    )
    missing = sorted(set(trusted_forbidden) - target_forbidden)
    if missing:
        errors.append(
            "Target doc-sync-rules cannot remove trusted forbidden paths: "
            f"{', '.join(missing)}"
        )


def check_trusted_required_paths(
    trusted_manifest: dict[str, object],
    required_paths: list[str],
    errors: list[str],
) -> None:
    trusted_required = required_paths_from(
        trusted_manifest, errors, "trusted doc-sync-rules"
    )
    target_required = set(required_paths)
    for relative_path in trusted_required:
        trusted_path = exact_case_real_path_at(TRUSTED_ROOT, relative_path)
        target_path = exact_case_real_path_at(ROOT, relative_path)
        if trusted_path is None:
            errors.append(
                "Trusted required path is missing, case-mismatched, symlinked, or "
                f"not a real file/directory: {relative_path}"
            )
        if relative_path not in target_required:
            errors.append(
                f"Target doc-sync-rules cannot remove trusted required path: {relative_path}"
            )
        if target_path is None:
            errors.append(
                "Missing or case-mismatched trusted required path, or path is "
                f"symlinked/not a real file or directory: {relative_path}"
            )
        elif trusted_path is not None and (
            trusted_path.is_dir() != target_path.is_dir()
            or trusted_path.is_file() != target_path.is_file()
        ):
            errors.append(
                f"Target required path type differs from trusted base: {relative_path}"
            )


def exact_case_real_path_at(root: Path, relative_path: str) -> Path | None:
    current = root
    if current.is_symlink() or not current.is_dir():
        return None
    for part in PurePosixPath(relative_path).parts:
        if part in {"", "."}:
            continue
        if part == ".." or current.is_symlink() or not current.is_dir():
            return None
        entries = {entry.name: entry for entry in current.iterdir()}
        current = entries.get(part)
        if current is None or current.is_symlink():
            return None
    return current if current.is_file() or current.is_dir() else None


def exact_case_path_exists_at(root: Path, relative_path: str) -> bool:
    return exact_case_real_path_at(root, relative_path) is not None


def exact_case_path_exists(relative_path: str) -> bool:
    return exact_case_path_exists_at(ROOT, relative_path)


def read_regular_text_at(
    root: Path,
    relative_path: str,
    errors: list[str],
    max_bytes: int = MAX_GOVERNANCE_TEXT_BYTES,
    metadata_out: list[os.stat_result] | None = None,
) -> str | None:
    required_flags = {
        name: getattr(os, name, None)
        for name in (
            "O_CLOEXEC",
            "O_DIRECTORY",
            "O_NOCTTY",
            "O_NOFOLLOW",
            "O_NONBLOCK",
        )
    }
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value != 0
        for value in required_flags.values()
    ):
        errors.append(
            f"safe descriptor traversal is unavailable for regular file: {relative_path}"
        )
        return None
    if (
        os.open not in os.supports_dir_fd
        or os.listdir not in os.supports_fd
        or os.stat not in os.supports_dir_fd
        or os.stat not in os.supports_follow_symlinks
    ):
        errors.append(
            f"descriptor-relative traversal is unavailable for regular file: {relative_path}"
        )
        return None
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        errors.append(f"regular text path must stay repository-relative: {relative_path}")
        return None
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        errors.append(f"regular text size limit must be positive: {relative_path}")
        return None

    directory_flags = (
        os.O_RDONLY
        | required_flags["O_CLOEXEC"]
        | required_flags["O_DIRECTORY"]
        | required_flags["O_NOFOLLOW"]
    )
    file_flags = (
        os.O_RDONLY
        | required_flags["O_CLOEXEC"]
        | required_flags["O_NOCTTY"]
        | required_flags["O_NOFOLLOW"]
        | required_flags["O_NONBLOCK"]
    )
    try:
        descriptors = [-1] * (len(relative.parts) + 1)
    except MemoryError:
        errors.append(f"cannot allocate safe descriptor state for: {relative_path}")
        return None
    opened_count = 0
    try:
        current = os.open(root, directory_flags)
        descriptors[opened_count] = current
        opened_count += 1
        for part in relative.parts[:-1]:
            if part not in os.listdir(current):
                errors.append(
                    f"required text path is missing or has wrong case: {relative_path}"
                )
                return None
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors[opened_count] = current
            opened_count += 1
        if relative.parts[-1] not in os.listdir(current):
            errors.append(
                f"required text path is missing or has wrong case: {relative_path}"
            )
            return None
        before_open = os.stat(
            relative.parts[-1], dir_fd=current, follow_symlinks=False
        )
        if not stat.S_ISREG(before_open.st_mode):
            errors.append(f"required text input is not a regular file: {relative_path}")
            return None
        descriptor = os.open(relative.parts[-1], file_flags, dir_fd=current)
        descriptors[opened_count] = descriptor
        opened_count += 1
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            errors.append(f"required text input is not a regular file: {relative_path}")
            return None
        if (metadata.st_dev, metadata.st_ino) != (
            before_open.st_dev,
            before_open.st_ino,
        ):
            errors.append(f"required text input changed while opening: {relative_path}")
            return None
        if metadata.st_size > max_bytes:
            errors.append(
                f"required text input exceeds {max_bytes} bytes: {relative_path}"
            )
            return None
        content = bytearray()
        while len(content) <= max_bytes:
            chunk = os.read(descriptor, min(65536, max_bytes + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        if len(content) > max_bytes:
            errors.append(
                f"required text input exceeds {max_bytes} bytes: {relative_path}"
            )
            return None
        text = bytes(content).decode("utf-8")
        final_metadata = os.fstat(descriptor)
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(metadata, field) != getattr(final_metadata, field)
            for field in stable_fields
        ):
            errors.append(f"required text input changed while reading: {relative_path}")
            return None
        if metadata_out is not None:
            metadata_out.append(final_metadata)
        return text
    except (OSError, UnicodeError, MemoryError) as exc:
        errors.append(f"cannot safely read regular file {relative_path}: {exc}")
        return None
    finally:
        for index in range(opened_count - 1, -1, -1):
            try:
                os.close(descriptors[index])
            except OSError:
                pass


def git_plumbing_output(
    args: list[str], label: str, errors: list[str], max_bytes: int
) -> bytes | None:
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
        errors.append(f"git plumbing byte limit must be non-negative while {label}")
        return None
    env = os.environ.copy()
    env.update(
        {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    reaped = False
    try:
        process = subprocess.Popen(
            ["git", "-C", str(ROOT), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        if process.stdout is None:
            errors.append(f"cannot {label} with git plumbing: stdout pipe unavailable")
            return None
        descriptor = process.stdout.fileno()
        os.set_blocking(descriptor, False)
        selector = selectors.DefaultSelector()
        selector.register(descriptor, selectors.EVENT_READ)
        deadline = time.monotonic() + 10
        output = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                errors.append(f"cannot {label} with git plumbing: timed out after 10 seconds")
                return None
            if not selector.select(remaining):
                errors.append(f"cannot {label} with git plumbing: timed out after 10 seconds")
                return None
            read_limit = min(65536, max_bytes + 1 - len(output))
            try:
                chunk = os.read(descriptor, read_limit)
            except BlockingIOError:
                continue
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > max_bytes:
                errors.append(
                    f"git plumbing output exceeds {max_bytes} bytes while {label}"
                )
                return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            errors.append(f"cannot {label} with git plumbing: timed out after 10 seconds")
            return None
        try:
            returncode = process.wait(timeout=remaining)
            reaped = True
        except subprocess.TimeoutExpired:
            errors.append(f"cannot {label} with git plumbing: timed out after 10 seconds")
            return None
        if returncode != 0:
            errors.append(f"cannot {label} with git plumbing")
            return None
        return bytes(output)
    except (OSError, ValueError, MemoryError) as exc:
        errors.append(f"cannot {label} with git plumbing: {exc}")
        return None
    finally:
        if selector is not None:
            try:
                selector.close()
            except (OSError, ValueError):
                pass
        if process is not None:
            if not reaped:
                try:
                    if process.poll() is None:
                        process.kill()
                except OSError:
                    pass
                try:
                    process.wait()
                except OSError:
                    pass
            if process.stdout is not None:
                try:
                    process.stdout.close()
                except OSError:
                    pass


def resolve_standalone_base(
    advertised_sha: str, errors: list[str]
) -> tuple[bool, str | None]:
    if FULL_SHA_RE.fullmatch(advertised_sha) is None:
        errors.append(
            f"advertised standalone base {STANDALONE_BASE_ENV} must be an exact "
            "40-character hexadecimal SHA"
        )
        return False, None
    advertised_sha = advertised_sha.lower()
    if advertised_sha == ZERO_COMMIT_SHA:
        return True, None
    output = git_plumbing_output(
        ["rev-parse", "--verify", f"{advertised_sha}^{{commit}}"],
        f"resolve advertised standalone base {advertised_sha}",
        errors,
        64,
    )
    if output is None:
        return False, None
    try:
        resolved = output.decode("ascii").strip()
    except UnicodeDecodeError:
        errors.append("standalone base resolver returned non-ASCII output")
        return False, None
    if resolved != advertised_sha:
        errors.append(
            f"{STANDALONE_BASE_ENV} must resolve to the advertised commit itself"
        )
        return False, None
    return True, resolved


def optional_standalone_head() -> str | None:
    env = os.environ.copy()
    env.update(
        {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", "HEAD^{commit}"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    resolved = result.stdout.strip().lower()
    if result.returncode != 0 or FULL_SHA_RE.fullmatch(resolved) is None:
        return None
    return resolved


def require_standalone_tree_directory(
    base_sha: str, relative: str, errors: list[str]
) -> bool:
    output = git_plumbing_output(
        ["ls-tree", "-z", "--full-tree", base_sha, "--", f":(literal){relative}"],
        f"read standalone base directory entry for {relative}",
        errors,
        len(relative.encode("utf-8")) + 256,
    )
    if output is None:
        return False
    if not output:
        # A first Harness push can legitimately compare against a base commit
        # that predates the archive directories entirely.
        return True
    if output.count(b"\0") != 1 or not output.endswith(b"\0") or b"\t" not in output:
        errors.append(f"malformed standalone base directory entry for {relative}")
        return False
    header, entry_path = output[:-1].split(b"\t", 1)
    fields = header.split(b" ")
    if len(fields) != 3 or entry_path != relative.encode("utf-8"):
        errors.append(f"malformed standalone base directory entry for {relative}")
        return False
    try:
        mode, object_type, object_id = (
            fields[0].decode("ascii"),
            fields[1].decode("ascii"),
            fields[2].decode("ascii"),
        )
    except UnicodeDecodeError:
        errors.append(f"non-ASCII standalone base directory metadata for {relative}")
        return False
    if (
        mode != "040000"
        or object_type != "tree"
        or re.fullmatch(r"[0-9a-f]{40,64}", object_id) is None
    ):
        errors.append(
            f"standalone base directory must be a real Git tree, not a symlink or "
            f"special entry: {relative}"
        )
        return False
    return True


def standalone_tree_plan(
    base_sha: str, relative: str, errors: list[str]
) -> tuple[bool, str | None, bytes | None]:
    output = git_plumbing_output(
        ["ls-tree", "-z", "--full-tree", base_sha, "--", f":(literal){relative}"],
        f"read standalone base tree entry for {relative}",
        errors,
        len(relative.encode("utf-8")) + 256,
    )
    if output is None:
        return False, None, None
    if not output:
        return True, None, None
    if output.count(b"\0") != 1 or not output.endswith(b"\0") or b"\t" not in output:
        errors.append(f"malformed standalone base tree entry for {relative}")
        return False, None, None
    header, entry_path = output[:-1].split(b"\t", 1)
    fields = header.split(b" ")
    if len(fields) != 3 or entry_path != relative.encode("utf-8"):
        errors.append(f"malformed standalone base tree entry for {relative}")
        return False, None, None
    try:
        mode, object_type, object_id = (
            fields[0].decode("ascii"),
            fields[1].decode("ascii"),
            fields[2].decode("ascii"),
        )
    except UnicodeDecodeError:
        errors.append(f"non-ASCII standalone base tree metadata for {relative}")
        return False, None, None
    if object_type != "blob" or mode not in {"100644", "100755"}:
        return True, None, None
    if re.fullmatch(r"[0-9a-f]{40,64}", object_id) is None:
        errors.append(f"invalid standalone base blob id for {relative}")
        return False, None, None
    size_output = git_plumbing_output(
        ["cat-file", "-s", object_id],
        f"read standalone base blob size for {relative}",
        errors,
        32,
    )
    if size_output is None:
        return False, None, None
    try:
        size = int(size_output.decode("ascii").strip())
    except (UnicodeDecodeError, ValueError):
        errors.append(f"invalid standalone base blob size for {relative}")
        return False, None, None
    if size < 0 or size > MAX_GOVERNANCE_TEXT_BYTES:
        errors.append(
            f"standalone base blob exceeds {MAX_GOVERNANCE_TEXT_BYTES} bytes: {relative}"
        )
        return False, None, None
    blob = git_plumbing_output(
        ["cat-file", "blob", object_id],
        f"read standalone base blob for {relative}",
        errors,
        size,
    )
    if blob is None:
        return False, None, None
    if len(blob) != size:
        errors.append(f"standalone base blob size changed while reading: {relative}")
        return False, None, None
    try:
        blob.decode("utf-8")
    except UnicodeDecodeError:
        errors.append(f"standalone base blob is not strict UTF-8: {relative}")
        return False, None, None
    return True, mode, blob


def standalone_completed_plan_relatives(
    base_sha: str, errors: list[str]
) -> set[str] | None:
    docs_relative = DOCS_ROOT.relative_to(ROOT).as_posix()
    completed_prefix = f"{docs_relative}/exec-plans/completed/"
    if not require_standalone_tree_directory(
        base_sha, completed_prefix.rstrip("/"), errors
    ):
        return None
    output = git_plumbing_output(
        [
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            "--full-tree",
            base_sha,
            "--",
            f":(literal){completed_prefix}",
        ],
        f"list standalone completed plans at {base_sha}",
        errors,
        1024 * 1024,
    )
    if output is None:
        return None
    if output and not output.endswith(b"\0"):
        errors.append("malformed standalone completed-plan inventory")
        return None
    relatives: set[str] = set()
    for raw_path in output.rstrip(b"\0").split(b"\0") if output else ():
        try:
            relative = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            errors.append("standalone completed-plan inventory contains non-UTF-8 path")
            return None
        path = Path(relative)
        if (
            path.parent.as_posix() == completed_prefix.rstrip("/")
            and path.suffix == ".md"
        ):
            relatives.add(relative)
    return relatives


def standalone_active_plan_relatives(
    base_sha: str, errors: list[str]
) -> set[str] | None:
    docs_relative = DOCS_ROOT.relative_to(ROOT).as_posix()
    active_prefix = f"{docs_relative}/exec-plans/active/"
    if not require_standalone_tree_directory(
        base_sha, active_prefix.rstrip("/"), errors
    ):
        return None
    output = git_plumbing_output(
        [
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            "--full-tree",
            base_sha,
            "--",
            f":(literal){active_prefix}",
        ],
        f"list standalone active plans at {base_sha}",
        errors,
        1024 * 1024,
    )
    if output is None:
        return None
    if output and not output.endswith(b"\0"):
        errors.append("malformed standalone active-plan inventory")
        return None
    relatives: set[str] = set()
    for raw_path in output.rstrip(b"\0").split(b"\0") if output else ():
        try:
            relative = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            errors.append("standalone active-plan inventory contains non-UTF-8 path")
            return None
        path = Path(relative)
        if path.parent.as_posix() != active_prefix.rstrip("/"):
            errors.append(
                "standalone active-plan bookkeeping must contain only direct plan files: "
                f"{relative}"
            )
            continue
        if path.name == ".gitkeep":
            continue
        if path.suffix != ".md":
            errors.append(
                "standalone active-plan bookkeeping may contain only lowercase .md "
                f"files: {relative}"
            )
            continue
        relatives.add(relative)
    return relatives


def check_trusted_control_files(errors: list[str]) -> None:
    target_workflows = workflow_control_relatives(
        ROOT, "target workflow control directory", errors
    )
    trusted_workflows = workflow_control_relatives(
        TRUSTED_ROOT, "trusted workflow control directory", errors
    )
    if target_workflows != trusted_workflows:
        errors.append(
            "Target .github/workflows inventory must exactly match the trusted base; "
            "workflow additions, removals, and renames require the trusted bootstrap path"
        )

    control_files = set(TRUSTED_CONTROL_FILES) | target_workflows | trusted_workflows
    project_control = "scripts/check_docs_project.py"
    target_project = ROOT / project_control
    trusted_project = TRUSTED_ROOT / project_control
    target_has_project = target_project.exists() or target_project.is_symlink()
    trusted_has_project = trusted_project.exists() or trusted_project.is_symlink()
    if target_has_project != trusted_has_project:
        errors.append(
            "Target project docs checker inventory must exactly match the trusted base; "
            "adding or removing scripts/check_docs_project.py requires the trusted "
            "bootstrap path"
        )
    if target_has_project or trusted_has_project:
        control_files.add(project_control)
    for relative_path in sorted(control_files):
        target_text = read_regular_text_at(ROOT, relative_path, errors)
        trusted_text = read_regular_text_at(TRUSTED_ROOT, relative_path, errors)
        if target_text is None or trusted_text is None:
            continue
        if target_text.encode("utf-8") != trusted_text.encode("utf-8"):
            errors.append(
                "Target trusted control file differs byte-for-byte from the trusted "
                f"base: {relative_path}; control-plane updates require the trusted "
                "bootstrap path"
            )


def workflow_control_relatives(
    root: Path, label: str, errors: list[str]
) -> set[str]:
    workflows = root / ".github" / "workflows"
    if workflows.is_symlink() or not workflows.is_dir():
        errors.append(f"{label} must be a real directory, not a symlink: {workflows}")
        return set()

    relatives: set[str] = set()
    for current, dirnames, filenames in os.walk(
        workflows, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        for dirname in list(dirnames):
            candidate = current_path / dirname
            if candidate.is_symlink():
                errors.append(
                    f"{label} cannot contain a symlinked directory: "
                    f"{candidate.relative_to(root).as_posix()}"
                )
                dirnames.remove(dirname)
        for filename in filenames:
            candidate = current_path / filename
            relative = candidate.relative_to(root).as_posix()
            if candidate.is_symlink() or not candidate.is_file():
                errors.append(
                    f"{label} must contain only regular files: {relative}"
                )
                continue
            relatives.add(relative)
    return relatives


def string_list_field(
    manifest: dict[str, object], field: str, errors: list[str], label: str
) -> list[str]:
    value = manifest.get(field, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{label} {field} must be a list of strings")
        return []
    return value


def safe_markdown_tree(base: Path, errors: list[str]) -> list[Path]:
    if base.is_symlink() or (base.exists() and not base.is_dir()):
        errors.append(
            f"markdown scan root must be a real directory, not a symlink: "
            f"{base.relative_to(ROOT).as_posix()}"
        )
        return []
    if not base.exists():
        return []

    files: list[Path] = []
    for current, dirnames, filenames in os.walk(base, topdown=True, followlinks=False):
        current_path = Path(current)
        for dirname in list(dirnames):
            candidate = current_path / dirname
            if candidate.is_symlink():
                errors.append(
                    "markdown scan cannot traverse a symlinked directory: "
                    f"{candidate.relative_to(ROOT).as_posix()}"
                )
                dirnames.remove(dirname)
        for filename in filenames:
            if not filename.endswith(".md"):
                continue
            candidate = current_path / filename
            if candidate.is_symlink() or not candidate.is_file():
                errors.append(
                    "markdown input must be a regular file, not a symlink: "
                    f"{candidate.relative_to(ROOT).as_posix()}"
                )
                continue
            files.append(candidate)
    return files


def markdown_files(
    manifest: dict[str, object],
    trusted_manifest: dict[str, object],
    errors: list[str],
) -> list[Path]:
    patterns = string_list_field(
        manifest, "link_check_exclude_globs", errors, "doc-sync-rules"
    )
    trusted_patterns = string_list_field(
        trusted_manifest,
        "link_check_exclude_globs",
        errors,
        "trusted doc-sync-rules",
    )
    if patterns != trusted_patterns:
        errors.append(
            "Target doc-sync-rules link_check_exclude_globs must exactly match the "
            "trusted policy; additions, removals, and reordering are not allowed"
        )

    files: set[Path] = set()
    for candidate in ROOT.iterdir():
        if candidate.suffix != ".md":
            continue
        if candidate.is_symlink() or not candidate.is_file():
            errors.append(
                "root markdown input must be a regular file, not a symlink: "
                f"{candidate.relative_to(ROOT).as_posix()}"
            )
            continue
        files.add(candidate)
    for base in (DOCS_ROOT, ROOT / ".github"):
        files.update(safe_markdown_tree(base, errors))
    selected = [
        path
        for path in files
        if not any(
            fnmatch.fnmatch(path.relative_to(ROOT).as_posix(), pattern)
            for pattern in patterns
        )
    ]
    return sorted(selected)


def extract_links_from_text(
    markdown_path: Path, text: str
) -> list[tuple[str, Path | None]]:
    links: list[tuple[str, Path | None]] = []
    matches = (
        match
        for pattern in (INLINE_LINK_RE, REFERENCE_LINK_RE)
        for match in pattern.finditer(text)
    )
    for match in matches:
        raw = next(
            (group.strip() for group in match.groups() if group is not None), ""
        )
        if raw.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = raw.split("#", 1)[0]
        if target.startswith(("~/", "~\\", "//")) or re.match(
            r"^[A-Za-z]:[\\/]", target
        ):
            # Explicit machine-local evidence pointers are not repository links.
            continue
        if target.startswith(("/Users/", "/home/", "/private/", "/Volumes/")):
            continue
        if target.startswith("/"):
            links.append((raw, None))
            continue
        if target:
            links.append((raw, (markdown_path.parent / target).resolve()))
    return links


def extract_links(markdown_path: Path) -> list[tuple[str, Path | None]]:
    return extract_links_from_text(
        markdown_path, markdown_path.read_text(encoding="utf-8")
    )


def field_values(text: str, field: str) -> list[str]:
    pattern = re.compile(FIELD_RE_TEMPLATE.format(field=re.escape(field)), re.MULTILINE)
    return [match.group(1).strip() for match in pattern.finditer(text)]


def normalized(value: str) -> str:
    return value.strip().strip("`").lower().strip(".,;:")


def pending(value: str) -> bool:
    return normalized(value) in PENDING_VALUES


def required_field(
    text: str,
    plan: Path,
    field: str,
    errors: list[str],
    *,
    allow_pending: bool = False,
) -> str:
    values = field_values(text, field)
    relative = plan.relative_to(ROOT).as_posix()
    if len(values) != 1:
        errors.append(f"Active plan {relative} must contain exactly one '{field}' field")
        return ""
    value = values[0]
    if not allow_pending and pending(value):
        errors.append(f"Active plan {relative} has empty or pending '{field}'")
    return value


def enum_field(
    text: str,
    plan: Path,
    field: str,
    allowed: set[str],
    errors: list[str],
) -> str:
    value = normalized(required_field(text, plan, field, errors))
    if value and value not in allowed:
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} has invalid {field}: "
            f"{value}; expected one of {', '.join(sorted(allowed))}"
        )
    return value


def check_delegation_contract(text: str, plan: Path, errors: list[str]) -> None:
    task_class = enum_field(text, plan, "Task class", VALID_TASK_CLASSES, errors)
    budget = enum_field(text, plan, "Reasoning budget", VALID_REASONING_BUDGETS, errors)
    route = enum_field(text, plan, "Delegation route", VALID_DELEGATION_ROUTES, errors)
    required_field(text, plan, "Delegation decision", errors)
    used = normalized(required_field(text, plan, "Used subagent", errors))
    fallback = required_field(
        text,
        plan,
        "No-subagent fallback reason",
        errors,
        allow_pending=True,
    )

    if (
        task_class in VALID_TASK_CLASSES
        and budget in VALID_REASONING_BUDGETS
        and EXPECTED_BUDGET[task_class] != budget
    ):
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} maps {task_class} "
            f"to reasoning budget {budget}; expected {EXPECTED_BUDGET[task_class]}"
        )
    if (
        task_class in VALID_TASK_CLASSES
        and route in VALID_DELEGATION_ROUTES
        and route not in ALLOWED_ROUTES[task_class]
    ):
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} uses delegation route "
            f"{route} for {task_class}"
        )
    if used not in TRUE_VALUES | FALSE_VALUES:
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} has invalid "
            f"Used subagent value: {used}"
        )

    delegated = route in {"main+subagent", "main+work-thread", "main+parallel-subagents"}
    if delegated and used not in TRUE_VALUES:
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} uses {route} but "
            "does not record Used subagent: yes"
        )
    if route in {"single-agent", "no-subagent-fallback"} and used not in FALSE_VALUES:
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} uses {route} but "
            "does not record Used subagent: no"
        )
    if route == "no-subagent-fallback" and pending(fallback):
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} must provide a "
            "non-pending No-subagent fallback reason"
        )

    delegated_scope = required_field(
        text, plan, "Delegated scope", errors, allow_pending=not delegated
    )
    forbidden_scope = required_field(
        text, plan, "Forbidden scope", errors, allow_pending=not delegated
    )
    subagent_result = required_field(
        text, plan, "Subagent result", errors, allow_pending=True
    )
    main_review = required_field(
        text, plan, "Main agent review", errors, allow_pending=True
    )
    required_field(text, plan, "Rework requested", errors, allow_pending=True)
    accepted_diff = required_field(
        text, plan, "Final accepted diff", errors, allow_pending=True
    )
    if delegated and (pending(delegated_scope) or pending(forbidden_scope)):
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} must define delegated "
            "and forbidden scope before delegated work"
        )
    if delegated and OUT_OF_REPO_SCOPE_RE.search(delegated_scope):
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} must express "
            "Delegated scope with repository-relative paths, not an absolute "
            "machine or parent-workspace path"
        )
    if not pending(accepted_diff) and (pending(subagent_result) or pending(main_review)):
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} accepts a final diff "
            "before subagent result and main-agent review are complete"
        )


def check_claims_and_review(text: str, plan: Path, errors: list[str]) -> None:
    for claim in ("Context Claim", "Scope Claim", "Change Claim", "Validation Claim"):
        required_field(text, plan, claim, errors)
    required_field(text, plan, "Required", errors)
    completed_head = required_field(
        text, plan, "Completed review head", errors, allow_pending=True
    )
    review_result = required_field(
        text, plan, "Review result", errors, allow_pending=True
    )
    for field in (
        "Requested by",
        "Requested at",
        "Current review target pointer",
        "Heartbeat required",
        "Heartbeat interval",
        "Heartbeat stop condition",
        "Start tier",
        "Current tier",
        "Max attempts per tier",
        "Attempts at current tier",
        "Total repair attempts",
        "Escalation path",
        "Stop condition",
        "Last repeated finding",
        "Human intervention required",
        "Main synced",
        "Local branch deleted",
        "Heartbeat closed",
    ):
        required_field(text, plan, field, errors, allow_pending=True)
    if not pending(review_result) and pending(completed_head):
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} records a review result "
            "without a completed review head"
        )
    if not pending(completed_head):
        candidate = completed_head.strip().strip("`")
        if not FULL_SHA_RE.fullmatch(candidate):
            errors.append(
                f"Active plan {plan.relative_to(ROOT).as_posix()} must record "
                "Completed review head as a full 40-character commit SHA"
            )


def check_active_plan_directories(errors: list[str]) -> bool:
    valid = True
    for path, label in (
        (DOCS_ROOT / "exec-plans", "exec-plans directory"),
        (ACTIVE_PLAN_DIR, "active-plan directory"),
        (COMPLETED_PLAN_DIR, "completed-plan directory"),
    ):
        if path.is_symlink() or not path.is_dir():
            errors.append(f"{label} must be a real directory, not a symlink: {path.relative_to(ROOT)}")
            valid = False
    if valid:
        relative = ACTIVE_PLAN_SENTINEL.relative_to(ROOT).as_posix()
        if ACTIVE_PLAN_SENTINEL.is_symlink() or not ACTIVE_PLAN_SENTINEL.is_file():
            errors.append(
                "active-plan directory sentinel must be a regular file, not a "
                f"symlink or special file: {relative}"
            )
            valid = False
        elif ACTIVE_PLAN_SENTINEL.read_bytes() != b"":
            errors.append(
                f"active-plan directory sentinel must be exactly zero bytes: {relative}"
            )
            valid = False
        elif ACTIVE_PLAN_SENTINEL.stat().st_mode & 0o111:
            errors.append(
                f"active-plan directory sentinel must not be executable: {relative}"
            )
            valid = False
    return valid


def plan_files(directory: Path, label: str, errors: list[str]) -> list[Path]:
    if not check_active_plan_directories(errors):
        return []
    plans: list[Path] = []
    for path in sorted(directory.iterdir()):
        if path.name == ".gitkeep":
            continue
        if path.is_symlink() or not path.is_file():
            errors.append(
                f"{label} must be a regular file, not a symlink or special file: "
                f"{path.relative_to(ROOT).as_posix()}"
            )
            continue
        if path.suffix != ".md":
            errors.append(
                f"{label} bookkeeping may contain only lowercase .md plan files: "
                f"{path.relative_to(ROOT).as_posix()}"
            )
            continue
        plans.append(path)
    return plans


def active_plans(errors: list[str]) -> list[Path]:
    return plan_files(ACTIVE_PLAN_DIR, "Active plan", errors)


def completed_plans(errors: list[str]) -> list[Path]:
    return plan_files(COMPLETED_PLAN_DIR, "Completed plan", errors)


def trusted_completed_plan_relatives(errors: list[str]) -> set[str]:
    directory = TRUSTED_DOCS_ROOT / "exec-plans" / "completed"
    if directory.is_symlink() or not directory.is_dir():
        errors.append(
            "trusted completed-plan directory must be a real directory, not a symlink: "
            f"{directory}"
        )
        return set()
    relatives: set[str] = set()
    for path in sorted(directory.iterdir()):
        if path.name == ".gitkeep":
            continue
        relative = path.relative_to(TRUSTED_ROOT).as_posix()
        if path.is_symlink() or not path.is_file() or path.suffix != ".md":
            errors.append(
                "Trusted completed-plan bookkeeping must contain only regular lowercase "
                f".md files: {relative}"
            )
            continue
        relatives.add(relative)
    return relatives


def require_lifecycle_value(
    text: str,
    plan: Path,
    field: str,
    allowed: set[str],
    errors: list[str],
) -> None:
    values = lifecycle_field_values(text, field)
    relative = plan.relative_to(ROOT).as_posix()
    if len(values) != 1:
        errors.append(
            f"Plan {relative} must contain exactly one '{field}' field"
        )
        return
    value = normalized(values[0])
    if value not in allowed:
        errors.append(
            f"Plan {relative} has invalid {field}: {values[0] or '(empty)'}; "
            f"expected one of {', '.join(sorted(allowed))}"
        )


def require_canonical_lifecycle_value(
    text: str,
    plan: Path,
    field: str,
    allowed: set[str],
    errors: list[str],
) -> None:
    values = lifecycle_field_values(text, field)
    relative = plan.relative_to(ROOT).as_posix()
    if len(values) != 1:
        errors.append(f"Plan {relative} must contain exactly one '{field}' field")
        return
    if values[0] not in allowed:
        errors.append(
            f"Plan {relative} has invalid {field}: {values[0] or '(empty)'}; "
            f"expected canonical value {', '.join(sorted(allowed))}"
        )


def lifecycle_field_values(text: str, field: str) -> list[str]:
    pattern = re.compile(
        FIELD_RE_TEMPLATE.format(field=re.escape(field)),
        re.MULTILINE | re.IGNORECASE,
    )
    return [match.group(1).strip() for match in pattern.finditer(text)]


def lifecycle_skeleton(text: str) -> str | None:
    skeleton = text
    for field in PLAN_LIFECYCLE_FIELDS:
        pattern = re.compile(
            rf"^(?P<prefix>[ \t]*-[ \t]*{re.escape(field)}[ \t]*[:：][ \t]*)"
            rf"(?P<value>[^\r\n]*)(?P<line_ending>\r?)$",
            re.MULTILINE | re.IGNORECASE,
        )
        matches = list(pattern.finditer(skeleton))
        if len(matches) != 1:
            return None
        skeleton = pattern.sub(
            lambda match, field=field: (
                match.group("prefix")
                + f"<{field}>"
                + match.group("line_ending")
            ),
            skeleton,
            count=1,
        )
    return skeleton


def check_active_plans(errors: list[str]) -> None:
    plans = active_plans(errors)
    if len(plans) > 1:
        errors.append(
            f"Expected at most one active plan, found {len(plans)}: "
            + ", ".join(path.name for path in plans)
        )
        return
    for plan in plans:
        text = plan.read_text(encoding="utf-8")
        for field in PLAN_LIFECYCLE_FIELDS:
            if len(lifecycle_field_values(text, field)) != 1:
                errors.append(
                    f"Plan {plan.relative_to(ROOT).as_posix()} must contain exactly "
                    f"one '{field}' lifecycle field"
                )
        require_lifecycle_value(text, plan, "Status", {"active"}, errors)
        archived = lifecycle_field_values(text, "Active Plan archived")
        transition = lifecycle_field_values(text, "Transition invariant")
        if any(normalized(value) == "completed" for value in archived) or any(
            normalized(value) in COMPLETED_TRANSITION_VALUES for value in transition
        ):
            errors.append(
                f"Active plan {plan.relative_to(ROOT).as_posix()} contains mixed "
                "completed lifecycle state"
            )
        if not TASK_CLASSIFICATION_HEADING_RE.search(text):
            errors.append(
                f"Active plan {plan.relative_to(ROOT).as_posix()} missing required "
                "Task Classification / 任务分类 heading"
            )
        if not DOCUMENTATION_IMPACT_HEADING_RE.search(text):
            errors.append(
                f"Active plan {plan.relative_to(ROOT).as_posix()} missing required "
                "Documentation Impact / 文档影响 heading"
            )
        for section in REQUIRED_EVIDENCE_SECTIONS:
            if section not in text:
                errors.append(
                    f"Active plan {plan.relative_to(ROOT).as_posix()} "
                    f"missing required evidence section: {section}"
                )
        check_delegation_contract(text, plan, errors)
        check_claims_and_review(text, plan, errors)
        check_required_check_name(text, plan, errors)


def check_completed_plans(errors: list[str]) -> None:
    plans = completed_plans(errors)
    target_relatives = {plan.relative_to(ROOT).as_posix() for plan in plans}
    standalone_base: str | None = None
    if TRUSTED_ROOT == ROOT:
        advertised_sha = os.environ.get(STANDALONE_BASE_ENV)
        if advertised_sha is not None:
            valid_base, standalone_base = resolve_standalone_base(advertised_sha, errors)
            if not valid_base:
                return
        else:
            standalone_base = optional_standalone_head()
    if TRUSTED_ROOT != ROOT:
        trusted_relatives = trusted_completed_plan_relatives(errors)
        for relative in sorted(trusted_relatives - target_relatives):
            errors.append(
                "Completed plan content and mode are immutable after archival; deletion "
                f"is forbidden: {relative}"
            )
    elif standalone_base is not None:
        base_relatives = standalone_completed_plan_relatives(standalone_base, errors)
        if base_relatives is None:
            return
        for relative in sorted(base_relatives - target_relatives):
            errors.append(
                "Completed plan content and mode are immutable after archival; deletion "
                f"is forbidden: {relative}"
            )
    for plan in plans:
        relative = plan.relative_to(ROOT).as_posix()
        target_metadata: list[os.stat_result] = []
        text = read_regular_text_at(
            ROOT, relative, errors, metadata_out=target_metadata
        )
        if text is None:
            continue
        if TRUSTED_ROOT == ROOT and standalone_base is not None:
            valid_entry, base_mode, base_blob = standalone_tree_plan(
                standalone_base, relative, errors
            )
            if not valid_entry:
                continue
            if base_mode is not None:
                target_mode = (
                    "100755" if target_metadata[0].st_mode & 0o111 else "100644"
                )
                if base_mode == target_mode and base_blob == text.encode("utf-8"):
                    continue
                errors.append(
                    "Completed plan content and mode are immutable after archival: "
                    f"{relative}"
                )
                continue
        elif TRUSTED_ROOT != ROOT:
            trusted_plan = exact_case_real_path_at(TRUSTED_ROOT, relative)
            if trusted_plan is not None and trusted_plan.is_file():
                trusted_metadata: list[os.stat_result] = []
                trusted_text = read_regular_text_at(
                    TRUSTED_ROOT, relative, errors, metadata_out=trusted_metadata
                )
                if trusted_text is None:
                    continue
                same_mode = stat.S_IMODE(target_metadata[0].st_mode) == stat.S_IMODE(
                    trusted_metadata[0].st_mode
                )
                if same_mode and text.encode("utf-8") == trusted_text.encode("utf-8"):
                    continue
                errors.append(
                    "Completed plan content and mode are immutable after archival: "
                    f"{relative}"
                )
                continue
        for field, allowed in COMPLETED_LIFECYCLE_CONTRACT.items():
            require_canonical_lifecycle_value(text, plan, field, allowed, errors)


def trusted_active_plans(errors: list[str]) -> list[Path]:
    exec_plans = TRUSTED_DOCS_ROOT / "exec-plans"
    active = exec_plans / "active"
    for path, label in (
        (exec_plans, "trusted exec-plans directory"),
        (active, "trusted active-plan directory"),
    ):
        if path.is_symlink() or not path.is_dir():
            errors.append(f"{label} must be a real directory, not a symlink: {path}")
            return []
    plans: list[Path] = []
    for path in sorted(active.iterdir()):
        if path.name == ".gitkeep":
            continue
        if path.is_symlink() or not path.is_file():
            errors.append(
                "Trusted Active Plan must be a regular file, not a symlink or "
                f"special file: {path}"
            )
            continue
        if path.suffix != ".md":
            errors.append(
                "Trusted Active Plan bookkeeping may contain only lowercase .md "
                f"plan files: {path}"
            )
            continue
        plans.append(path)
    return plans


def exact_archive_index_transition(
    index_path: str,
    trusted_active: Path,
    completed_plan: Path,
    errors: list[str],
) -> bool:
    trusted_index = TRUSTED_ROOT / index_path
    target_index = ROOT / index_path
    trusted_metadata: list[os.stat_result] = []
    target_metadata: list[os.stat_result] = []
    trusted_text = read_regular_text_at(
        TRUSTED_ROOT, index_path, errors, metadata_out=trusted_metadata
    )
    target_text = read_regular_text_at(
        ROOT, index_path, errors, metadata_out=target_metadata
    )
    if trusted_text is None or target_text is None:
        return False
    if stat.S_IMODE(trusted_metadata[0].st_mode) != stat.S_IMODE(
        target_metadata[0].st_mode
    ):
        errors.append(
            f"{index_path} archive cleanup may not change the index file mode"
        )
        return False

    active_links = [
        raw
        for raw, linked in extract_links(trusted_index)
        if linked is not None and linked == trusted_active.resolve()
    ]
    if len(active_links) != 1:
        errors.append(
            f"trusted {index_path} must contain exactly one link to the Active Plan "
            "for an archive cleanup transition"
        )
        return False
    raw = active_links[0]
    raw_path, separator, fragment = raw.partition("#")
    active_relative = os.path.relpath(
        trusted_active, trusted_index.parent
    ).replace(os.sep, "/")
    completed_relative = os.path.relpath(
        completed_plan, target_index.parent
    ).replace(os.sep, "/")
    prefix = "./" if raw_path.startswith("./") else ""
    if raw_path.removeprefix("./") != active_relative or trusted_text.count(raw) != 1:
        errors.append(
            f"trusted {index_path} Active Plan link is not an unambiguous repository-"
            "relative archive target"
        )
        return False
    completed_raw = prefix + completed_relative
    if separator:
        completed_raw += separator + fragment
    expected = trusted_text.replace(raw, completed_raw, 1)
    completed_links = [
        linked
        for _, linked in extract_links(target_index)
        if linked is not None and linked == completed_plan.resolve()
    ]
    if len(completed_links) != 1 or target_text != expected:
        errors.append(
            f"{index_path} archive cleanup may only change the unique Active Plan "
            "link from active/ to completed/"
        )
        return False
    return True


def exact_standalone_archive_index_transition(
    index_path: str,
    active_relative: str,
    completed_plan: Path,
    base_sha: str,
    errors: list[str],
) -> bool:
    valid_entry, base_mode, base_blob = standalone_tree_plan(
        base_sha, index_path, errors
    )
    if not valid_entry:
        return False
    if base_mode is None or base_blob is None:
        errors.append(
            f"standalone base {index_path} must be a regular file for archive cleanup"
        )
        return False
    trusted_text = base_blob.decode("utf-8")
    target_metadata: list[os.stat_result] = []
    target_text = read_regular_text_at(
        ROOT, index_path, errors, metadata_out=target_metadata
    )
    if target_text is None:
        return False
    target_mode = "100755" if target_metadata[0].st_mode & 0o111 else "100644"
    if base_mode != target_mode:
        errors.append(
            f"{index_path} archive cleanup may not change the index file mode"
        )
        return False

    source_index = ROOT / index_path
    target_index = ROOT / index_path
    active_plan = (ROOT / active_relative).resolve()
    active_links = [
        raw
        for raw, linked in extract_links_from_text(source_index, trusted_text)
        if linked is not None and linked == active_plan
    ]
    if len(active_links) != 1:
        errors.append(
            f"standalone base {index_path} must contain exactly one link to the "
            "Active Plan for an archive cleanup transition"
        )
        return False
    raw = active_links[0]
    raw_path, separator, fragment = raw.partition("#")
    active_relative_from_index = os.path.relpath(
        ROOT / active_relative, source_index.parent
    ).replace(os.sep, "/")
    completed_relative = os.path.relpath(
        completed_plan, target_index.parent
    ).replace(os.sep, "/")
    prefix = "./" if raw_path.startswith("./") else ""
    if (
        raw_path.removeprefix("./") != active_relative_from_index
        or trusted_text.count(raw) != 1
    ):
        errors.append(
            f"standalone base {index_path} Active Plan link is not an unambiguous "
            "repository-relative archive target"
        )
        return False
    completed_raw = prefix + completed_relative
    if separator:
        completed_raw += separator + fragment
    expected = trusted_text.replace(raw, completed_raw, 1)
    completed_links = [
        linked
        for _, linked in extract_links(target_index)
        if linked is not None and linked == completed_plan.resolve()
    ]
    if len(completed_links) != 1 or target_text != expected:
        errors.append(
            f"{index_path} archive cleanup may only change the unique Active Plan "
            "link from active/ to completed/"
        )
        return False
    return True


def validate_archive_plan_transition(
    source_text: str,
    source_mode: str,
    completed_plan: Path,
    errors: list[str],
) -> bool:
    completed_relative = completed_plan.relative_to(ROOT).as_posix()
    completed_metadata: list[os.stat_result] = []
    completed_text = read_regular_text_at(
        ROOT, completed_relative, errors, metadata_out=completed_metadata
    )
    if completed_text is None:
        return False
    target_mode = "100755" if completed_metadata[0].st_mode & 0o111 else "100644"
    if source_mode != target_mode:
        errors.append(
            "archive cleanup may not change the Active Plan file mode while moving "
            "it to completed/"
        )
        return False

    source_status = lifecycle_field_values(source_text, "Status")
    if len(source_status) != 1 or normalized(source_status[0]) != "active":
        errors.append(
            "archive cleanup source must contain exactly one 'Status: active' field"
        )
        return False
    source_archived = lifecycle_field_values(source_text, "Active Plan archived")
    source_transition = lifecycle_field_values(source_text, "Transition invariant")
    if (
        len(source_archived) != 1
        or normalized(source_archived[0]) == "completed"
        or len(source_transition) != 1
        or normalized(source_transition[0]) in COMPLETED_TRANSITION_VALUES
    ):
        errors.append(
            "archive cleanup source contains mixed or already-completed lifecycle state"
        )
        return False
    if any(
        len(values := lifecycle_field_values(completed_text, field)) != 1
        or values[0] not in allowed
        for field, allowed in COMPLETED_LIFECYCLE_CONTRACT.items()
    ):
        errors.append(
            "archive cleanup destination must contain the completed lifecycle contract"
        )
        return False
    source_skeleton = lifecycle_skeleton(source_text)
    completed_skeleton = lifecycle_skeleton(completed_text)
    if source_skeleton is None or completed_skeleton is None:
        errors.append(
            "archive cleanup plans must contain exactly one of each lifecycle field"
        )
        return False
    if source_skeleton != completed_skeleton:
        errors.append(
            "archive cleanup may only change the canonical lifecycle fields in the "
            "moved plan"
        )
        return False
    return True


def exact_standalone_archive_cleanup(
    index_path: str, base_sha: str, errors: list[str]
) -> bool:
    active_relatives = standalone_active_plan_relatives(base_sha, errors)
    if active_relatives is None:
        return False
    if not active_relatives:
        return True
    if len(active_relatives) != 1:
        errors.append(
            "archive cleanup requires exactly one standalone base Active Plan; found "
            f"{len(active_relatives)}"
        )
        return False
    active_relative = next(iter(active_relatives))
    completed_plan = COMPLETED_PLAN_DIR / Path(active_relative).name
    if completed_plan.is_symlink() or not completed_plan.is_file():
        errors.append(
            "archive cleanup must move the standalone base Active Plan to the same "
            f"regular completed filename: {completed_plan.relative_to(ROOT).as_posix()}"
        )
        return False

    valid_entry, source_mode, source_blob = standalone_tree_plan(
        base_sha, active_relative, errors
    )
    if not valid_entry:
        return False
    if source_mode is None or source_blob is None:
        errors.append("standalone base Active Plan must be a regular file")
        return False
    source_text = source_blob.decode("utf-8")
    source_plan = ROOT / active_relative
    if not validate_archive_plan_transition(
        source_text, source_mode, completed_plan, errors
    ):
        return False
    return exact_standalone_archive_index_transition(
        index_path,
        source_plan.relative_to(ROOT).as_posix(),
        completed_plan,
        base_sha,
        errors,
    )


def exact_archive_cleanup(index_path: str, errors: list[str]) -> bool:
    trusted_plans = trusted_active_plans(errors)
    if len(trusted_plans) != 1:
        errors.append(
            "archive cleanup requires exactly one trusted Active Plan; found "
            f"{len(trusted_plans)}"
        )
        return False
    trusted_plan = trusted_plans[0]
    completed_plan = COMPLETED_PLAN_DIR / trusted_plan.name
    if completed_plan.is_symlink() or not completed_plan.is_file():
        errors.append(
            "archive cleanup must move the trusted Active Plan to the same regular "
            f"completed filename: {completed_plan.relative_to(ROOT).as_posix()}"
        )
        return False

    trusted_relative = trusted_plan.relative_to(TRUSTED_ROOT).as_posix()
    trusted_metadata: list[os.stat_result] = []
    trusted_text = read_regular_text_at(
        TRUSTED_ROOT, trusted_relative, errors, metadata_out=trusted_metadata
    )
    if trusted_text is None:
        return False
    trusted_mode = "100755" if trusted_metadata[0].st_mode & 0o111 else "100644"
    if not validate_archive_plan_transition(
        trusted_text, trusted_mode, completed_plan, errors
    ):
        return False
    return exact_archive_index_transition(
        index_path, trusted_plan, completed_plan, errors
    )


def check_target_invariants(
    trusted_manifest: dict[str, object], errors: list[str]
) -> None:
    invariants = trusted_manifest.get("target_invariants", [])
    if not isinstance(invariants, list):
        errors.append("trusted doc-sync-rules target_invariants must be a list")
        return
    plans = active_plans(errors)
    for index, spec in enumerate(invariants):
        label = f"trusted doc-sync-rules target_invariants[{index}]"
        if not isinstance(spec, dict):
            errors.append(f"{label} must be an object")
            continue
        invariant_type = spec.get("type")
        if invariant_type != "active_plan_index_link":
            errors.append(f"{label}.type is unsupported: {invariant_type!r}")
            continue
        index_path = spec.get("index")
        if not isinstance(index_path, str) or not index_path:
            errors.append(f"{label}.index must be a non-empty repository path")
            continue
        if not exact_case_path_exists(index_path):
            errors.append(f"{label}.index is missing or case-mismatched: {index_path}")
            continue
        source = ROOT / index_path
        if source.is_symlink() or not source.is_file():
            errors.append(f"{label}.index must be a regular file: {index_path}")
            continue
        if len(plans) == 0:
            if TRUSTED_ROOT == ROOT:
                advertised_sha = os.environ.get(STANDALONE_BASE_ENV)
                if advertised_sha is not None:
                    valid_base, standalone_base = resolve_standalone_base(
                        advertised_sha, errors
                    )
                    if not valid_base:
                        continue
                elif os.environ.get("CI", "").casefold() == "true":
                    errors.append(
                        f"{STANDALONE_BASE_ENV} is required in CI when no Active Plan "
                        "exists so archive transitions cannot be mistaken for idle state"
                    )
                    continue
                else:
                    standalone_base = optional_standalone_head()
                if standalone_base is not None:
                    exact_standalone_archive_cleanup(
                        index_path, standalone_base, errors
                    )
                continue
            trusted_plans = trusted_active_plans(errors)
            if len(trusted_plans) == 0:
                continue
            exact_archive_cleanup(index_path, errors)
            continue
        if len(plans) != 1:
            continue
        active_plan = plans[0].resolve()
        linked_targets = {
            linked for _, linked in extract_links(source) if linked is not None
        }
        if active_plan not in linked_targets:
            errors.append(
                f"{index_path} must link to the current Active Plan: "
                f"{active_plan.relative_to(ROOT).as_posix()}"
            )


def check_required_check_name(text: str, path: Path, errors: list[str]) -> None:
    values = field_values(text, "Required check name")
    has_merge_readiness = bool(
        re.search(r"^## Merge Readiness\s*$", text, re.MULTILINE)
    )
    relative = path.relative_to(ROOT).as_posix()
    if has_merge_readiness and len(values) != 1:
        errors.append(
            f"{relative} must contain exactly one 'Required check name' field"
        )
        return
    if len(values) > 1:
        errors.append(
            f"{relative} must contain at most one 'Required check name' field"
        )
        return
    if values and normalized(values[0]) != "loop/checkpoints":
        errors.append(
            f"{relative} Required check name must be 'loop/checkpoints'"
        )


def check_current_head_governance(errors: list[str]) -> None:
    relative = f"{DOCS_ROOT.name}/governance/checkpoint-ci-gate.md"
    # Pin every parent directory with no-follow descriptors, then open the final
    # component non-blocking and read only after bounded regular-file validation.
    text = read_regular_text_at(ROOT, relative, errors)
    if text is None:
        return
    count = text.count(CURRENT_HEAD_REVIEW_HEADING)
    if count != 1:
        errors.append(
            "checkpoint governance must contain exactly one canonical "
            "Current-Head Codex Review section"
        )
        return
    section_body = text.split(CURRENT_HEAD_REVIEW_HEADING, 1)[1]
    section_body = re.split(r"(?=^## )", section_body, maxsplit=1, flags=re.MULTILINE)[0]
    section = CURRENT_HEAD_REVIEW_HEADING + section_body
    digest = hashlib.sha256((section.rstrip() + "\n").encode("utf-8")).hexdigest()
    if digest != CURRENT_HEAD_REVIEW_SHA256:
        errors.append(
            "checkpoint governance Current-Head Codex Review section differs "
            "from the trusted canonical contract"
        )


def workflow_mapping_entries(text: str) -> dict[tuple[str, ...], list[str]]:
    """Return YAML mapping paths while ignoring comments and block scalars."""
    entries: dict[tuple[str, ...], list[str]] = {}
    stack: list[tuple[int, str]] = []
    block_scalar_indent: int | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if block_scalar_indent is not None:
            if indent > block_scalar_indent:
                continue
            block_scalar_indent = None
        match = YAML_MAPPING_KEY_RE.match(raw_line)
        if match is None:
            continue
        key = match.group("key")
        value = match.group("value").strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = tuple(item[1] for item in stack) + (key,)
        entries.setdefault(path, []).append(value)
        if value == "":
            stack.append((indent, key))
        elif value in {"|", "|-", "|+", ">", ">-", ">+"}:
            block_scalar_indent = indent
    return entries


def workflow_structure_errors(text: str) -> list[str]:
    entries = workflow_mapping_entries(text)
    required_paths = (
        ("on", "pull_request_target"),
        ("on", "repository_dispatch"),
        ("on", "push"),
        ("jobs", "resolve-pull-request"),
        ("jobs", "mark-checkpoints-pending"),
        ("jobs", "pull-request-checkpoints"),
        ("jobs", "publish-checkpoints-result"),
        ("jobs", "dispatch-open-pull-requests"),
        ("jobs", "default-branch-checkpoints"),
    )
    errors = [
        f"missing or duplicate workflow mapping: {'.'.join(path)}"
        for path in required_paths
        if len(entries.get(path, [])) != 1
    ]
    if entries.get(("on", "repository_dispatch", "types"), []) != [
        "[loop-checkpoints-reconcile]"
    ]:
        errors.append(
            "on.repository_dispatch.types must be [loop-checkpoints-reconcile]"
        )
    if entries.get(("permissions",), []) != ["{}"]:
        errors.append("top-level permissions must be an empty mapping")
    return errors


def check_codex_review_workflows(
    required_paths: list[str], errors: list[str]
) -> None:
    gate_relative = ".github/workflows/codex-review-gate.yml"
    heartbeat_relative = ".github/workflows/codex-review-heartbeat.yml"
    signal_relative = ".github/workflows/codex-review-signal.yml"
    for relative in (gate_relative, heartbeat_relative):
        if relative not in required_paths:
            errors.append(f"doc-sync-rules must require trusted workflow: {relative}")

    signal_path = ROOT / signal_relative
    if signal_relative in required_paths or signal_path.exists() or signal_path.is_symlink():
        errors.append(
            "PR-sourced Codex review signal workflow must be absent; review evidence "
            "is reconciled by the trusted heartbeat"
        )

    gate_path = ROOT / gate_relative
    if gate_path.is_symlink() or not gate_path.is_file():
        errors.append(f"Codex review gate must be a regular file: {gate_relative}")
    else:
        gate_text = gate_path.read_text(encoding="utf-8")
        gate_entries = workflow_mapping_entries(gate_text)
        required_triggers = (
            ("on", "pull_request_target"),
            ("on", "issue_comment"),
            ("on", "repository_dispatch"),
            ("on", "push"),
        )
        forbidden_triggers = (
            ("on", "pull_request_review"),
            ("on", "pull_request_review_comment"),
            ("on", "workflow_run"),
        )
        if any(len(gate_entries.get(path, [])) != 1 for path in required_triggers):
            errors.append("Codex review gate is missing a trusted reconciliation trigger")
        if any(gate_entries.get(path) for path in forbidden_triggers):
            errors.append(
                "Codex review gate cannot use PR-sourced review or workflow_run triggers"
            )
        if signal_relative in gate_text or "route-review-signal" in gate_text:
            errors.append("Codex review gate still references the deleted signal route")

    heartbeat_path = ROOT / heartbeat_relative
    if heartbeat_path.is_symlink() or not heartbeat_path.is_file():
        errors.append(
            f"Codex review heartbeat must be a regular file: {heartbeat_relative}"
        )
    else:
        heartbeat_text = heartbeat_path.read_text(encoding="utf-8")
        heartbeat_entries = workflow_mapping_entries(heartbeat_text)
        if len(heartbeat_entries.get(("on", "schedule"), [])) != 1:
            errors.append("Codex review heartbeat must use a default-branch schedule")
        required_fragments = (
            'cron: "*/5 * * * *"',
            'pulls?state=open&base=main&per_page=100',
            "event_type=codex-review-reconcile",
            'client_payload[pr_number]=${number}',
        )
        if any(fragment not in heartbeat_text for fragment in required_fragments):
            errors.append(
                "Codex review heartbeat must reconcile every open main PR every five minutes"
            )
        forbidden_fragments = (
            "statuses: write",
            "actions/checkout",
            "created_at",
            "updated_at",
            "age cutoff",
            "42 hours",
        )
        if any(fragment in heartbeat_text for fragment in forbidden_fragments):
            errors.append(
                "Codex review heartbeat cannot write statuses, checkout code, or age-gate PRs"
            )


def check_document_status_workflow(
    manifest: dict[str, object],
    trusted_manifest: dict[str, object],
    required_paths: list[str],
    errors: list[str],
) -> None:
    candidates = [
        value
        for value in required_paths
        if value in {
            ".github/workflows/docs-ci.yml",
            ".github/workflows/checkpoint-ci.yml",
        }
    ]
    if len(candidates) != 1:
        errors.append(
            "doc-sync-rules must require exactly one trusted document status workflow"
        )
        return
    relative = candidates[0]
    required_check = manifest.get("required_check")
    trusted_required_check = trusted_manifest.get("required_check")
    if not isinstance(required_check, dict):
        errors.append("doc-sync-rules required_check must be an object")
    else:
        expected = {
            "name": "loop/checkpoints",
            "workflow": relative,
            "emitter": "trusted_commit_status",
            "required_on": "main",
        }
        for field, value in expected.items():
            if required_check.get(field) != value:
                errors.append(
                    f"doc-sync-rules required_check.{field} must be {value!r}"
                )
    if not isinstance(trusted_required_check, dict):
        errors.append("trusted doc-sync-rules required_check must be an object")
        trusted_required_check = {}
    elif required_check != trusted_required_check:
        errors.append(
            "Target doc-sync-rules cannot remove or rewrite the trusted required_check"
        )
    trusted_workflow_sha256 = trusted_required_check.get("workflow_sha256")
    if (
        not isinstance(trusted_workflow_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", trusted_workflow_sha256) is None
    ):
        errors.append(
            "trusted doc-sync-rules required_check.workflow_sha256 must be a "
            "lowercase SHA-256"
        )
    path = ROOT / relative
    if path.is_symlink() or not path.is_file():
        errors.append(f"Trusted document status workflow must be a regular file: {relative}")
        return
    text = path.read_text(encoding="utf-8")
    structure_errors = workflow_structure_errors(text)
    if structure_errors:
        errors.append(
            f"Trusted document status workflow structure is incomplete: {relative}: "
            + "; ".join(structure_errors)
        )
    markers = (
        "  resolve-pull-request:\n",
        "  mark-checkpoints-pending:\n",
        "  pull-request-checkpoints:\n",
        "  publish-checkpoints-result:\n",
        "  dispatch-open-pull-requests:\n",
        "  default-branch-checkpoints:\n",
    )
    if "# HARNESS_TRUSTED_DOC_STATUS_V4" not in text or any(
        marker not in text for marker in markers
    ):
        errors.append(f"Trusted document status workflow contract is missing: {relative}")
        return
    workflow_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if workflow_digest != trusted_workflow_sha256:
        errors.append(
            f"Trusted document status workflow differs from the trusted whole-file digest: {relative}"
        )
    resolver_job = text.split(markers[0], 1)[1].split(markers[1], 1)[0]
    pending_job = text.split(markers[1], 1)[1].split(markers[2], 1)[0]
    validation_job = text.split(markers[2], 1)[1].split(markers[3], 1)[0]
    publisher_job = text.split(markers[3], 1)[1].split(markers[4], 1)[0]
    fanout_job = text.split(markers[4], 1)[1].split(markers[5], 1)[0]
    default_branch_job = text.split(markers[5], 1)[1]
    pre_jobs = text.split("jobs:\n", 1)[0]
    required_fragments = (
        "branches: [main]",
        'gh api "repos/${GITHUB_REPOSITORY}/pulls/${PULL_REQUEST_NUMBER}"',
        'gh api "repos/${base_repository}/git/ref/heads/${base_ref}"',
        'gh api "repos/${live_base_repository}/git/ref/heads/${live_base_ref}"',
        "head_sha: ${{ steps.resolve.outputs.head_sha }}",
        "base_sha: ${{ steps.resolve.outputs.base_sha }}",
        "repository: ${{ needs.resolve-pull-request.outputs.head_repository }}",
        "ref: ${{ needs.resolve-pull-request.outputs.head_sha }}",
        "repository: ${{ github.repository }}",
        "ref: ${{ needs.resolve-pull-request.outputs.base_sha }}",
        "HARNESS_TRUSTED_REPO_ROOT: ${{ github.workspace }}/trusted",
        'git -c protocol.file.allow=always -C target fetch',
        '"${GITHUB_WORKSPACE}/trusted" "${PR_BASE_SHA}"',
        'git -C trusted rev-parse HEAD',
        '"${actual_base_sha}" != "${PR_BASE_SHA}"',
        'git -C target merge-tree --write-tree',
        'git -c core.hooksPath=/dev/null -C target commit-tree',
        'git -C target reset --hard "${merge_commit}"',
        "python3 -I -B trusted/scripts/check_docs.py --all",
        "trusted/scripts/check_loop_checkpoints.py",
        '"${live_head_sha}" != "${EXPECTED_HEAD_SHA}"',
        '"${live_head_repository}" != "${EXPECTED_HEAD_REPOSITORY}"',
        '"${live_base_sha}" != "${EXPECTED_BASE_SHA}"',
        "refusing a stale status write",
        "fail_closed_before_pending_write()",
        'prewrite_drift_description="Live base changed before pending status;',
        "Failed to leave the bound head with the latest pre-pending fail-closed status.",
        "repos/${GITHUB_REPOSITORY}/dispatches",
        "event_type=loop-checkpoints-reconcile",
        "client_payload[pull_request_number]",
        "if: ${{ always() && github.event_name == 'push' }}",
        '--base "${BEFORE_SHA}" --head HEAD --diff-mode direct',
        '--head HEAD --diff-mode root',
        "A zero-before created-ref push must point at a root commit.",
    )
    if any(fragment not in text for fragment in required_fragments):
        errors.append(f"Trusted document status workflow is incomplete: {relative}")
    if (
        "jq -r '.base.sha'" in text
        or text.count("/git/ref/heads/${") != 4
        or text.count(
            'if [[ "${live_base_sha}" != "${EXPECTED_BASE_SHA}" ]]; then'
        )
        != 2
    ):
        errors.append(
            "Trusted document status workflow must bind and revalidate the live base ref directly: "
            f"{relative}"
        )
    evaluate_marker = "      - name: Evaluate with trusted code\n"
    if evaluate_marker not in validation_job:
        errors.append(
            f"Trusted document status workflow is missing its trusted evaluation step: {relative}"
        )
    else:
        evaluate_step = validation_job.split(evaluate_marker, 1)[1]
        run_marker = "        run: |\n"
        if run_marker not in evaluate_step:
            errors.append(
                f"Trusted document status workflow evaluation step has no executable script: {relative}"
            )
        else:
            run_body = evaluate_step.split(run_marker, 1)[1]
            script_lines: list[str] = []
            for line in run_body.splitlines():
                if line and not line.startswith("          "):
                    break
                script_lines.append(line[10:] if line else "")
            commands: list[str] = []
            pending = ""
            for line in script_lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                pending = f"{pending} {stripped}".strip()
                if pending.endswith("\\"):
                    pending = pending[:-1].rstrip()
                    continue
                commands.append(pending)
                pending = ""
            if pending:
                commands.append(pending)
            expected_scope_command = [
                "python3",
                "-I",
                "-B",
                "trusted/scripts/check_loop_checkpoints.py",
                "--base",
                "${PR_BASE_SHA}",
                "--head",
                "HEAD",
            ]
            parsed_commands: list[list[str]] = []
            for command in commands:
                try:
                    parsed_commands.append(shlex.split(command))
                except ValueError:
                    errors.append(
                        f"Trusted document status workflow evaluation step has invalid shell syntax: {relative}"
                    )
                    break
            if expected_scope_command not in parsed_commands:
                errors.append(
                    "Trusted document status workflow must evaluate the synthetic merge "
                    f"with --base ${{PR_BASE_SHA}} --head HEAD: {relative}"
                )
    if re.search(r"^  pull_request:\s*$", pre_jobs, flags=re.MULTILINE):
        errors.append(f"Trusted document status workflow cannot use pull_request: {relative}")
    if "workflow_dispatch:" in pre_jobs:
        errors.append(
            f"Trusted document status workflow cannot use workflow_dispatch: {relative}"
        )
    if text.count("context=loop/checkpoints") != 2:
        errors.append(
            f"Trusted document status workflow must publish loop/checkpoints twice: {relative}"
        )
    if text.count("statuses: write") != 2:
        errors.append(
            f"Trusted document status workflow must isolate exactly two status writers: {relative}"
        )
    if text.count("actions/checkout@v7") != 3:
        errors.append(
            f"Trusted document status workflow must use two isolated PR checkouts and one default checkout: {relative}"
        )
    if validation_job.count("persist-credentials: false") != 2:
        errors.append(
            f"Trusted document validation checkouts must disable credential persistence: {relative}"
        )
    if validation_job.count("fetch-depth: 0") != 2:
        errors.append(
            f"Trusted target and base checkouts must both fetch complete history: {relative}"
        )
    default_branch_contract = (
        "          fetch-depth: 0\n",
        "          HARNESS_STANDALONE_BASE_SHA: ${{ github.event.before }}\n",
        "        run: python3 -I -B scripts/check_docs.py --all\n",
    )
    if (
        default_branch_job.count("fetch-depth: 0") != 1
        or text.count("HARNESS_STANDALONE_BASE_SHA: ${{ github.event.before }}") != 1
        or any(fragment not in default_branch_job for fragment in default_branch_contract)
        or "check_loop_checkpoints.py --worktree-only" in default_branch_job
    ):
        errors.append(
            "Trusted default-branch document check must fetch complete history and "
            f"bind github.event.before only to check_docs.py: {relative}"
        )
    target_checkout_contract = (
        "          repository: ${{ needs.resolve-pull-request.outputs.head_repository }}\n"
        "          ref: ${{ needs.resolve-pull-request.outputs.head_sha }}\n"
        "          # This checkout is parsed as data only; target code is never executed here.\n"
        "          allow-unsafe-pr-checkout: true\n"
        "          fetch-depth: 0\n"
        "          path: target\n"
        "          persist-credentials: false\n"
    )
    if (
        text.count("allow-unsafe-pr-checkout: true") != 1
        or target_checkout_contract not in validation_job
    ):
        errors.append(
            "Trusted document workflow must opt in exactly once for the data-only "
            f"fork target checkout: {relative}"
        )
    if (
        len(
            re.findall(
                r"^\s+(?:-\s+)?uses:", validation_job, flags=re.MULTILINE
            )
        )
        != 3
        or len(re.findall(r"^        run:", validation_job, flags=re.MULTILINE)) != 2
        or "working-directory:" in validation_job
    ):
        errors.append(
            f"Trusted document validation job may only fetch data and run trusted checkers: {relative}"
        )
    if "statuses: write" in validation_job:
        errors.append(
            f"Trusted document validation job cannot write statuses: {relative}"
        )
    if "github.event.pull_request.head" in validation_job or "github.event.pull_request.base" in validation_job:
        errors.append(
            f"Trusted validation must consume live resolver outputs, not event PR identity: {relative}"
        )
    if "actions/checkout" in pending_job or "actions/checkout" in publisher_job:
        errors.append(
            f"Trusted document status-writing jobs cannot check out repository content: {relative}"
        )
    prewrite_drift_guard = (
        "if ! verify_live_identity; then\n"
        "            fail_closed_before_pending_write\n"
        "            exit 1\n"
        "          fi"
    )
    if pending_job.count(prewrite_drift_guard) != 2:
        errors.append(
            "Trusted document pending writer must fail the bound head when the live "
            f"base drifts before either pending pre-write check: {relative}"
        )
    if any(
        "actions/checkout" in job or "statuses: write" in job
        for job in (resolver_job, fanout_job)
    ):
        errors.append(
            f"Trusted resolver and dispatch fanout cannot check out content or write statuses: {relative}"
        )
    if "statuses: write" not in pending_job or "statuses: write" not in publisher_job:
        errors.append(
            f"Trusted document pending and publisher jobs must own status writes: {relative}"
        )
    if "needs.pull-request-checkpoints.result" not in publisher_job:
        errors.append(
            f"Trusted document publisher must consume the read-only validation result: {relative}"
        )


def check_additional_required_checks(
    manifest: dict[str, object],
    trusted_manifest: dict[str, object],
    required_paths: list[str],
    errors: list[str],
) -> None:
    checks = manifest.get("additional_required_checks", [])
    if not isinstance(checks, list):
        errors.append("doc-sync-rules additional_required_checks must be a list")
        return
    trusted_checks = trusted_manifest.get("additional_required_checks", [])
    if not isinstance(trusted_checks, list):
        errors.append(
            "trusted doc-sync-rules additional_required_checks must be a list"
        )
        trusted_checks = []
    for trusted_spec in trusted_checks:
        if not isinstance(trusted_spec, dict):
            errors.append(
                "trusted doc-sync-rules additional_required_checks contains a "
                "non-object entry"
            )
            continue
        if trusted_spec not in checks:
            name = trusted_spec.get("name", "<unnamed>")
            errors.append(
                "Target doc-sync-rules cannot remove or rewrite trusted additional "
                f"required check: {name}"
            )
    names: set[str] = set()
    for index, spec in enumerate(checks):
        label = f"doc-sync-rules additional_required_checks[{index}]"
        if not isinstance(spec, dict):
            errors.append(f"{label} must be an object")
            continue
        expected_fields = {
            "emitter": "actions_check_run",
            "required_on": "main",
            "app_id": GITHUB_ACTIONS_APP_ID,
        }
        for field, expected in expected_fields.items():
            if spec.get(field) != expected:
                errors.append(f"{label}.{field} must be {expected!r}")
        name = spec.get("name")
        workflow = spec.get("workflow")
        digest = spec.get("workflow_sha256")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{label}.name must be a non-empty string")
        elif name in {"loop/checkpoints", "codex-review"}:
            errors.append(f"{label}.name cannot reuse a Harness status context")
        elif name in names:
            errors.append(f"{label}.name is duplicated: {name}")
        else:
            names.add(name)
        if not isinstance(workflow, str) or not workflow.startswith(
            ".github/workflows/"
        ):
            errors.append(f"{label}.workflow must name a workflow path")
            continue
        if ".." in PurePosixPath(workflow).parts:
            errors.append(f"{label}.workflow must stay inside .github/workflows")
            continue
        if workflow not in required_paths:
            errors.append(f"{label}.workflow must also appear in required_paths")
        path = exact_case_real_path_at(ROOT, workflow)
        if path is None or not path.is_file():
            errors.append(f"{label}.workflow must be a regular file: {workflow}")
            continue
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            errors.append(f"{label}.workflow_sha256 must be a lowercase SHA-256")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            errors.append(
                f"{label}.workflow_sha256 does not match the required workflow"
            )


def check_deferred_paths(
    manifest: dict[str, object], required_paths: list[str], errors: list[str]
) -> None:
    required = set(required_paths)
    for field, value in manifest.items():
        if field != "deferred_paths" and not (
            field.startswith("planned_") and field.endswith("_paths")
        ):
            continue
        if not isinstance(value, list):
            errors.append(f"doc-sync-rules {field} must be a list")
            continue
        for entry in value:
            path = entry.get("path") if isinstance(entry, dict) else entry
            if not isinstance(path, str):
                errors.append(
                    f"doc-sync-rules {field} entries must be paths or path objects"
                )
                continue
            if path in required:
                errors.append(
                    f"doc-sync-rules {field} still defers required path: {path}"
                )


def check_trusted_diff_classes(
    manifest: dict[str, object],
    trusted_manifest: dict[str, object],
    errors: list[str],
) -> None:
    diff_classes = manifest.get("diff_classes", {})
    trusted_diff_classes = trusted_manifest.get("diff_classes", {})
    if not isinstance(diff_classes, dict):
        errors.append("doc-sync-rules diff_classes must be an object")
        diff_classes = {}
    if not isinstance(trusted_diff_classes, dict):
        errors.append("trusted doc-sync-rules diff_classes must be an object")
        return
    unknown = sorted(set(diff_classes) - set(trusted_diff_classes))
    if unknown:
        errors.append(
            "Target doc-sync-rules cannot add diff classes unknown to the trusted "
            f"policy: {', '.join(unknown)}"
        )
    for name, trusted_spec in trusted_diff_classes.items():
        if diff_classes.get(name) != trusted_spec:
            errors.append(
                "Target doc-sync-rules cannot remove or rewrite trusted diff class: "
                f"{name}"
            )


def entrypoint_map(
    manifest: dict[str, object], errors: list[str], label: str
) -> dict[str, set[str]]:
    entries = manifest.get("entrypoint_links", [])
    if not isinstance(entries, list):
        errors.append(f"{label} entrypoint_links must be a list")
        return {}
    result: dict[str, set[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"{label} entrypoint_links contains a non-object entry")
            continue
        source = entry.get("source")
        targets = entry.get("targets")
        if (
            not isinstance(source, str)
            or not source
            or not isinstance(targets, list)
            or not all(isinstance(target, str) and target for target in targets)
        ):
            errors.append(
                f"{label} entrypoint link entries require a non-empty source and "
                "string targets"
            )
            continue
        result.setdefault(source, set()).update(targets)
    return result


def check_entrypoint_links(
    manifest: dict[str, object],
    trusted_manifest: dict[str, object],
    errors: list[str],
) -> None:
    entrypoints = entrypoint_map(manifest, errors, "doc-sync-rules")
    trusted_entrypoints = entrypoint_map(
        trusted_manifest, errors, "trusted doc-sync-rules"
    )
    for source, trusted_targets in trusted_entrypoints.items():
        missing = sorted(trusted_targets - entrypoints.get(source, set()))
        if missing:
            errors.append(
                "Target doc-sync-rules cannot remove trusted entrypoint links from "
                f"{source}: {', '.join(missing)}"
            )

    for source_value, targets in entrypoints.items():
        source = exact_case_real_path_at(ROOT, source_value)
        if source is None or not source.is_file():
            errors.append(
                f"Entrypoint source must be a regular file: {source_value}"
            )
            continue
        linked_targets = {
            path for _, path in extract_links(source) if path is not None
        }
        for target in sorted(targets):
            declared = PurePosixPath(target)
            if declared.is_absolute() or not declared.parts or any(
                part in {"", ".", ".."} for part in declared.parts
            ):
                errors.append(
                    f"Entrypoint target must be a repository-relative path: {target}"
                )
                continue
            expected_target = exact_case_real_path_at(ROOT, target)
            if expected_target is None or not expected_target.is_file():
                errors.append(
                    f"Entrypoint target must be a regular repository file: {target}"
                )
                continue
            if expected_target.resolve() not in linked_targets:
                errors.append(f"Entrypoint {source_value} must link to {target}")


def load_project_module() -> ModuleType | None:
    if not PROJECT_CHECK.exists():
        return None
    spec = importlib.util.spec_from_file_location("harness_project_check_docs", PROJECT_CHECK)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {PROJECT_CHECK}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_docs(repo_root: Path | None = None):
    """Compatibility API for repository tools that imported the old checker."""
    module = load_project_module()
    project_check = getattr(module, "check_docs", None) if module else None
    if not callable(project_check):
        raise ImportError("project checker does not expose check_docs(repo_root)")
    return project_check(repo_root or ROOT)


def validate(repo_root: Path | None = None) -> list[str]:
    """Compatibility API for repositories whose tests import validate(root)."""
    module = load_project_module()
    project_validate = getattr(module, "validate", None) if module else None
    if callable(project_validate):
        return project_validate(repo_root or ROOT)
    requested_root = (repo_root or ROOT).expanduser().resolve()
    if requested_root != ROOT:
        raise ValueError(
            "validate(repo_root) must target HARNESS_REPO_ROOT or the checker repository"
        )
    errors, _ = validate_repo()
    return errors


def run_project_check(argv: list[str]) -> int:
    if not PROJECT_CHECK.exists():
        return 0
    return subprocess.run(
        [sys.executable, "-I", "-B", str(PROJECT_CHECK), *argv],
        cwd=ROOT,
        check=False,
    ).returncode


def validate_repo() -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    rules_path = DOCS_ROOT / "doc-sync-rules.json"
    contract_path = ROOT / ".harness" / "repo-contract.json"
    if rules_path.is_symlink():
        errors.append("doc sync rules must be a regular file, not a symlink")
        manifest: dict[str, object] = {}
    else:
        manifest = load_json(rules_path, errors, "doc sync rules")
    if contract_path.is_symlink():
        errors.append("repo contract must be a regular file, not a symlink")
        contract: dict[str, object] = {}
    else:
        contract = load_json(contract_path, errors, "repo contract")
    trusted_manifest = load_trusted_manifest(errors)

    required_paths = required_paths_from(manifest, errors, "doc-sync-rules")
    for relative_path in required_paths:
        if not exact_case_path_exists(relative_path):
            errors.append(f"Missing or case-mismatched required path: {relative_path}")
    check_trusted_required_paths(trusted_manifest, required_paths, errors)
    check_trusted_control_files(errors)
    check_trusted_forbidden_paths(manifest, trusted_manifest, errors)
    check_deferred_paths(manifest, required_paths, errors)
    check_trusted_diff_classes(manifest, trusted_manifest, errors)
    check_document_status_workflow(
        manifest, trusted_manifest, required_paths, errors
    )
    check_codex_review_workflows(required_paths, errors)
    check_additional_required_checks(
        manifest, trusted_manifest, required_paths, errors
    )
    check_current_head_governance(errors)
    plan_template_relative = f"{DOCS_ROOT.name}/exec-plans/template.md"
    plan_template = exact_case_real_path_at(ROOT, plan_template_relative)
    if plan_template is None or not plan_template.is_file():
        errors.append(
            "Active Plan template must be a regular file, not a symlink: "
            f"{plan_template_relative}"
        )
    else:
        check_required_check_name(
            plan_template.read_text(encoding="utf-8"), plan_template, errors
        )

    for markdown_path in markdown_files(manifest, trusted_manifest, errors):
        for raw, linked in extract_links(markdown_path):
            if linked is None:
                errors.append(
                    f"Non-portable site-root link in "
                    f"{markdown_path.relative_to(ROOT).as_posix()}: {raw}"
                )
            elif not linked.is_relative_to(ROOT):
                errors.append(
                    f"Repository link escapes the checkout in "
                    f"{markdown_path.relative_to(ROOT).as_posix()}: {raw}"
                )
            elif not linked.exists():
                errors.append(
                    f"Broken link in {markdown_path.relative_to(ROOT).as_posix()}: {raw}"
                )

    check_entrypoint_links(manifest, trusted_manifest, errors)

    if contract:
        if contract.get("mode") != "repo-native-agent-cicd":
            errors.append("repo contract mode must be repo-native-agent-cicd")
        if "delegation_contract" not in contract:
            errors.append("repo contract is missing delegation_contract")
        checkpoint = contract.get("checkpoint_gate")
        if not isinstance(checkpoint, dict):
            errors.append("repo contract checkpoint_gate must be an object")
        else:
            for field in ("planned_required_check", "required_check"):
                if field in checkpoint and checkpoint.get(field) != "loop/checkpoints":
                    errors.append(
                        f"repo contract checkpoint_gate {field} must be 'loop/checkpoints'"
                    )
            required_job = checkpoint.get("required_check_job")
            if required_job is not None:
                if not isinstance(required_job, dict):
                    errors.append(
                        "repo contract checkpoint_gate required_check_job must be an object"
                    )
                else:
                    expected_status_contract = {
                        "workflow": ".github/workflows/docs-ci.yml",
                        "context": "loop/checkpoints",
                        "emitter": "trusted_commit_status",
                    }
                    for field, expected in expected_status_contract.items():
                        if required_job.get(field) != expected:
                            errors.append(
                                "repo contract checkpoint_gate required_check_job "
                                f"{field} must be {expected!r}"
                            )
                    if "job" in required_job:
                        errors.append(
                            "repo contract checkpoint_gate required_check_job cannot "
                            "name an Actions job for a trusted commit-status context"
                        )
        review = contract.get("codex_review")
        if not isinstance(review, dict):
            errors.append("repo contract codex_review must be an object")
        else:
            expected_review_policy = {
                "supervision_model": "repository_self_supervised",
                "required_check": "codex-review",
                "status_app_id": 15368,
                "status_source_isolation": "shared_actions_app_not_isolated",
                "source_isolated": False,
                "required_check_activation": "required_after_live_emitter_smoke",
                "required_check_activation_scope": "per_repository",
                "trusted_status_workflow": ".github/workflows/codex-review-gate.yml",
                "trusted_events": [
                    "pull_request_target",
                    "issue_comment",
                    "repository_dispatch",
                ],
                "status_writer_events": [
                    "pull_request_target",
                    "issue_comment",
                    "repository_dispatch",
                ],
                "heartbeat_event": "schedule",
                "artifact_binding": "live_pr_head_sha",
            }
            for field, expected in expected_review_policy.items():
                if review.get(field) != expected:
                    errors.append(
                        "repo contract codex_review "
                        f"{field} must be {expected!r} for the ordinary "
                        "repository-self-supervised template"
                    )

    check_active_plans(errors)
    check_completed_plans(errors)
    check_target_invariants(trusted_manifest, errors)
    return errors, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--skip-project-check", action="store_true")
    args, passthrough = parser.parse_known_args(argv)

    errors, _ = validate_repo()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    if not args.skip_project_check:
        project_status = run_project_check(["--all", *passthrough])
        if project_status != 0:
            return project_status
    print("Docs checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
