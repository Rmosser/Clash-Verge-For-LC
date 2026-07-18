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
- Validated lowercase .md plans under docs/exec-plans/active/ are allowed
  (unless denied) as harness bookkeeping. Completed plans require either the
  Active Plan Scope or a verified archive-only transition; they cannot create
  their own provenance.
- With zero active plans, only conservative trivial documentation paths and
  plan bookkeeping may change. Governance, code, CI, configuration, release,
  and security surfaces still require an Active Plan.

PR validation uses a merge-base diff; push validation uses the exact predecessor
diff, and a first root push uses the root tree. Each mode also includes
uncommitted working-tree changes. A same-commit check is allowed only when a real
uncommitted diff exists or `--worktree-only` explicitly requests worktree-only
validation.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import posixpath
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

CHECKER_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("HARNESS_REPO_ROOT", CHECKER_ROOT)).expanduser().resolve()
TRUSTED_ROOT = Path(
    os.environ.get("HARNESS_TRUSTED_REPO_ROOT", CHECKER_ROOT)
).expanduser().resolve()


def exact_docs_root_name(root: Path, label: str) -> str:
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
    return docs_root.name


DOCS_ROOT_NAME = exact_docs_root_name(ROOT, "validation target")
TRUSTED_DOCS_ROOT_NAME = exact_docs_root_name(
    TRUSTED_ROOT, "trusted verifier checkout"
)
ACTIVE_DIR = ROOT / DOCS_ROOT_NAME / "exec-plans" / "active"
COMPLETED_DIR = ROOT / DOCS_ROOT_NAME / "exec-plans" / "completed"
ACTIVE_SENTINEL = ACTIVE_DIR / ".gitkeep"
RULES_PATH = ROOT / DOCS_ROOT_NAME / "doc-sync-rules.json"
TRUSTED_RULES_PATH = TRUSTED_ROOT / TRUSTED_DOCS_ROOT_NAME / "doc-sync-rules.json"
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
TRIVIAL_DOC_EXTENSIONS = {
    ".avif",
    ".gif",
    ".jpeg",
    ".jpg",
    ".md",
    ".markdown",
    ".png",
    ".rst",
    ".svg",
    ".txt",
    ".webp",
}
PRODUCT_GOVERNANCE_DOC_TOKENS = {
    "architecture",
    "architectures",
    "config",
    "configs",
    "configuration",
    "configurations",
    "design",
    "designs",
    "deploy",
    "deployment",
    "golden",
    "prd",
    "prds",
    "release",
    "releases",
    "rollback",
    "runbook",
    "runbooks",
    "secure",
    "security",
    "spec",
    "specification",
    "specifications",
    "specs",
    "threat",
    "threats",
    "threatmodel",
}
IGNORED_WORKTREE_PATTERNS = (
    "**/__pycache__/*.pyc",
    "**/.DS_Store",
)
BACKTICK_RE = re.compile(r"`([^`]+)`")
FIELD_RE_TEMPLATE = r"^[ \t]*-[ \t]*{field}[ \t]*[:：][ \t]*(.*)$"
COMPLETED_TRANSITION_VALUES = {"satisfied", "closed", "satisfied/closed"}
CANONICAL_COMPLETED_TRANSITION_VALUES = {"satisfied/closed"}
DEFERRED_ROLLOUT_CLOSURE_VALUES = {"deferred-to-rollout-closure"}
LEGACY_ARCHIVE_PREFIX = "archived-before-harness-upgrade-"
PLAN_LIFECYCLE_FIELDS = (
    "Status",
    "Main synced",
    "Active Plan archived",
    "Transition invariant",
    "Local branch deleted",
    "Heartbeat closed",
)
COMPLETED_LIFECYCLE_CONTRACT = {
    "Status": "completed",
    "Main synced": "completed",
    "Active Plan archived": "completed",
    "Transition invariant": "satisfied/closed",
    "Local branch deleted": "deferred-to-rollout-closure",
    "Heartbeat closed": "deferred-to-rollout-closure",
}
INLINE_LINK_RE = re.compile(
    r"!?\[[^\]]*\]\(\s*(?:<([^>\r\n]+)>|([^\s)]+))"
)
REFERENCE_LINK_RE = re.compile(
    r"^[ \t]{0,3}\[[^\]\r\n]+\]:[ \t]*(?:<([^>\r\n]+)>|([^\s]+))",
    re.MULTILINE,
)
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


