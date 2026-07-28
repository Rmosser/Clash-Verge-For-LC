#!/usr/bin/env python3
"""Fail-closed repository Harness checker executed from the trusted base."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple

CONTRACT_PATH = ".harness/repo-contract.json"
RECEIPT_PATH = ".harness/baseline-receipt.json"
CONTRACT_VERSION = "repo-harness-v3"
RECEIPT_VERSION = "repo-harness-baseline-receipt-v1"
VERIFIER_RELEASE = "repo-harness-verifier-v3.1"
VERIFIER_PATH = "scripts/check_harness.py"
SUPPORTED_VERIFIER_RELEASES = frozenset({VERIFIER_RELEASE})
EXTERNAL_AUTHORITY_REQUIRED = (
    "repo-harness-verifier-v3.1 is a pending-establishment diagnostic only; "
    "active gate, pending recovery, and receipt acceptance require the "
    "separately versioned source-isolated publisher and platform attestor"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RFC3339_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$"
)
EXTERNAL_STATUS_SYSTEM_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_CONTRACT_BYTES = 1024 * 1024
MAX_VERIFIER_BYTES = 4 * 1024 * 1024
MAX_ACTIVE_PLAN_BYTES = 1024 * 1024
MAX_EVAL_MANIFEST_BYTES = 1024 * 1024
MAX_REQUIRED_FILE_BYTES = 16 * 1024 * 1024
EXECUTION_PLAN_POLICY = {
    "active_plan_directory": "docs/exec-plans/active",
    "pending_establishment": {
        "required_active_plan_count": 1,
        "nested_active_plans": "forbidden",
        "ordinary_product_work": "forbidden_until_active_baseline",
    },
}
PLACEHOLDER_VALUE_RE = re.compile(
    r"^(?:tbd|todo|pending|unknown|n/?a|none|not[_ -]?applicable|"
    r"placeholder|fill(?: me)? in|<[^>]*>|\{\{[^}]*\}\})[.!]?$",
    re.IGNORECASE,
)
PLAN_SECTIONS = (
    "## Metadata",
    "## Goal",
    "## Scope",
    "## Baseline",
    "## Implementation",
    "## Delegation Audit",
    "## Validation",
    "## Documentation Impact",
    "## Closeout",
)
class HarnessError(RuntimeError):
    pass


class DiffEntry(NamedTuple):
    status: str
    paths: tuple[str, ...]


def safe_relative_parts(relative: str) -> tuple[str, ...]:
    relative_path = Path(relative)
    if (
        not relative
        or relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        raise HarnessError(f"unsafe repository-relative path: {relative}")
    return relative_path.parts


def open_repo_regular_file(
    root: Path,
    relative: str,
    *,
    max_bytes: int = MAX_REQUIRED_FILE_BYTES,
) -> tuple[int, os.stat_result]:
    """Open a bounded regular file without following any repository symlink."""
    if max_bytes <= 0:
        raise HarnessError("file size limit must be positive")
    parts = safe_relative_parts(relative)
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise HarnessError(f"cannot resolve repository root: {root}: {exc}") from exc
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_flag is None:
        raise HarnessError("platform lacks fail-closed no-follow file primitives")
    base_flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
    directory_flags = base_flags | directory_flag
    directory_fd = -1
    try:
        directory_fd = os.open(resolved_root, directory_flags)
        for component in parts[:-1]:
            before = os.stat(
                component,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
                raise HarnessError(
                    f"repository path component is not a real directory: {relative}"
                )
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            after = os.fstat(next_fd)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                os.close(next_fd)
                raise HarnessError(
                    f"repository path changed during validation: {relative}"
                )
            os.close(directory_fd)
            directory_fd = next_fd

        before = os.stat(
            parts[-1],
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise HarnessError(
                f"repository file is not a regular no-symlink file: {relative}"
            )
        if before.st_size > max_bytes:
            raise HarnessError(
                f"repository file exceeds {max_bytes} byte limit: {relative}"
            )
        file_fd = os.open(parts[-1], base_flags, dir_fd=directory_fd)
        after = os.fstat(file_fd)
        if (
            not stat.S_ISREG(after.st_mode)
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or after.st_size > max_bytes
        ):
            os.close(file_fd)
            raise HarnessError(
                f"repository file changed during validation: {relative}"
            )
        return file_fd, after
    except (OSError, ValueError) as exc:
        raise HarnessError(f"cannot safely open repository file {relative}: {exc}") from exc
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)


def read_repo_regular_bytes(
    root: Path,
    relative: str,
    *,
    max_bytes: int = MAX_REQUIRED_FILE_BYTES,
) -> bytes:
    file_fd, before = open_repo_regular_file(
        root,
        relative,
        max_bytes=max_bytes,
    )
    chunks: list[bytes] = []
    remaining = max_bytes + 1
    try:
        while remaining:
            chunk = os.read(file_fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(file_fd)
    except OSError as exc:
        raise HarnessError(f"cannot safely read repository file {relative}: {exc}") from exc
    finally:
        os.close(file_fd)
    if len(data) > max_bytes:
        raise HarnessError(
            f"repository file exceeds {max_bytes} byte limit: {relative}"
        )
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or len(data) != after.st_size
    ):
        raise HarnessError(f"repository file changed while reading: {relative}")
    return data


def read_repo_regular_text(
    root: Path,
    relative: str,
    *,
    max_bytes: int = MAX_REQUIRED_FILE_BYTES,
) -> str:
    try:
        return read_repo_regular_bytes(
            root,
            relative,
            max_bytes=max_bytes,
        ).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HarnessError(
            f"repository file is not valid UTF-8: {relative}: {exc}"
        ) from exc


def is_repo_regular_file(
    root: Path,
    relative: str,
    *,
    max_bytes: int = MAX_REQUIRED_FILE_BYTES,
) -> bool:
    try:
        file_fd, _ = open_repo_regular_file(
            root,
            relative,
            max_bytes=max_bytes,
        )
        os.close(file_fd)
        return True
    except HarnessError:
        return False


def load_repo_json(
    root: Path,
    relative: str,
    *,
    max_bytes: int = MAX_CONTRACT_BYTES,
) -> dict[str, Any]:
    try:
        data = json.loads(
            read_repo_regular_text(
                root,
                relative,
                max_bytes=max_bytes,
            )
        )
    except json.JSONDecodeError as exc:
        raise HarnessError(f"cannot read valid JSON: {relative}: {exc}") from exc
    if not isinstance(data, dict):
        raise HarnessError(f"JSON root must be an object: {relative}")
    return data


def sha256_repo_file(
    root: Path,
    relative: str,
    *,
    max_bytes: int = MAX_VERIFIER_BYTES,
) -> str:
    return hashlib.sha256(
        read_repo_regular_bytes(
            root,
            relative,
            max_bytes=max_bytes,
        )
    ).hexdigest()


def sha256_external_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise HarnessError(f"cannot hash verifier file: {path}: {exc}") from exc


def normalize_specs(value: Any, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise HarnessError(f"{field} must be a non-empty list")
    specs: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise HarnessError(f"{field} entries must be objects")
        kind = item.get("kind")
        pattern = item.get("pattern")
        if kind not in {"exact", "glob"} or not isinstance(pattern, str) or not pattern:
            raise HarnessError(f"invalid {field} entry: {item!r}")
        if pattern.startswith("/") or ".." in Path(pattern).parts:
            raise HarnessError(f"unsafe path pattern in {field}: {pattern}")
        specs.append({"kind": kind, "pattern": pattern})
    return specs


def matches(path: str, spec: dict[str, str]) -> bool:
    if spec["kind"] == "exact":
        return path == spec["pattern"]
    return fnmatch.fnmatchcase(path, spec["pattern"])


def matches_any(path: str, specs: list[dict[str, str]]) -> bool:
    return any(matches(path, spec) for spec in specs)


def harness_check(contract: dict[str, Any]) -> dict[str, Any]:
    matches = [
        check
        for check in contract.get("required_checks", [])
        if isinstance(check, dict) and check.get("context") == "harness/evidence"
    ]
    if len(matches) != 1:
        raise HarnessError("exactly one harness/evidence check is required")
    return matches[0]


def validate_contract(
    contract: dict[str, Any],
    root: Path,
    *,
    check_files: bool = True,
) -> None:
    if check_files and not is_repo_regular_file(root, CONTRACT_PATH):
        raise HarnessError("contract must be a regular in-repository file")
    if contract.get("contract_version") != CONTRACT_VERSION:
        raise HarnessError("unsupported contract_version")
    repository = contract.get("repository")
    if not isinstance(repository, str) or not REPOSITORY_RE.fullmatch(repository):
        raise HarnessError("repository must be OWNER/REPOSITORY")
    repository_id = contract.get("repository_id")
    if repository_id is not None and (
        not isinstance(repository_id, int)
        or isinstance(repository_id, bool)
        or repository_id <= 0
    ):
        raise HarnessError("repository_id must be null or a positive integer")
    default_branch = contract.get("default_branch")
    if (
        not isinstance(default_branch, str)
        or not default_branch
        or default_branch != default_branch.strip()
        or default_branch.startswith("/")
        or default_branch.endswith("/")
        or ".." in default_branch
        or any(character.isspace() or ord(character) < 32 for character in default_branch)
    ):
        raise HarnessError("default_branch is required")

    verifier = contract.get("verifier")
    if not isinstance(verifier, dict):
        raise HarnessError("verifier policy is required")
    release = verifier.get("release")
    verifier_sha = verifier.get("sha256")
    if release not in SUPPORTED_VERIFIER_RELEASES:
        raise HarnessError("unsupported verifier release")
    if not isinstance(verifier_sha, str) or not SHA256_RE.fullmatch(verifier_sha):
        raise HarnessError("verifier sha256 must be a lowercase SHA-256")
    if verifier.get("authority") != "source_isolated_publisher_bundle":
        raise HarnessError("verifier authority must be source isolated")
    if check_files:
        if not is_repo_regular_file(
            root,
            VERIFIER_PATH,
            max_bytes=MAX_VERIFIER_BYTES,
        ):
            raise HarnessError("repository verifier copy is missing or not regular")
        if sha256_repo_file(root, VERIFIER_PATH) != verifier_sha:
            raise HarnessError("repository verifier copy does not match its declared hash")
        if (
            release == VERIFIER_RELEASE
            and sha256_external_file(Path(__file__).resolve()) != verifier_sha
        ):
            raise HarnessError(
                "repository verifier copy does not match the executing publisher/Skill bundle"
            )

    execution_plan_policy = contract.get("execution_plan_policy")
    if execution_plan_policy != EXECUTION_PLAN_POLICY:
        raise HarnessError(
            "execution_plan_policy must explicitly forbid nested/additional "
            "pending plans and ordinary product work before an active baseline"
        )

    control = normalize_specs(contract.get("control_plane_paths"), "control_plane_paths")
    audit = normalize_specs(contract.get("audit_state_paths"), "audit_state_paths")
    if any(spec["kind"] != "exact" for spec in audit):
        raise HarnessError("audit_state_paths must use exact paths")
    if not matches_any(CONTRACT_PATH, control):
        raise HarnessError("contract is not covered by control_plane_paths")
    if not matches_any(RECEIPT_PATH, audit):
        raise HarnessError("baseline receipt is not covered by audit_state_paths")
    if matches_any(RECEIPT_PATH, control):
        raise HarnessError("baseline receipt overlaps control_plane_paths")
    for audit_spec in audit:
        if matches_any(audit_spec["pattern"], control):
            raise HarnessError(
                f"audit path overlaps control_plane_paths: {audit_spec['pattern']}"
            )

    required = contract.get("required_files")
    if not isinstance(required, list) or not required:
        raise HarnessError("required_files must be a non-empty list")
    for item in required:
        if not isinstance(item, str) or not item:
            raise HarnessError("required_files entries must be paths")
        item_path = Path(item)
        if item_path.is_absolute() or ".." in item_path.parts:
            raise HarnessError(f"unsafe required file path: {item}")
        controlled = matches_any(item, control)
        audited = matches_any(item, audit)
        if controlled == audited:
            raise HarnessError(f"required file must match exactly one trust set: {item}")
        if check_files and not is_repo_regular_file(root, item):
            raise HarnessError(f"required file is missing or not regular: {item}")

    groups = contract.get("revalidation_groups")
    if not isinstance(groups, dict) or not groups:
        raise HarnessError("revalidation_groups must be a non-empty object")
    group_paths: list[str] = []
    for name, group in groups.items():
        if not isinstance(name, str) or not isinstance(group, dict):
            raise HarnessError("invalid revalidation group")
        paths = group.get("paths")
        commands = group.get("commands")
        if not isinstance(paths, list) or not paths:
            raise HarnessError(f"group {name} has no paths")
        if not isinstance(commands, list) or not commands:
            raise HarnessError(f"group {name} has no commands")
        for path in paths:
            if (
                not isinstance(path, str)
                or not path
                or Path(path).is_absolute()
                or ".." in Path(path).parts
            ):
                raise HarnessError(f"group {name} has an unsafe path")
            group_paths.append(path)
        for command in commands:
            if (
                not isinstance(command, str)
                or not command.strip()
                or command.strip() in {":", "true", "false"}
            ):
                raise HarnessError(f"group {name} has an invalid validation command")
    for spec in control:
        if not any(
            spec["pattern"] == path
            or fnmatch.fnmatchcase(spec["pattern"], path)
            or fnmatch.fnmatchcase(path, spec["pattern"])
            for path in group_paths
        ):
            raise HarnessError(
                f"control pattern is not assigned to a revalidation group: {spec['pattern']}"
            )

    checks = contract.get("required_checks")
    if not isinstance(checks, list) or not checks:
        raise HarnessError("required_checks must be a non-empty list")
    contexts: set[str] = set()
    harness_checks: list[dict[str, Any]] = []
    for check in checks:
        if not isinstance(check, dict):
            raise HarnessError("required_checks entries must be objects")
        context = check.get("context")
        if not isinstance(context, str) or not context:
            raise HarnessError("required check context is required")
        if check.get("kind") != "machine":
            raise HarnessError("required checks may represent machine gates only")
        publisher = check.get("publisher")
        if not isinstance(publisher, dict):
            raise HarnessError("required check publisher must be an object")
        model = publisher.get("model")
        if context == "harness/evidence":
            if model != "source_isolated_github_app":
                raise HarnessError(
                    "harness/evidence publisher must be a source-isolated GitHub App"
                )
            harness_checks.append(check)
        elif model == "github_actions_shared":
            if publisher.get("app_id") is not None or publisher.get("app_slug") not in {
                None,
                "github-actions",
            }:
                raise HarnessError("shared Actions publisher identity is resolved live")
        elif model == "github_app":
            app_id = publisher.get("app_id")
            app_slug = publisher.get("app_slug")
            if (
                not isinstance(app_id, int)
                or isinstance(app_id, bool)
                or app_id <= 0
                or not isinstance(app_slug, str)
                or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", app_slug)
            ):
                raise HarnessError("product GitHub App publisher identity is incomplete")
        elif model == "external_commit_status":
            system = publisher.get("system")
            if set(publisher) != {"model", "system"}:
                raise HarnessError(
                    "external Commit Status publisher must contain only model and system"
                )
            if (
                not isinstance(system, str)
                or len(system) > 64
                or not EXTERNAL_STATUS_SYSTEM_RE.fullmatch(system)
            ):
                raise HarnessError(
                    "external Commit Status system must be a lowercase hyphenated slug"
                )
        else:
            raise HarnessError("unsupported required check publisher model")
        contexts.add(context)
    if len(harness_checks) != 1:
        raise HarnessError("exactly one harness/evidence check is required")
    if len(contexts) != len(checks):
        raise HarnessError("required check contexts must be unique")
    harness_check = harness_checks[0]

    platform_gate = contract.get("platform_gate")
    if not isinstance(platform_gate, dict):
        raise HarnessError("platform_gate policy is required")
    platform_state = platform_gate.get("state")
    if platform_state not in {"pending", "active"}:
        raise HarnessError("platform_gate state must be pending or active")
    publisher = harness_check["publisher"]
    app_id = publisher.get("app_id")
    app_slug = publisher.get("app_slug")
    if platform_state == "pending":
        reason = platform_gate.get("pending_reason")
        if not isinstance(reason, str) or not reason:
            raise HarnessError("pending platform gate needs a concrete reason")
        if app_id is not None or app_slug is not None:
            raise HarnessError("pending platform gate must not claim a publisher identity")
    else:
        if platform_gate.get("pending_reason") not in {None, ""}:
            raise HarnessError("active platform gate must not retain a pending reason")
        if not isinstance(app_id, int) or isinstance(app_id, bool) or app_id <= 0:
            raise HarnessError("active platform gate needs a positive GitHub App id")
        if (
            not isinstance(app_slug, str)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", app_slug)
        ):
            raise HarnessError("active platform gate needs a valid GitHub App slug")
        if app_slug == "github-actions":
            raise HarnessError(
                "the shared GitHub Actions App cannot publish harness/evidence"
            )
        if repository_id is None:
            raise HarnessError("active platform gate needs the immutable repository_id")

    publisher_validation = contract.get("publisher_validation")
    if not isinstance(publisher_validation, dict):
        raise HarnessError("publisher_validation policy is required")
    if publisher_validation.get("model") != "external_sandbox_profile":
        raise HarnessError("publisher must use an external sandbox profile")
    profile_id = publisher_validation.get("profile_id")
    profile_sha = publisher_validation.get("profile_sha256")
    if platform_state == "pending":
        if profile_id is not None or profile_sha is not None:
            raise HarnessError("pending platform gate must not claim a validation profile")
    elif (
        not isinstance(profile_id, str)
        or not re.fullmatch(r"[A-Za-z0-9._/-]+", profile_id)
        or not isinstance(profile_sha, str)
        or not SHA256_RE.fullmatch(profile_sha)
    ):
        raise HarnessError("active platform gate needs a bound sandbox profile")

    task_policy = contract.get("task_record_policy")
    if not isinstance(task_policy, dict):
        raise HarnessError("task_record_policy is required")
    if task_policy.get("record_actual") != ["model", "reasoning_effort", "speed"]:
        raise HarnessError("task records must capture actual model, effort, and speed")
    if task_policy.get("model_policy") != "record_selector_value_verbatim":
        raise HarnessError("model must be recorded from the actual selector value")
    if task_policy.get("reasoning_effort_values") != [
        "light",
        "medium",
        "high",
        "extra_high",
        "ultra",
    ]:
        raise HarnessError("unexpected reasoning-effort values")
    if task_policy.get("speed_values") != ["standard", "fast"]:
        raise HarnessError("unexpected speed values")

    review = contract.get("review")
    if not isinstance(review, dict):
        raise HarnessError("review policy is required")
    if review.get("supervision_model") != "trusted_agent_interpreted":
        raise HarnessError("unexpected review supervision model")
    if review.get("head_requirement") != "exact_live_pr_head":
        raise HarnessError("Review must bind to the exact live PR head")
    if review.get("clean_requirement") != "complete_explicit_no_findings":
        raise HarnessError("Review clean semantics are incomplete")
    if review.get("finding_policy") != "any_finding_blocks":
        raise HarnessError("any finding must block")
    if review.get("required_status_translation") is not False:
        raise HarnessError("Review must not be translated into a required status")
    authors = review.get("allowed_authors")
    if not isinstance(authors, list) or not authors or not all(
        isinstance(author, str) and author for author in authors
    ):
        raise HarnessError("review allowed_authors must be non-empty")
    fail_closed = review.get("fail_closed_on")
    required_failures = {
        "missing",
        "partial",
        "timeout",
        "stale_head",
        "ambiguous_author",
    }
    if not isinstance(fail_closed, list) or not required_failures.issubset(
        set(fail_closed)
    ):
        raise HarnessError("Review fail-closed cases are incomplete")

    github = contract.get("github_policy")
    required_true = (
        "pr_only",
        "strict_base_freshness",
        "no_bypass",
        "same_repository_prs_only",
        "expected_head_required",
    )
    if not isinstance(github, dict) or any(github.get(key) is not True for key in required_true):
        raise HarnessError("GitHub policy does not require all atomic machine gates")
    if github.get("force_push_allowed") is not False:
        raise HarnessError("force-push must be disabled")
    if github.get("branch_deletion_allowed") is not False:
        raise HarnessError("default-branch deletion must be disabled")
    if (
        github.get("merge_authority_model")
        != "owner_or_explicitly_authorized_agent_initiates_without_bypass"
    ):
        raise HarnessError("unexpected merge authority model")

    baseline = contract.get("baseline_receipt")
    if not isinstance(baseline, dict):
        raise HarnessError("baseline_receipt policy is required")
    if baseline.get("path") != RECEIPT_PATH or baseline.get("schema_version") != RECEIPT_VERSION:
        raise HarnessError("unexpected baseline receipt policy")
    if baseline.get("evidence_kind") != "github_app_check_run":
        raise HarnessError("baseline evidence must be a GitHub App check run")
    if baseline.get("check_name") != "harness/baseline":
        raise HarnessError("unexpected baseline check name")
    allowed_validators = baseline.get("allowed_validators")
    if not isinstance(allowed_validators, list) or not allowed_validators or not all(
        isinstance(actor, str) and actor for actor in allowed_validators
    ):
        raise HarnessError("baseline receipt allowed_validators must be non-empty")


def require_superset(
    trusted: list[Any],
    candidate: list[Any],
    field: str,
) -> None:
    missing = [item for item in trusted if item not in candidate]
    if missing:
        raise HarnessError(f"candidate contract removes trusted {field}: {missing!r}")


def validate_candidate_contract_transition(
    trusted_contract: dict[str, Any],
    candidate_contract: dict[str, Any],
    trusted_root: Path,
    target_root: Path,
) -> None:
    for field in ("repository", "default_branch"):
        if candidate_contract.get(field) != trusted_contract.get(field):
            raise HarnessError(f"candidate contract changes immutable {field}")
    for field in (
        "task_record_policy",
        "execution_plan_policy",
        "review",
        "github_policy",
        "baseline_receipt",
    ):
        if candidate_contract.get(field) != trusted_contract.get(field):
            raise HarnessError(f"candidate contract changes immutable {field}")

    require_superset(
        trusted_contract["control_plane_paths"],
        candidate_contract["control_plane_paths"],
        "control_plane_paths",
    )
    if candidate_contract["audit_state_paths"] != trusted_contract["audit_state_paths"]:
        raise HarnessError("candidate contract changes immutable audit_state_paths")
    require_superset(
        trusted_contract["required_files"],
        candidate_contract["required_files"],
        "required_files",
    )
    trusted_checks = {
        check["context"]: check for check in trusted_contract["required_checks"]
    }
    candidate_checks = {
        check["context"]: check for check in candidate_contract["required_checks"]
    }
    missing_checks = sorted(set(trusted_checks) - set(candidate_checks))
    if missing_checks:
        raise HarnessError(f"candidate removes required checks: {missing_checks!r}")
    trusted_check = trusted_checks["harness/evidence"]
    candidate_check = candidate_checks["harness/evidence"]
    if candidate_check.get("kind") != trusted_check.get("kind"):
        raise HarnessError("candidate changes harness/evidence kind")
    trusted_publisher = trusted_check["publisher"]
    candidate_publisher = candidate_check["publisher"]
    if candidate_publisher.get("model") != trusted_publisher.get("model"):
        raise HarnessError("candidate changes required check publisher model")

    trusted_state = trusted_contract["platform_gate"]["state"]
    candidate_state = candidate_contract["platform_gate"]["state"]
    if trusted_state == "active":
        if candidate_contract.get("repository_id") != trusted_contract.get("repository_id"):
            raise HarnessError("candidate changes immutable repository_id")
        if candidate_state != "active":
            raise HarnessError("candidate deactivates the platform machine gate")
        if candidate_publisher != trusted_publisher:
            raise HarnessError("candidate changes the active publisher identity")
        if (
            candidate_contract["publisher_validation"]
            != trusted_contract["publisher_validation"]
        ):
            raise HarnessError("candidate changes the active validation profile")
    elif candidate_state == "pending":
        if candidate_contract.get("repository_id") != trusted_contract.get("repository_id"):
            raise HarnessError("pending candidate changes repository_id")
        if candidate_publisher != trusted_publisher:
            raise HarnessError("pending candidate changes an unbound publisher identity")
        if (
            candidate_contract["publisher_validation"]
            != trusted_contract["publisher_validation"]
        ):
            raise HarnessError("pending candidate changes validation profile")
    elif candidate_state != "active":
        raise HarnessError("invalid platform gate transition")
    for context, trusted_product_check in trusted_checks.items():
        if context == "harness/evidence":
            continue
        if candidate_checks[context] != trusted_product_check:
            raise HarnessError(
                f"candidate changes trusted product check definition: {context}"
            )

    trusted_groups = trusted_contract["revalidation_groups"]
    candidate_groups = candidate_contract["revalidation_groups"]
    for name, trusted_group in trusted_groups.items():
        candidate_group = candidate_groups.get(name)
        if not isinstance(candidate_group, dict):
            raise HarnessError(f"candidate contract removes revalidation group: {name}")
        require_superset(
            trusted_group["paths"],
            candidate_group.get("paths", []),
            f"revalidation_groups.{name}.paths",
        )
        require_superset(
            trusted_group["commands"],
            candidate_group.get("commands", []),
            f"revalidation_groups.{name}.commands",
        )

    if candidate_contract["verifier"] != trusted_contract["verifier"]:
        raise HarnessError(
            "repo-harness-v3 verifier identity is immutable; use a new contract "
            "version and an external publisher handoff"
        )


def validate_receipt_evidence_run(
    pointer: str,
    receipt: dict[str, Any],
    contract: dict[str, Any],
) -> None:
    del pointer, receipt, contract
    raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)


def run_revalidation_commands(
    root: Path,
    contract: dict[str, Any],
) -> None:
    del root, contract
    raise HarnessError(
        "contract command strings are audit instructions, not trusted "
        "executables; run them only in an operator-selected disposable sandbox"
    )


def validate_live_platform(contract: dict[str, Any]) -> None:
    del contract
    raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)


def active_plans(root: Path) -> list[Path]:
    root = root.resolve()
    directory_relative = EXECUTION_PLAN_POLICY["active_plan_directory"]
    directory = root / directory_relative
    current = root
    try:
        for component in safe_relative_parts(directory_relative):
            current /= component
            info = os.lstat(current)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise HarnessError("Active Plan directory must be a real directory")
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise HarnessError(f"cannot inspect Active Plan directory: {exc}") from exc

    plans: list[Path] = []
    for current_directory, directory_names, file_names in os.walk(
        directory,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current_directory)
        for name in directory_names:
            nested = current_path / name
            try:
                info = os.lstat(nested)
            except OSError as exc:
                raise HarnessError(
                    f"cannot inspect Active Plan path: {nested}: {exc}"
                ) from exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise HarnessError(
                    f"Active Plan path is not a real directory: "
                    f"{nested.relative_to(root).as_posix()}"
                )
        for name in file_names:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if not is_repo_regular_file(
                root,
                relative,
                max_bytes=MAX_ACTIVE_PLAN_BYTES,
            ):
                raise HarnessError(
                    f"Active Plan path must be a bounded regular file: {relative}"
                )
            if path.suffix != ".md":
                continue
            if path.parent != directory:
                raise HarnessError(f"nested Active Plans are forbidden: {relative}")
            plans.append(path)
    return sorted(plans)


def rendered_plan_text(text: str) -> str:
    """Remove Markdown regions that do not render as plan prose."""
    visible_lines: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
        match = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})", line)
        if fence is not None:
            if (
                match is not None
                and match.group(1)[0] == fence[0]
                and len(match.group(1)) >= fence[1]
            ):
                fence = None
            visible_lines.append("\n" if line.endswith("\n") else "")
            continue
        if match is not None:
            fence = (match.group(1)[0], len(match.group(1)))
            visible_lines.append("\n" if line.endswith("\n") else "")
            continue
        visible_lines.append(line)

    visible = "".join(visible_lines)
    visible = re.sub(
        r"<!--.*?-->",
        lambda match: "\n" * match.group(0).count("\n"),
        visible,
        flags=re.DOTALL,
    )
    if "<!--" in visible or "-->" in visible:
        raise HarnessError("Active Plan contains a malformed HTML comment")
    return visible


def plan_section(text: str, heading: str) -> str:
    text = rendered_plan_text(text)
    matches = list(
        re.finditer(
        rf"^{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
        )
    )
    if not matches:
        raise HarnessError(f"Active Plan is missing section: {heading}")
    if len(matches) != 1:
        raise HarnessError(f"Active Plan has duplicate section: {heading}")
    return matches[0].group("body")


def plan_field(section: str, key: str) -> str:
    section = rendered_plan_text(section)
    matches = list(
        re.finditer(
            rf"^- {re.escape(key)}:[ \t]*(\S[^\r\n]*)[ \t]*$",
            section,
            re.MULTILINE,
        )
    )
    if not matches:
        raise HarnessError(f"Active Plan has no concrete {key}")
    if len(matches) != 1:
        raise HarnessError(f"Active Plan has duplicate {key}")
    return matches[0].group(1).strip()


def is_placeholder_value(value: str) -> bool:
    normalized = value.strip()
    normalized = re.sub(r"^(?:>\s*)+", "", normalized)
    normalized = re.sub(r"^#{1,6}[ \t]+", "", normalized)
    wrappers = (("**", "**"), ("__", "__"), ("~~", "~~"), ("*", "*"), ("_", "_"))
    changed = True
    while changed:
        changed = False
        for opening, closing in wrappers:
            if (
                normalized.startswith(opening)
                and normalized.endswith(closing)
                and len(normalized) > len(opening) + len(closing)
            ):
                normalized = normalized[len(opening) : -len(closing)].strip()
                changed = True
        match = re.fullmatch(r"(`+)(.*?)\1", normalized, re.DOTALL)
        if match is not None:
            normalized = match.group(2).strip()
            changed = True
        match = re.fullmatch(
            r"!?\[([^\]\r\n]*)\]\([^)\r\n]*\)",
            normalized,
        )
        if match is not None:
            normalized = match.group(1).strip()
            changed = True
        match = re.fullmatch(
            r"!?\[([^\]\r\n]*)\]\[[^\]\r\n]*\]",
            normalized,
        )
        if match is not None:
            normalized = match.group(1).strip()
            changed = True
    return not normalized or PLACEHOLDER_VALUE_RE.fullmatch(normalized) is not None


def require_concrete_section(text: str, heading: str) -> str:
    section = plan_section(text, heading)
    candidates: list[str] = []
    visible_section = rendered_plan_text(section)
    for raw_line in visible_section.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^(?:[-*+]|\d+[.)])\s*", "", line).strip()
        field_match = re.fullmatch(
            r"[A-Za-z][A-Za-z0-9 _-]{0,80}:[ \t]*(.*)",
            line,
        )
        if field_match is not None:
            line = field_match.group(1).strip()
        candidates.append(line)
    if not candidates or all(is_placeholder_value(value) for value in candidates):
        raise HarnessError(
            f"Active Plan section has no concrete non-placeholder body: {heading}"
        )
    return section


def validate_active_plan(root: Path, contract: dict[str, Any]) -> None:
    plans = active_plans(root)
    expected_count = contract["execution_plan_policy"]["pending_establishment"][
        "required_active_plan_count"
    ]
    if len(plans) > expected_count:
        raise HarnessError("multiple Active Plans are forbidden")
    if not plans:
        return
    plan_relative = plans[0].relative_to(root.resolve()).as_posix()
    text = read_repo_regular_text(
        root,
        plan_relative,
        max_bytes=MAX_ACTIVE_PLAN_BYTES,
    )
    visible_text = rendered_plan_text(text)
    section_positions: list[int] = []
    for section in PLAN_SECTIONS:
        matches = list(
            re.finditer(
                rf"^{re.escape(section)}\s*$",
                visible_text,
                re.MULTILINE,
            )
        )
        if not matches:
            raise HarnessError(f"Active Plan is missing section: {section}")
        if len(matches) != 1:
            raise HarnessError(f"Active Plan has duplicate section: {section}")
        section_positions.append(matches[0].start())
    if section_positions != sorted(section_positions):
        raise HarnessError("Active Plan sections are out of order")
    template_text = read_repo_regular_text(
        root,
        "docs/exec-plans/template.md",
        max_bytes=MAX_ACTIVE_PLAN_BYTES,
    )
    if text.strip() == template_text.strip():
        raise HarnessError("Active Plan must not be an unchanged template")
    for heading in PLAN_SECTIONS:
        if plan_section(text, heading).strip() == plan_section(
            template_text,
            heading,
        ).strip():
            raise HarnessError(
                f"Active Plan section must not remain unchanged from template: {heading}"
            )
        if heading != "## Delegation Audit":
            require_concrete_section(text, heading)

    required_fields = {
        "## Scope": ("In scope", "Out of scope"),
        "## Validation": (
            "Required files",
            "Required checks",
            "Positive tests",
            "Negative tests",
            "Current-head Review",
        ),
        "## Closeout": (
            "Final evidence",
            "Merge receipt",
            "Archive destination",
        ),
    }
    for heading, keys in required_fields.items():
        section = plan_section(text, heading)
        for key in keys:
            value = plan_field(section, key)
            if is_placeholder_value(value):
                raise HarnessError(f"Active Plan has no concrete {key}")

    metadata = require_concrete_section(text, "## Metadata")
    values: dict[str, str] = {}
    for key in (
        "Status",
        "Task class",
        "Model",
        "Reasoning effort",
        "Speed",
        "Delegation route",
        "Owner",
    ):
        values[key] = plan_field(metadata, key)
    if values["Status"] != "active":
        raise HarnessError("Active Plan status must be active")
    if is_placeholder_value(values["Owner"]):
        raise HarnessError("Active Plan has no concrete Owner")
    task_policy = contract["task_record_policy"]
    unknown_allowed = task_policy.get("unknown_allowed") is True
    if (
        is_placeholder_value(values["Model"])
        and not (values["Model"] == "unknown" and unknown_allowed)
    ):
        raise HarnessError("Active Plan has no concrete Model")
    if values["Task class"] not in task_policy["task_class_values"]:
        raise HarnessError("Active Plan has an invalid task class")
    unknown = {"unknown"} if unknown_allowed else set()
    if values["Reasoning effort"] not in set(task_policy["reasoning_effort_values"]) | unknown:
        raise HarnessError("Active Plan has an invalid reasoning effort")
    if values["Speed"] not in set(task_policy["speed_values"]) | unknown:
        raise HarnessError("Active Plan has an invalid speed")
    route = values["Delegation route"]
    if route not in {"single_agent", "main_plus_subagent", "multi_stage"}:
        raise HarnessError("Active Plan has an invalid delegation route")

    audit_text = plan_section(text, "## Delegation Audit")
    audit_values: dict[str, str] = {}
    for key in (
        "Delegated scope",
        "Forbidden scope",
        "No-subagent fallback reason",
        "Subagent result",
        "Main agent review",
        "Rework requested",
        "Final accepted diff",
    ):
        audit_values[key] = plan_field(audit_text, key)
    if route == "single_agent":
        delegated_fields = {
            key: value
            for key, value in audit_values.items()
            if key != "No-subagent fallback reason"
        }
        if any(value != "not_applicable" for value in delegated_fields.values()):
            raise HarnessError(
                "single-agent plan delegation audit must be not_applicable"
            )
        fallback_reason = audit_values["No-subagent fallback reason"]
        if (
            values["Task class"] in {"standard", "critical"}
            and (
                fallback_reason == "not_applicable"
                or is_placeholder_value(fallback_reason)
            )
        ):
            raise HarnessError(
                "nontrivial single-agent plan needs a concrete "
                "No-subagent fallback reason"
            )
    else:
        if audit_values["No-subagent fallback reason"] != "not_applicable":
            raise HarnessError(
                "delegated plan No-subagent fallback reason must be not_applicable"
            )
        if is_placeholder_value(audit_values["Delegated scope"]):
            raise HarnessError("delegated plan needs a concrete delegated scope")
        if is_placeholder_value(audit_values["Forbidden scope"]):
            raise HarnessError("delegated plan needs a concrete forbidden scope")
        if is_placeholder_value(audit_values["Subagent result"]):
            raise HarnessError("delegated plan needs a concrete subagent result")
        main_review = audit_values["Main agent review"]
        rework = audit_values["Rework requested"]
        accepted = audit_values["Final accepted diff"]
        if main_review not in {"pending", "rework_requested", "accepted"}:
            raise HarnessError("invalid Main agent review state")
        if rework not in {"pending", "none", "completed"}:
            raise HarnessError("invalid Rework requested state")
        if accepted not in {"pending", "accepted"}:
            raise HarnessError("invalid Final accepted diff state")
        state = (main_review, rework, accepted)
        allowed_states = {
            ("pending", "pending", "pending"),
            ("rework_requested", "pending", "pending"),
            ("accepted", "none", "accepted"),
            ("accepted", "completed", "accepted"),
        }
        if state not in allowed_states:
            raise HarnessError(
                "delegation handoff must be fully pending, rework-requested, "
                "or fully accepted"
            )

    impact_text = require_concrete_section(text, "## Documentation Impact")
    impact_result = plan_field(impact_text, "Result")
    if impact_result not in {"updated", "not_applicable"}:
        raise HarnessError("Active Plan has no valid Documentation Impact result")
    impact_evidence = plan_field(impact_text, "Evidence")
    if is_placeholder_value(impact_evidence):
        raise HarnessError("Documentation Impact needs concrete evidence")


def validate_pending_establishment(
    root: Path,
    contract: dict[str, Any],
) -> None:
    if contract["platform_gate"]["state"] != "pending":
        return
    receipt_path = root / RECEIPT_PATH
    if receipt_path.exists() or receipt_path.is_symlink():
        raise HarnessError(
            "pending establishment must not contain a baseline receipt"
        )
    expected_count = contract["execution_plan_policy"]["pending_establishment"][
        "required_active_plan_count"
    ]
    if len(active_plans(root)) != expected_count:
        count_label = "one" if expected_count == 1 else str(expected_count)
        raise HarnessError(
            f"pending establishment requires exactly {count_label} Active Plan"
        )


def validate_expected_identity(
    contract: dict[str, Any],
    *,
    expected_repository: str | None,
    expected_repository_id: int | None,
    expected_default_branch: str | None,
) -> None:
    if (
        expected_repository is not None
        and contract["repository"] != expected_repository
    ):
        raise HarnessError("contract repository does not match runtime identity")
    if (
        expected_repository_id is not None
        and contract["repository_id"] != expected_repository_id
    ):
        raise HarnessError(
            "contract repository_id does not match runtime identity"
        )
    if (
        expected_default_branch is not None
        and contract["default_branch"] != expected_default_branch
    ):
        raise HarnessError(
            "contract default branch does not match runtime identity"
        )


def validate_eval_rules(root: Path) -> None:
    root = root.resolve()
    current = root
    try:
        for component in safe_relative_parts("evals/harness"):
            current /= component
            root_info = os.lstat(current)
            if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(
                root_info.st_mode
            ):
                raise HarnessError(
                    "evals/harness and its ancestors must be real directories"
                )
    except FileNotFoundError:
        return
    except OSError as exc:
        raise HarnessError(f"cannot inspect evals/harness: {exc}") from exc
    eval_root = current

    immediate_rule_directories: set[Path] = set()
    manifests: list[Path] = []
    for current_directory, directory_names, file_names in os.walk(
        eval_root,
        topdown=True,
        followlinks=False,
    ):
        current = Path(current_directory)
        for name in directory_names:
            path = current / name
            try:
                info = os.lstat(path)
            except OSError as exc:
                raise HarnessError(f"cannot inspect evaluation path {path}: {exc}") from exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise HarnessError(
                    f"evaluation path must be a real directory: "
                    f"{path.relative_to(root).as_posix()}"
                )
            if current == eval_root:
                immediate_rule_directories.add(path)
        for name in file_names:
            path = current / name
            relative = path.relative_to(root).as_posix()
            if not is_repo_regular_file(
                root,
                relative,
                max_bytes=MAX_REQUIRED_FILE_BYTES,
            ):
                raise HarnessError(
                    f"evaluation asset must be a bounded regular file: {relative}"
                )
            if current == eval_root:
                raise HarnessError(
                    f"evaluation files must live inside one rule directory: {relative}"
                )
            if name == "manifest.json":
                if current.parent != eval_root:
                    raise HarnessError(
                        f"evaluation manifest must be exactly one rule directory "
                        f"below evals/harness: {relative}"
                    )
                manifests.append(path)

    manifest_parents = {path.parent for path in manifests}
    missing = sorted(immediate_rule_directories - manifest_parents)
    if missing:
        relative = missing[0].relative_to(root).as_posix()
        raise HarnessError(f"evaluation rule directory has no manifest.json: {relative}")

    for manifest_path in sorted(manifests):
        relative_manifest = manifest_path.relative_to(root).as_posix()
        if not is_repo_regular_file(root, relative_manifest):
            raise HarnessError(
                f"evaluation manifest must be a regular file: {relative_manifest}"
            )
        manifest = load_repo_json(
            root,
            relative_manifest,
            max_bytes=MAX_EVAL_MANIFEST_BYTES,
        )
        state = manifest.get("state")
        if state not in {"candidate", "shadow", "active", "monitored", "deprecated"}:
            raise HarnessError(f"invalid evaluation state: {manifest_path}")
        if state not in {"active", "monitored"}:
            continue
        required_files = (
            "violation_example",
            "safe_counterexample",
            "unrelated_control",
        )
        example_paths: dict[str, Path] = {}
        example_identities: dict[str, tuple[int, int]] = {}
        for field in required_files:
            relative = manifest.get(field)
            if not isinstance(relative, str) or not relative:
                raise HarnessError(f"{manifest_path}: missing {field}")
            try:
                relative_parts = safe_relative_parts(relative)
            except HarnessError as exc:
                raise HarnessError(
                    f"{manifest_path}: unsafe file for {field}"
                ) from exc
            example_path = manifest_path.parent.joinpath(*relative_parts)
            try:
                example_path.relative_to(manifest_path.parent)
            except ValueError as exc:
                raise HarnessError(
                    f"{manifest_path}: unsafe file for {field}"
                ) from exc
            example_relative = example_path.relative_to(root).as_posix()
            if example_path == manifest_path:
                raise HarnessError(
                    f"{manifest_path}: example for {field} cannot be the manifest"
                )
            if not is_repo_regular_file(root, example_relative):
                raise HarnessError(f"{manifest_path}: missing file for {field}")
            info = os.stat(example_path, follow_symlinks=False)
            example_paths[field] = example_path
            example_identities[field] = (info.st_dev, info.st_ino)
        if len(set(example_paths.values())) != len(required_files):
            raise HarnessError(
                f"{manifest_path}: active rule examples must use distinct paths"
            )
        if len(set(example_identities.values())) != len(required_files):
            raise HarnessError(
                f"{manifest_path}: active rule examples must be distinct files"
            )
        regression = manifest.get("regression")
        if not isinstance(regression, dict) or regression.get("result") != "passed":
            raise HarnessError(f"{manifest_path}: active rule needs a passed regression")
        if manifest.get("owner_confirmed") is not True:
            raise HarnessError(f"{manifest_path}: active rule needs Owner confirmation")


def validate_receipt_structure(
    receipt: dict[str, Any],
    contract: dict[str, Any],
    expected_sha: str | None = None,
) -> None:
    """Validate JSON shape only; this function never establishes readiness."""
    if contract["platform_gate"]["state"] != "active":
        raise HarnessError("pending platform gate cannot have a baseline receipt")
    if receipt.get("schema_version") != RECEIPT_VERSION:
        raise HarnessError("unsupported receipt schema")
    if receipt.get("repository") != contract.get("repository"):
        raise HarnessError("receipt repository does not match contract")
    if receipt.get("contract_version") != CONTRACT_VERSION:
        raise HarnessError("receipt contract version does not match")
    sha = receipt.get("validated_commit_sha")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise HarnessError("validated_commit_sha must be a full lowercase 40-character SHA")
    if expected_sha is not None and sha != expected_sha:
        raise HarnessError("cleanup receipt must bind to the cleanup PR base")
    if receipt.get("validation_type") not in {"full", "partial"}:
        raise HarnessError("receipt validation_type must be full or partial")
    if receipt.get("validated_by") not in contract["baseline_receipt"][
        "allowed_validators"
    ]:
        raise HarnessError("receipt validated_by is not allowed by the contract")
    validated_at = receipt.get("validated_at")
    if not isinstance(validated_at, str) or not RFC3339_UTC_RE.fullmatch(validated_at):
        raise HarnessError("receipt validated_at must be UTC RFC3339 seconds")
    try:
        parsed_at = datetime.strptime(validated_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise HarnessError("receipt validated_at is not a real UTC timestamp") from exc
    if parsed_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HarnessError("receipt validated_at is in the future")
    groups = receipt.get("validated_groups")
    results = receipt.get("results")
    if not isinstance(groups, list) or not groups:
        raise HarnessError("receipt has no validated_groups")
    if len(groups) != len(set(groups)):
        raise HarnessError("receipt validated_groups contains duplicates")
    known_groups = set(contract.get("revalidation_groups", {}))
    if not set(groups).issubset(known_groups):
        raise HarnessError("receipt contains an unknown revalidation group")
    if receipt.get("validation_type") == "full" and set(groups) != known_groups:
        raise HarnessError("full validation must include every revalidation group")
    if not isinstance(results, dict):
        raise HarnessError("receipt has no group results")
    if set(results) != known_groups:
        missing = sorted(known_groups - set(results))
        extra = sorted(set(results) - known_groups)
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if extra:
            detail.append("extra=" + ",".join(extra))
        raise HarnessError(
            "receipt results must contain exactly every current revalidation "
            "group (" + "; ".join(detail) + ")"
        )
    for group in sorted(known_groups):
        result = results.get(group)
        if not isinstance(result, dict) or result.get("result") != "passed":
            raise HarnessError(f"receipt group did not pass: {group}")
        pointer = result.get("evidence")
        if not isinstance(pointer, str) or not pointer:
            raise HarnessError(f"receipt group has no evidence pointer: {group}")
        check_run_prefix = f"https://github.com/{contract['repository']}/runs/"
        run_id = pointer.removeprefix(check_run_prefix)
        if (
            not pointer.startswith(check_run_prefix)
            or not run_id.isdigit()
            or run_id == "0"
        ):
            raise HarnessError(
                f"receipt group evidence must identify a GitHub App check run: {group}"
            )


def git_result(git_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", f"--git-dir={git_dir}", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def git_commit_exists(git_dir: Path, sha: str) -> bool:
    return git_result(git_dir, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def git_is_ancestor(git_dir: Path, ancestor: str, descendant: str) -> bool:
    return (
        git_result(
            git_dir,
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
        ).returncode
        == 0
    )


def load_contract_at_commit(git_dir: Path, sha: str, root: Path) -> dict[str, Any]:
    completed = git_result(git_dir, "show", f"{sha}:{CONTRACT_PATH}")
    if completed.returncode != 0:
        raise HarnessError(
            f"validated commit has no readable contract: {completed.stderr.strip()}"
        )
    try:
        contract = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise HarnessError("validated commit contract is invalid JSON") from exc
    if not isinstance(contract, dict):
        raise HarnessError("validated commit contract root must be an object")
    validate_contract(contract, root, check_files=False)
    return contract


def git_diff_entries(git_dir: Path, base_sha: str, head_sha: str) -> list[DiffEntry]:
    completed = git_result(
        git_dir,
        "diff",
        "--name-status",
        "-z",
        "-M",
        base_sha,
        head_sha,
    )
    if completed.returncode != 0:
        raise HarnessError(f"cannot classify Git diff: {completed.stderr.strip()}")
    fields = completed.stdout.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    entries: list[DiffEntry] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        path_count = 2 if status.startswith(("R", "C")) else 1
        if not status or index + path_count > len(fields):
            raise HarnessError("git returned a malformed NUL-delimited diff")
        paths = tuple(fields[index : index + path_count])
        if any(not path for path in paths):
            raise HarnessError("git returned an empty changed path")
        entries.append(DiffEntry(status, paths))
        index += path_count
    return entries


def changed_paths(entries: list[DiffEntry]) -> set[str]:
    return {path for entry in entries for path in entry.paths}


def control_specs_for(*contracts: dict[str, Any]) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for contract in contracts:
        specs.extend(
            normalize_specs(contract["control_plane_paths"], "control_plane_paths")
        )
    return specs


def affected_groups(
    entries: list[DiffEntry],
    *contracts: dict[str, Any],
) -> set[str]:
    paths = changed_paths(entries)
    control_specs = control_specs_for(*contracts)
    control_paths = {
        path for path in paths if matches_any(path, control_specs)
    }
    if not control_paths:
        return set()
    groups: set[str] = set()
    current_groups = contracts[-1]["revalidation_groups"]
    if CONTRACT_PATH in control_paths:
        return set(current_groups)
    for path in control_paths:
        matched = False
        for name, group in current_groups.items():
            patterns = group.get("paths", [])
            if any(
                isinstance(pattern, str)
                and fnmatch.fnmatchcase(path, pattern)
                for pattern in patterns
            ):
                groups.add(name)
                matched = True
        if not matched:
            groups.update(current_groups)
    return groups


def validate_all_group_evidence(
    receipt: dict[str, Any],
    contract: dict[str, Any],
) -> None:
    results = receipt.get("results")
    if not isinstance(results, dict):
        raise HarnessError("receipt has no group results")
    missing = []
    for group in contract["revalidation_groups"]:
        result = results.get(group)
        if (
            not isinstance(result, dict)
            or result.get("result") != "passed"
            or not isinstance(result.get("evidence"), str)
            or not result["evidence"]
        ):
            missing.append(group)
    if missing:
        raise HarnessError(
            "receipt lacks passed evidence for groups: " + ", ".join(sorted(missing))
        )


def validate_trusted_baseline(
    trusted_root: Path,
    trusted_contract: dict[str, Any],
    git_dir: Path,
    base_sha: str,
) -> None:
    del trusted_root, trusted_contract, git_dir, base_sha
    raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)


def is_receipt_cleanup(entries: list[DiffEntry]) -> bool:
    if len(entries) != 2:
        return False
    receipt_entries = [
        entry
        for entry in entries
        if entry.paths == (RECEIPT_PATH,) and entry.status in {"A", "M"}
    ]
    plan_entries = [
        entry
        for entry in entries
        if entry.status == "R100"
        and len(entry.paths) == 2
        and entry.paths[0].startswith("docs/exec-plans/active/")
        and entry.paths[0].endswith(".md")
        and entry.paths[1].startswith("docs/exec-plans/completed/")
        and entry.paths[1].endswith(".md")
    ]
    if len(receipt_entries) != 1 or len(plan_entries) != 1:
        return False
    return Path(plan_entries[0].paths[0]).name == Path(plan_entries[0].paths[1]).name


def validate_receipt_cleanup(
    trusted_root: Path,
    target_root: Path,
    trusted_contract: dict[str, Any],
    git_dir: Path,
    base_sha: str,
    entries: list[DiffEntry],
) -> None:
    del trusted_root, target_root, trusted_contract, git_dir, base_sha, entries
    raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)


def verify_candidate(
    trusted_root: Path,
    target_root: Path,
    git_dir: Path | None,
    base_sha: str | None,
    head_sha: str | None,
) -> None:
    trusted_contract = load_repo_json(trusted_root, CONTRACT_PATH)
    validate_contract(trusted_contract, trusted_root)

    for relative in trusted_contract["required_files"]:
        max_bytes = (
            MAX_VERIFIER_BYTES
            if relative == VERIFIER_PATH
            else MAX_REQUIRED_FILE_BYTES
        )
        if not is_repo_regular_file(
            target_root,
            relative,
            max_bytes=max_bytes,
        ):
            raise HarnessError(
                f"candidate deletes or replaces required file: {relative}"
            )

    candidate_contract = load_repo_json(target_root, CONTRACT_PATH)
    validate_contract(candidate_contract, target_root)
    validate_candidate_contract_transition(
        trusted_contract,
        candidate_contract,
        trusted_root,
        target_root,
    )
    validate_active_plan(target_root, trusted_contract)
    validate_eval_rules(target_root)
    trusted_state = trusted_contract["platform_gate"]["state"]
    candidate_state = candidate_contract["platform_gate"]["state"]
    if trusted_state == "active" or candidate_state == "active":
        raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)
    validate_pending_establishment(target_root, candidate_contract)

    if git_dir is None:
        return
    if not base_sha or not head_sha or not SHA_RE.fullmatch(base_sha) or not SHA_RE.fullmatch(head_sha):
        raise HarnessError("base and head must be full lowercase SHAs")
    entries = git_diff_entries(git_dir, base_sha, head_sha)
    paths = sorted(changed_paths(entries))
    audit = normalize_specs(trusted_contract["audit_state_paths"], "audit_state_paths")
    if any(matches_any(path, audit) for path in paths):
        raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)

    control = normalize_specs(trusted_contract["control_plane_paths"], "control_plane_paths")
    control_changed = any(matches_any(path, control) for path in paths)
    plans = active_plans(target_root)
    del control_changed, plans
    raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--trusted-root", type=Path)
    parser.add_argument("--target-root", type=Path)
    parser.add_argument("--git-dir", type=Path)
    parser.add_argument("--base-sha")
    parser.add_argument("--head-sha")
    parser.add_argument("--expected-repository")
    parser.add_argument("--expected-repository-id", type=int)
    parser.add_argument("--expected-default-branch")
    parser.add_argument("--check-platform", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.repo:
            root = args.repo.resolve()
            contract = load_repo_json(root, CONTRACT_PATH)
            validate_contract(contract, root)
            validate_expected_identity(
                contract,
                expected_repository=args.expected_repository,
                expected_repository_id=args.expected_repository_id,
                expected_default_branch=args.expected_default_branch,
            )
            validate_active_plan(root, contract)
            validate_eval_rules(root)
            validate_pending_establishment(root, contract)
            if args.check_platform:
                validate_live_platform(contract)
            if contract["platform_gate"]["state"] == "active":
                raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)
        else:
            if args.check_platform:
                raise HarnessError(
                    "--check-platform requires --repo"
                )
            if args.trusted_root is None or args.target_root is None:
                raise HarnessError("--repo or both --trusted-root and --target-root are required")
            verify_candidate(
                args.trusted_root.resolve(),
                args.target_root.resolve(),
                args.git_dir.resolve() if args.git_dir else None,
                args.base_sha,
                args.head_sha,
            )
            candidate_contract = load_repo_json(
                args.target_root.resolve(),
                CONTRACT_PATH,
            )
            validate_expected_identity(
                candidate_contract,
                expected_repository=args.expected_repository,
                expected_repository_id=args.expected_repository_id,
                expected_default_branch=args.expected_default_branch,
            )
    except HarnessError as exc:
        print(f"harness check failed: {exc}", file=sys.stderr)
        return 1
    print("harness diagnostic structure check passed; readiness is not established")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
