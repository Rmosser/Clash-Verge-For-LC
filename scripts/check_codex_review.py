#!/usr/bin/env python3
"""Evaluate Codex review evidence for the live PR head and publish a status.

The trusted default-branch workflow calls this script for PR, review, and
comment events. It never executes code from the pull-request branch. A
non-trivial PR passes only when a Codex artifact is explicitly bound to the
current head SHA and the live base review epoch, with no current-head Codex
finding present.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTHORS = ("chatgpt-codex-connector[bot]",)
DEFAULT_CONTEXT = "codex-review"
DEFAULT_BASE_REF = "main"
GITHUB_ACTIONS_APP_ID = 15368
GITHUB_ACTIONS_STATUS_CREATOR = "github-actions[bot]"
STATUS_BASE_RE = re.compile(r"; base=([0-9a-f]{40})\.$", re.IGNORECASE)
TRIVIAL_FILES = {
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "LICENSE.md",
}
TRIVIAL_DOC_PREFIXES = ("docs/",)
TRIVIAL_DOC_SUFFIXES = (".adoc", ".md", ".mdx", ".rst", ".txt")
TRUSTED_TRIGGER_ASSOCIATIONS = {"COLLABORATOR", "MEMBER", "OWNER"}
REACTIONS_FIELD = "_codex_trigger_reactions"
PRIVILEGED_REVIEW_TRIGGER_ENTRYPOINTS = frozenset(
    {
        "scripts/fetch_pr_feedback.py",
        "scripts/render_codex_docs_review_comment.py",
        "scripts/run_docs_consistency_audit.py",
        "scripts/should_trigger_codex_review.py",
    }
)
# These modules are imported or dynamically loaded by the entrypoints above.
# Keep the complete closure immutable because the workflow carries write
# permissions and exposes CODEX_REVIEW_TRIGGER_TOKEN to its comment step.
PRIVILEGED_REVIEW_TRIGGER_HELPERS = PRIVILEGED_REVIEW_TRIGGER_ENTRYPOINTS | {
    "scripts/active_plan_checks.py",
    "scripts/check_doc_sync.py",
    "scripts/check_docs.py",
    "scripts/check_docs_common.py",
    "scripts/check_docs_links.py",
    "scripts/check_docs_paths.py",
    "scripts/check_docs_project.py",
    "scripts/check_docs_structure.py",
    "scripts/check_knowledge_index.py",
    "scripts/check_plan_required.py",
    "scripts/codex_review_adjudicator.py",
}
TRUSTED_CONTROL_PATHS = {
    ".github/doc-sync-rules.json",
    ".harness/repo-contract.json",
    "Docs",
    "Docs/doc-sync-rules.json",
    "docs",
    "docs/doc-sync-rules.json",
    "scripts/check_codex_review.py",
    "scripts/check_doc_sync.py",
    "scripts/check_docs.py",
    "scripts/check_docs_project.py",
    "scripts/check_loop_checkpoints.py",
} | PRIVILEGED_REVIEW_TRIGGER_HELPERS
TRUSTED_CONTROL_PREFIXES = (".github/workflows/",)
NON_TRIVIAL_DOC_PATHS = (
    "docs/index.md",
    "docs/INDEX.md",
    "docs/doc-sync-rules.json",
    "docs/governance/",
    "docs/exec-plans/",
)
NON_TRIVIAL_DOC_TOKENS = {
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
REVIEWED_COMMIT_LABEL_PATTERN = r"(?:\*\*Reviewed commit:\*\*|Reviewed commit:)"
REVIEWED_COMMIT_FIELD_RE = re.compile(
    REVIEWED_COMMIT_LABEL_PATTERN + r"\s*`([^`]+)`",
    re.IGNORECASE,
)
VALID_REVIEWED_COMMIT_RE = re.compile(r"[0-9a-f]{10,40}", re.IGNORECASE)
TRIGGER_RE = re.compile(r"^\s*@codex\s+review\s*$", re.IGNORECASE | re.MULTILINE)
TRIGGER_HEAD_RE = re.compile(
    r"^\s*(?:\*\*Head SHA(?::\*\*|\*\*:)|Head SHA:)\s*"
    r"`?([0-9a-f]{40})`?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
FINDING_RE = re.compile(
    r"(?:img\.shields\.io/badge/P[0-3]-|\bP[0-3]\s+Badge\b|"
    r"\[\s*P[0-3]\s*\]|\bP[0-3]\s*(?::|-)\s*\S|"
    r"\bP[0-3]\b\s+(?:finding|issue|bug|risk)\b|"
    r"\bPriority\s*[0-3]\b|"
    r"changes requested|needs changes|needs repair|please fix|blocking finding)",
    re.IGNORECASE,
)
CLEAN_BODY_RE = re.compile(
    r"^\s*(?:(?:#{1,6}\s*)?Codex Review:\s*)?"
    r"(?:Didn't find any major issues|Did not find any major issues|"
    r"No major issues|No findings)\.?\s*"
    r"(?:"
    + REVIEWED_COMMIT_LABEL_PATTERN
    + r"\s*`[0-9a-f]{10,40}`\s*)?"
    r"(?:Comment\s+[`\"']?@codex\s+review[`\"']?\s+to\s+run\s+again\.?\s*)?$",
    re.IGNORECASE | re.DOTALL,
)
STANDARD_CODEX_DETAILS_PATTERN = (
    r"<details>\s*<summary>\s*(?:\u2139\ufe0f?\s*)?"
    r"About Codex in GitHub\s*</summary>\s*"
    r"<br\s*/?>\s*"
    r"\[Your team has set up Codex to review pull requests in this repo\]"
    r"\(https?://chatgpt\.com/codex/(?:cloud/)?settings/general\)\.\s*"
    r"Reviews are triggered when you\s*"
    r"-\s*Open a pull request for review\s*"
    r"-\s*Mark a draft as ready\s*"
    r"-\s*Comment\s+[\"\u201c]@codex review[\"\u201d]\.\s*"
    r"If Codex has suggestions, it will comment;\s*"
    r"otherwise it will react with\s*\U0001f44d\ufe0f?\.\s*"
    r"Codex can also answer questions or update the PR\.\s*"
    r"Try commenting\s+[\"\u201c]@codex address that feedback[\"\u201d]\.\s*"
    r"</details>"
)
CLEAN_CELEBRATION_PATTERN = (
    r"(?!(?:\*\*Reviewed commit:\*\*|Reviewed commit:))"
    r"(?P<celebration>[^\r\n]{1,80})"
)
STANDARD_FOOTER_CLEAN_BODY_RE = re.compile(
    r"^\s*(?:(?:#{1,6}\s*)?Codex Review:\s*)?"
    r"(?:Didn't find any major issues|Did not find any major issues|"
    r"No major issues|No findings)\.?\s*"
    r"(?:"
    + CLEAN_CELEBRATION_PATTERN
    + r"\s*)?"
    r"(?:"
    + REVIEWED_COMMIT_LABEL_PATTERN
    + r"\s*`[0-9a-f]{10,40}`\s*)?"
    + STANDARD_CODEX_DETAILS_PATTERN
    + r"\s*$",
    re.IGNORECASE,
)
FULL_CLEAN_ISSUE_COMMENT_RE = re.compile(
    r"^\s*Codex Review:\s*Didn't find any major issues\.\s*"
    r"(?:"
    + CLEAN_CELEBRATION_PATTERN
    + r"\s*)?"
    + REVIEWED_COMMIT_LABEL_PATTERN
    + r"\s*`[0-9a-f]{10,40}`\s*"
    + STANDARD_CODEX_DETAILS_PATTERN
    + r"\s*$",
    re.IGNORECASE,
)
INCOMPLETE_REVIEW_RE = re.compile(
    r"(?:\btimed?\s+out\b|\btimeout\b|"
    r"\b(?:analysis|review)\s+(?:is\s+|was\s+)?incomplete\b|"
    r"\bpartial(?:ly)?\s+(?:analysis|review)\b|"
    r"\b(?:could not|unable to|failed to)\s+(?:complete|finish)\b|"
    r"\bencountered an error\b)",
    re.IGNORECASE,
)
UNSAFE_CLEAN_CELEBRATION_RE = re.compile(
    r"\b(?:but|however|except|although|unless|finding|findings|issue|issues|"
    r"bug|bugs|risk|risks|change|changes|fix|fixes|repair|pending|incomplete|"
    r"unsupported|security|threat|vulnerability|bypass|error|failed|failure|"
    r"warning|concern|concerns|blocker|blocking)\b",
    re.IGNORECASE,
)


class GateError(RuntimeError):
    pass


@dataclass(frozen=True)
class GateResult:
    state: str
    classification: str
    head_sha: str
    description: str
    reasons: tuple[str, ...]
    evidence_url: str | None = None
    publish: bool = True


@dataclass(frozen=True)
class PullIdentity:
    state: str
    head_repository: str
    head_sha: str
    base_repository: str
    base_ref: str
    base_sha: str


class GitHubAPI:
    def __init__(self, token: str, api_url: str) -> None:
        if not token:
            raise GateError("GITHUB_TOKEN is required for live evaluation")
        self.token = token
        self.api_url = api_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "harness-codex-review-gate",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GateError(f"GitHub API {method} {path} failed: {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise GateError(f"GitHub API {method} {path} failed: {exc.reason}") from exc
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GateError(f"GitHub API {method} {path} returned invalid JSON") from exc

    def get_pages(self, path: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, 101):
            payload = self.request(
                "GET", f"{path}{separator}per_page=100&page={page}"
            )
            if not isinstance(payload, list):
                raise GateError(f"GitHub API GET {path} did not return a list")
            if not all(isinstance(item, dict) for item in payload):
                raise GateError(f"GitHub API GET {path} returned malformed rows")
            rows.extend(payload)
            if len(payload) < 100:
                return rows
        raise GateError(f"GitHub API GET {path} exceeded 100 pages")


def repo_path(repository: str) -> str:
    parts = repository.split("/")
    if len(parts) != 2 or not all(parts):
        raise GateError("repository must look like owner/name")
    return "/".join(urllib.parse.quote(part, safe="") for part in parts)


def load_contract() -> dict[str, Any]:
    path = ROOT / ".harness" / "repo-contract.json"
    if path.is_symlink():
        raise GateError("repo contract must be a regular file, not a symlink")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"cannot read {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise GateError("repo contract must be a JSON object")
    return payload


def load_review_required_patterns() -> tuple[str, ...]:
    docs_roots = [
        child for child in ROOT.iterdir() if child.name in {"docs", "Docs"}
    ]
    if len(docs_roots) != 1:
        raise GateError("expected exactly one real docs/ or Docs/ governance root")
    docs_root = docs_roots[0]
    if docs_root.is_symlink() or not docs_root.is_dir():
        raise GateError("docs/ or Docs/ governance root must be a real directory")
    path = docs_root / "doc-sync-rules.json"
    if path.is_symlink():
        raise GateError("doc sync rules must be a regular file, not a symlink")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"cannot read doc sync rules: {exc}") from exc
    if not isinstance(payload, dict):
        raise GateError("doc sync rules must be a JSON object")
    diff_classes = payload.get("diff_classes", {})
    if not isinstance(diff_classes, dict):
        raise GateError("doc-sync-rules diff_classes must be an object")
    patterns: list[str] = []
    for name, spec in diff_classes.items():
        if not isinstance(spec, dict) or spec.get("requires_codex_review") is not True:
            continue
        paths = spec.get("paths")
        if not isinstance(paths, list) or not all(
            isinstance(value, str) and value for value in paths
        ):
            raise GateError(
                f"diff class {name} requires Codex review but has invalid paths"
            )
        patterns.extend(paths)
    return tuple(patterns)


def review_contract(contract: dict[str, Any]) -> dict[str, Any]:
    value = contract.get("codex_review")
    if not isinstance(value, dict):
        raise GateError("repo contract codex_review must be an object")
    return value


def accepted_authors(contract: dict[str, Any]) -> set[str]:
    raw = review_contract(contract).get("accepted_authors", DEFAULT_AUTHORS)
    if not isinstance(raw, list) and not isinstance(raw, tuple):
        raise GateError("codex_review.accepted_authors must be a list")
    authors = {normalize_login(value) for value in raw if normalize_login(value)}
    if not authors:
        raise GateError("codex_review.accepted_authors cannot be empty")
    return authors


def normalize_login(value: Any) -> str:
    login = str(value or "").strip().casefold()
    return login[:-5] if login.endswith("[bot]") else login


def actor_login(item: dict[str, Any]) -> str:
    user = item.get("user")
    if isinstance(user, dict):
        return normalize_login(user.get("login"))
    return ""


def trusted_codex_actor(item: dict[str, Any], authors: set[str]) -> bool:
    user = item.get("user")
    return bool(
        isinstance(user, dict)
        and user.get("type") == "Bot"
        and actor_login(item) in authors
    )


def trusted_trigger(
    item: dict[str, Any], authors: set[str]
) -> bool:
    return bool(
        actor_login(item)
        and actor_login(item) not in authors
        and str(item.get("author_association") or "").upper()
        in TRUSTED_TRIGGER_ASSOCIATIONS
        and TRIGGER_RE.search(str(item.get("body") or ""))
        and artifact_time(item)
    )


def trigger_bound_to_full_head(item: dict[str, Any], head_sha: str) -> bool:
    markers = TRIGGER_HEAD_RE.findall(str(item.get("body") or ""))
    return len(markers) == 1 and markers[0].casefold() == head_sha.casefold()


def reviewed_head(body: str, head_sha: str) -> bool:
    markers = REVIEWED_COMMIT_FIELD_RE.findall(body)
    return bool(markers) and all(
        VALID_REVIEWED_COMMIT_RE.fullmatch(value)
        and head_sha.lower().startswith(value.lower())
        for value in markers
    )


def stale_or_invalid_review_marker(body: str, head_sha: str) -> bool:
    markers = REVIEWED_COMMIT_FIELD_RE.findall(body)
    return bool(markers) and not reviewed_head(body, head_sha)


def explicitly_stale_review_marker(body: str, head_sha: str) -> bool:
    markers = REVIEWED_COMMIT_FIELD_RE.findall(body)
    return bool(markers) and all(
        VALID_REVIEWED_COMMIT_RE.fullmatch(value)
        and not head_sha.lower().startswith(value.lower())
        for value in markers
    )


def finding_body(body: str) -> bool:
    return bool(FINDING_RE.search(body))


def safe_clean_celebration(value: str) -> bool:
    celebration = value.strip()
    return bool(
        celebration
        and "\n" not in celebration
        and "\r" not in celebration
        and len(celebration) <= 80
        and not finding_body(celebration)
        and not INCOMPLETE_REVIEW_RE.search(celebration)
        and not UNSAFE_CLEAN_CELEBRATION_RE.search(celebration)
    )


def structured_footer_clean_body(body: str) -> bool:
    for pattern in (STANDARD_FOOTER_CLEAN_BODY_RE, FULL_CLEAN_ISSUE_COMMENT_RE):
        match = pattern.fullmatch(body)
        if match is None:
            continue
        celebration = str(match.groupdict().get("celebration") or "")
        return not celebration or safe_clean_celebration(celebration)
    return False


def clean_body(body: str) -> bool:
    return bool(
        CLEAN_BODY_RE.fullmatch(body) or structured_footer_clean_body(body)
    )


def recognized_commented_review_body(body: str, head_sha: str) -> bool:
    if INCOMPLETE_REVIEW_RE.search(body):
        return False
    return clean_body(body)


def trivial_path(path: str, review_required_patterns: tuple[str, ...]) -> bool:
    if any(
        path.startswith(pattern) if pattern.endswith("/") else fnmatch.fnmatchcase(path, pattern)
        for pattern in review_required_patterns
    ):
        return False
    if path in TRIVIAL_FILES:
        return True
    docs_prefix = next(
        (
            f"{child.name}/"
            for child in ROOT.iterdir()
            if child.name in {"docs", "Docs"}
            and not child.is_symlink()
            and child.is_dir()
        ),
        "",
    )
    if not docs_prefix or not path.startswith(docs_prefix):
        return False
    normalized = path.casefold()
    if not normalized.endswith(TRIVIAL_DOC_SUFFIXES):
        return False
    semantic_tokens = [
        tuple(filter(None, re.split(r"[^a-z0-9]+", component)))
        for component in normalized.split("/")[1:]
    ]
    if any(
        NON_TRIVIAL_DOC_TOKENS.intersection(tokens)
        or any(
            tokens[index : index + 2] == ("threat", "model")
            for index in range(len(tokens) - 1)
        )
        for tokens in semantic_tokens
    ):
        return False
    return not any(
        normalized == blocked.casefold() or normalized.startswith(blocked.casefold())
        for blocked in NON_TRIVIAL_DOC_PATHS
    )


def changed_paths(files: list[dict[str, Any]]) -> list[str]:
    paths: set[str] = set()
    for item in files:
        for key in ("filename", "previous_filename"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                paths.add(value.strip())
    return sorted(paths)


def conflicting_docs_root_path(path: str) -> bool:
    candidates = [
        child.name
        for child in ROOT.iterdir()
        if child.name in {"docs", "Docs"}
        and not child.is_symlink()
        and child.is_dir()
    ]
    if len(candidates) != 1:
        raise GateError("expected exactly one real docs/ or Docs/ governance root")
    top_level = path.split("/", 1)[0]
    return top_level in {"docs", "Docs"} and top_level != candidates[0]


def artifact_url(item: dict[str, Any]) -> str | None:
    for key in ("html_url", "url"):
        value = item.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return None


def artifact_time(item: dict[str, Any]) -> str:
    for key in ("submitted_at", "updated_at", "created_at"):
        value = item.get(key)
        if isinstance(value, str):
            return value
    return ""


def review_activity_time(item: dict[str, Any]) -> str:
    values = [
        value
        for key in (
            "submitted_at",
            "created_at",
            "updated_at",
            "edited_at",
            "last_edited_at",
        )
        if isinstance((value := item.get(key)), str) and value
    ]
    return max(values, default="")


def evidence_time(item: dict[str, Any]) -> str:
    if "submitted_at" in item:
        return review_activity_time(item)
    return artifact_time(item)


def review_blocking_reasons(review: dict[str, Any], head_sha: str) -> list[str]:
    state = str(review.get("state") or "").upper()
    body = str(review.get("body") or "")
    reasons: list[str] = []
    if state not in {"APPROVED", "COMMENTED", "CHANGES_REQUESTED"}:
        reasons.append(
            f"Codex review has unsupported current-head state: {state or 'MISSING'}"
        )
    if state == "CHANGES_REQUESTED":
        reasons.append("Codex requested changes on the current head")
    if finding_body(body):
        reasons.append("Codex review body contains a current-head finding")
    if stale_or_invalid_review_marker(body, head_sha):
        reasons.append(
            "Codex review body contains a stale or invalid reviewed-commit marker"
        )
    if state == "APPROVED" and body.strip() and not clean_body(body):
        reasons.append(
            "Codex APPROVED review contains non-clean text for the current head"
        )
    if state == "COMMENTED" and not recognized_commented_review_body(
        body, head_sha
    ):
        reasons.append(
            "Codex COMMENTED review is incomplete or unrecognized for the current head"
        )
    return reasons


def evaluate(
    payload: dict[str, Any],
    contract: dict[str, Any],
    expected_head: str = "",
    bootstrap_control_plane_review: bool = False,
    evidence_not_before: str = "",
) -> GateResult:
    pull = payload.get("pull")
    if not isinstance(pull, dict):
        raise GateError("payload.pull must be an object")
    head = pull.get("head")
    head_sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(head_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", head_sha):
        raise GateError("payload.pull.head.sha must be a full 40-character SHA")
    head_sha = head_sha.lower()

    if expected_head and expected_head.lower() != head_sha:
        return GateResult(
            state="failure",
            classification="stale-event",
            head_sha=head_sha,
            description=f"Review event is stale for current head {head_sha[:10]}.",
            reasons=(
                f"event head {expected_head.lower()} does not match live PR head {head_sha}",
            ),
            publish=False,
        )

    files = payload.get("files")
    reviews = payload.get("reviews")
    review_comments = payload.get("review_comments")
    issue_comments = payload.get("issue_comments")
    for label, value in (
        ("files", files),
        ("reviews", reviews),
        ("review_comments", review_comments),
        ("issue_comments", issue_comments),
    ):
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise GateError(f"payload.{label} must be a list of objects")

    paths = changed_paths(files)
    declared_changed_files = pull.get("changed_files")
    files_truncated = bool(
        isinstance(declared_changed_files, int)
        and declared_changed_files > len(files)
    )
    review_required_patterns = load_review_required_patterns()
    is_trivial = (
        not files_truncated
        and bool(paths)
        and all(trivial_path(path, review_required_patterns) for path in paths)
    )
    required = review_contract(contract).get("required_for_non_trivial_pr") is True
    changed_control_paths = sorted(
        path
        for path in paths
        if path in TRUSTED_CONTROL_PATHS
        or conflicting_docs_root_path(path)
        or any(path.startswith(prefix) for prefix in TRUSTED_CONTROL_PREFIXES)
    )
    if changed_control_paths and not bootstrap_control_plane_review:
        return GateResult(
            state="failure",
            classification="trusted-control-change",
            head_sha=head_sha,
            description="Trusted workflow and Codex gate controls cannot change in a PR.",
            reasons=(
                f"trusted control paths are immutable from pull-request branches: "
                f"{changed_control_paths}; use the platform migration procedure",
            ),
        )
    if is_trivial or not required:
        reason = (
            "all changed paths are conservative documentation-only paths"
            if is_trivial
            else "repo contract does not require Codex review"
        )
        return GateResult(
            state="success",
            classification="trivial" if is_trivial else "not-required",
            head_sha=head_sha,
            description=f"Codex review is not required for head {head_sha[:10]}.",
            reasons=(reason,),
        )

    authors = accepted_authors(contract)
    triggers = [
        item
        for item in issue_comments
        if trusted_trigger(item, authors)
        and trigger_bound_to_full_head(item, head_sha)
    ]
    latest_trigger = max(triggers, key=artifact_time) if triggers else None
    trigger_time = artifact_time(latest_trigger) if latest_trigger else ""

    request_contexts = [
        item
        for item in issue_comments
        if actor_login(item) not in authors
        and TRIGGER_RE.search(str(item.get("body") or ""))
        and artifact_time(item)
    ]

    def after_latest_trigger(item: dict[str, Any]) -> bool:
        timestamp = artifact_time(item)
        if latest_trigger is None:
            return bool(timestamp)
        # GitHub exposes only second precision here. Equal timestamps cannot
        # prove causal order across the issue, review, and inline-comment APIs.
        return bool(timestamp and timestamp > trigger_time)

    def at_or_after_latest_trigger(item: dict[str, Any]) -> bool:
        timestamp = artifact_time(item)
        if latest_trigger is None:
            return bool(timestamp)
        return bool(timestamp and timestamp >= trigger_time)

    def review_after_latest_trigger(item: dict[str, Any]) -> bool:
        timestamp = review_activity_time(item)
        if latest_trigger is None:
            return bool(timestamp)
        return bool(timestamp and timestamp > trigger_time)

    def review_at_or_after_latest_trigger(item: dict[str, Any]) -> bool:
        timestamp = review_activity_time(item)
        if latest_trigger is None:
            return bool(timestamp)
        return bool(timestamp and timestamp >= trigger_time)

    def issue_clean_has_provenance(item: dict[str, Any], body: str) -> bool:
        if not reviewed_head(body, head_sha):
            return False
        if structured_footer_clean_body(body):
            return True
        timestamp = artifact_time(item)
        return bool(
            timestamp
            and any(artifact_time(request) < timestamp for request in triggers)
        )

    def belongs_to_live_base_epoch(item: dict[str, Any]) -> bool:
        timestamp = evidence_time(item)
        return bool(timestamp and (not evidence_not_before or timestamp > evidence_not_before))

    current_review_round = [
        item
        for item in reviews
        if trusted_codex_actor(item, authors)
        and (
            str(item.get("state") or "").upper() != "DISMISSED"
            or finding_body(str(item.get("body") or ""))
        )
        and str(item.get("commit_id") or "").lower() == head_sha
        and review_at_or_after_latest_trigger(item)
    ]
    current_reviews = [
        item for item in current_review_round if review_after_latest_trigger(item)
    ]
    current_review_ids = {
        str(item.get("id"))
        for item in current_review_round
        if item.get("id") is not None
    }
    current_inline = [
        item
        for item in review_comments
        if trusted_codex_actor(item, authors)
        and (
            str(item.get("commit_id") or "").lower() == head_sha
            or str(item.get("pull_request_review_id")) in current_review_ids
        )
        and at_or_after_latest_trigger(item)
    ]
    current_issue_findings: list[dict[str, Any]] = []
    for item in issue_comments:
        body = str(item.get("body") or "")
        if not trusted_codex_actor(item, authors) or not finding_body(body):
            continue
        if latest_trigger is not None and not at_or_after_latest_trigger(item):
            continue
        if latest_trigger is None and not reviewed_head(body, head_sha):
            continue
        if explicitly_stale_review_marker(body, head_sha):
            # A delayed result explicitly bound to an older head cannot poison
            # the current review round. Malformed or mixed markers remain
            # fail-closed because they are not trustworthy stale bindings.
            continue
        current_issue_findings.append(item)

    blockers: list[str] = []
    for review in current_review_round:
        blockers.extend(review_blocking_reasons(review, head_sha))
    if current_inline:
        blockers.append(
            f"Codex left {len(current_inline)} inline finding(s) on the current head"
        )
    if current_issue_findings:
        blockers.append(
            f"Codex left {len(current_issue_findings)} finding-bearing issue comment(s) "
            "after the latest review request"
        )
    if files_truncated:
        blockers.append(
            "GitHub returned fewer changed-file rows than pull.changed_files; "
            "review classification is fail-closed"
        )

    clean_artifacts: list[dict[str, Any]] = []
    for review in current_reviews:
        state = str(review.get("state") or "").upper()
        body = str(review.get("body") or "")
        marker_is_consistent = not stale_or_invalid_review_marker(body, head_sha)
        if (
            (
                state == "APPROVED"
                and (not body.strip() or clean_body(body))
                and not finding_body(body)
                and marker_is_consistent
            )
            or (
                state == "COMMENTED"
                and not finding_body(body)
                and marker_is_consistent
                and recognized_commented_review_body(body, head_sha)
            )
        ) and belongs_to_live_base_epoch(review):
            clean_artifacts.append(review)
    for comment in issue_comments:
        body = str(comment.get("body") or "")
        if (
            trusted_codex_actor(comment, authors)
            and not stale_or_invalid_review_marker(body, head_sha)
            and reviewed_head(body, head_sha)
            and clean_body(body)
            and not finding_body(body)
            and after_latest_trigger(comment)
            and issue_clean_has_provenance(comment, body)
            and belongs_to_live_base_epoch(comment)
        ):
            clean_artifacts.append(comment)

    if latest_trigger and trigger_bound_to_full_head(latest_trigger, head_sha):
        reactions = latest_trigger.get(REACTIONS_FIELD, [])
        if not isinstance(reactions, list) or not all(
            isinstance(item, dict) for item in reactions
        ):
            raise GateError("trusted trigger reactions must be a list of objects")
        for reaction in reactions:
            created_at = reaction.get("created_at")
            if (
                reaction.get("content") == "+1"
                and trusted_codex_actor(reaction, authors)
                and isinstance(created_at, str)
                and created_at > trigger_time
                and belongs_to_live_base_epoch(reaction)
            ):
                reaction_artifact = dict(reaction)
                reaction_artifact["html_url"] = artifact_url(latest_trigger)
                clean_artifacts.append(reaction_artifact)

    ambiguous_issue_comments: list[dict[str, Any]] = []
    if clean_artifacts:
        latest_clean_time = max(evidence_time(item) for item in clean_artifacts)
        for comment in issue_comments:
            body = str(comment.get("body") or "")
            if (
                not trusted_codex_actor(comment, authors)
                or not at_or_after_latest_trigger(comment)
                or comment in clean_artifacts
                or comment in current_issue_findings
                or artifact_time(comment) < latest_clean_time
            ):
                continue
            if explicitly_stale_review_marker(body, head_sha):
                continue
            ambiguous_issue_comments.append(comment)
        if ambiguous_issue_comments:
            blockers.append(
                f"Codex left {len(ambiguous_issue_comments)} ambiguous issue comment(s) "
                "at or after the latest clean artifact"
            )

    if blockers:
        blocker_evidence = (
            current_inline
            or current_issue_findings
            or ambiguous_issue_comments
            or current_review_round
            or ([latest_trigger] if latest_trigger else [])
        )
        return GateResult(
            state="failure",
            classification="non-trivial",
            head_sha=head_sha,
            description=f"Codex review has findings for current head {head_sha[:10]}.",
            reasons=tuple(dict.fromkeys(blockers)),
            evidence_url=(
                artifact_url(blocker_evidence[0]) if blocker_evidence else None
            ),
        )
    if not clean_artifacts:
        request_was_observed = bool(latest_trigger or request_contexts)
        description = (
            f"Codex review is missing for current head {head_sha[:10]}."
            if request_was_observed
            else f"Codex review was not requested for head {head_sha[:10]}."
        )
        reason = (
            "no clean Codex artifact is explicitly bound to the live PR head "
            "and current base review epoch"
            if request_was_observed
            else "no automatic current-head artifact or trusted explicit review request "
            "produced clean evidence for the current base review epoch"
        )
        return GateResult(
            state="failure",
            classification="non-trivial",
            head_sha=head_sha,
            description=description,
            reasons=(reason,),
            evidence_url=artifact_url(latest_trigger) if latest_trigger else None,
        )

    latest = max(clean_artifacts, key=evidence_time)
    return GateResult(
        state="success",
        classification="non-trivial",
        head_sha=head_sha,
        description=f"Codex review is clean for current head {head_sha[:10]}.",
        reasons=(
            "clean current-head Codex artifact found in the live base review epoch "
            "with no current-head findings",
        ),
        evidence_url=artifact_url(latest),
    )


def live_pull(api: GitHubAPI, repository: str, pr_number: int) -> dict[str, Any]:
    base = f"/repos/{repo_path(repository)}"
    pull = api.request("GET", f"{base}/pulls/{pr_number}")
    if not isinstance(pull, dict):
        raise GateError("GitHub pull request response must be an object")
    live_ref = api.request("GET", f"{base}/git/ref/heads/{DEFAULT_BASE_REF}")
    live_object = live_ref.get("object") if isinstance(live_ref, dict) else None
    live_base_sha = (
        live_object.get("sha") if isinstance(live_object, dict) else None
    )
    if not isinstance(live_base_sha, str) or not re.fullmatch(
        r"[0-9a-fA-F]{40}", live_base_sha
    ):
        raise GateError("GitHub live base ref SHA is malformed")
    pull_base = pull.get("base")
    if not isinstance(pull_base, dict):
        raise GateError("GitHub pull request base identity is missing")
    resolved = dict(pull)
    resolved["base"] = {**pull_base, "sha": live_base_sha.lower()}
    return resolved


def pull_head(pull: dict[str, Any]) -> str:
    head = pull.get("head")
    sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise GateError("GitHub pull request head SHA is malformed")
    return sha.lower()


def pull_identity(pull: dict[str, Any], repository: str) -> PullIdentity:
    state = pull.get("state")
    head = pull.get("head")
    base = pull.get("base")
    head_repo = head.get("repo") if isinstance(head, dict) else None
    base_repo = base.get("repo") if isinstance(base, dict) else None
    head_repository = (
        head_repo.get("full_name") if isinstance(head_repo, dict) else None
    )
    base_repository = (
        base_repo.get("full_name") if isinstance(base_repo, dict) else None
    )
    base_ref = base.get("ref") if isinstance(base, dict) else None
    base_sha = base.get("sha") if isinstance(base, dict) else None
    if state != "open":
        raise GateError("pull request must remain open")
    if not isinstance(head_repository, str) or not head_repository:
        raise GateError("GitHub pull request head repository is missing")
    if (
        not isinstance(base_repository, str)
        or base_repository.casefold() != repository.casefold()
        or base_ref != DEFAULT_BASE_REF
    ):
        raise GateError(
            f"pull request must target {repository}:{DEFAULT_BASE_REF}"
        )
    if not isinstance(base_sha, str) or not re.fullmatch(
        r"[0-9a-fA-F]{40}", base_sha
    ):
        raise GateError("GitHub pull request base SHA is malformed")
    return PullIdentity(
        state=state,
        head_repository=head_repository,
        head_sha=pull_head(pull),
        base_repository=base_repository,
        base_ref=base_ref,
        base_sha=base_sha.lower(),
    )


def same_pull_identity(left: PullIdentity, right: PullIdentity) -> bool:
    return (
        left.state == right.state
        and left.head_repository.casefold() == right.head_repository.casefold()
        and left.head_sha == right.head_sha
        and left.base_repository.casefold() == right.base_repository.casefold()
        and left.base_ref == right.base_ref
        and left.base_sha == right.base_sha
    )


def live_payload(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    contract: dict[str, Any],
) -> dict[str, Any]:
    base = f"/repos/{repo_path(repository)}"
    pull = live_pull(api, repository, pr_number)
    if not same_pull_identity(pull_identity(pull, repository), expected_identity):
        raise GateError("pull request identity changed during review reconciliation")
    issue_comments = api.get_pages(f"{base}/issues/{pr_number}/comments")
    authors = accepted_authors(contract)
    enriched_issue_comments: list[dict[str, Any]] = []
    for comment in issue_comments:
        enriched = dict(comment)
        comment_id = comment.get("id")
        if (
            trusted_trigger(comment, authors)
            and trigger_bound_to_full_head(comment, expected_identity.head_sha)
            and isinstance(comment_id, int)
            and comment_id > 0
        ):
            enriched[REACTIONS_FIELD] = api.get_pages(
                f"{base}/issues/comments/{comment_id}/reactions"
            )
        enriched_issue_comments.append(enriched)
    files = api.get_pages(f"{base}/pulls/{pr_number}/files")
    reviews = api.get_pages(f"{base}/pulls/{pr_number}/reviews")
    review_comments = api.get_pages(f"{base}/pulls/{pr_number}/comments")
    final_pull = live_pull(api, repository, pr_number)
    if not same_pull_identity(
        pull_identity(final_pull, repository), expected_identity
    ):
        raise GateError(
            "pull request identity changed while collecting review artifacts"
        )
    return {
        "pull": final_pull,
        "files": files,
        "reviews": reviews,
        "review_comments": review_comments,
        "issue_comments": enriched_issue_comments,
    }


def post_status(
    api: GitHubAPI,
    repository: str,
    head_sha: str,
    state: str,
    context: str,
    description: str,
    target_url: str,
) -> None:
    payload: dict[str, Any] = {
        "state": state,
        "context": context,
        "description": description[:140],
    }
    if target_url:
        payload["target_url"] = target_url
    api.request(
        "POST",
        f"/repos/{repo_path(repository)}/statuses/{head_sha}",
        payload,
    )


def statuses_for_identity(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
) -> list[dict[str, Any]]:
    live_identity = pull_identity(live_pull(api, repository, pr_number), repository)
    if not same_pull_identity(live_identity, expected_identity):
        raise GateError("pull request identity changed before current status read")
    statuses = api.get_pages(
        f"/repos/{repo_path(repository)}/commits/"
        f"{expected_identity.head_sha}/statuses"
    )
    live_identity = pull_identity(live_pull(api, repository, pr_number), repository)
    if not same_pull_identity(live_identity, expected_identity):
        raise GateError("pull request identity changed during current status read")
    return statuses


def latest_status_for_identity(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    context: str,
) -> dict[str, Any] | None:
    return next(
        (
            status
            for status in statuses_for_identity(
                api, repository, pr_number, expected_identity
            )
            if status.get("context") == context
        ),
        None,
    )


def status_matches_result(
    status: dict[str, Any] | None,
    result: GateResult,
    context: str,
    status_app_id: int,
    expected_identity: PullIdentity,
) -> bool:
    return bool(
        trusted_status_writer(status, status_app_id)
        and status.get("context") == context
        and status.get("state") == result.state
        and status.get("description")
        == bound_status_description(result.description, expected_identity.base_sha)
    )


def trusted_status_writer(
    status: dict[str, Any] | None,
    status_app_id: int,
) -> bool:
    if status_app_id != GITHUB_ACTIONS_APP_ID:
        raise GateError(
            f"unsupported trusted status App id: {status_app_id}; "
            f"expected GitHub Actions App {GITHUB_ACTIONS_APP_ID}"
        )
    creator = status.get("creator") if status is not None else None
    return bool(
        status is not None
        and isinstance(creator, dict)
        and creator.get("type") == "Bot"
        and normalize_login(creator.get("login"))
        == normalize_login(GITHUB_ACTIONS_STATUS_CREATOR)
    )


def bound_status_description(description: str, base_sha: str) -> str:
    suffix = f"; base={base_sha}."
    prefix = description.strip().removesuffix(".")
    return f"{prefix[: 140 - len(suffix)].rstrip()}{suffix}"


def pending_status_description(expected_identity: PullIdentity) -> str:
    return bound_status_description(
        f"Reconciling Codex review for current head {expected_identity.head_sha[:10]}.",
        expected_identity.base_sha,
    )


def reconciliation_pending_status_description(
    expected_identity: PullIdentity,
) -> str:
    return bound_status_description(
        f"Codex review evidence changed for current head {expected_identity.head_sha[:10]}.",
        expected_identity.base_sha,
    )


def status_matches_pending(
    status: dict[str, Any] | None,
    context: str,
    expected_identity: PullIdentity,
    status_app_id: int,
) -> bool:
    return bool(
        trusted_status_writer(status, status_app_id)
        and status.get("context") == context
        and status.get("state") == "pending"
        and status.get("description")
        in {
            pending_status_description(expected_identity),
            reconciliation_pending_status_description(expected_identity),
        }
    )


def status_base_sha(status: dict[str, Any]) -> str:
    description = status.get("description")
    if not isinstance(description, str):
        return ""
    match = STATUS_BASE_RE.search(description)
    return match.group(1).lower() if match else ""


def live_base_evidence_cutoff(
    statuses: list[dict[str, Any]],
    context: str,
    expected_identity: PullIdentity,
    status_app_id: int,
) -> tuple[bool, str]:
    trusted = [
        status
        for status in statuses
        if status.get("context") == context
        and trusted_status_writer(status, status_app_id)
        and status_base_sha(status)
    ]
    if not trusted:
        return False, ""

    latest_base_sha = status_base_sha(trusted[0])
    if latest_base_sha != expected_identity.base_sha:
        return True, ""

    current_epoch: list[dict[str, Any]] = []
    for status in trusted:
        if status_base_sha(status) != expected_identity.base_sha:
            break
        current_epoch.append(status)
    current_base_pending_times = [
        created_at
        for status in current_epoch
        if status.get("state") == "pending"
        and status.get("description") == pending_status_description(expected_identity)
        and isinstance((created_at := status.get("created_at")), str)
        and created_at
    ]
    return False, min(current_base_pending_times, default="")


def prepare_live_base_evidence_epoch(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    context: str,
    target_url: str,
    status_app_id: int,
    *,
    establish_missing_epoch: bool,
) -> str:
    statuses = statuses_for_identity(
        api, repository, pr_number, expected_identity
    )
    base_drifted, cutoff = live_base_evidence_cutoff(
        statuses, context, expected_identity, status_app_id
    )
    if cutoff:
        return cutoff
    if not base_drifted and not establish_missing_epoch:
        return ""
    if not publish_pending(
        api,
        repository,
        pr_number,
        expected_identity,
        context,
        target_url,
    ):
        raise GateError("could not establish the live base review epoch")
    statuses = statuses_for_identity(
        api, repository, pr_number, expected_identity
    )
    base_drifted, cutoff = live_base_evidence_cutoff(
        statuses, context, expected_identity, status_app_id
    )
    if base_drifted or not cutoff:
        raise GateError("live base pending status did not expose a review epoch timestamp")
    return cutoff


def publish_fail_closed_for_bound_head(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    context: str,
    target_url: str,
    description: str,
    observed_pull: dict[str, Any] | None = None,
) -> bool:
    try:
        current_pull = observed_pull or live_pull(api, repository, pr_number)
        if pull_head(current_pull) != expected_identity.head_sha:
            return False
    except GateError:
        return False
    post_status(
        api,
        repository,
        expected_identity.head_sha,
        "failure",
        context,
        bound_status_description(description, expected_identity.base_sha),
        target_url,
    )
    return True


def publish_pending(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    context: str,
    target_url: str,
    description: str = "",
) -> bool:
    observed_pull: dict[str, Any] | None = None
    try:
        observed_pull = live_pull(api, repository, pr_number)
        live_identity = pull_identity(observed_pull, repository)
    except GateError:
        publish_fail_closed_for_bound_head(
            api,
            repository,
            pr_number,
            expected_identity,
            context,
            target_url,
            "PR identity changed before codex-review pending publication.",
            observed_pull,
        )
        return False
    if not same_pull_identity(live_identity, expected_identity):
        publish_fail_closed_for_bound_head(
            api,
            repository,
            pr_number,
            expected_identity,
            context,
            target_url,
            "PR identity changed before codex-review pending publication.",
            observed_pull,
        )
        return False
    post_status(
        api,
        repository,
        expected_identity.head_sha,
        "pending",
        context,
        description or pending_status_description(expected_identity),
        target_url,
    )
    return fail_closed_after_status_write(
        api,
        repository,
        pr_number,
        expected_identity,
        context,
        target_url,
    )


def fail_closed_after_status_write(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    context: str,
    target_url: str,
) -> bool:
    observed_pull: dict[str, Any] | None = None
    try:
        observed_pull = live_pull(api, repository, pr_number)
        live_identity = pull_identity(observed_pull, repository)
        if same_pull_identity(live_identity, expected_identity):
            return True
    except GateError:
        pass
    publish_fail_closed_for_bound_head(
        api,
        repository,
        pr_number,
        expected_identity,
        context,
        target_url,
        "PR identity changed after codex-review status write.",
        observed_pull,
    )
    return False


def publish_status(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    result: GateResult,
    context: str,
    target_url: str,
) -> bool:
    if not result.publish:
        return False
    if result.head_sha != expected_identity.head_sha:
        return False
    observed_pull: dict[str, Any] | None = None
    try:
        observed_pull = live_pull(api, repository, pr_number)
        live_identity = pull_identity(observed_pull, repository)
    except GateError:
        publish_fail_closed_for_bound_head(
            api,
            repository,
            pr_number,
            expected_identity,
            context,
            target_url,
            "PR identity changed before final codex-review status publication.",
            observed_pull,
        )
        return False
    if not same_pull_identity(live_identity, expected_identity):
        publish_fail_closed_for_bound_head(
            api,
            repository,
            pr_number,
            expected_identity,
            context,
            target_url,
            "PR identity changed before final codex-review status publication.",
            observed_pull,
        )
        return False
    post_status(
        api,
        repository,
        expected_identity.head_sha,
        result.state,
        context,
        bound_status_description(
            result.description, expected_identity.base_sha
        ),
        target_url,
    )
    return fail_closed_after_status_write(
        api,
        repository,
        pr_number,
        expected_identity,
        context,
        target_url,
    )


def github_event_payload() -> dict[str, Any]:
    raw_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    if not raw_path:
        return {}
    try:
        payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError("could not read the trusted GitHub event payload") from exc
    if not isinstance(payload, dict):
        raise GateError("trusted GitHub event payload must be an object")
    return payload


def evidence_event_requires_pending(
    contract: dict[str, Any],
    expected_head: str,
    *,
    event_name: str = "",
    event_payload: dict[str, Any] | None = None,
) -> bool:
    resolved_event_name = (
        event_name
        or os.environ.get("HARNESS_RECONCILE_REASON", "")
        or os.environ.get("GITHUB_EVENT_NAME", "")
    ).strip().casefold()
    if resolved_event_name != "issue_comment":
        return False
    payload = github_event_payload() if event_payload is None else event_payload
    if str(payload.get("action") or "").casefold() not in {
        "created",
        "edited",
        "deleted",
    }:
        return False
    comment = payload.get("comment")
    if not isinstance(comment, dict):
        return False
    authors = accepted_authors(contract)
    if trusted_codex_actor(comment, authors):
        return True
    return bool(
        trusted_trigger(comment, authors)
        and trigger_bound_to_full_head(comment, expected_head)
    )


def publish_evidence_pending_before_artifacts(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    context: str,
    target_url: str,
    status_app_id: int,
) -> bool:
    latest_status = latest_status_for_identity(
        api,
        repository,
        pr_number,
        expected_identity,
        context,
    )
    if status_matches_pending(
        latest_status, context, expected_identity, status_app_id
    ):
        return True
    return publish_pending(
        api,
        repository,
        pr_number,
        expected_identity,
        context,
        target_url,
        reconciliation_pending_status_description(expected_identity),
    )



def publish_status_if_changed(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    result: GateResult,
    context: str,
    target_url: str,
    status_app_id: int,
) -> bool:
    if not result.publish or result.head_sha != expected_identity.head_sha:
        return False
    latest_status = latest_status_for_identity(
        api,
        repository,
        pr_number,
        expected_identity,
        context,
    )
    if status_matches_result(
        latest_status, result, context, status_app_id, expected_identity
    ):
        return True
    pending_matches = status_matches_pending(
        latest_status, context, expected_identity, status_app_id
    )
    if not pending_matches and not publish_pending(
        api,
        repository,
        pr_number,
        expected_identity,
        context,
        target_url,
    ):
        return False
    return publish_status(
        api,
        repository,
        pr_number,
        expected_identity,
        result,
        context,
        target_url,
    )


def invalidate_status_after_exception(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    context: str,
    target_url: str,
) -> bool:
    result = GateResult(
        state="failure",
        classification="gate-error",
        head_sha=expected_identity.head_sha,
        description=(
            "Codex review gate failed closed for current head "
            f"{expected_identity.head_sha[:10]}."
        ),
        reasons=("gate evaluation or publication raised an exception",),
    )
    try:
        latest_status = latest_status_for_identity(
            api,
            repository,
            pr_number,
            expected_identity,
            context,
        )
    except GateError:
        return publish_fail_closed_for_bound_head(
            api,
            repository,
            pr_number,
            expected_identity,
            context,
            target_url,
            result.description,
        )
    if status_matches_result(
        latest_status,
        result,
        context,
        GITHUB_ACTIONS_APP_ID,
        expected_identity,
    ):
        return True
    return publish_status(
        api,
        repository,
        pr_number,
        expected_identity,
        result,
        context,
        target_url,
    )


def parse_pr_number(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise GateError("PR number must be an integer") from exc
    if number < 1:
        raise GateError("PR number must be positive")
    return number


def require_expected_base(identity: PullIdentity, expected_base: str) -> None:
    if expected_base and expected_base.lower() != identity.base_sha:
        raise GateError("live PR base changed after the trusted policy checkout")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--pr-number", default=os.environ.get("PR_NUMBER", ""))
    parser.add_argument(
        "--expected-head", default=os.environ.get("EXPECTED_HEAD_SHA", "")
    )
    parser.add_argument(
        "--expected-base", default=os.environ.get("EXPECTED_BASE_SHA", "")
    )
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--bootstrap-control-plane-review", action="store_true")
    parser.add_argument("--context", default=os.environ.get("REVIEW_STATUS_CONTEXT", ""))
    parser.add_argument("--target-url", default=os.environ.get("GITHUB_RUN_URL", ""))
    args = parser.parse_args()

    api: GitHubAPI | None = None
    pr_number: int | None = None
    initial_identity: PullIdentity | None = None
    status_app_id: int | None = None
    context = args.context or DEFAULT_CONTEXT
    try:
        if args.bootstrap_control_plane_review and (
            not args.fixture or args.publish
        ):
            raise GateError(
                "--bootstrap-control-plane-review requires --fixture and forbids --publish"
            )
        initial_pull: dict[str, Any] | None = None
        if not args.fixture:
            if not args.repository:
                raise GateError("--repository or GITHUB_REPOSITORY is required")
            pr_number = parse_pr_number(args.pr_number)
            api = GitHubAPI(
                os.environ.get("GITHUB_TOKEN", ""),
                os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            )
            initial_pull = live_pull(api, args.repository, pr_number)
            initial_identity = pull_identity(initial_pull, args.repository)
            require_expected_base(initial_identity, args.expected_base)

        # Resolve the live status identity before parsing repository policy so a
        # malformed contract cannot leave an earlier green result authoritative.
        contract = load_contract()
        config = review_contract(contract)
        raw_status_app_id = config.get("status_app_id")
        if not isinstance(raw_status_app_id, int) or isinstance(
            raw_status_app_id, bool
        ):
            raise GateError("codex_review.status_app_id must be an integer")
        status_app_id = raw_status_app_id
        context = args.context or str(config.get("required_check") or DEFAULT_CONTEXT)
        evidence_not_before = ""
        reconcile_reason = os.environ.get(
            "HARNESS_RECONCILE_REASON", ""
        ).strip().casefold()
        if (
            args.publish
            and initial_identity is not None
            and (
                not args.expected_head
                or args.expected_head.lower() == initial_identity.head_sha
            )
        ):
            is_evidence_event = evidence_event_requires_pending(
                contract,
                initial_identity.head_sha,
                event_name=reconcile_reason,
            )
            if reconcile_reason == "issue_comment" and not is_evidence_event:
                print("Ignoring unrelated issue_comment reconciliation event.")
                return 0
            evidence_not_before = prepare_live_base_evidence_epoch(
                api,
                args.repository,
                pr_number,
                initial_identity,
                context,
                args.target_url,
                status_app_id,
                establish_missing_epoch=(
                    reconcile_reason == "default-branch-push"
                ),
            )
            if is_evidence_event and not publish_evidence_pending_before_artifacts(
                api,
                args.repository,
                pr_number,
                initial_identity,
                context,
                args.target_url,
                status_app_id,
            ):
                raise GateError(
                    "could not invalidate prior status before reading changed evidence"
                )
        if args.fixture:
            payload = json.loads(args.fixture.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise GateError("fixture must contain a JSON object")
        else:
            assert api is not None
            assert pr_number is not None
            assert initial_pull is not None
            assert initial_identity is not None
            initial_head = initial_identity.head_sha
            if args.expected_head and args.expected_head.lower() != initial_head:
                payload = {
                    "pull": initial_pull,
                    "files": [],
                    "reviews": [],
                    "review_comments": [],
                    "issue_comments": [],
                }
            else:
                payload = live_payload(
                    api, args.repository, pr_number, initial_identity, contract
                )
        result = evaluate(
            payload,
            contract,
            args.expected_head,
            args.bootstrap_control_plane_review,
            evidence_not_before=evidence_not_before,
        )
        if args.publish:
            if args.fixture:
                raise GateError("--publish cannot be used with --fixture")
            assert api is not None
            assert pr_number is not None
            if result.publish:
                # Re-read every artifact before deciding whether the current status
                # is already the exact final result. Serialized workflow concurrency
                # plus this second evaluation keeps late findings from being skipped
                # or overwritten by an older run.
                result = evaluate(
                    live_payload(
                        api,
                        args.repository,
                        pr_number,
                        initial_identity,
                        contract,
                    ),
                    contract,
                    args.expected_head,
                    evidence_not_before=evidence_not_before,
                )
            if result.publish and not publish_status_if_changed(
                api,
                args.repository,
                pr_number,
                initial_identity,
                result,
                context,
                args.target_url,
                status_app_id,
            ):
                result = GateResult(
                    state="failure",
                    classification="stale-writer",
                    head_sha=result.head_sha,
                    description="PR identity changed before the final review status write.",
                    reasons=("final status was not published to a changed PR identity",),
                )
    except Exception as exc:
        print(f"check_codex_review: {exc}", file=sys.stderr)
        if (
            args.publish
            and api is not None
            and pr_number is not None
            and initial_identity is not None
        ):
            try:
                invalidated = invalidate_status_after_exception(
                    api,
                    args.repository,
                    pr_number,
                    initial_identity,
                    context,
                    args.target_url,
                )
                if not invalidated:
                    print(
                        "check_codex_review: could not invalidate status because "
                        "the live PR identity changed",
                        file=sys.stderr,
                    )
            except Exception as invalidation_exc:
                print(
                    "check_codex_review: failed to invalidate prior status: "
                    f"{invalidation_exc}",
                    file=sys.stderr,
                )
        return 2

    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if not result.publish or result.state == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
