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
import unicodedata
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
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
MAX_GOVERNANCE_INSPECTION_BYTES = 4 * 1024 * 1024
EXECUTION_PLAN_POLICY = {
    "active_plan_directory": "docs/exec-plans/active",
    "pending_establishment": {
        "required_active_plan_count": 1,
        "nested_active_plans": "forbidden",
        "ordinary_product_work": "forbidden_until_active_baseline",
    },
}
CONTRACT_REQUIRED_KEYS = frozenset(
    {
        "contract_version",
        "repository",
        "repository_id",
        "default_branch",
        "verifier",
        "execution_plan_policy",
        "control_plane_paths",
        "audit_state_paths",
        "required_files",
        "required_checks",
        "revalidation_groups",
        "review",
        "github_policy",
        "platform_gate",
        "publisher_validation",
        "baseline_receipt",
        "task_record_policy",
    }
)
CONTRACT_OPTIONAL_KEYS = frozenset(
    {
        "active_plan_required_sections",
        "active_plan_required_fields",
        "active_plan_required_tables",
    }
)
LEGACY_REVIEW_WORKFLOW_NAMES = frozenset(
    {
        f"codex-review-{suffix}.{extension}"
        for suffix in ("gate", "signal", "heart" + "beat")
        for extension in ("yml", "yaml")
    }
)
LEGACY_RUNTIME_EXACT_PATHS = frozenset(
    {
        "scripts/check_codex_review.py",
        "scripts/check_merge_receipt.py",
        "scripts/check_loop_checkpoints.py",
    }
)
LEGACY_REVIEW_WORKFLOW_MARKERS = (
    "statuses: write",
    "check_codex_review.py",
    "check_merge_receipt.py",
    "createcommitstatus",
    "create-" + "check-run",
    "/status" + "es/",
    "repository-self-" + "supervised",
    "repository_self_" + "supervised",
)
LEGACY_GOVERNANCE_PATHS = (
    "docs/doc-sync-rules.json",
    "docs/governance/checkpoint-ci-gate.md",
)
LEGACY_RUNTIME_KNOWN_SHA256 = {
    "docs/doc-sync-rules.json": (
        "66802b96f8cae40a4ee873779b2b6baf0d27a77d32a1f063c842f0993090f244"
    ),
    "docs/governance/checkpoint-ci-gate.md": (
        "10299c7d5819ba3e4458440161445793cf3dc45200868c80c029813fd907449a"
    ),
}
V3_ARTIFACT_MARKERS = {
    "AGENTS.md": ("$manage-repo-harness",),
    "scripts/check_harness.py": (
        "repo-harness-verifier-v3.1",
        "repo-harness-v3",
    ),
    "docs/governance/harness.md": ("repo-harness-v3",),
    "docs/exec-plans/template.md": (
        "## Delegation Audit",
        "Revalidation groups:",
        "baseline-receipt cleanup PR",
    ),
    "docs/index.md": (
        ".harness/repo-contract.json",
        "governance/harness.md",
    ),
    "docs/INDEX.md": (
        ".harness/repo-contract.json",
        "governance/harness.md",
    ),
    ".github/pull_request_template.md": (
        "Plan lifecycle: `product-same-PR` | `harness-post-merge-cleanup`",
        "Source-isolated publisher App id:",
        "## Current-head Review",
    ),
    ".github/PULL_REQUEST_TEMPLATE.md": (
        "Plan lifecycle: `product-same-PR` | `harness-post-merge-cleanup`",
        "Source-isolated publisher App id:",
        "## Current-head Review",
    ),
}
V3_ARTIFACT_EXACT_PATHS = (RECEIPT_PATH,)
LEGACY_GOVERNANCE_MARKERS = (
    "codex-review-gate",
    "codex-review-signal",
    "codex-review-" + "heart" + "beat",
    "check_codex_review.py",
    "check_merge_receipt.py",
    "repository-self-" + "supervised",
    "repository_self_" + "supervised",
    "trusted-owner-merge-executor",
    "trusted_owner_serialized",
    "fenced lease",
    "fenced_lease",
)
PLACEHOLDER_VALUE_RE = re.compile(
    r"^(?:tbd|todo|pending|unknown|n/?a|none|not[_ -]?applicable|"
    r"placeholder|fill(?: me)? in|<[^>]*>|\{\{[^}]*\}\})$",
    re.IGNORECASE,
)
NOT_APPLICABLE_VALUE_RE = re.compile(
    r"^not[_ -]?applicable$",
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
COMMONMARK_BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|"
    "colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|"
    "footer|form|frame|frameset|h1|h2|h3|h4|h5|h6|head|header|hr|html|"
    "iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|"
    "option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|"
    "title|tr|track|ul"
)
VOID_HTML_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
VISIBLE_INLINE_HTML_TAGS = frozenset(
    {
        "b",
        "br",
        "code",
        "del",
        "em",
        "i",
        "kbd",
        "mark",
        "s",
        "small",
        "strong",
        "sub",
        "sup",
        "u",
        "wbr",
    }
)
RAW_HTML_BLOCK_START_RE = re.compile(
    rf"^[ \t]{{0,3}}(?:"
    rf"</?(?:script|pre|style|textarea)(?=[ \t>/]|$)|"
    rf"</?(?:{COMMONMARK_BLOCK_TAGS})(?=[ \t>/]|$)|"
    r"<\?|<![A-Z]|<!\[CDATA\[|"
    r"</?[A-Za-z][A-Za-z0-9-]*(?:[ \t]+[^<>]*)?/?[ \t]*>[ \t]*$"
    r")",
    re.IGNORECASE,
)
COMMONMARK_AUTOLINK_RE = re.compile(
    r"<(?P<target>"
    r"(?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\x00-\x20]*)"
    r"|(?:[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)"
    r")>"
)
COMMONMARK_CODE_SPAN_RE = re.compile(
    r"(?<!`)(?P<ticks>`+)(?!`)(?P<body>.*?)(?<!`)(?P=ticks)(?!`)",
    re.DOTALL,
)


class HarnessError(RuntimeError):
    pass