def git_nul_paths(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        fail([
            f"git {' '.join(args)} failed: {detail}",
            "if the base ref is missing, fetch it first (CI checkout needs fetch-depth: 0)",
        ])
    if result.stdout and not result.stdout.endswith(b"\0"):
        fail([f"git {' '.join(args)} returned malformed non-NUL path output"])
    return [
        os.fsdecode(token)
        for token in result.stdout.rstrip(b"\0").split(b"\0")
        if token
    ]


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


def find_active_plan(changed_paths: set[str]) -> tuple[Path | None, set[str]]:
    for path, label in (
        (ACTIVE_DIR.parent, "exec-plans directory"),
        (ACTIVE_DIR, "active-plan directory"),
        (COMPLETED_DIR, "completed-plan directory"),
    ):
        if path.is_symlink() or not path.is_dir():
            fail([
                f"{label} must be a real directory, not a symlink: "
                f"{path.relative_to(ROOT)}"
            ])
    sentinel_relative = ACTIVE_SENTINEL.relative_to(ROOT).as_posix()
    if ACTIVE_SENTINEL.is_symlink() or not ACTIVE_SENTINEL.is_file():
        fail([
            "active-plan directory sentinel must be a regular file, not a symlink "
            f"or special file: {sentinel_relative}"
        ])
    if ACTIVE_SENTINEL.read_bytes() != b"":
        fail([
            "active-plan directory sentinel must be exactly zero bytes: "
            f"{sentinel_relative}"
        ])
    if ACTIVE_SENTINEL.stat().st_mode & 0o111:
        fail([
            "active-plan directory sentinel must not be executable: "
            f"{sentinel_relative}"
        ])
    plans = plan_files(ACTIVE_DIR, "Active Plan")
    completed = plan_files(COMPLETED_DIR, "Completed plan")
    if len(plans) > 1:
        fail([f"expected at most one active plan, found: {', '.join(p.name for p in plans)}"])
    for plan in plans:
        text = plan.read_text(encoding="utf-8")
        for field in PLAN_LIFECYCLE_FIELDS:
            if len(lifecycle_field_values(text, field)) != 1:
                fail([
                    f"{plan.relative_to(ROOT).as_posix()} must contain exactly one "
                    f"'{field}' lifecycle field"
                ])
        require_lifecycle_value(plan, "Status", {"active"})
        archived = lifecycle_field_values(text, "Active Plan archived")
        transition = lifecycle_field_values(text, "Transition invariant")
        if any(normalized(value) == "completed" for value in archived) or any(
            normalized(value) in COMPLETED_TRANSITION_VALUES for value in transition
        ):
            fail([
                f"{plan.relative_to(ROOT).as_posix()} contains mixed completed "
                "lifecycle state"
            ])
    for plan in completed:
        if plan.relative_to(ROOT).as_posix() not in changed_paths:
            continue
        require_lifecycle_value(plan, "Status", {"completed"})
        require_lifecycle_value(plan, "Active Plan archived", {"completed"})
        require_lifecycle_value(
            plan, "Transition invariant", COMPLETED_TRANSITION_VALUES
        )
    bookkeeping_paths = {path.relative_to(ROOT).as_posix() for path in plans}
    return (plans[0] if plans else None), bookkeeping_paths


def plan_files(directory: Path, label: str) -> list[Path]:
    plans: list[Path] = []
    for path in sorted(directory.iterdir()):
        if path.name == ".gitkeep":
            continue
        if path.is_symlink() or not path.is_file():
            fail([
                f"{label} must be a regular file, not a symlink or special file: "
                f"{path.relative_to(ROOT).as_posix()}"
            ])
        if path.suffix != ".md":
            fail([
                f"{label} bookkeeping may contain only lowercase .md plan files: "
                f"{path.relative_to(ROOT).as_posix()}"
            ])
        plans.append(path)
    return plans


def lifecycle_field_values(text: str, field: str) -> list[str]:
    pattern = re.compile(
        FIELD_RE_TEMPLATE.format(field=re.escape(field)),
        re.MULTILINE | re.IGNORECASE,
    )
    return [match.group(1).strip() for match in pattern.finditer(text)]


def normalized(value: str) -> str:
    return value.strip().strip("`").lower().strip(".,;:")


def require_lifecycle_value(plan: Path, field: str, allowed: set[str]) -> None:
    values = lifecycle_field_values(plan.read_text(encoding="utf-8"), field)
    if len(values) != 1 or normalized(values[0]) not in allowed:
        rendered = values[0] if len(values) == 1 and values[0] else "missing/duplicate/pending"
        fail([
            f"{plan.relative_to(ROOT).as_posix()} must contain exactly one "
            f"'{field}' field with one of {', '.join(sorted(allowed))}; got {rendered}"
        ])


def line_tokens(line: str) -> list[str]:
    tokens: list[str] = []
    for token in BACKTICK_RE.findall(line):
        token = token.strip()
        if token.startswith("./"):
            token = token[2:]
        if token:
            tokens.append(token)
    return tokens


def section_bodies(text: str, heading_re: str) -> list[str]:
    return [
        match.group(1)
        for match in re.finditer(
            rf"{heading_re}(.*?)(?=^## |\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
    ]


def section_body(text: str, heading_re: str) -> str | None:
    bodies = section_bodies(text, heading_re)
    return bodies[0] if bodies else None


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
    for non_goals in section_bodies(text, r"^## (?:Non-Goals|非目标)\s*$"):
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


def untracked_worktree_paths() -> set[str]:
    paths = set(
        git_nul_paths("ls-files", "-z", "--others", "--exclude-standard")
    )
    return {
        path
        for path in paths
        if not any(
            fnmatch.fnmatch(path, pattern)
            for pattern in IGNORED_WORKTREE_PATTERNS
        )
    }


def ref_exists(ref: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
    ).returncode == 0


def changed_files(
    base: str,
    head: str,
    *,
    worktree_only: bool = False,
    diff_mode: str = "merge-base",
) -> list[str]:
    # --no-renames keeps committed renames as delete+add so the diff lists
    # both the old and the new path.
    files: set[str] = set()
    head_exists = ref_exists(head)
    base_exists = ref_exists(base)
    worktree = worktree_paths()
    if diff_mode == "root":
        if not head_exists:
            fail([f"head ref is unavailable: {head}"])
        parents = git_output("rev-list", "--parents", "-n", "1", head).split()
        if len(parents) != 1:
            fail(["root diff mode requires head to resolve to a root commit"])
        files.update(
            git_nul_paths(
                "diff-tree",
                "--root",
                "--no-commit-id",
                "-r",
                "-z",
                "--name-only",
                "--no-renames",
                head,
            )
        )
        files.update(worktree)
        return sorted(files)
    same_commit = (
        head_exists
        and base_exists
        and git_output("rev-parse", base).strip()
        == git_output("rev-parse", head).strip()
    )
    if (
        os.environ.get("GITHUB_BASE_REF", "").strip()
        and head_exists
        and base_exists
        and same_commit
    ):
        fail([
            f"PR base {base} resolves to the same commit as head {head}",
            "normal PR validation must compare the live PR head with its real base",
        ])
    if same_commit and not worktree_only and not worktree:
        fail([
            f"base {base} and head {head} resolve to the same committed revision",
            "a clean committed checkout has no trustworthy diff; compare a real base "
            "and head, or pass --worktree-only for an intentional worktree-only check",
        ])
    if worktree_only:
        return sorted(worktree)
    current_head = (
        git_output("rev-parse", "HEAD").strip() if ref_exists("HEAD") else ""
    )
    resolved_head = git_output("rev-parse", head).strip() if head_exists else ""
    if worktree and base_exists and resolved_head == current_head:
        comparison_ref = base
        if diff_mode == "merge-base" and not same_commit:
            comparison_ref = git_output("merge-base", base, head).strip()
        files.update(
            git_nul_paths(
                "diff",
                "-z",
                "--name-only",
                "--no-renames",
                comparison_ref,
            )
        )
        files.update(untracked_worktree_paths())
        return sorted(files)
    if head_exists and base_exists and not same_commit:
        diff_range = (
            f"{base}...{head}" if diff_mode == "merge-base" else f"{base}..{head}"
        )
        files.update(
            git_nul_paths(
                "diff", "-z", "--name-only", "--no-renames", diff_range
            )
        )
    elif head_exists and base_exists:
        files.update(
            git_nul_paths("diff", "-z", "--name-only", "--no-renames", base, head)
        )
    elif base not in {"HEAD", head}:
        fail([
            f"base ref is unavailable: {base}",
            "fetch the base ref or set HARNESS_DIFF_BASE_REF to the actual PR base",
        ])
    files.update(worktree)
    return sorted(files)


def completed_plan_comparison_ref(
    base: str, head: str, *, worktree_only: bool, diff_mode: str
) -> str:
    if worktree_only or diff_mode == "root":
        return head
    if ref_exists(base) and ref_exists(head):
        base_sha = git_output("rev-parse", base).strip()
        head_sha = git_output("rev-parse", head).strip()
        if base_sha != head_sha and diff_mode == "merge-base":
            return git_output("merge-base", base, head).strip()
    return base


def reject_deleted_completed_plans(changed_paths: list[str], comparison_ref: str) -> None:
    completed_prefix = f"{DOCS_ROOT_NAME}/exec-plans/completed/"
    deleted: list[str] = []
    for relative in changed_paths:
        if not relative.startswith(completed_prefix) or not relative.endswith(".md"):
            continue
        target = ROOT / relative
        if target.exists() or target.is_symlink():
            continue
        if subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{comparison_ref}:{relative}"],
            capture_output=True,
            text=True,
        ).returncode == 0:
            deleted.append(relative)
    if deleted:
        fail([
            "completed plans are immutable archive evidence and cannot be deleted or renamed",
            *[f"deleted completed plan: {relative}" for relative in sorted(deleted)],
        ])


def matches_pattern(path: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        return path.startswith(pattern)
    if "*" in pattern or "?" in pattern or "[" in pattern:
        return fnmatch.fnmatch(path, pattern)
    return path == pattern


def load_policy(path: Path, label: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        fail([f"{label} must be a regular file: {path}"])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail([f"cannot read {label}: {exc}"])
    if not isinstance(payload, dict):
        fail([f"{label} must contain a top-level object"])
    return payload


def string_list_field(
    payload: dict[str, object], field: str, label: str
) -> list[str]:
    value = payload.get(field, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        fail([f"{label} {field} must be a list of strings"])
    return value


def scope_policy() -> tuple[list[str], list[str], list[str]]:
    target = load_policy(RULES_PATH, "target doc-sync-rules")
    trusted = load_policy(TRUSTED_RULES_PATH, "trusted doc-sync-rules")
    target_forbidden = string_list_field(
        target, "forbidden_paths", "target doc-sync-rules"
    )
    trusted_forbidden = string_list_field(
        trusted, "forbidden_paths", "trusted doc-sync-rules"
    )
    missing = sorted(set(trusted_forbidden) - set(target_forbidden))
    if missing:
        fail([
            "target doc-sync-rules cannot remove trusted forbidden paths: "
            f"{', '.join(missing)}"
        ])

    payload = target
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
    invariants = trusted.get("target_invariants", [])
    if not isinstance(invariants, list):
        fail(["trusted doc-sync-rules target_invariants must be a list"])
    archive_indexes: list[str] = []
    for index, spec in enumerate(invariants):
        if not isinstance(spec, dict):
            fail([f"trusted target_invariants[{index}] must be an object"])
        if spec.get("type") != "active_plan_index_link":
            fail([f"trusted target_invariants[{index}] has unsupported type"])
        index_path = spec.get("index")
        if not isinstance(index_path, str) or not index_path:
            fail([f"trusted target_invariants[{index}].index must be a path"])
        archive_indexes.append(index_path)
    return (
        patterns,
        sorted(set(target_forbidden) | set(trusted_forbidden)),
        archive_indexes,
    )


def lifecycle_skeleton(text: str) -> str | None:
    skeleton = text
    for field in PLAN_LIFECYCLE_FIELDS:
        pattern = re.compile(
            FIELD_RE_TEMPLATE.format(field=re.escape(field)),
            re.MULTILINE | re.IGNORECASE,
        )
        matches = list(pattern.finditer(skeleton))
        if len(matches) != 1:
            return None
        skeleton = pattern.sub(
            lambda match, field=field: (
                match.group(0)[: match.start(1) - match.start(0)]
                + f"<{field}>"
            ),
            skeleton,
            count=1,
        )
    return skeleton


def canonical_legacy_archive_text(source_text: str) -> str | None:
    matches_by_field: dict[str, re.Match[str]] = {}
    for field in PLAN_LIFECYCLE_FIELDS:
        pattern = re.compile(
            rf"^(?P<prefix>[ \t]*-[ \t]*{re.escape(field)}[ \t]*[:：][ \t]*)"
            rf"(?P<value>[^\r\n]*)(?P<line_ending>\r?\n?)$",
            re.MULTILINE | re.IGNORECASE,
        )
        matches = list(pattern.finditer(source_text))
        if len(matches) > 1:
            return None
        if matches:
            matches_by_field[field] = matches[0]
    missing = [field for field in PLAN_LIFECYCLE_FIELDS if field not in matches_by_field]
    if not missing:
        return None

    line_ending = "\r\n" if "\r\n" in source_text else "\n"
    migrated = source_text
    present_fields = sorted(
        matches_by_field,
        key=lambda field: matches_by_field[field].start(),
        reverse=True,
    )
    for field in present_fields:
        match = matches_by_field[field]
        previous = match.group("value").strip()
        ending = match.group("line_ending") or line_ending
        replacement = (
            f"- {field}: {COMPLETED_LIFECYCLE_CONTRACT[field]}{ending}"
            f"Completed-plan migration evidence for {field}; previous value JSON = "
            f"{json.dumps(previous)}.{ending}"
        )
        if not match.group("line_ending"):
            replacement = replacement.removesuffix(ending)
        migrated = migrated[: match.start()] + replacement + migrated[match.end() :]

    lines = migrated.splitlines(keepends=True)
    insert_at = 1
    if len(lines) > 1 and not lines[1].strip():
        insert_at = 2
    inserted: list[str] = []
    for field in missing:
        inserted.extend(
            [
                f"- {field}: {COMPLETED_LIFECYCLE_CONTRACT[field]}{line_ending}",
                f"Completed-plan migration evidence for {field}; "
                f"previous value JSON = null.{line_ending}",
            ]
        )
    inserted.append(line_ending)
    lines[insert_at:insert_at] = inserted
    return "".join(lines)


def markdown_link_targets(text: str) -> list[str]:
    targets: list[str] = []
    for pattern in (INLINE_LINK_RE, REFERENCE_LINK_RE):
        for match in pattern.finditer(text):
            raw = next(
                (group.strip() for group in match.groups() if group is not None),
                "",
            )
            if raw:
                targets.append(raw)
    return targets


def git_file_at(ref: str, path: str) -> tuple[str, str] | None:
    line = git_output("ls-tree", ref, "--", path).strip()
    if not line:
        return None
    metadata, listed_path = line.split("\t", 1)
    mode = metadata.split(" ", 1)[0]
    if listed_path != path:
        return None
    return mode, git_output("show", f"{ref}:{path}")


def archive_source_snapshot(
    base: str, head: str, *, diff_mode: str
) -> tuple[str, str, Callable[[str], str | None]] | None:
    active_prefix = f"{DOCS_ROOT_NAME}/exec-plans/active/"
    if TRUSTED_ROOT != ROOT:
        trusted_active = TRUSTED_ROOT / TRUSTED_DOCS_ROOT_NAME / "exec-plans" / "active"
        if trusted_active.is_symlink() or not trusted_active.is_dir():
            fail(["trusted active-plan directory must be a real directory"])
        plans = [
            path
            for path in sorted(trusted_active.glob("*.md"))
            if path.name != ".gitkeep"
        ]
        if any(path.is_symlink() or not path.is_file() for path in plans):
            fail(["trusted Active Plan must be a regular file"])
        if not plans:
            return None
        if len(plans) != 1:
            fail([f"archive cleanup requires one trusted Active Plan, found {len(plans)}"])
        plan = plans[0]

        def trusted_read(relative: str) -> str | None:
            candidate = TRUSTED_ROOT / relative
            if candidate.is_symlink() or not candidate.is_file():
                return None
            return candidate.read_text(encoding="utf-8")

        relative = f"{DOCS_ROOT_NAME}/exec-plans/active/{plan.name}"
        return relative, plan.read_text(encoding="utf-8"), trusted_read

    if diff_mode == "root":
        return None
    source_ref = base
    if diff_mode == "merge-base" and ref_exists(base) and ref_exists(head):
        source_ref = git_output("merge-base", base, head).strip()
    names = [
        path
        for path in git_lines("ls-tree", "-r", "--name-only", source_ref, "--", active_prefix)
        if path.endswith(".md") and not path.endswith("/.gitkeep")
    ]
    if not names:
        return None
    if len(names) != 1:
        fail([f"archive cleanup requires one base Active Plan, found {len(names)}"])
    source = git_file_at(source_ref, names[0])
    if source is None or source[0] not in {"100644", "100755"}:
        fail(["base Active Plan must be a regular file"])

    def git_read(relative: str) -> str | None:
        entry = git_file_at(source_ref, relative)
        if entry is None or entry[0] not in {"100644", "100755"}:
            return None
        return entry[1]

    return names[0], source[1], git_read


def archive_cleanup_index_allowlist(
    changed: list[str],
    base: str,
    head: str,
    index_paths: list[str],
    *,
    diff_mode: str,
) -> set[str]:
    if not index_paths:
        return set()
    snapshot = archive_source_snapshot(base, head, diff_mode=diff_mode)
    if snapshot is None:
        return set()
    source_path, source_text, source_read = snapshot
    if source_path not in changed or any(ACTIVE_DIR.glob("*.md")):
        return set()
    if len(index_paths) != 1:
        fail(["Active Plan archive cleanup requires exactly one index-link invariant"])
    index_path = index_paths[0]
    legacy_source = any(
        len(lifecycle_field_values(source_text, field)) == 0
        for field in PLAN_LIFECYCLE_FIELDS
    )
    completed_name = Path(source_path).name
    if legacy_source:
        completed_name = f"{LEGACY_ARCHIVE_PREFIX}{completed_name}"
    completed_path = (
        f"{DOCS_ROOT_NAME}/exec-plans/completed/{completed_name}"
    )
    required = {source_path, completed_path, index_path}
    missing = sorted(required - set(changed))
    if missing:
        fail([
            "incomplete Active Plan archive cleanup; missing diff paths: "
            f"{', '.join(missing)}"
        ])
    unexpected = sorted(set(changed) - required)
    if unexpected:
        fail([
            "archive-only cleanup must change exactly the active plan, its completed "
            "destination, and the trusted index; unexpected diff paths: "
            f"{', '.join(unexpected)}"
        ])
    completed = ROOT / completed_path
    target_index = ROOT / index_path
    if completed.is_symlink() or not completed.is_file():
        fail([f"archive destination must be a regular file: {completed_path}"])
    if target_index.is_symlink() or not target_index.is_file():
        fail([f"archive index must be a regular file: {index_path}"])
    completed_text = completed.read_text(encoding="utf-8")
    completed_contract = {
        "Status": {"completed"},
        "Main synced": {"completed"},
        "Active Plan archived": {"completed"},
        "Transition invariant": CANONICAL_COMPLETED_TRANSITION_VALUES,
        "Local branch deleted": DEFERRED_ROLLOUT_CLOSURE_VALUES,
        "Heartbeat closed": DEFERRED_ROLLOUT_CLOSURE_VALUES,
    }
    if legacy_source:
        if canonical_legacy_archive_text(source_text) != completed_text:
            fail([
                "legacy archive destination must be the exact reversible canonical "
                "migration of the source Active Plan"
            ])
    else:
        source_status = lifecycle_field_values(source_text, "Status")
        source_archived = lifecycle_field_values(source_text, "Active Plan archived")
        source_transition = lifecycle_field_values(source_text, "Transition invariant")
        if (
            len(source_status) != 1
            or normalized(source_status[0]) != "active"
            or len(source_archived) != 1
            or normalized(source_archived[0]) == "completed"
            or len(source_transition) != 1
            or normalized(source_transition[0]) in COMPLETED_TRANSITION_VALUES
        ):
            fail(["archive cleanup source has duplicate or mixed lifecycle state"])
    for field, allowed in completed_contract.items():
        values = lifecycle_field_values(completed_text, field)
        if len(values) != 1 or normalized(values[0]) not in allowed:
            fail([f"archive destination has invalid or duplicate {field}"])
    if (
        not legacy_source
        and lifecycle_skeleton(source_text) != lifecycle_skeleton(completed_text)
    ):
        fail([
            "archive cleanup may only change canonical lifecycle fields in the moved plan"
        ])

    source_index = source_read(index_path)
    if source_index is None:
        fail([f"trusted archive index must be a regular file: {index_path}"])
    target_index_text = target_index.read_text(encoding="utf-8")
    index_parent = posixpath.dirname(index_path)
    active_relative = posixpath.relpath(source_path, index_parent)
    completed_relative = posixpath.relpath(completed_path, index_parent)
    matching = [
        raw
        for raw in markdown_link_targets(source_index)
        if raw.partition("#")[0].removeprefix("./") == active_relative
    ]
    if len(matching) != 1 or source_index.count(matching[0]) != 1:
        fail(["trusted index must have one unambiguous Active Plan link"])
    raw = matching[0]
    raw_path, separator, fragment = raw.partition("#")
    prefix = "./" if raw_path.startswith("./") else ""
    replacement = prefix + completed_relative
    if separator:
        replacement += separator + fragment
    expected_index = source_index.replace(raw, replacement, 1)
    if target_index_text != expected_index:
        fail([
            "archive cleanup index may only change the unique plan link from "
            "active/ to completed/"
        ])
    target_matches = [
        raw
        for raw in markdown_link_targets(target_index_text)
        if raw.partition("#")[0].removeprefix("./") == completed_relative
    ]
    if len(target_matches) != 1:
        fail(["archive cleanup index must contain one completed-plan link"])
    return required


def is_product_governance_doc(path: str) -> bool:
    relative = path.removeprefix(f"{DOCS_ROOT_NAME}/")
    tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", relative.lower())
        if token
    }
    return bool(tokens & PRODUCT_GOVERNANCE_DOC_TOKENS)


def trivial_without_plan(path: str, required_plan_patterns: list[str]) -> bool:
    if any(matches_pattern(path, pattern) for pattern in required_plan_patterns):
        return False
    if path in TRIVIAL_WITHOUT_PLAN_FILES:
        return True
    if not path.startswith(TRIVIAL_WITHOUT_PLAN_PREFIXES):
        return False
    if any(
        path == forbidden or path.startswith(forbidden)
        for forbidden in TRIVIAL_WITHOUT_PLAN_FORBIDDEN
    ):
        return False
    if is_product_governance_doc(path):
        return False
    return Path(path).suffix.lower() in TRIVIAL_DOC_EXTENSIONS


def classify(
    path: str,
    allows: list[str],
    denies: list[str],
    *,
    has_active_plan: bool = True,
    required_plan_patterns: list[str] | None = None,
    no_plan_allowed: set[str] | None = None,
    bookkeeping_allowed: set[str] | None = None,
) -> str | None:
    """Return the failure reason for path, or None when it is acceptable."""
    if any(matches_pattern(path, pattern) for pattern in denies):
        return "forbidden by Scope"
    if has_active_plan and path in (bookkeeping_allowed or set()):
        return None
    if not has_active_plan:
        if path in (no_plan_allowed or set()):
            return None
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
    parser.add_argument(
        "--worktree-only",
        action="store_true",
        help="intentionally validate only staged, unstaged, and untracked changes",
    )
    parser.add_argument(
        "--diff-mode",
        choices=("merge-base", "direct", "root"),
        default="merge-base",
        help="use PR merge-base, push-predecessor, or root-tree diff semantics",
    )
    args = parser.parse_args()
    if args.worktree_only and args.diff_mode != "merge-base":
        parser.error("--worktree-only cannot be combined with --diff-mode")
    if args.diff_mode == "root" and args.base:
        parser.error("--diff-mode root does not accept --base")
    base = args.base or ("HEAD" if args.worktree_only else default_base())

    changed = changed_files(
        base,
        args.head,
        worktree_only=args.worktree_only,
        diff_mode=args.diff_mode,
    )
    reject_deleted_completed_plans(
        changed,
        completed_plan_comparison_ref(
            base,
            args.head,
            worktree_only=args.worktree_only,
            diff_mode=args.diff_mode,
        ),
    )
    plan, bookkeeping_allowed = find_active_plan(set(changed))
    allows, denies = scope_patterns(plan) if plan else ([], [])
    required_plan_patterns, policy_denies, archive_indexes = scope_policy()
    denies.extend(policy_denies)
    archive_allowed = (
        archive_cleanup_index_allowlist(
            changed,
            base,
            args.head,
            archive_indexes,
            diff_mode=args.diff_mode,
        )
        if plan is None
        else set()
    )
    problems = [
        f"{reason}: {path}"
        for path in changed
        if (
            reason := classify(
                path,
                allows,
                denies,
                has_active_plan=plan is not None,
                required_plan_patterns=required_plan_patterns,
                no_plan_allowed=archive_allowed,
                bookkeeping_allowed=bookkeeping_allowed,
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
    print(
        "check_loop_checkpoints: passed against "
        f"base {base} and head {args.head} ({args.diff_mode})"
    )


if __name__ == "__main__":
    main()
