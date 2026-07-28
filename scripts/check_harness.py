#!/usr/bin/env python3
"""Fail-closed repository Harness checker executed from the trusted base."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
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
PLAN_SECTIONS = (
    "## Metadata",
    "## Goal",
    "## Scope",
    "## Baseline",
    "## Implementation",
    "## Validation",
    "## Closeout",
)
class HarnessError(RuntimeError):
    pass


class DiffEntry(NamedTuple):
    status: str
    paths: tuple[str, ...]


def is_repo_regular_file(root: Path, relative: str) -> bool:
    root = root.resolve()
    relative_path = Path(relative)
    if (
        not relative
        or relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        return False
    path = root / relative_path
    try:
        if not path.is_file() or path.is_symlink():
            return False
        current = path
        while current != root:
            if current.parent == current:
                return False
            if current.is_symlink():
                return False
            current = current.parent
        return path.resolve().is_relative_to(root)
    except OSError:
        return False


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"cannot read valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HarnessError(f"JSON root must be an object: {path}")
    return data


def sha256_file(path: Path) -> str:
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
        if not is_repo_regular_file(root, VERIFIER_PATH):
            raise HarnessError("repository verifier copy is missing or not regular")
        if sha256_file(root / VERIFIER_PATH) != verifier_sha:
            raise HarnessError("repository verifier copy does not match its declared hash")
        if release == VERIFIER_RELEASE and sha256_file(Path(__file__).resolve()) != verifier_sha:
            raise HarnessError(
                "repository verifier copy does not match the executing publisher/Skill bundle"
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
    directory = root / "docs/exec-plans/active"
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise HarnessError("Active Plan directory must be a real directory")
    plans = sorted(path for path in directory.glob("*.md"))
    for path in plans:
        relative = path.relative_to(root).as_posix()
        if not is_repo_regular_file(root, relative):
            raise HarnessError(f"Active Plan must be a regular file: {relative}")
    return plans


def validate_active_plan(root: Path, contract: dict[str, Any]) -> None:
    plans = active_plans(root)
    if len(plans) > 1:
        raise HarnessError("multiple Active Plans are forbidden")
    if not plans:
        return
    text = plans[0].read_text(encoding="utf-8")
    missing = [section for section in PLAN_SECTIONS if section not in text]
    if missing:
        raise HarnessError(f"Active Plan is missing sections: {', '.join(missing)}")
    if text.strip() == (root / "docs/exec-plans/template.md").read_text(
        encoding="utf-8"
    ).strip():
        raise HarnessError("Active Plan must not be an unchanged template")
    metadata = text.split("## Goal", 1)[0]
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
        match = re.search(rf"^- {re.escape(key)}:\s*(\S.*)$", metadata, re.MULTILINE)
        if match is None:
            raise HarnessError(f"Active Plan has no concrete {key}")
        values[key] = match.group(1).strip()
    if values["Status"] != "active":
        raise HarnessError("Active Plan status must be active")
    task_policy = contract["task_record_policy"]
    if values["Task class"] not in task_policy["task_class_values"]:
        raise HarnessError("Active Plan has an invalid task class")
    unknown = {"unknown"} if task_policy.get("unknown_allowed") is True else set()
    if values["Reasoning effort"] not in set(task_policy["reasoning_effort_values"]) | unknown:
        raise HarnessError("Active Plan has an invalid reasoning effort")
    if values["Speed"] not in set(task_policy["speed_values"]) | unknown:
        raise HarnessError("Active Plan has an invalid speed")


def validate_eval_rules(root: Path) -> None:
    eval_root = root / "evals/harness"
    if not eval_root.exists():
        return
    if eval_root.is_symlink() or not eval_root.is_dir():
        raise HarnessError("evals/harness must be a real directory")
    for manifest_path in sorted(eval_root.glob("*/manifest.json")):
        relative_manifest = manifest_path.relative_to(root).as_posix()
        if not is_repo_regular_file(root, relative_manifest):
            raise HarnessError(
                f"evaluation manifest must be a regular file: {relative_manifest}"
            )
        manifest = load_json(manifest_path)
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
        for field in required_files:
            relative = manifest.get(field)
            if not isinstance(relative, str) or not relative:
                raise HarnessError(f"{manifest_path}: missing {field}")
            example_path = manifest_path.parent / relative
            try:
                example_relative = example_path.relative_to(root).as_posix()
            except ValueError as exc:
                raise HarnessError(
                    f"{manifest_path}: unsafe file for {field}"
                ) from exc
            if not is_repo_regular_file(root, example_relative):
                raise HarnessError(f"{manifest_path}: missing file for {field}")
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
    trusted_contract = load_json(trusted_root / CONTRACT_PATH)
    validate_contract(trusted_contract, trusted_root)
    validate_active_plan(target_root, trusted_contract)
    validate_eval_rules(target_root)

    for relative in trusted_contract["required_files"]:
        if not is_repo_regular_file(target_root, relative):
            raise HarnessError(
                f"candidate deletes or replaces required file: {relative}"
            )

    candidate_contract = load_json(target_root / CONTRACT_PATH)
    validate_contract(candidate_contract, target_root)
    validate_candidate_contract_transition(
        trusted_contract,
        candidate_contract,
        trusted_root,
        target_root,
    )
    trusted_state = trusted_contract["platform_gate"]["state"]
    candidate_state = candidate_contract["platform_gate"]["state"]
    if trusted_state == "active" or candidate_state == "active":
        raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)

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
            contract = load_json(root / CONTRACT_PATH)
            validate_contract(contract, root)
            if (
                args.expected_repository is not None
                and contract["repository"] != args.expected_repository
            ):
                raise HarnessError("contract repository does not match runtime identity")
            if (
                args.expected_repository_id is not None
                and contract["repository_id"] != args.expected_repository_id
            ):
                raise HarnessError(
                    "contract repository_id does not match runtime identity"
                )
            if (
                args.expected_default_branch is not None
                and contract["default_branch"] != args.expected_default_branch
            ):
                raise HarnessError(
                    "contract default branch does not match runtime identity"
                )
            validate_active_plan(root, contract)
            validate_eval_rules(root)
            if contract["platform_gate"]["state"] == "pending":
                receipt_path = root / RECEIPT_PATH
                if receipt_path.exists() or receipt_path.is_symlink():
                    raise HarnessError(
                        "pending establishment must not contain a baseline receipt"
                    )
                if len(active_plans(root)) != 1:
                    raise HarnessError(
                        "pending establishment requires exactly one Active Plan"
                    )
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
            trusted_contract = load_json(
                args.trusted_root.resolve() / CONTRACT_PATH
            )
            if (
                args.expected_repository is not None
                and trusted_contract["repository"] != args.expected_repository
            ):
                raise HarnessError("contract repository does not match runtime identity")
            if (
                args.expected_default_branch is not None
                and trusted_contract["default_branch"]
                != args.expected_default_branch
            ):
                raise HarnessError(
                    "contract default branch does not match runtime identity"
                )
    except HarnessError as exc:
        print(f"harness check failed: {exc}", file=sys.stderr)
        return 1
    print("harness diagnostic structure check passed; readiness is not established")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