class _VisibleInlineTextParser(HTMLParser):
    """Collect the text a simple inline HTML wrapper contributes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_stack: list[tuple[str, bool]] = []
        self.hidden_depth = 0

    @staticmethod
    def _is_hidden(
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> bool:
        if tag.casefold() in {"script", "style", "template"}:
            return True
        normalized = {
            name.casefold(): (value or "").casefold()
            for name, value in attrs
        }
        if "hidden" in normalized or normalized.get("aria-hidden") == "true":
            return True
        style = re.sub(r"\s+", "", normalized.get("style", ""))
        if "display:none" in style or "visibility:hidden" in style:
            return True
        if normalized:
            raise HarnessError(
                "inline HTML attributes are not allowed in concrete plan evidence"
            )
        return False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        folded = tag.casefold()
        if folded not in VISIBLE_INLINE_HTML_TAGS:
            raise HarnessError(
                f"unsupported inline HTML tag in concrete plan evidence: {tag}"
            )
        if folded in VOID_HTML_TAGS:
            self._is_hidden(tag, attrs)
            return
        hidden = self.hidden_depth > 0 or self._is_hidden(tag, attrs)
        self.hidden_stack.append((folded, hidden))
        if hidden:
            self.hidden_depth += 1

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        folded = tag.casefold()
        if folded not in VISIBLE_INLINE_HTML_TAGS:
            raise HarnessError(
                f"unsupported inline HTML tag in concrete plan evidence: {tag}"
            )
        if folded not in VOID_HTML_TAGS:
            raise HarnessError(
                "non-void self-closing inline HTML is not allowed in "
                f"concrete plan evidence: {tag}"
            )
        self._is_hidden(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag not in VISIBLE_INLINE_HTML_TAGS:
            raise HarnessError(
                f"unsupported inline HTML tag in concrete plan evidence: {tag}"
            )
        matching = next(
            (
                index
                for index in range(len(self.hidden_stack) - 1, -1, -1)
                if self.hidden_stack[index][0] == tag
            ),
            None,
        )
        if matching is None:
            return
        removed = self.hidden_stack[matching:]
        del self.hidden_stack[matching:]
        self.hidden_depth -= sum(1 for _, hidden in removed if hidden)

    def handle_data(self, data: str) -> None:
        if self.hidden_depth == 0:
            self.parts.append(data)


class DiffEntry(NamedTuple):
    status: str
    paths: tuple[str, ...]


class GitTreeEntry(NamedTuple):
    mode: str
    object_type: str
    object_id: str
    path: bytes


class FilesystemEntry(NamedTuple):
    kind: str
    mode: int
    size: int
    mtime_ns: int
    device: int
    inode: int


class ActivePlanTableRequirement(NamedTuple):
    header: tuple[str, ...]
    min_rows: int


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


def strict_json_loads(text: str, label: str) -> Any:
    def reject_duplicate_keys(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise HarnessError(f"duplicate JSON key in {label}: {key}")
            value[key] = item
        return value

    def reject_nonstandard_constant(token: str) -> Any:
        raise HarnessError(
            f"non-standard JSON constant in {label}: {token}"
        )

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonstandard_constant,
        )
    except json.JSONDecodeError as exc:
        raise HarnessError(f"cannot read valid JSON: {label}: {exc}") from exc


def load_repo_json(
    root: Path,
    relative: str,
    *,
    max_bytes: int = MAX_CONTRACT_BYTES,
) -> dict[str, Any]:
    data = strict_json_loads(
        read_repo_regular_text(
            root,
            relative,
            max_bytes=max_bytes,
        ),
        relative,
    )
    if not isinstance(data, dict):
        raise HarnessError(f"JSON root must be an object: {relative}")
    return data


def legacy_runtime_paths(root: Path) -> tuple[str, ...]:
    found: set[str] = set()
    for relative in LEGACY_RUNTIME_EXACT_PATHS:
        path = root / relative
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise HarnessError(
                f"cannot inspect legacy runtime path {relative}: {exc}"
            ) from exc
        found.add(relative)

    workflow_relative = ".github/workflows"
    workflow_directory = root
    try:
        for component in safe_relative_parts(workflow_relative):
            workflow_directory /= component
            metadata = os.lstat(workflow_directory)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(
                metadata.st_mode
            ):
                raise HarnessError(
                    ".github/workflows must be a real in-repository directory"
                )
    except FileNotFoundError:
        workflow_directory = None
    except OSError as exc:
        raise HarnessError(f"cannot inspect .github/workflows: {exc}") from exc

    if workflow_directory is not None:
        try:
            workflow_names = sorted(os.listdir(workflow_directory))
        except OSError as exc:
            raise HarnessError(f"cannot enumerate .github/workflows: {exc}") from exc
        for name in workflow_names:
            if not name.casefold().endswith((".yml", ".yaml")):
                continue
            relative = f"{workflow_relative}/{name}"
            if name.casefold() in LEGACY_REVIEW_WORKFLOW_NAMES:
                found.add(relative)
                continue
            text = read_repo_regular_text(
                root,
                relative,
                max_bytes=MAX_GOVERNANCE_INSPECTION_BYTES,
            ).casefold()
            if any(marker in text for marker in LEGACY_REVIEW_WORKFLOW_MARKERS):
                found.add(relative)

    for relative in LEGACY_GOVERNANCE_PATHS:
        path = root / relative
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise HarnessError(
                f"cannot inspect legacy governance path {relative}: {exc}"
            ) from exc
        if sha256_repo_file(
            root,
            relative,
            max_bytes=MAX_GOVERNANCE_INSPECTION_BYTES,
        ) == LEGACY_RUNTIME_KNOWN_SHA256.get(relative):
            found.add(relative)
            continue
        text = read_repo_regular_text(
            root,
            relative,
            max_bytes=MAX_GOVERNANCE_INSPECTION_BYTES,
        ).casefold()
        if any(marker in text for marker in LEGACY_GOVERNANCE_MARKERS):
            found.add(relative)
    return tuple(sorted(found))


def repo_path_has_exact_case(root: Path, relative: str) -> bool:
    current = root
    parts = Path(relative).parts
    for index, part in enumerate(parts):
        try:
            with os.scandir(current) as entries:
                match = next((entry for entry in entries if entry.name == part), None)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise HarnessError(
                f"cannot inspect repository path casing for {relative}: {exc}"
            ) from exc
        if match is None:
            return False
        if index < len(parts) - 1 and not match.is_dir(follow_symlinks=False):
            return False
        current = current / part
    return True


def v3_artifact_paths(root: Path) -> tuple[str, ...]:
    found: set[str] = set()
    for relative in V3_ARTIFACT_EXACT_PATHS:
        if not repo_path_has_exact_case(root, relative):
            continue
        path = root / relative
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise HarnessError(
                f"cannot inspect v3 artifact path {relative}: {exc}"
            ) from exc
        found.add(relative)
    for relative, markers in V3_ARTIFACT_MARKERS.items():
        if not repo_path_has_exact_case(root, relative):
            continue
        if not is_repo_regular_file(
            root,
            relative,
            max_bytes=MAX_GOVERNANCE_INSPECTION_BYTES,
        ):
            continue
        text = read_repo_regular_text(
            root,
            relative,
            max_bytes=MAX_GOVERNANCE_INSPECTION_BYTES,
        )
        if all(marker in text for marker in markers):
            found.add(relative)
    return tuple(sorted(found))


def validate_no_legacy_runtime(root: Path) -> None:
    legacy = legacy_runtime_paths(root)
    if legacy:
        raise HarnessError(
            "v3 tree retains legacy Harness runtime paths: "
            + ", ".join(legacy)
        )


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


def active_plan_required_sections(contract: dict[str, Any]) -> tuple[str, ...]:
    value = contract.get("active_plan_required_sections", [])
    if not isinstance(value, list):
        raise HarnessError("active_plan_required_sections must be a list")
    sections: list[str] = []
    for heading in value:
        if (
            not isinstance(heading, str)
            or heading != heading.strip()
            or re.fullmatch(r"## [^\r\n]+", heading) is None
            or heading in PLAN_SECTIONS
        ):
            raise HarnessError(
                "active_plan_required_sections entries must be additional "
                "level-two Markdown headings"
            )
        sections.append(heading)
    if len(sections) != len(set(sections)):
        raise HarnessError("active_plan_required_sections must be unique")
    return tuple(sections)


def active_plan_required_fields(
    contract: dict[str, Any],
) -> dict[str, tuple[str, ...]]:
    value = contract.get("active_plan_required_fields", {})
    if not isinstance(value, dict):
        raise HarnessError("active_plan_required_fields must be an object")
    allowed_sections = set(PLAN_SECTIONS) | set(
        active_plan_required_sections(contract)
    )
    requirements: dict[str, tuple[str, ...]] = {}
    for section, labels in value.items():
        if section not in allowed_sections:
            raise HarnessError(
                "active_plan_required_fields references an undeclared section"
            )
        if not isinstance(labels, list) or not labels:
            raise HarnessError(
                "active_plan_required_fields entries must be non-empty lists"
            )
        normalized: list[str] = []
        for label in labels:
            if (
                not isinstance(label, str)
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,80}", label) is None
            ):
                raise HarnessError(
                    "active_plan_required_fields labels must be bounded field names"
                )
            normalized.append(label)
        if len(normalized) != len(set(normalized)):
            raise HarnessError("active_plan_required_fields labels must be unique")
        requirements[section] = tuple(normalized)
    return requirements


def active_plan_required_tables(
    contract: dict[str, Any],
) -> dict[str, ActivePlanTableRequirement]:
    value = contract.get("active_plan_required_tables", {})
    if not isinstance(value, dict):
        raise HarnessError("active_plan_required_tables must be an object")
    allowed_sections = set(PLAN_SECTIONS) | set(
        active_plan_required_sections(contract)
    )
    requirements: dict[str, ActivePlanTableRequirement] = {}
    for section, rule in value.items():
        if section not in allowed_sections:
            raise HarnessError(
                "active_plan_required_tables references an undeclared section"
            )
        if not isinstance(rule, dict) or set(rule) != {"header", "min_rows"}:
            raise HarnessError(
                "active_plan_required_tables entries require only header and min_rows"
            )
        header = rule["header"]
        min_rows = rule["min_rows"]
        if not isinstance(header, list) or not header:
            raise HarnessError("active plan table header must be a non-empty list")
        normalized: list[str] = []
        for cell in header:
            if (
                not isinstance(cell, str)
                or cell != cell.strip()
                or not cell
                or len(cell) > 80
                or "|" in cell
                or "\r" in cell
                or "\n" in cell
            ):
                raise HarnessError("active plan table header contains an invalid cell")
            normalized.append(cell)
        if len(normalized) != len(set(normalized)):
            raise HarnessError("active plan table header cells must be unique")
        if (
            not isinstance(min_rows, int)
            or isinstance(min_rows, bool)
            or min_rows < 1
        ):
            raise HarnessError("active plan table min_rows must be a positive integer")
        requirements[section] = ActivePlanTableRequirement(
            tuple(normalized),
            min_rows,
        )
    return requirements


def validate_contract(
    contract: dict[str, Any],
    root: Path,
    *,
    check_files: bool = True,
) -> None:
    if check_files and not is_repo_regular_file(root, CONTRACT_PATH):
        raise HarnessError("contract must be a regular in-repository file")
    contract_keys = set(contract)
    missing_keys = sorted(CONTRACT_REQUIRED_KEYS - contract_keys)
    unexpected_keys = sorted(
        contract_keys - CONTRACT_REQUIRED_KEYS - CONTRACT_OPTIONAL_KEYS
    )
    if missing_keys or unexpected_keys:
        details: list[str] = []
        if missing_keys:
            details.append(f"missing={missing_keys!r}")
        if unexpected_keys:
            details.append(f"unexpected={unexpected_keys!r}")
        raise HarnessError(
            "contract top-level schema differs from this verifier release "
            f"({'; '.join(details)})"
        )
    if contract.get("contract_version") != CONTRACT_VERSION:
        raise HarnessError("unsupported contract_version")
    if check_files:
        validate_no_legacy_runtime(root)
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
    active_plan_required_sections(contract)
    active_plan_required_fields(contract)
    active_plan_required_tables(contract)

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
    expected_platform_keys = (
        {"state", "pending_reason"}
        if platform_state == "pending"
        else {"state"}
    )
    if set(platform_gate) != expected_platform_keys:
        raise HarnessError(
            f"{platform_state} platform_gate schema must contain exactly "
            f"{sorted(expected_platform_keys)!r}"
        )
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
    expected_task_policy_keys = {
        "task_class_values",
        "record_actual",
        "model_policy",
        "reasoning_effort_values",
        "speed_values",
        "unknown_allowed",
    }
    if set(task_policy) != expected_task_policy_keys:
        raise HarnessError("task_record_policy contains undeclared fields")
    if task_policy.get("task_class_values") != [
        "trivial",
        "standard",
        "critical",
    ]:
        raise HarnessError("unexpected task-class values")
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
    expected_review_keys = {
        "supervision_model",
        "allowed_authors",
        "head_requirement",
        "clean_requirement",
        "finding_policy",
        "fail_closed_on",
        "required_status_translation",
    }
    if set(review) != expected_review_keys:
        raise HarnessError("review policy contains undeclared fields")
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
    expected_github_policy_keys = {
        "pr_only",
        "strict_base_freshness",
        "no_bypass",
        "same_repository_prs_only",
        "force_push_allowed",
        "branch_deletion_allowed",
        "expected_head_required",
        "merge_authority_model",
    }
    if not isinstance(github, dict) or set(github) != expected_github_policy_keys:
        raise HarnessError("github_policy contains undeclared fields")
    required_true = (
        "pr_only",
        "strict_base_freshness",
        "no_bypass",
        "same_repository_prs_only",
        "expected_head_required",
    )
    if any(github.get(key) is not True for key in required_true):
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
    if set(baseline) != {
        "path",
        "schema_version",
        "evidence_kind",
        "check_name",
        "allowed_validators",
    }:
        raise HarnessError("baseline_receipt policy contains undeclared fields")
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
        list(active_plan_required_sections(trusted_contract)),
        list(active_plan_required_sections(candidate_contract)),
        "active_plan_required_sections",
    )
    trusted_fields = active_plan_required_fields(trusted_contract)
    candidate_fields = active_plan_required_fields(candidate_contract)
    for section, labels in trusted_fields.items():
        if section not in candidate_fields:
            raise HarnessError(
                f"candidate contract removes trusted Active Plan fields: {section}"
            )
        require_superset(
            list(labels),
            list(candidate_fields[section]),
            f"active_plan_required_fields.{section}",
        )
    trusted_tables = active_plan_required_tables(trusted_contract)
    candidate_tables = active_plan_required_tables(candidate_contract)
    for section, requirement in trusted_tables.items():
        candidate_requirement = candidate_tables.get(section)
        if candidate_requirement is None:
            raise HarnessError(
                f"candidate contract removes trusted Active Plan table: {section}"
            )
        if candidate_requirement.header != requirement.header:
            raise HarnessError(
                f"candidate contract changes trusted Active Plan table header: {section}"
            )
        if candidate_requirement.min_rows < requirement.min_rows:
            raise HarnessError(
                f"candidate contract weakens Active Plan table min_rows: {section}"
            )

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
            raise HarnessError(
                "nested Active Plans are forbidden: "
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
            if path.name == ".gitkeep" and path.parent == directory:
                if read_repo_regular_text(
                    root,
                    relative,
                    max_bytes=MAX_ACTIVE_PLAN_BYTES,
                ).strip():
                    raise HarnessError(
                        "Active Plan .gitkeep sentinel must be empty"
                    )
                continue
            if path.suffix != ".md":
                raise HarnessError(
                    f"unexpected file in Active Plan directory: {relative}"
                )
            if path.parent != directory:
                raise HarnessError(f"nested Active Plans are forbidden: {relative}")
            plans.append(path)
    return sorted(plans)


def markdown_character_is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def protect_inline_code_spans(text: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Replace complete CommonMark backtick spans with collision-free tokens."""
    runs: list[tuple[int, int, int]] = []
    cursor = 0
    while cursor < len(text):
        start = text.find("`", cursor)
        if start < 0:
            break
        if markdown_character_is_escaped(text, start):
            cursor = start + 1
            continue
        end = start + 1
        while end < len(text) and text[end] == "`":
            end += 1
        runs.append((start, end, end - start))
        cursor = end

    next_same_length: list[int | None] = [None] * len(runs)
    last_by_length: dict[int, int] = {}
    for index in range(len(runs) - 1, -1, -1):
        delimiter_length = runs[index][2]
        next_same_length[index] = last_by_length.get(delimiter_length)
        last_by_length[delimiter_length] = index

    parts: list[str] = []
    spans: list[tuple[str, str]] = []
    cursor = 0
    run_index = 0
    while run_index < len(runs):
        opener_start, opener_end, _ = runs[run_index]
        parts.append(text[cursor:opener_start])
        closing_index = next_same_length[run_index]
        if closing_index is None:
            parts.append(text[opener_start:opener_end])
            cursor = opener_end
            run_index += 1
            continue
        closing_end = runs[closing_index][1]
        literal = text[opener_start:closing_end]
        token = f"\x00HARNESS-CODE-SPAN-{len(spans)}\x00"
        while token in text:
            token += "\x00"
        spans.append((token, literal))
        parts.append(token)
        cursor = closing_end
        run_index = closing_index + 1
    parts.append(text[cursor:])
    return "".join(parts), tuple(spans)


