#!/usr/bin/env python3
"""Evaluate Codex review evidence for the live PR head and publish a status.

The trusted default-branch workflow calls this script for PR, review, and
comment events. It never executes code from the pull-request branch. A
non-trivial PR passes only when a Codex artifact is explicitly bound to the
current head SHA and no current-head Codex finding is present.
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
}
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
    "golden",
    "prd",
    "prds",
    "release",
    "releases",
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
    r"^\s*(?:\*\*)?Head SHA(?:\*\*)?:\s*`?([0-9a-f]{40})`?\s*$",
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
ALLOWED_CLEAN_CELEBRATIONS = (
    "Delightful!",
    "Hooray!",
    "Nice work!",
    "Bravo.",
    "Swish!",
    "Breezy!",
    "Keep it up!",
    "You're on a roll.",
    "Chef's kiss.",
    "Can't wait for the next one!",
    "Another round soon, please!",
    "Already looking forward to the next diff.",
    "More of your lovely PRs please.",
    "What shall we delve into next?",
    ":+1:",
    ":rocket:",
    ":tada:",
)
CLEAN_CELEBRATION_PATTERN = "(?:" + "|".join(
    re.escape(value) for value in ALLOWED_CLEAN_CELEBRATIONS
) + ")"
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
    if login.endswith("[bot]"):
        login = login[:-5]
    return login


def actor_login(item: dict[str, Any]) -> str:
    user = item.get("user")
    if isinstance(user, dict):
        return normalize_login(user.get("login"))
    return ""


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


def clean_body(body: str) -> bool:
    return bool(
        CLEAN_BODY_RE.fullmatch(body)
        or STANDARD_FOOTER_CLEAN_BODY_RE.fullmatch(body)
        or FULL_CLEAN_ISSUE_COMMENT_RE.fullmatch(body)
    )


def finding_body(body: str) -> bool:
    return bool(FINDING_RE.search(body))


def recognized_commented_review_body(body: str, head_sha: str) -> bool:
    if INCOMPLETE_REVIEW_RE.search(body):
        return False
    return clean_body(body)


def trivial_path(path: str, review_required_patterns: tuple[str, ...]) -> bool:
    if any(fnmatch.fnmatchcase(path, pattern) for pattern in review_required_patterns):
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
        tuple(filter(None, re.split(r"[-_.]+", component)))
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


def evaluate(
    payload: dict[str, Any],
    contract: dict[str, Any],
    expected_head: str = "",
    bootstrap_control_plane_review: bool = False,
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

    def issue_clean_has_provenance(item: dict[str, Any], body: str) -> bool:
        if not reviewed_head(body, head_sha):
            return False
        if STANDARD_FOOTER_CLEAN_BODY_RE.fullmatch(body):
            return True
        timestamp = artifact_time(item)
        return bool(
            timestamp
            and any(artifact_time(request) < timestamp for request in triggers)
        )

    current_review_round = [
        item
        for item in reviews
        if actor_login(item) in authors
        and str(item.get("commit_id") or "").lower() == head_sha
        and at_or_after_latest_trigger(item)
    ]
    current_reviews = [
        item for item in current_review_round if after_latest_trigger(item)
    ]
    current_inline = [
        item
        for item in review_comments
        if actor_login(item) in authors
        and str(item.get("commit_id") or "").lower() == head_sha
        and at_or_after_latest_trigger(item)
    ]
    current_issue_findings: list[dict[str, Any]] = []
    for item in issue_comments:
        body = str(item.get("body") or "")
        if actor_login(item) not in authors or not finding_body(body):
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
        state = str(review.get("state") or "").upper()
        body = str(review.get("body") or "")
        if state not in {"APPROVED", "COMMENTED", "CHANGES_REQUESTED"}:
            blockers.append(
                f"Codex review has unsupported current-head state: {state or 'MISSING'}"
            )
        if state == "CHANGES_REQUESTED":
            blockers.append("Codex requested changes on the current head")
        if finding_body(body):
            blockers.append("Codex review body contains a current-head finding")
        if stale_or_invalid_review_marker(body, head_sha):
            blockers.append(
                "Codex review body contains a stale or invalid reviewed-commit marker"
            )
        if state == "APPROVED" and body.strip() and not clean_body(body):
            blockers.append(
                "Codex APPROVED review contains non-clean text for the current head"
            )
        if state == "COMMENTED" and not recognized_commented_review_body(
            body, head_sha
        ):
            blockers.append(
                "Codex COMMENTED review is incomplete or unrecognized for the current head"
            )
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
            state == "APPROVED"
            and (not body.strip() or clean_body(body))
            and not finding_body(body)
            and marker_is_consistent
        ) or (
            state == "COMMENTED"
            and not finding_body(body)
            and marker_is_consistent
            and recognized_commented_review_body(body, head_sha)
        ):
            clean_artifacts.append(review)
    for comment in issue_comments:
        body = str(comment.get("body") or "")
        if (
            actor_login(comment) in authors
            and not stale_or_invalid_review_marker(body, head_sha)
            and reviewed_head(body, head_sha)
            and clean_body(body)
            and not finding_body(body)
            and after_latest_trigger(comment)
            and issue_clean_has_provenance(comment, body)
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
                and actor_login(reaction) in authors
                and isinstance(created_at, str)
                and created_at > trigger_time
            ):
                reaction_artifact = dict(reaction)
                reaction_artifact["html_url"] = artifact_url(latest_trigger)
                clean_artifacts.append(reaction_artifact)

    ambiguous_issue_comments: list[dict[str, Any]] = []
    if clean_artifacts:
        latest_clean_time = max(artifact_time(item) for item in clean_artifacts)
        for comment in issue_comments:
            body = str(comment.get("body") or "")
            if (
                actor_login(comment) not in authors
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
            "no clean Codex artifact is explicitly bound to the live PR head"
            if request_was_observed
            else "no automatic current-head artifact or trusted explicit review request "
            "produced clean evidence"
        )
        return GateResult(
            state="failure",
            classification="non-trivial",
            head_sha=head_sha,
            description=description,
            reasons=(reason,),
            evidence_url=artifact_url(latest_trigger) if latest_trigger else None,
        )

    latest = max(clean_artifacts, key=artifact_time)
    return GateResult(
        state="success",
        classification="non-trivial",
        head_sha=head_sha,
        description=f"Codex review is clean for current head {head_sha[:10]}.",
        reasons=("clean current-head Codex artifact found with no current-head findings",),
        evidence_url=artifact_url(latest),
    )


def live_pull(api: GitHubAPI, repository: str, pr_number: int) -> dict[str, Any]:
    base = f"/repos/{repo_path(repository)}"
    pull = api.request("GET", f"{base}/pulls/{pr_number}")
    if not isinstance(pull, dict):
        raise GateError("GitHub pull request response must be an object")
    return pull


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
    return {
        "pull": pull,
        "files": api.get_pages(f"{base}/pulls/{pr_number}/files"),
        "reviews": api.get_pages(f"{base}/pulls/{pr_number}/reviews"),
        "review_comments": api.get_pages(f"{base}/pulls/{pr_number}/comments"),
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


def latest_status_for_identity(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    context: str,
) -> dict[str, Any] | None:
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
    return next(
        (status for status in statuses if status.get("context") == context),
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
        and status.get("description") == pending_status_description(expected_identity)
    )


def publish_pending(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    context: str,
    target_url: str,
) -> bool:
    live_identity = pull_identity(live_pull(api, repository, pr_number), repository)
    if not same_pull_identity(live_identity, expected_identity):
        return False
    post_status(
        api,
        repository,
        expected_identity.head_sha,
        "pending",
        context,
        pending_status_description(expected_identity),
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
    try:
        live_identity = pull_identity(live_pull(api, repository, pr_number), repository)
        if same_pull_identity(live_identity, expected_identity):
            return True
    except GateError:
        pass
    post_status(
        api,
        repository,
        expected_identity.head_sha,
        "failure",
        context,
        bound_status_description(
            "PR identity changed after codex-review status write.",
            expected_identity.base_sha,
        ),
        target_url,
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
    live_identity = pull_identity(live_pull(api, repository, pr_number), repository)
    if not same_pull_identity(live_identity, expected_identity):
        return False
    post_status(
        api,
        repository,
        result.head_sha,
        result.state,
        context,
        bound_status_description(result.description, expected_identity.base_sha),
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


def publish_pending_before_evaluation(
    api: GitHubAPI,
    repository: str,
    pr_number: int,
    expected_identity: PullIdentity,
    context: str,
    target_url: str,
    status_app_id: int,
    *,
    force: bool,
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
    current_base_suffix = f"; base={expected_identity.base_sha}."
    if (
        not force
        and trusted_status_writer(latest_status, status_app_id)
        and latest_status.get("context") == context
        and latest_status.get("state") in {"success", "failure"}
        and str(latest_status.get("description") or "").endswith(current_base_suffix)
    ):
        return True
    return publish_pending(
        api,
        repository,
        pr_number,
        expected_identity,
        context,
        target_url,
    )


def evidence_event_requires_pending(contract: dict[str, Any]) -> bool:
    if os.environ.get("HARNESS_EVIDENCE_EVENT") == "1":
        return True
    if os.environ.get("HARNESS_EVENT_NAME") != "issue_comment":
        return False

    authors = accepted_authors(contract)
    author = os.environ.get("HARNESS_COMMENT_AUTHOR", "")
    if normalize_login(author) in authors:
        return True
    return bool(
        normalize_login(author)
        and normalize_login(author) not in authors
        and os.environ.get("HARNESS_COMMENT_ASSOCIATION", "").upper()
        in TRUSTED_TRIGGER_ASSOCIATIONS
        and TRIGGER_RE.search(os.environ.get("HARNESS_COMMENT_BODY", ""))
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
    latest_status = latest_status_for_identity(
        api,
        repository,
        pr_number,
        expected_identity,
        context,
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
        contract = load_contract()
        if args.bootstrap_control_plane_review and (
            not args.fixture or args.publish
        ):
            raise GateError(
                "--bootstrap-control-plane-review requires --fixture and forbids --publish"
            )
        config = review_contract(contract)
        raw_status_app_id = config.get("status_app_id")
        if not isinstance(raw_status_app_id, int) or isinstance(
            raw_status_app_id, bool
        ):
            raise GateError("codex_review.status_app_id must be an integer")
        status_app_id = raw_status_app_id
        context = args.context or str(config.get("required_check") or DEFAULT_CONTEXT)
        if args.fixture:
            payload = json.loads(args.fixture.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise GateError("fixture must contain a JSON object")
        else:
            if not args.repository:
                raise GateError("--repository or GITHUB_REPOSITORY is required")
            pr_number = parse_pr_number(args.pr_number)
            api = GitHubAPI(
                os.environ.get("GITHUB_TOKEN", ""),
                os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            )
            initial_pull = live_pull(api, args.repository, pr_number)
            initial_identity = pull_identity(initial_pull, args.repository)
            initial_head = initial_identity.head_sha
            require_expected_base(initial_identity, args.expected_base)
            if args.expected_head and args.expected_head.lower() != initial_head:
                payload = {
                    "pull": initial_pull,
                    "files": [],
                    "reviews": [],
                    "review_comments": [],
                    "issue_comments": [],
                }
            else:
                if args.publish and not publish_pending_before_evaluation(
                    api,
                    args.repository,
                    pr_number,
                    initial_identity,
                    context,
                    args.target_url,
                    status_app_id,
                    force=evidence_event_requires_pending(contract),
                ):
                    raise GateError(
                        "pull request identity changed while marking review pending"
                    )
                payload = live_payload(
                    api, args.repository, pr_number, initial_identity, contract
                )
        result = evaluate(
            payload,
            contract,
            args.expected_head,
            args.bootstrap_control_plane_review,
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
                    publish=False,
                )
    except Exception as exc:
        print(f"check_codex_review: {exc}", file=sys.stderr)
        if (
            args.publish
            and api is not None
            and pr_number is not None
            and initial_identity is not None
            and status_app_id is not None
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
