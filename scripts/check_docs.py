#!/usr/bin/env python3
from __future__ import annotations

# HARNESS_WRAPPER_CHECK_DOCS_V2

import argparse
import fnmatch
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


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
    "## 任务分类",
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
    "Completed review head",
    "Review result",
    "## Repair Ledger",
    "## Post-Merge Cleanup",
]


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
    return [
        path
        for path in files
        if path.exists()
        and not any(
            fnmatch.fnmatch(path.relative_to(ROOT).as_posix(), pattern)
            for pattern in patterns
        )
    ]


def extract_links(markdown_path: Path) -> list[tuple[str, Path]]:
    text = markdown_path.read_text(encoding="utf-8")
    links: list[tuple[str, Path]] = []
    for match in LINK_RE.finditer(text):
        raw = (match.group(1) or match.group(2) or "").strip()
        if raw.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = raw.split("#", 1)[0]
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
    if not pending(review_result) and pending(completed_head):
        errors.append(
            f"Active plan {plan.relative_to(ROOT).as_posix()} records a review result "
            "without a completed review head"
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
        for section in REQUIRED_EVIDENCE_SECTIONS:
            if section not in text:
                errors.append(
                    f"Active plan {plan.relative_to(ROOT).as_posix()} "
                    f"missing required evidence section: {section}"
                )
        check_delegation_contract(text, plan, errors)
        check_claims_and_review(text, plan, errors)


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

    for markdown_path in markdown_files(manifest):
        for raw, linked in extract_links(markdown_path):
            if not linked.exists():
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
        review = contract.get("codex_review")
        if not isinstance(review, dict):
            errors.append("repo contract codex_review must be an object")
        else:
            expected_review_policy = {
                "supervision_model": "repository_self_supervised",
                "required_check": "codex-review",
                "status_app_id": 15368,
                "status_source_isolation": "shared_actions_app_not_isolated",
                "required_check_activation": "required_after_live_emitter_smoke",
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
    args, passthrough = parser.parse_known_args(argv)
    if not args.all:
        raise SystemExit("Only --all is supported by the Harness wrapper.")

    errors, _ = validate_repo()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    project_status = run_project_check(["--all", *passthrough])
    if project_status != 0:
        return project_status
    print("Docs checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