def restore_inline_code_spans(
    text: str,
    spans: tuple[tuple[str, str], ...],
) -> str:
    for token, literal in spans:
        text = text.replace(token, literal)
    return text


def render_inline_code_and_html_comments(text: str) -> str:
    """Remove real HTML comments while preserving bounded inline-code literals."""
    output: list[str] = []
    cursor = 0
    while cursor < len(text):
        if text.startswith("<!--", cursor):
            end = text.find("-->", cursor + 4)
            if end < 0:
                raise HarnessError("Active Plan contains a malformed HTML comment")
            comment = text[cursor : end + 3]
            output.append("\n" * comment.count("\n"))
            cursor = end + 3
            continue
        if text.startswith("-->", cursor):
            raise HarnessError("Active Plan contains a malformed HTML comment")
        if text[cursor] == "`" and not markdown_character_is_escaped(text, cursor):
            run_end = cursor + 1
            while run_end < len(text) and text[run_end] == "`":
                run_end += 1
            delimiter = text[cursor:run_end]
            search = run_end
            closing = -1
            while True:
                candidate = text.find(delimiter, search)
                if candidate < 0:
                    break
                after = candidate + len(delimiter)
                if (
                    not markdown_character_is_escaped(text, candidate)
                    and (candidate == 0 or text[candidate - 1] != "`")
                    and (after == len(text) or text[after] != "`")
                ):
                    closing = candidate
                    break
                search = candidate + 1
            if closing >= 0:
                span_end = closing + len(delimiter)
                literal = text[cursor:span_end]
                if "\n" in literal or "\r" in literal:
                    output.append(
                        "".join(
                            character
                            if character in {"\n", "\r"}
                            else " "
                            for character in literal
                        )
                    )
                else:
                    output.append(literal)
                cursor = span_end
                continue
            output.append(delimiter)
            cursor = run_end
            continue
        output.append(text[cursor])
        cursor += 1
    return "".join(output)


