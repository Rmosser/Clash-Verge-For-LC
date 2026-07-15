#!/usr/bin/env python3
"""Checkpoint verifier: reconcile Scope Claim vs git diff.

Convention:
- The single active plan under docs/exec-plans/active/ is the scope truth.
- Backtick-quoted tokens in the plan's `## Scope` section are machine-readable
  paths: exact file path, directory prefix ending with `/`, or fnmatch glob.
- A Scope line containing a negation marker (see FORBIDDEN_LINE_RE: forbidden,
  excluded, do not, must not, never, 禁止, 不允许, 不得, 不要, 勿改 ...)
  contributes its backticked tokens to a denylist instead. The machine only
  recognizes these markers; the canonical place to declare forbidden paths is
  the ## Non-Goals section.
- All backticked tokens in ## Non-Goals (or ## 非目标) join the denylist,
  regardless of wording. Deny overrides allow and the always-allowed
  bookkeeping paths.
- Glob patterns use fnmatch semantics: `*` also crosses `/`.
- A plan with more than one ## Scope heading fails (ambiguous scope truth).
- Free-text scope bullets without backticks are human context; the machine
  ignores them, so machine-relevant paths must be backtick-quoted.
- docs/exec-plans/active/ and completed/ are always allowed (unless denied):
  plan rotation and archival are harness bookkeeping, not product scope.
- With zero active plans, only conservative trivial documentation paths and
  plan bookkeeping may change. Governance, code, CI, configuration, release,
  and security surfaces still require an Active Plan.

The diff is the merge-base diff against a real PR/default-branch base plus any
uncommitted working-tree changes. A committed PR must never use HEAD as both
base and head; `--base HEAD` is reserved for unborn or explicit pre-commit
worktree checks.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(
    os.environ.get("HARNESS_REPO_ROOT", Path(__file__).resolve().parents[1])
).expanduser().resolve()


def exact_docs_root_name() -> str:
    candidates = [
        child for child in ROOT.iterdir() if child.name in {"docs", "Docs"}
    ]
    if len(candidates) != 1:
        raise RuntimeError("expected exactly one real docs/ or Docs/ governance root")
    root = candidates[0]
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("docs/ or Docs/ governance root must be a real directory")
    return root.name


DOCS_ROOT_NAME = exact_docs_root_name()
ACTIVE_DIR = ROOT / DOCS_ROOT_NAME / "exec-plans" / "active"
RULES_PATH = ROOT / DOCS_ROOT_NAME / "doc-sync-rules.json"
ALWAYS_ALLOWED_PREFIXES = (
    f"{DOCS_ROOT_NAME}/exec-plans/active/",
    f"{DOCS_ROOT_NAME}/exec-plans/completed/",
)
TRIVIAL_WITHOUT_PLAN_FILES = {
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "LICENSE.md",
}
TRIVIAL_WITHOUT_PLAN_PREFIXES = (f"{DOCS_ROOT_NAME}/",)
TRIVIAL_WITHOUT_PLAN_FORBIDDEN = (
    f"{DOCS_ROOT_NAME}/index.md",
    f"{DOCS_ROOT_NAME}/INDEX.md",
    f"{DOCS_ROOT_NAME}/doc-sync-rules.json",
    f"{DOCS_ROOT_NAME}/governance/",
    f"{DOCS_ROOT_NAME}/exec-plans/",
)
IGNORED_WORKTREE_PATTERNS = (
    "**/__pycache__/*.pyc",
    "**/.DS_Store",
)
BACKTICK_RE = re.compile(r"`([^`]+)`")
FORBIDDEN_LINE_RE = re.compile(
    r"forbidden|excluded?|exclude|deny|denied|must not|do not|don'?t|never"
    r"|not allowed|out of scope|off[- ]?limits"
    r"|禁止|不允许|不得|不要|不能|不修改|不动|勿改|勿动|禁改|非目标",
    re.IGNORECASE,
)


def fail(messages: list[str]) -> None:
    for message in messages:
        print(f"check_loop_checkpoints: {message}", file=sys.stderr)
    raise SystemExit(1)


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail([
            f"git {' '.join(args)} failed: {result.stderr.strip()}",
            "if the base ref is missing, fetch it first (CI checkout needs fetch-depth: 0)",
        ])
    return result.stdout


def git_lines(*args: str) -> list[str]:
    return [line for line in git_output(*args).splitlines() if line.strip()]


def default_base() -> str:
    explicit = os.environ.get("HARNESS_DIFF_BASE_REF", "").strip()
    if not explicit:
        explicit = os.environ.get("SUBHUB_DIFF_BASE_REF", "").strip()
    if explicit:
        return explicit
    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    if base_ref:
        for candidate in (f"origin/{base_ref}", base_ref):
            if ref_exists(candidate):
                return candidate
        return f"origin/{base_ref}"

    result = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "symbolic-ref",
            "--quiet",
            "--short",
            "refs/remotes/origin/HEAD",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and ref_exists(result.stdout.strip()):
        return result.stdout.strip()

    for candidate in ("origin/main", "origin/master", "main", "master"):
        if ref_exists(candidate):
            return candidate
    if not ref_exists("HEAD"):
        return "HEAD"
    fail([
        "no real PR/default-branch base ref is available",
        "fetch the default branch, set HARNESS_DIFF_BASE_REF, or pass --base "
        "with the actual PR base; use --base HEAD only for an explicit "
        "pre-commit worktree check",
    ])
    raise AssertionError("fail() exits")


def find_active_plan() -> Path | None:
    plans = sorted(
        path for path in ACTIVE_DIR.glob("*.md") if path.name != ".gitkeep"
    )
    if len(plans) > 1:
        fail([f"expected at most one active plan, found: {', '.join(p.name for p in plans)}"])
    return plans[0] if plans else None


def line_tokens(line: str) -> list[str]:
    tokens: list[str] = []
    for token in BACKTICK_RE.findall(line):
        token = token.strip()
        if token.startswith("./"):
            token = token[2:]
        if token:
            tokens.append(token)
    return tokens


def section_body(text: str, heading_re: str) -> str | None:
    match = re.search(rf"{heading_re}(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else None


def scope_patterns(plan: Path) -> tuple[list[str], list[str]]:
    text = plan.read_text(encoding="utf-8")
    if len(re.findall(r"^## Scope\s*$", text, re.MULTILINE)) > 1:
        fail([f"{plan.relative_to(ROOT)} has more than one '## Scope' heading; scope truth is ambiguous"])
    scope = section_body(text, r"^## Scope\s*$")
    if scope is None:
        fail([f"{plan.relative_to(ROOT)} has no '## Scope' section to reconcile against"])
    allows: list[str] = []
    denies: list[str] = []
    for line in scope.splitlines():
        tokens = line_tokens(line)
        if not tokens:
            continue
        (denies if FORBIDDEN_LINE_RE.search(line) else allows).extend(tokens)
    # Non-goals are part of the Scope Claim; every backticked token there is
    # forbidden regardless of wording, so deny does not depend on marker
    # vocabulary recognition.
    non_goals = section_body(text, r"^## (?:Non-Goals|非目标)\s*$")
    if non_goals is not None:
        for line in non_goals.splitlines():
            denies.extend(line_tokens(line))
    return allows, denies


def worktree_paths() -> set[str]:
    # porcelain v1 -z: each entry is `XY path`; for renames/copies the source
    # path follows as the next NUL-separated token. Both sides must be checked,
    # otherwise a rename out of scope into scope hides the out-of-scope removal.
    # -uall expands untracked directories into individual file paths; the
    # default collapsed `?? dir/` entry would let a broad allowlist hide
    # forbidden paths nested inside a brand-new directory.
    paths: set[str] = set()
    tokens = iter(git_output("status", "--porcelain", "-z", "-uall").split("\0"))
    for token in tokens:
        if len(token) < 4:
            continue
        status = token[:2]
        path = token[3:]
        ignored_untracked_noise = status == "??" and any(
            fnmatch.fnmatch(path, pattern)
            for pattern in IGNORED_WORKTREE_PATTERNS
        )
        if not ignored_untracked_noise:
            paths.add(path)
        if "R" in status or "C" in status:
            source = next(tokens, "")
            paths.add(source)
    paths.discard("")
    return paths


def ref_exists(ref: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
    ).returncode == 0


def changed_files(base: str, head: str) -> list[str]:
    # --no-renames keeps committed renames as delete+add so the diff lists
    # both the old and the new path.
    files: set[str] = set()
    head_exists = ref_exists(head)
    base_exists = ref_exists(base)
    if (
        os.environ.get("GITHUB_BASE_REF", "").strip()
        and head_exists
        and base_exists
        and git_output("rev-parse", base).strip()
        == git_output("rev-parse", head).strip()
    ):
        fail([
            f"PR base {base} resolves to the same commit as head {head}",
            "normal PR validation must compare the live PR head with its real base",
        ])
    if head_exists and base_exists and base != head:
        files.update(
            git_lines("diff", "--name-only", "--no-renames", f"{base}...{head}")
        )
    elif head_exists and base_exists:
        files.update(git_lines("diff", "--name-only", "--no-renames", base, head))
    elif base not in {"HEAD", head}:
        fail([
            f"base ref is unavailable: {base}",
            "fetch the base ref or set HARNESS_DIFF_BASE_REF to the actual PR base",
        ])
    files.update(worktree_paths())
    return sorted(files)


def matches_pattern(path: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        return path.startswith(pattern)
    if "*" in pattern or "?" in pattern or "[" in pattern:
        return fnmatch.fnmatch(path, pattern)
    return path == pattern


def active_plan_required_patterns() -> list[str]:
    try:
        payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail([
            f"cannot read active-plan policy from "
            f"{RULES_PATH.relative_to(ROOT)}: {exc}"
        ])
    diff_classes = payload.get("diff_classes", {})
    if not isinstance(diff_classes, dict):
        fail(["doc-sync-rules diff_classes must be an object when present"])
    patterns: list[str] = []
    for name, spec in diff_classes.items():
        if not isinstance(spec, dict) or spec.get("requires_active_plan") is not True:
            continue
        paths = spec.get("paths")
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            fail([f"diff class {name} requires an Active Plan but has invalid paths"])
        patterns.extend(paths)
    return patterns


def trivial_without_plan(path: str, required_plan_patterns: list[str]) -> bool:
    if any(matches_pattern(path, pattern) for pattern in required_plan_patterns):
        return False
    if path in TRIVIAL_WITHOUT_PLAN_FILES:
        return True
    if not path.startswith(TRIVIAL_WITHOUT_PLAN_PREFIXES):
        return False
    return not any(
        path == forbidden or path.startswith(forbidden)
        for forbidden in TRIVIAL_WITHOUT_PLAN_FORBIDDEN
    )


def classify(
    path: str,
    allows: list[str],
    denies: list[str],
    *,
    has_active_plan: bool = True,
    required_plan_patterns: list[str] | None = None,
) -> str | None:
    """Return the failure reason for path, or None when it is acceptable."""
    if any(matches_pattern(path, pattern) for pattern in denies):
        return "forbidden by Scope"
    if path.startswith(ALWAYS_ALLOWED_PREFIXES):
        return None
    if not has_active_plan:
        return (
            None
            if trivial_without_plan(path, required_plan_patterns or [])
            else "requires an Active Plan"
        )
    if any(matches_pattern(path, pattern) for pattern in allows):
        return None
    return "not in Scope allowlist"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="base ref for the merge-base diff")
    parser.add_argument("--head", default="HEAD", help="head ref for the merge-base diff")
    args = parser.parse_args()
    base = args.base or default_base()

    plan = find_active_plan()
    allows, denies = scope_patterns(plan) if plan else ([], [])
    required_plan_patterns = active_plan_required_patterns()
    problems = [
        f"{reason}: {path}"
        for path in changed_files(base, args.head)
        if (
            reason := classify(
                path,
                allows,
                denies,
                has_active_plan=plan is not None,
                required_plan_patterns=required_plan_patterns,
            )
        )
    ]

    if problems:
        plan_label = str(plan.relative_to(ROOT)) if plan else "no active plan"
        fail([
            f"Scope Claim vs git diff failed against {plan_label}",
            *problems,
            f"allowed: {', '.join(allows) if allows else '(none)'}",
            f"forbidden: {', '.join(denies) if denies else '(none)'}",
            "fix: add allowed paths as backticked entries in the active plan '## Scope' section;",
            "lines marked forbidden/禁止 contribute denylist entries that override allows,",
            "or move the change into its own plan / PR",
        ])
    print(f"check_loop_checkpoints: passed against base {base} and head {args.head}")


if __name__ == "__main__":
    main()
