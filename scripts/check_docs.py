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
import subprocess
import sys
from pathlib import Path, PurePosixPath
from types import ModuleType

ROOT = Path(
    os.environ.get("HARNESS_REPO_ROOT", Path(__file__).resolve().parents[1])
).expanduser().resolve()


def exact_docs_root() -> Path:
    candidates = [
        child for child in ROOT.iterdir() if child.name in {"docs", "Docs"}
    ]
    if len(candidates) != 1:
        raise RuntimeError("expected exactly one real docs/ or Docs/ governance root")
    root = candidates[0]
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("docs/ or Docs/ governance root must be a real directory")
    return root


DOCS_ROOT = exact_docs_root()
ACTIVE_PLAN_DIR = DOCS_ROOT / "exec-plans" / "active"
PROJECT_CHECK = ROOT / "scripts" / "check_docs_project.py"
LINK_RE = re.compile(r"!\[[^\]]+\]\(([^)]+)\)|\[[^\]]+\]\(([^)]+)\)")
FIELD_RE_TEMPLATE = r"^[ \t]*-[ \t]*{field}[ \t]*[:：][ \t]*(.*)$"
PENDING_VALUES = {"", "-", "n/a", "na", "none", "pending", "unknown", "`pending`", "`unknown`"}
TRUE_VALUES = {"yes", "true", "used"}
FALSE_VALUES = {"no", "false", "not used", "none", "n/a", "na", "-"}
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
ABSOLUTE_SCOPE_RE = re.compile(
    r"(?:^|[\s`(])(?:/[^\s`,;)]+|~(?:/|\\)[^\s`,;)]+|"
    r"[A-Za-z]:[\\/][^\s`,;)]+)"
)
CURRENT_HEAD_REVIEW_HEADING = "## Current-Head Codex Review\n\n"
CURRENT_HEAD_REVIEW_SHA256 = (
    "fd6c635bd11942af98c2c9ecaf7f4d61930d6c7731075ee7228b1bab9cda5165"
)
TRUSTED_DOC_CONTROL_SHA256 = (
    "1acac5e32199bebca6074c4d43b96fc88ab125acac2d456d511a707c6d17efc2"
)


def load_json(path: Path, errors: list[str], label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"Missing {label}: {path.relative_to(ROOT).as_posix()}")
        return {}
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid {label}: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"Invalid {label}: top-level value must be an object")
        return {}
    return payload


def exact_case_path_exists(relative_path: str) -> bool:
    current = ROOT
    for part in PurePosixPath(relative_path).parts:
        if part in {"", "."}:
            continue
        if part == ".." or not current.is_dir():
            return False
        names = {entry.name for entry in current.iterdir()}
        if part not in names:
            return False
        current = current / part
    return current.exists()


def markdown_files(manifest: dict[str, object]) -> list[Path]:
    files = [ROOT / "AGENTS.md"]
    for base in (DOCS_ROOT, ROOT / ".github"):
        if base.exists():
            files.extend(sorted(base.rglob("*.md")))
    patterns = [str(value) for value in manifest.get("link_check_exclude_globs", [])]
    selected = [
        path
        for path in files
        if path.exists()
        and not any(
            fnmatch.fnmatch(path.relative_to(ROOT).as_posix(), pattern)
            for pattern in patterns
        )
    ]
    symlinks = [path for path in selected if path.is_symlink()]
    if symlinks:
        joined = ", ".join(path.relative_to(ROOT).as_posix() for path in symlinks)
        raise RuntimeError(f"markdown inputs must be regular files, not symlinks: {joined}")
    return selected


def extract_links(markdown_path: Path) -> list[tuple[str, Path]]:
    text = markdown_path.read_text(encoding="utf-8")
    links: list[tuple[str, Path]] = []
    for match in LINK_RE.finditer(text):
        raw = (match.group(1) or match.group(2) or "").strip()
        if raw.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = raw.split("#", 1)[0]
        if (
            target.startswith(("/", "~/", "~\\", "//"))
            or re.match(r"^[A-Za-z]:[\\/]", target)
        ):
            # Absolute filesystem paths and site-root links are not portable
            # repository links and cannot be resolved on a CI runner.
            continue
        if target:
            links.append((raw, (markdown_path.parent / target).resolve()))
    return links


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
    if delegated and ABSOLUTE_SCOPE_RE.search(delegated_scope):
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


def check_active_plans(errors: list[str]) -> None:
    plans = sorted(
        path for path in ACTIVE_PLAN_DIR.glob("*.md") if path.name != ".gitkeep"
    )
    if len(plans) > 1:
        errors.append(
            f"Expected at most one active plan, found {len(plans)}: "
            + ", ".join(path.name for path in plans)
        )
        return
    for plan in plans:
        text = plan.read_text(encoding="utf-8")
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
    path = DOCS_ROOT / "governance" / "checkpoint-ci-gate.md"
    text = path.read_text(encoding="utf-8")
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