def rendered_plan_text(text: str) -> str:
    """Remove Markdown regions that do not render as plan prose."""
    def indentation_columns(value: str) -> int:
        columns = 0
        for character in value:
            if character == " ":
                columns += 1
            elif character == "\t":
                columns += 4 - (columns % 4)
            else:
                break
        return columns

    def fence_parts(value: str) -> tuple[str, str] | None:
        indent = re.match(r"^[ \t]*", value)
        assert indent is not None
        if indentation_columns(indent.group(0)) > 3:
            return None
        match = re.fullmatch(
            r"(`{3,}|~{3,})([^\r\n]*)",
            value[len(indent.group(0)) :],
        )
        if match is None:
            return None
        return match.group(1), match.group(2)

    visible_lines: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        container_content = strip_commonmark_container_prefixes(content)
        if container_content != content:
            if (
                fence_parts(container_content) is not None
                or indentation_columns(container_content) >= 4
            ):
                raise HarnessError(
                    "Active Plan contains a code block inside a Markdown container"
                )
        if fence is not None:
            closing = fence_parts(content)
            if (
                closing is not None
                and not closing[1].strip()
                and closing[0][0] == fence[0]
                and len(closing[0]) >= fence[1]
            ):
                fence = None
            visible_lines.append("\n" if line.endswith("\n") else "")
            continue
        opening = fence_parts(content)
        if opening is not None:
            marker, info = opening
            if marker[0] != "`" or "`" not in info:
                fence = (marker[0], len(marker))
                visible_lines.append("\n" if line.endswith("\n") else "")
                continue
        if indentation_columns(content) >= 4:
            visible_lines.append("\n" if line.endswith("\n") else "")
            continue
        visible_lines.append(line)

    if fence is not None:
        raise HarnessError("Active Plan contains an unterminated fenced block")
    visible = render_inline_code_and_html_comments("".join(visible_lines))
    if any(
        RAW_HTML_BLOCK_START_RE.match(line)
        for line in visible.splitlines()
    ):
        raise HarnessError("Active Plan contains raw HTML block markup")
    return visible


def self_test_rendered_plan_text() -> None:
    protected = (
        "`<!-- literal -->`\n"
        "`<!-- exact-scope:begin -->`\n"
        "<!-- real comment -->\n"
        "visible\n"
    )
    rendered = rendered_plan_text(protected)
    for literal in (
        "`<!-- literal -->`",
        "`<!-- exact-scope:begin -->`",
    ):
        if literal not in rendered:
            raise HarnessError(
                f"inline-code rendering self-test lost literal: {literal}"
            )
    if "real comment" in rendered or "visible" not in rendered:
        raise HarnessError("HTML-comment rendering self-test failed")
    precedence = rendered_plan_text("<!-- ` internal -->\nafter `visible`\n")
    if "internal" in precedence or "`visible`" not in precedence:
        raise HarnessError("comment/code precedence self-test failed")
    multiline = rendered_plan_text(
        "# Plan ``\n## Metadata\n- Owner: Rmosser\n``\n"
    )
    if "## Metadata" in multiline or "Owner:" in multiline:
        raise HarnessError("multiline code-span structure self-test failed")

    negative_cases = (
        "<!-- unmatched opener",
        "--> unmatched closer",
        "`unmatched delimiter <!--",
        "<section>\n",
    )
    for fixture in negative_cases:
        try:
            rendered_plan_text(fixture)
        except HarnessError:
            continue
        raise HarnessError(
            "rendering self-test accepted unsafe markup: "
            + repr(fixture)
        )


def plan_heading_pattern(heading: str) -> str:
    if not heading.startswith("## "):
        raise HarnessError(f"unsupported Active Plan heading: {heading}")
    label = re.escape(heading[3:])
    return rf"^[ ]{{0,3}}##[ \t]+{label}(?:[ \t]+#+)?[ \t]*$"


def plan_section(text: str, heading: str) -> str:
    text = rendered_plan_text(text)
    matches = list(
        re.finditer(
            plan_heading_pattern(heading)
            + r"\n(?P<body>.*?)(?=^[ ]{0,3}##(?:[ \t]+|$)|\Z)",
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


def visible_inline_text(value: str) -> str:
    code_spans: list[tuple[str, str]] = []
    autolinks: list[tuple[str, str]] = []

    def normalize_code_span_body(body: str) -> str:
        literal = body.replace("\r\n", "\n").replace("\r", "\n")
        literal = literal.replace("\n", " ")
        if (
            len(literal) >= 2
            and literal.startswith(" ")
            and literal.endswith(" ")
            and literal.strip(" ")
        ):
            literal = literal[1:-1]
        return literal

    def protect_autolink(match: re.Match[str]) -> str:
        target = match.group("target")
        token = f"\x00AUTOLINK-{len(autolinks)}\x00"
        while token in value:
            token += "\x00"
        autolinks.append((token, target))
        return token

    protected, raw_code_spans = protect_inline_code_spans(value)
    for token, raw_literal in raw_code_spans:
        delimiter_length = len(raw_literal) - len(raw_literal.lstrip("`"))
        literal = raw_literal[delimiter_length:-delimiter_length]
        code_spans.append((token, normalize_code_span_body(literal)))
    protected = COMMONMARK_AUTOLINK_RE.sub(protect_autolink, protected)
    parser = _VisibleInlineTextParser()
    try:
        parser.feed(protected)
        parser.close()
    except Exception as exc:
        raise HarnessError(f"cannot parse inline HTML: {exc}") from exc
    rendered = "".join(parser.parts)
    for token, literal in code_spans:
        rendered = rendered.replace(token, literal)
    for token, target in autolinks:
        rendered = rendered.replace(token, target)
    return rendered


def matches_placeholder_token(value: str) -> bool:
    candidate = value.strip()
    while candidate:
        if PLACEHOLDER_VALUE_RE.fullmatch(candidate) is not None:
            return True
        if unicodedata.category(candidate[-1]).startswith("P"):
            candidate = candidate[:-1].rstrip()
            continue
        if unicodedata.category(candidate[0]).startswith("P"):
            candidate = candidate[1:].lstrip()
            continue
        return False
    return True


def normalize_visible_plan_value(value: str) -> tuple[str, bool]:
    """Normalize rendered scalar prose and flag non-visible/unsafe values."""
    normalized = unicodedata.normalize("NFKC", value.strip())
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Mn"}
        for character in normalized
    ):
        return "", True
    prefix_changed = True
    while prefix_changed:
        previous = normalized
        normalized = re.sub(r"^(?:>[ \t]*)+", "", normalized)
        normalized = re.sub(
            r"^(?:[-*+]|\d+[.)])[ \t]+",
            "",
            normalized,
        )
        normalized = re.sub(r"^\[[ xX-]\][ \t]*", "", normalized)
        prefix_changed = normalized != previous
    normalized = re.sub(r"^#{1,6}[ \t]+", "", normalized)
    normalized = re.sub(r"[ \t]+#+[ \t]*$", "", normalized)
    normalized = re.sub(r"(?<!\\)\\[ \t]*$", "", normalized)
    wrappers = (("**", "**"), ("__", "__"), ("~~", "~~"), ("*", "*"), ("_", "_"))
    changed = True
    while changed:
        normalized = unicodedata.normalize("NFKC", normalized)
        if any(
            unicodedata.category(character) in {"Cc", "Cf", "Mn"}
            for character in normalized
        ):
            return "", True
        changed = False
        for opening, closing in wrappers:
            if (
                normalized.startswith(opening)
                and normalized.endswith(closing)
                and len(normalized) > len(opening) + len(closing)
            ):
                normalized = normalized[len(opening) : -len(closing)].strip()
                changed = True
        match = re.fullmatch(
            r"(?<!`)(?P<ticks>`+)(?!`)(?P<body>.*?)"
            r"(?<!`)(?P=ticks)(?!`)",
            normalized,
            re.DOTALL,
        )
        if match is not None:
            # Inline code is visible literal text. Angle-bracket content inside
            # it is not raw HTML and must not be interpreted as such.
            return match.group("body").strip(), False
        match = re.fullmatch(
            r"(?P<image>!?)\[(?P<label>[^\]\r\n]*)\](?P<suffix>.*)",
            normalized,
            re.DOTALL,
        )
        if match is not None and (
            not match.group("suffix")
            or match.group("suffix").startswith(("(", "["))
        ):
            if match.group("image"):
                return "", True
            normalized = match.group("label").strip()
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
        match = re.fullmatch(r"!?\[([^\]\r\n]+)\]", normalized)
        if match is not None:
            normalized = match.group(1).strip()
            changed = True
        if matches_placeholder_token(normalized):
            return normalized, False
        rendered = visible_inline_text(normalized).strip()
        if rendered != normalized:
            normalized = rendered
            changed = True
        markdown_plain = re.sub(
            r"!?\[([^\]\r\n]*)\]\([^)\r\n]*\)",
            r"\1",
            normalized,
        )
        markdown_plain = re.sub(
            r"!?\[([^\]\r\n]*)\]\[[^\]\r\n]*\]",
            r"\1",
            markdown_plain,
        )
        markdown_plain = re.sub(r"(?<!\\)[*_~`]+", "", markdown_plain).strip()
        if markdown_plain != normalized:
            normalized = markdown_plain
            changed = True
    return normalized, False


def is_placeholder_value(value: str) -> bool:
    normalized, forced_placeholder = normalize_visible_plan_value(value)
    if forced_placeholder:
        return True
    lowered = normalized.lower()
    return (
        not normalized
        or lowered in {"...", "…"}
        or lowered.startswith("replace with ")
        or matches_placeholder_token(normalized)
    )


def is_semantic_not_applicable(value: str) -> bool:
    normalized, forced_placeholder = normalize_visible_plan_value(value)
    if forced_placeholder:
        return False
    candidate = normalized.strip()
    while candidate:
        if NOT_APPLICABLE_VALUE_RE.fullmatch(candidate) is not None:
            return True
        if not unicodedata.category(candidate[-1]).startswith("P"):
            return False
        candidate = candidate[:-1].rstrip()
    return False


def markdown_table_cells(line: str) -> tuple[str, ...] | None:
    stripped = line.strip(" \t")
    separators: list[int] = []
    for index, character in enumerate(stripped):
        if character != "|":
            continue
        backslashes = 0
        cursor = index
        while cursor > 0 and stripped[cursor - 1] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            separators.append(index)
    if not separators:
        return None
    boundaries = [-1, *separators, len(stripped)]
    cells = [
        stripped[boundaries[index] + 1 : boundaries[index + 1]].strip(" \t")
        for index in range(len(boundaries) - 1)
    ]
    if separators[0] == 0:
        cells.pop(0)
    if separators[-1] == len(stripped) - 1:
        cells.pop()
    if not cells:
        return None
    return tuple(cell.replace(r"\|", "|") for cell in cells)


class MarkdownTableBlock(NamedTuple):
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    start: int
    end: int
    safe_layout: bool


def indentation_columns(value: str, initial: int = 0) -> int:
    columns = initial
    for character in value:
        if character == " ":
            columns += 1
        elif character == "\t":
            columns += 4 - (columns % 4)
        else:
            break
    return columns


def consume_indentation_columns(value: str, expected: int) -> str | None:
    columns = 0
    cursor = 0
    while cursor < len(value) and value[cursor] in " \t":
        next_columns = indentation_columns(value[cursor], columns)
        if next_columns > expected:
            return None
        columns = next_columns
        cursor += 1
        if columns == expected:
            return value[cursor:]
    return None


def commonmark_container_prefixes(
    value: str,
    *,
    allow_non_one_ordered: bool = True,
) -> tuple[tuple[str, ...], str]:
    normalized = value
    prefixes: list[str] = []
    while True:
        previous = normalized
        quote = re.match(
            r"^[ \t]{0,3}>[ \t]?",
            normalized,
        )
        if quote is not None:
            prefixes.append("quote")
            normalized = normalized[quote.end() :]
            continue
        leading = re.match(r"^[ \t]*", normalized)
        assert leading is not None
        leading_text = leading.group(0)
        leading_columns = indentation_columns(leading_text)
        if leading_columns <= 3:
            marker = re.match(
                r"(?:(?P<bullet>[-+*])|"
                r"(?P<number>\d{1,9})(?P<delimiter>[.)]))",
                normalized[leading.end() :],
            )
            if marker is not None:
                if (
                    marker.group("number") not in {None, "1"}
                    and not allow_non_one_ordered
                ):
                    return tuple(prefixes), normalized
                marker_end = leading.end() + marker.end()
                whitespace = re.match(r"[ \t]+", normalized[marker_end:])
                if whitespace is not None:
                    whitespace_text = whitespace.group(0)
                    marker_end_columns = (
                        leading_columns + len(marker.group(0))
                    )
                    padding_columns = (
                        indentation_columns(
                            whitespace_text,
                            marker_end_columns,
                        )
                        - marker_end_columns
                    )
                    if 1 <= padding_columns <= 4:
                        content_start = marker_end + whitespace.end()
                        prefixes.append(
                            f"list:{marker_end_columns + padding_columns}"
                        )
                        normalized = normalized[content_start:]
                        continue
                    # Five or more columns after a marker count as one
                    # padding column; the remainder stays in the content.
                    first_whitespace = whitespace_text[0]
                    one_column = (
                        indentation_columns(
                            first_whitespace,
                            marker_end_columns,
                        )
                        - marker_end_columns
                    )
                    prefixes.append(
                        f"list:{marker_end_columns + one_column}"
                    )
                    normalized = normalized[marker_end + 1 :]
                    continue
        if normalized == previous:
            return tuple(prefixes), normalized


def strip_commonmark_container_prefixes(value: str) -> str:
    return commonmark_container_prefixes(value)[1]


def starts_gfm_table_interrupting_block(value: str) -> bool:
    return bool(
        re.match(
            r"^[ ]{0,3}(?:"
            r"#{1,6}(?:[ \t]+|$)|"
            r"`{3,}|~{3,}|"
            r"(?:\*[ \t]*){3,}[ \t]*$|"
            r"(?:-[ \t]*){3,}[ \t]*$|"
            r"(?:_[ \t]*){3,}[ \t]*$"
            r")",
            value,
        )
        or RAW_HTML_BLOCK_START_RE.match(value)
        or re.match(r"^(?: {4}|\t)", value)
    )


def normalize_markdown_table_context_line(
    line: str,
    expected_prefixes: tuple[str, ...],
) -> str | None:
    normalized = line
    for prefix in expected_prefixes:
        if prefix == "quote":
            quote = re.match(r"^[ \t]{0,3}>[ \t]?", normalized)
            if quote is None:
                return None
            normalized = normalized[quote.end() :]
            continue
        if not prefix.startswith("list:"):
            return None
        indentation = int(prefix.removeprefix("list:"))
        remainder = consume_indentation_columns(normalized, indentation)
        if remainder is None:
            return None
        normalized = remainder
    # A new container starts a different block rather than another table row.
    nested_prefixes, _ = commonmark_container_prefixes(normalized)
    if nested_prefixes:
        return None
    return normalized


def markdown_table_data_cells(
    line: str,
    expected_prefixes: tuple[str, ...],
) -> tuple[str, ...] | None:
    """Parse one GFM table row without treating a new block as table data."""
    normalized = normalize_markdown_table_context_line(
        line,
        expected_prefixes,
    )
    if (
        normalized is None
        or not normalized.strip(" \t")
        or starts_gfm_table_interrupting_block(normalized)
    ):
        return None
    cells = markdown_table_cells(normalized)
    if cells is not None:
        return cells
    # Within an open table, plain non-blank text is a short one-cell row.
    return (normalized.strip(" \t"),)


def markdown_table_blocks(
    lines: list[str],
) -> tuple[
    tuple[MarkdownTableBlock, ...],
    tuple[tuple[int, tuple[str, ...]], ...],
]:
    """Parse actual GFM table blocks and expose top-level header candidates."""
    blocks: list[MarkdownTableBlock] = []
    candidates: list[tuple[int, tuple[str, ...]]] = []
    index = 0
    while index < len(lines):
        prefixes, header_line = commonmark_container_prefixes(
            lines[index],
            allow_non_one_ordered=(
                index == 0
                or not strip_commonmark_container_prefixes(
                    lines[index - 1]
                ).strip(" \t")
            ),
        )
        header = markdown_table_cells(header_line)
        if header is None:
            index += 1
            continue
        candidates.append((index, header))
        if index + 1 >= len(lines):
            index += 1
            continue
        separator_prefixes, separator_line = commonmark_container_prefixes(
            lines[index + 1]
        )
        separator = markdown_table_cells(separator_line)
        is_table = (
            separator is not None
            and len(separator) == len(header)
            and all(
                re.fullmatch(r":?-{3,}:?", cell) is not None
                for cell in separator
            )
        )
        if not is_table:
            index += 1
            continue
        safe_layout = (
            not prefixes
            and not separator_prefixes
            and (
                index == 0
                or not strip_commonmark_container_prefixes(
                    lines[index - 1]
                ).strip(" \t")
            )
        )
        end = index + 2
        rows: list[tuple[str, ...]] = []
        while end < len(lines):
            if safe_layout:
                row = markdown_table_data_cells(lines[end], ())
            else:
                row_text = strip_commonmark_container_prefixes(lines[end])
                if not row_text.strip(" \t"):
                    row = None
                else:
                    row = markdown_table_cells(row_text)
                    if row is None:
                        row = (row_text.strip(" \t"),)
            if row is None:
                break
            rows.append(row)
            end += 1
        blocks.append(
            MarkdownTableBlock(
                header=header,
                rows=tuple(rows),
                start=index,
                end=end,
                safe_layout=safe_layout,
            )
        )
        index = end
    return tuple(blocks), tuple(candidates)


def reject_reference_definitions(lines: list[str], heading: str) -> None:
    open_label = False
    label_size = 0
    for raw_line in lines:
        line = strip_commonmark_container_prefixes(raw_line)
        if re.match(r"^[ \t]{0,3}\[.+\]:", line):
            raise HarnessError(
                f"Active Plan {heading} contains a non-rendered "
                "reference definition"
            )
        if open_label:
            label_size += len(line) + 1
            if re.search(r"\]:[ \t]*(?:\S|$)", line):
                raise HarnessError(
                    f"Active Plan {heading} contains a non-rendered "
                    "multiline reference definition"
                )
            if not line.strip() or label_size > 1000:
                open_label = False
            continue
        if re.match(r"^[ \t]{0,3}\[[^\]\r\n]*$", line):
            open_label = True
            label_size = len(line)


def reject_markdown_link_or_image_syntax(text: str, heading: str) -> None:
    if re.search(r"!\[", text) or re.search(
        r"\](?:[ \t\r\n]*)[\[(]",
        text,
    ):
        raise HarnessError(
            f"Active Plan {heading} uses Markdown link or image syntax; "
            "use visible prose and a CommonMark autolink instead"
        )


def validate_required_plan_table(
    text: str,
    heading: str,
    requirement: ActivePlanTableRequirement,
) -> None:
    section = rendered_plan_text(plan_section(text, heading))
    lines = section.splitlines()
    blocks, candidates = markdown_table_blocks(lines)
    matches = [
        block
        for block in blocks
        if block.safe_layout and block.header == requirement.header
    ]
    candidate_indexes = [
        index
        for index, header in candidates
        if header == requirement.header
    ]
    if len(matches) != 1 or len(candidate_indexes) != 1:
        if not matches and len(candidate_indexes) == 1:
            candidate_index = candidate_indexes[0]
            if candidate_index + 1 >= len(lines):
                raise HarnessError(
                    f"Active Plan table has no separator in {heading}"
                )
            raise HarnessError(
                f"Active Plan table has an invalid separator in {heading}"
            )
        raise HarnessError(
            f"Active Plan must contain exactly one required table in {heading}"
        )
    rows = matches[0].rows
    if len(rows) < requirement.min_rows:
        raise HarnessError(
            f"Active Plan table has fewer than {requirement.min_rows} rows in "
            f"{heading}"
        )
    for row in rows:
        visible_row = tuple(
            visible_inline_text(cell).strip()
            for cell in row[: len(requirement.header)]
        )
        if (
            len(row) < len(requirement.header)
            or any(is_placeholder_value(cell) for cell in visible_row)
        ):
            raise HarnessError(
                f"Active Plan table has an incomplete or placeholder row in {heading}"
            )


def require_concrete_section(text: str, heading: str) -> str:
    section = plan_section(text, heading)
    candidates: list[str] = []
    rendered_section = rendered_plan_text(section)
    reject_reference_definitions(rendered_section.splitlines(), heading)
    reject_markdown_link_or_image_syntax(rendered_section, heading)
    non_table_lines = rendered_section.splitlines()
    table_blocks, _ = markdown_table_blocks(non_table_lines)
    for block in table_blocks:
        if not block.safe_layout:
            for line_index in range(block.start, block.end):
                non_table_lines[line_index] = ""
            continue
        header_width = len(block.header)
        for row in block.rows:
            visible_row = tuple(
                visible_inline_text(cell).strip()
                for cell in row[:header_width]
            )
            if (
                len(row) >= header_width
                and all(
                    cell and not is_placeholder_value(cell)
                    for cell in visible_row
                )
            ):
                candidates.extend(visible_row)
        for line_index in range(block.start, block.end):
            non_table_lines[line_index] = ""
    visible_section = visible_inline_text("\n".join(non_table_lines))
    lines = visible_section.splitlines()
    index = 0
    while index < len(lines):
        raw_line = strip_commonmark_container_prefixes(lines[index])
        reference = re.match(
            r"^[ \t]{0,3}\[[^\]\r\n]+\]:(?P<definition>.*)$",
            raw_line,
        )
        if reference is not None:
            if not reference.group("definition").strip():
                raise HarnessError(
                    f"Active Plan {heading} contains an ambiguous multiline "
                    "reference definition"
                )
            if (
                index + 1 < len(lines)
                and re.fullmatch(
                    r"""[ \t]{0,3}(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|"""
                    r"""\((?:[^)\\]|\\.)*\))[ \t]*""",
                    lines[index + 1],
                )
                is not None
            ):
                index += 2
            else:
                index += 1
            continue
        index += 1
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch(r"#{1,6}(?:[ \t]+#*[ \t]*)?", line):
            continue
        if re.fullmatch(
            r"(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,}",
            line,
        ):
            continue
        if re.fullmatch(r"(?:=+|-+)", line):
            continue
        if re.fullmatch(r"\[[^\]\r\n]+\]:[ \t]*\S.*", line):
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
    additional_sections = active_plan_required_sections(contract)
    section_positions: list[int] = []
    for section in PLAN_SECTIONS:
        matches = list(
            re.finditer(
                plan_heading_pattern(section),
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
    for section in additional_sections:
        matches = list(
            re.finditer(
                plan_heading_pattern(section),
                visible_text,
                re.MULTILINE,
            )
        )
        if not matches:
            raise HarnessError(f"Active Plan is missing section: {section}")
        if len(matches) != 1:
            raise HarnessError(f"Active Plan has duplicate section: {section}")
    template_text = read_repo_regular_text(
        root,
        "docs/exec-plans/template.md",
        max_bytes=MAX_ACTIVE_PLAN_BYTES,
    )
    if text.strip() == template_text.strip():
        raise HarnessError("Active Plan must not be an unchanged template")
    for heading, labels in active_plan_required_fields(contract).items():
        section = plan_section(text, heading)
        for label in labels:
            value = plan_field(section, label)
            if is_placeholder_value(value):
                raise HarnessError(
                    f"Active Plan has no concrete required field: {label}"
                )
    for heading, requirement in active_plan_required_tables(contract).items():
        validate_required_plan_table(text, heading, requirement)
    for heading in PLAN_SECTIONS + additional_sections:
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
        if any(
            not is_semantic_not_applicable(value)
            for value in delegated_fields.values()
        ):
            raise HarnessError(
                "single-agent plan delegation audit must be not_applicable"
            )
        fallback_reason = audit_values["No-subagent fallback reason"]
        fallback_is_not_applicable = is_semantic_not_applicable(
            fallback_reason
        )
        fallback_is_placeholder = is_placeholder_value(fallback_reason)
        if values["Task class"] in {"standard", "critical"} and (
            fallback_is_not_applicable or fallback_is_placeholder
        ):
            raise HarnessError(
                "nontrivial single-agent plan needs a concrete "
                "No-subagent fallback reason"
            )
        if (
            values["Task class"] == "trivial"
            and fallback_is_placeholder
            and not fallback_is_not_applicable
        ):
            raise HarnessError(
                "trivial single-agent plan needs a concrete "
                "No-subagent fallback reason or not_applicable"
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


def git_bytes_result(
    git_dir: Path,
    *args: str,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", f"--git-dir={git_dir}", *args],
        capture_output=True,
        check=False,
    )


def git_commit_exists(git_dir: Path, sha: str) -> bool:
    completed = git_result(git_dir, "cat-file", "-t", sha)
    return completed.returncode == 0 and completed.stdout.strip() == "commit"


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


def display_git_path(path: bytes) -> str:
    return path.decode("utf-8", errors="backslashreplace")


def git_tree_entries(git_dir: Path, sha: str) -> dict[bytes, GitTreeEntry]:
    completed = git_bytes_result(
        git_dir,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        sha,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise HarnessError(f"cannot read Git tree: {detail}")
    entries: dict[bytes, GitTreeEntry] = {}
    for record in completed.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path = record.split(b"\t", 1)
            mode_bytes, object_type_bytes, object_id_bytes = metadata.split(b" ", 2)
            mode = mode_bytes.decode("ascii")
            object_type = object_type_bytes.decode("ascii")
            object_id = object_id_bytes.decode("ascii")
        except (UnicodeDecodeError, ValueError) as exc:
            raise HarnessError("Git tree contains a malformed entry") from exc
        parts = path.split(b"/")
        if (
            not path
            or path.startswith(b"/")
            or any(part in {b"", b".", b".."} for part in parts)
        ):
            raise HarnessError("Git tree contains an unsafe path")
        if parts[0] == b".git":
            raise HarnessError("Git tree contains reserved root .git metadata")
        if path in entries:
            raise HarnessError(
                f"Git tree contains a duplicate path: {display_git_path(path)}"
            )
        if (mode, object_type) not in {
            ("100644", "blob"),
            ("100755", "blob"),
            ("120000", "blob"),
            ("160000", "commit"),
        }:
            raise HarnessError(
                f"Git tree contains unsupported mode/type at "
                f"{display_git_path(path)}"
            )
        entries[path] = GitTreeEntry(mode, object_type, object_id, path)
    return entries


def filesystem_snapshot(root: Path) -> dict[bytes, FilesystemEntry]:
    resolved = root.resolve(strict=True)
    root_bytes = os.fsencode(resolved)
    snapshot: dict[bytes, FilesystemEntry] = {}

    def visit(directory: bytes, prefix: bytes) -> None:
        try:
            with os.scandir(directory) as iterator:
                children = sorted(iterator, key=lambda item: item.name)
        except OSError as exc:
            raise HarnessError(f"cannot inspect source snapshot: {exc}") from exc
        for child in children:
            name = child.name
            if not isinstance(name, bytes):
                raise HarnessError("filesystem did not preserve source path bytes")
            if not prefix and name == b".git":
                continue
            relative = name if not prefix else prefix + b"/" + name
            try:
                info = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise HarnessError(
                    f"cannot inspect source path {display_git_path(relative)}: {exc}"
                ) from exc
            if stat.S_ISDIR(info.st_mode):
                kind = "tree"
            elif stat.S_ISREG(info.st_mode):
                kind = "blob"
            elif stat.S_ISLNK(info.st_mode):
                kind = "symlink"
            else:
                raise HarnessError(
                    f"source snapshot contains a special file: "
                    f"{display_git_path(relative)}"
                )
            snapshot[relative] = FilesystemEntry(
                kind,
                info.st_mode,
                info.st_size,
                info.st_mtime_ns,
                info.st_dev,
                info.st_ino,
            )
            if kind == "tree":
                visit(os.path.join(directory, name), relative)

    visit(root_bytes, b"")
    return snapshot


def git_blob_id(data: bytes, algorithm: str) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError as exc:
        raise HarnessError(f"unsupported Git object format: {algorithm}") from exc
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def read_snapshot_symlink(root: Path, relative: bytes) -> bytes:
    absolute = os.path.join(os.fsencode(root.resolve(strict=True)), relative)
    try:
        before = os.lstat(absolute)
        target = os.readlink(absolute)
        after = os.lstat(absolute)
    except OSError as exc:
        raise HarnessError(
            f"cannot read source symlink {display_git_path(relative)}: {exc}"
        ) from exc
    if (
        not stat.S_ISLNK(before.st_mode)
        or (before.st_dev, before.st_ino, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_mtime_ns)
    ):
        raise HarnessError(
            f"source symlink changed during validation: {display_git_path(relative)}"
        )
    if not isinstance(target, bytes):
        raise HarnessError("filesystem did not preserve symlink target bytes")
    return target


def validate_source_snapshot(
    git_dir: Path,
    sha: str,
    root: Path,
    *,
    label: str,
) -> None:
    tree = git_tree_entries(git_dir, sha)
    required_kinds: dict[bytes, str] = {}
    optional_kinds: dict[bytes, str] = {}
    for path, entry in tree.items():
        parts = path.split(b"/")
        if entry.mode == "160000":
            for index in range(1, len(parts)):
                optional_kinds.setdefault(b"/".join(parts[:index]), "tree")
            optional_kinds[path] = "tree"
            continue
        for index in range(1, len(parts)):
            required_kinds.setdefault(b"/".join(parts[:index]), "tree")
        required_kinds[path] = "symlink" if entry.mode == "120000" else "blob"

    for path in required_kinds:
        optional_kinds.pop(path, None)
    allowed_kinds = {**optional_kinds, **required_kinds}

    before = filesystem_snapshot(root)
    extra_paths = set(before) - set(allowed_kinds)
    missing_paths = set(required_kinds) - set(before)
    if extra_paths or missing_paths:
        deepest_first = lambda path: (-path.count(b"/"), path)
        extra = sorted(
            extra_paths,
            key=deepest_first,
        )
        missing = sorted(
            missing_paths,
            key=deepest_first,
        )
        details: list[str] = []
        if missing:
            details.append("missing=" + display_git_path(missing[0]))
        if extra:
            details.append("extra=" + display_git_path(extra[0]))
        raise HarnessError(
            f"{label} root does not match Git {sha} source snapshot "
            f"({'; '.join(details)})"
        )
    for path, expected_kind in allowed_kinds.items():
        if path not in before:
            continue
        actual = before[path]
        if actual.kind != expected_kind:
            raise HarnessError(
                f"{label} root path kind differs from Git: "
                f"{display_git_path(path)}"
            )
        if expected_kind == "tree":
            continue
        entry = tree[path]
        if expected_kind == "blob":
            expected_executable = entry.mode == "100755"
            actual_executable = bool(actual.mode & 0o111)
            if actual_executable != expected_executable:
                raise HarnessError(
                    f"{label} root file mode differs from Git: "
                    f"{display_git_path(path)}"
                )

    object_format = git_result(
        git_dir,
        "rev-parse",
        "--show-object-format",
    )
    if object_format.returncode != 0:
        raise HarnessError("cannot determine Git object format")
    algorithm = object_format.stdout.strip()
    for path, entry in tree.items():
        if entry.mode == "160000":
            continue
        if entry.mode == "120000":
            data = read_snapshot_symlink(root, path)
        else:
            data = read_repo_regular_bytes(
                root,
                os.fsdecode(path),
                max_bytes=MAX_REQUIRED_FILE_BYTES,
            )
        if git_blob_id(data, algorithm) != entry.object_id:
            raise HarnessError(
                f"{label} root bytes differ from Git: {display_git_path(path)}"
            )

    after = filesystem_snapshot(root)
    if before != after:
        raise HarnessError(f"{label} source snapshot changed during validation")


def load_raw_contract_at_commit(
    git_dir: Path,
    sha: str,
    *,
    required: bool,
) -> dict[str, Any] | None:
    entry = git_tree_entries(git_dir, sha).get(os.fsencode(CONTRACT_PATH))
    if entry is None:
        if required:
            raise HarnessError("validated commit has no readable contract")
        return None
    if entry.mode not in {"100644", "100755"} or entry.object_type != "blob":
        raise HarnessError("validated commit contract is not a regular Git blob")
    completed = git_result(git_dir, "show", f"{sha}:{CONTRACT_PATH}")
    if completed.returncode != 0:
        raise HarnessError("cannot read validated commit contract")
    if len(completed.stdout.encode("utf-8")) > MAX_CONTRACT_BYTES:
        raise HarnessError("validated commit contract exceeds the size limit")
    contract = strict_json_loads(
        completed.stdout,
        "validated commit contract",
    )
    if not isinstance(contract, dict):
        raise HarnessError("validated commit contract root must be an object")
    return contract


def load_contract_at_commit(git_dir: Path, sha: str, root: Path) -> dict[str, Any]:
    contract = load_raw_contract_at_commit(git_dir, sha, required=True)
    assert contract is not None
    validate_contract(contract, root, check_files=False)
    return contract


def legacy_contract_repository(contract: dict[str, Any]) -> str | None:
    identities: set[str] = set()

    def record(value: Any, label: str, *, allow_none: bool = False) -> None:
        if value is None and allow_none:
            return
        if not isinstance(value, str) or REPOSITORY_RE.fullmatch(value) is None:
            raise HarnessError(
                f"recognized legacy contract has invalid repository identity: {label}"
            )
        if not value.lower().startswith("local/"):
            identities.add(value)

    for key in ("repository", "repo_full_name"):
        if key in contract:
            record(contract[key], key)
    if "repo" in contract:
        value = contract["repo"]
        if isinstance(value, dict):
            if "github_full_name" in value:
                record(
                    value["github_full_name"],
                    "repo.github_full_name",
                    allow_none=True,
                )
        else:
            record(value, "repo")
    project = contract.get("project")
    if isinstance(project, dict):
        if "repo_full_name" in project:
            record(
                project["repo_full_name"],
                "project.repo_full_name",
                allow_none=True,
            )
    if len(identities) > 1:
        raise HarnessError(
            "recognized legacy contract declares ambiguous repository identities"
        )
    return next(iter(identities)) if identities else None


def validate_recognized_legacy_contract(
    contract: dict[str, Any],
    candidate_repository: str,
) -> str:
    def has_fields(required: dict[str, type]) -> bool:
        return all(
            isinstance(contract.get(key), expected)
            for key, expected in required.items()
        )

    contract_version = contract.get("contract_version")
    has_schema_version = "schema_version" in contract
    has_numeric_version = "version" in contract
    generation: str | None = None
    if contract_version in {"legacy-v1", "legacy-v2"}:
        recognized = (
            not has_schema_version
            and not has_numeric_version
            and contract.get("mode") == "repo-native-agent-cicd"
            and has_fields(
                {
                    "repo": str,
                    "boundary": dict,
                    "checkpoint_gate": dict,
                    "codex_review": dict,
                }
            )
        )
        if recognized:
            generation = contract_version
    elif contract_version in {
        "agent-cicd-checkpoint-gate-v0",
        "agent-cicd-checkpoint-gate-v1",
    }:
        recognized = (
            not has_schema_version
            and not has_numeric_version
            and contract.get("mode") == "repo-native-agent-cicd"
            and has_fields(
                {
                    "repo": str,
                    "boundary": dict,
                    "checkpoint_gate": dict,
                    "codex_review": dict,
                }
            )
        )
        if recognized:
            generation = (
                "legacy-v1"
                if contract_version == "agent-cicd-checkpoint-gate-v0"
                else "legacy-v2"
            )
    elif contract_version == "woodpecker-rainierdev-actions-migration-v1":
        recognized = (
            not has_schema_version
            and not has_numeric_version
            and contract.get("mode") == "repo-native-agent-cicd"
            and has_fields(
                {
                    "repo": str,
                    "boundary": dict,
                    "checkpoint_gate": dict,
                    "codex_review": dict,
                    "actions_migration": dict,
                    "actions_outage_safety": dict,
                    "runtime_contract": dict,
                }
            )
        )
        if recognized:
            generation = "legacy-v2"
    elif contract_version == "workspace-harness-governance-v0":
        recognized = (
            not has_schema_version
            and not has_numeric_version
            and contract.get("mode") == "repo-native-agent-cicd"
            and has_fields(
                {
                    "repo": dict,
                    "entrypoints": dict,
                    "boundary": dict,
                    "validation_registry": dict,
                    "codex_review": dict,
                    "platform_gate": dict,
                }
            )
        )
        if recognized:
            generation = "legacy-v1"
    elif contract_version is None and has_schema_version:
        schema_version = contract.get("schema_version")
        valid_version = (
            isinstance(schema_version, int)
            and not isinstance(schema_version, bool)
            and schema_version == 1
            and not has_numeric_version
        )
        runtime_profile = (
            valid_version
            and contract.get("governance_model") == "agent-cicd"
            and "agent_cicd" not in contract
            and has_fields(
                {
                    "repo_full_name": str,
                    "entrypoints": dict,
                    "active_plan": dict,
                    "claims": list,
                    "required_local_checks": list,
                    "readiness": dict,
                }
            )
        )
        xhs_profile = (
            valid_version
            and "governance_model" not in contract
            and has_fields(
                {
                    "repo_full_name": str,
                    "agent_cicd": dict,
                    "claims": dict,
                    "allowed_pr1_paths": list,
                    "forbidden_without_explicit_authorization": list,
                    "validation_registry": dict,
                    "readiness": dict,
                }
            )
        )
        if runtime_profile != xhs_profile:
            generation = "legacy-v2"
    elif contract_version is None and has_numeric_version:
        numeric_version = contract.get("version")
        recognized = (
            isinstance(numeric_version, int)
            and not isinstance(numeric_version, bool)
            and numeric_version == 1
            and not has_schema_version
            and has_fields(
                {
                    "project": dict,
                    "agent_cicd": dict,
                    "claims": dict,
                    "gates": dict,
                    "forbidden_in_pr1": list,
                }
            )
        )
        if recognized:
            generation = "legacy-v2"
    if generation is None:
        raise HarnessError(
            "base contract does not match a recognized legacy shape"
        )
    identity = legacy_contract_repository(contract)
    if identity is not None and identity.lower() != candidate_repository.lower():
        raise HarnessError(
            "legacy and candidate repository identities do not match"
        )
    return generation


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
        if entry.paths == (RECEIPT_PATH,) and entry.status == "A"
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
    *,
    expected_repository: str | None = None,
    expected_repository_id: int | None = None,
    expected_default_branch: str | None = None,
) -> None:
    if git_dir is None or base_sha is None or head_sha is None:
        raise HarnessError(
            "candidate mode requires --git-dir, --base-sha, and --head-sha"
        )
    if not SHA_RE.fullmatch(base_sha) or not SHA_RE.fullmatch(head_sha):
        raise HarnessError("base and head must be full lowercase SHAs")
    if not git_commit_exists(git_dir, base_sha):
        raise HarnessError("candidate base commit does not exist in --git-dir")
    if not git_commit_exists(git_dir, head_sha):
        raise HarnessError("candidate head commit does not exist in --git-dir")
    if not git_is_ancestor(git_dir, base_sha, head_sha):
        raise HarnessError("candidate base is not an ancestor of head")

    validate_source_snapshot(
        git_dir,
        base_sha,
        trusted_root,
        label="trusted",
    )
    validate_source_snapshot(
        git_dir,
        head_sha,
        target_root,
        label="target",
    )

    candidate_contract = load_repo_json(target_root, CONTRACT_PATH)
    head_contract = load_contract_at_commit(git_dir, head_sha, target_root)
    if candidate_contract != head_contract:
        raise HarnessError("target root contract does not match head contract")
    validate_contract(candidate_contract, target_root)
    validate_expected_identity(
        candidate_contract,
        expected_repository=expected_repository,
        expected_repository_id=expected_repository_id,
        expected_default_branch=expected_default_branch,
    )
    trusted_contract = load_raw_contract_at_commit(
        git_dir,
        base_sha,
        required=False,
    )
    partial_v3 = v3_artifact_paths(trusted_root)
    if trusted_contract is None:
        legacy = legacy_runtime_paths(trusted_root)
        if legacy:
            raise HarnessError(
                "contractless base with legacy Harness runtime is unknown: "
                + ", ".join(legacy)
            )
        if partial_v3:
            raise HarnessError(
                "contractless base contains partial v3 Harness artifacts: "
                + ", ".join(partial_v3)
            )
    entries = git_diff_entries(git_dir, base_sha, head_sha)
    paths = sorted(changed_paths(entries))
    if (
        trusted_contract is None
        or trusted_contract.get("contract_version") != CONTRACT_VERSION
    ):
        if trusted_contract is not None:
            validate_recognized_legacy_contract(
                trusted_contract,
                candidate_contract["repository"],
            )
            if partial_v3:
                raise HarnessError(
                    "legacy base is mixed with v3 Harness artifacts: "
                    + ", ".join(partial_v3)
                )
            trusted_root_contract = load_repo_json(trusted_root, CONTRACT_PATH)
            if trusted_root_contract != trusted_contract:
                raise HarnessError(
                    "trusted root contract does not match base contract"
                )
        if CONTRACT_PATH not in paths:
            raise HarnessError(
                "initial pending establishment must add or replace the contract"
            )
        if candidate_contract["platform_gate"]["state"] != "pending":
            raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)
        validate_active_plan(target_root, candidate_contract)
        validate_eval_rules(target_root)
        validate_pending_establishment(target_root, candidate_contract)
        audit = normalize_specs(
            candidate_contract["audit_state_paths"],
            "audit_state_paths",
        )
        if any(matches_any(path, audit) for path in paths):
            raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)
        raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)

    trusted_root_contract = load_repo_json(trusted_root, CONTRACT_PATH)
    if trusted_root_contract != trusted_contract:
        raise HarnessError("trusted root contract does not match base contract")
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

    validate_candidate_contract_transition(
        trusted_contract,
        candidate_contract,
        trusted_root,
        target_root,
    )
    validate_active_plan(target_root, trusted_contract)
    if (
        active_plan_required_sections(candidate_contract)
        != active_plan_required_sections(trusted_contract)
        or active_plan_required_fields(candidate_contract)
        != active_plan_required_fields(trusted_contract)
        or active_plan_required_tables(candidate_contract)
        != active_plan_required_tables(trusted_contract)
    ):
        validate_active_plan(target_root, candidate_contract)
    validate_eval_rules(target_root)
    trusted_state = trusted_contract["platform_gate"]["state"]
    candidate_state = candidate_contract["platform_gate"]["state"]
    if trusted_state == "active" or candidate_state == "active":
        raise HarnessError(EXTERNAL_AUTHORITY_REQUIRED)
    validate_pending_establishment(target_root, candidate_contract)

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
    parser.add_argument("--self-test-rendering", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.self_test_rendering:
            if (
                args.repo
                or args.trusted_root
                or args.target_root
                or args.git_dir
                or args.base_sha
                or args.head_sha
                or args.expected_repository
                or args.expected_repository_id is not None
                or args.expected_default_branch
                or args.check_platform
            ):
                raise HarnessError(
                    "--self-test-rendering cannot be combined with verification arguments"
                )
            self_test_rendered_plan_text()
        elif args.repo:
            if any(
                value is not None
                for value in (
                    args.trusted_root,
                    args.target_root,
                    args.git_dir,
                    args.base_sha,
                    args.head_sha,
                )
            ):
                raise HarnessError(
                    "--repo cannot be combined with candidate-mode arguments"
                )
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
            if args.git_dir is None or args.base_sha is None or args.head_sha is None:
                raise HarnessError(
                    "candidate mode requires --git-dir, --base-sha, and --head-sha"
                )
            verify_candidate(
                args.trusted_root.resolve(),
                args.target_root.resolve(),
                args.git_dir.resolve(),
                args.base_sha,
                args.head_sha,
                expected_repository=args.expected_repository,
                expected_repository_id=args.expected_repository_id,
                expected_default_branch=args.expected_default_branch,
            )
    except HarnessError as exc:
        print(f"harness check failed: {exc}", file=sys.stderr)
        return 1
    if args.self_test_rendering:
        print("harness plan rendering self-test passed")
    else:
        print("harness diagnostic structure check passed; readiness is not established")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