def check_document_status_workflow(
    manifest: dict[str, object], required_paths: list[str], errors: list[str]
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
    path = ROOT / relative
    if path.is_symlink() or not path.is_file():
        errors.append(f"Trusted document status workflow must be a regular file: {relative}")
        return
    text = path.read_text(encoding="utf-8")
    markers = (
        "  mark-checkpoints-pending:\n",
        "  pull-request-checkpoints:\n",
        "  publish-checkpoints-result:\n",
        "  default-branch-checkpoints:\n",
    )
    if "# HARNESS_TRUSTED_DOC_STATUS_V2" not in text or any(
        marker not in text for marker in markers
    ):
        errors.append(f"Trusted document status workflow contract is missing: {relative}")
        return
    control_text = text.split(markers[3], 1)[0]
    control_digest = hashlib.sha256(
        (control_text.rstrip() + "\n").encode("utf-8")
    ).hexdigest()
    if control_digest != TRUSTED_DOC_CONTROL_SHA256:
        errors.append(
            f"Trusted document status workflow control plane differs from the canonical contract: {relative}"
        )
    pending_job = text.split(markers[0], 1)[1].split(markers[1], 1)[0]
    validation_job = text.split(markers[1], 1)[1].split(markers[2], 1)[0]
    publisher_job = text.split(markers[2], 1)[1].split(markers[3], 1)[0]
    pre_jobs = text.split("jobs:\n", 1)[0]
    required_fragments = (
        "pull_request_target:",
        "permissions: {}",
        "repository: ${{ github.event.pull_request.head.repo.full_name }}",
        "ref: ${{ github.event.pull_request.head.sha }}",
        "allow-unsafe-pr-checkout: true",
        "ref: ${{ github.event.pull_request.base.sha }}",
        'git -c protocol.file.allow=always -C target fetch',
        '"${GITHUB_WORKSPACE}/trusted" "${PR_BASE_SHA}"',
        "python3 -I -B trusted/scripts/check_docs.py",
        "--all --skip-project-check",
        "trusted/scripts/check_loop_checkpoints.py",
        '--base "${PR_BASE_SHA}" --head "${PR_HEAD_SHA}"',
    )
    if any(fragment not in text for fragment in required_fragments):
        errors.append(f"Trusted document status workflow is incomplete: {relative}")
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
    if text.count("actions/checkout@v4") != 3:
        errors.append(
            f"Trusted document status workflow must use two isolated PR checkouts and one default checkout: {relative}"
        )
    if validation_job.count("persist-credentials: false") != 2:
        errors.append(
            f"Trusted document validation checkouts must disable credential persistence: {relative}"
        )
    if text.count("allow-unsafe-pr-checkout: true") != 1:
        errors.append(
            f"Trusted document target checkout must use exactly one explicit data-only fork opt-out: {relative}"
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
    if "actions/checkout" in pending_job or "actions/checkout" in publisher_job:
        errors.append(
            f"Trusted document status-writing jobs cannot check out repository content: {relative}"
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
    manifest: dict[str, object], required_paths: list[str], errors: list[str]
) -> None:
    checks = manifest.get("additional_required_checks", [])
    if not isinstance(checks, list):
        errors.append("doc-sync-rules additional_required_checks must be a list")
        return
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
        if workflow not in required_paths:
            errors.append(f"{label}.workflow must also appear in required_paths")
        path = ROOT / workflow
        if path.is_symlink() or not path.is_file():
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

    required_paths = manifest.get("required_paths", [])
    if not isinstance(required_paths, list) or not all(
        isinstance(value, str) for value in required_paths
    ):
        errors.append("doc-sync-rules required_paths must be a list of strings")
        required_paths = []
    for relative_path in required_paths:
        if not exact_case_path_exists(relative_path):
            errors.append(f"Missing or case-mismatched required path: {relative_path}")
    check_deferred_paths(manifest, required_paths, errors)
    check_document_status_workflow(manifest, required_paths, errors)
    check_additional_required_checks(manifest, required_paths, errors)
    check_current_head_governance(errors)
    plan_template = DOCS_ROOT / "exec-plans" / "template.md"
    check_required_check_name(
        plan_template.read_text(encoding="utf-8"), plan_template, errors
    )

    for markdown_path in markdown_files(manifest):
        for raw, linked in extract_links(markdown_path):
            if not linked.is_relative_to(ROOT):
                errors.append(
                    f"Repository link escapes the checkout in "
                    f"{markdown_path.relative_to(ROOT).as_posix()}: {raw}"
                )
            elif not linked.exists():
                errors.append(
                    f"Broken link in {markdown_path.relative_to(ROOT).as_posix()}: {raw}"
                )

    entrypoints = manifest.get("entrypoint_links", [])
    if not isinstance(entrypoints, list):
        errors.append("doc-sync-rules entrypoint_links must be a list")
        entrypoints = []
    for entry in entrypoints:
        if not isinstance(entry, dict):
            errors.append("entrypoint_links contains a non-object entry")
            continue
        source_value = entry.get("source")
        targets = entry.get("targets")
        if not isinstance(source_value, str) or not isinstance(targets, list):
            errors.append("entrypoint link entries require source and targets")
            continue
        if not exact_case_path_exists(source_value):
            errors.append(f"Entrypoint source missing or case-mismatched: {source_value}")
            continue
        source = ROOT / source_value
        linked_targets = {path for _, path in extract_links(source)}
        for target in targets:
            if not isinstance(target, str):
                errors.append(f"Entrypoint {source_value} has a non-string target")
                continue
            expected_targets = {
                (ROOT / target).resolve(),
                (source.parent / target).resolve(),
            }
            if linked_targets.isdisjoint(expected_targets):
                errors.append(f"Entrypoint {source_value} must link to {target}")

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
