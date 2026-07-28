#!/usr/bin/env python3
"""Validate the repository-owned documentation inventory and entrypoint links."""

from __future__ import annotations

import argparse
import copy
import json
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = "docs/doc-sync-rules.json"
LINK_RE = re.compile(r"\[[^\]]*\]\(\s*(?:<([^>\r\n]+)>|([^\s)]+))")
INLINE_CODE_RE = re.compile(r"(?P<ticks>`+)[^\r\n]*?(?P=ticks)")
COMMONMARK_BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|"
    "colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|"
    "footer|form|frame|frameset|h1|h2|h3|h4|h5|h6|head|header|hr|html|"
    "iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|"
    "option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|"
    "title|tr|track|ul"
)
RAW_HTML_BLOCK_START_RE = re.compile(
    rf"^[ \t]{{0,3}}(?:"
    rf"</?(?:script|pre|style|textarea)(?=[ \t>/])|"
    rf"</?(?:{COMMONMARK_BLOCK_TAGS})(?=[ \t>/])|"
    r"<\?|<![A-Z]|<!\[CDATA\[|"
    r"</?[A-Za-z][^<]*>[ \t]*$"
    r")",
    re.IGNORECASE,
)


class DocsError(ValueError):
    pass


def fail(message: str) -> None:
    raise DocsError(message)


def visible_markdown(text: str) -> str:
    lines: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if fence is not None:
            marker = re.fullmatch(r"[ \t]{0,3}(`{3,}|~{3,})[ \t]*", content)
            if (
                marker is not None
                and marker.group(1)[0] == fence[0]
                and len(marker.group(1)) >= fence[1]
            ):
                fence = None
            lines.append("\n" if line.endswith("\n") else "")
            continue
        marker = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})([^\r\n]*)$", content)
        if marker is not None:
            delimiter = marker.group(1)
            info = marker.group(2)
            if delimiter[0] != "`" or "`" not in info:
                fence = (delimiter[0], len(delimiter))
                lines.append("\n" if line.endswith("\n") else "")
                continue
        if line.startswith(("\t", "    ")):
            lines.append("\n" if line.endswith("\n") else "")
            continue
        lines.append(INLINE_CODE_RE.sub("", line))
    if fence is not None:
        fail("documentation contains an unterminated fenced code block")
    visible = re.sub(
        r"<!--.*?-->",
        lambda match: "\n" * match.group(0).count("\n"),
        "".join(lines),
        flags=re.DOTALL,
    )
    if "<!--" in visible or "-->" in visible:
        fail("documentation contains a malformed HTML comment")
    if any(RAW_HTML_BLOCK_START_RE.match(line) for line in visible.splitlines()):
        fail("documentation contains raw HTML block markup")
    return visible


def markdown_character_is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def canonical_relative(
    value: Any,
    label: str,
    *,
    allow_parent: bool = False,
) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        fail(f"{label} must be a non-empty POSIX path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", "."} for part in relative.parts):
        fail(f"{label} must be repository-relative")
    if not allow_parent and ".." in relative.parts:
        fail(f"{label} must not contain parent traversal")
    return relative


def bounded_path(
    root: Path,
    relative: PurePosixPath,
    label: str,
    *,
    require_file: bool = False,
) -> Path:
    candidate = root.joinpath(*relative.parts)
    try:
        candidate.resolve(strict=False).relative_to(root.resolve())
    except (OSError, ValueError):
        fail(f"{label} escapes the repository")
    current = root
    for part in relative.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError:
            fail(f"{label} is missing: {relative.as_posix()}")
        if stat.S_ISLNK(metadata.st_mode):
            fail(f"{label} uses a symlink: {relative.as_posix()}")
    metadata = candidate.lstat()
    if require_file and not stat.S_ISREG(metadata.st_mode):
        fail(f"{label} must be a regular file: {relative.as_posix()}")
    if not require_file and not (
        stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)
    ):
        fail(f"{label} must be a regular file or directory: {relative.as_posix()}")
    return candidate


def link_targets(source: Path, root: Path) -> set[Path]:
    try:
        text = visible_markdown(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read {source.relative_to(root).as_posix()}: {exc}")
    raw_targets: list[str] = []
    for match in LINK_RE.finditer(text):
        opening_bracket = match.start()
        if markdown_character_is_escaped(text, opening_bracket):
            continue
        if (
            opening_bracket > 0
            and text[opening_bracket - 1] == "!"
            and not markdown_character_is_escaped(text, opening_bracket - 1)
        ):
            continue
        raw_targets.append((match.group(1) or match.group(2) or "").strip())
    targets: set[Path] = set()
    for raw in raw_targets:
        if raw.startswith(("http://", "https://", "mailto:", "#")):
            continue
        raw = raw.split("#", 1)[0]
        if not raw:
            continue
        target = canonical_relative(raw, "Markdown link", allow_parent=True)
        resolved = (source.parent / Path(*target.parts)).resolve(strict=False)
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            fail(
                f"Markdown link escapes the repository in "
                f"{source.relative_to(root).as_posix()}: {raw}"
            )
        targets.add(resolved)
    return targets


def validate(value: Any, root: Path = ROOT) -> None:
    expected_keys = {
        "contract_version",
        "required_paths",
        "audit_state_path",
        "entrypoint_links",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        fail(f"{RULES_PATH} must contain exactly {sorted(expected_keys)}")
    if value["contract_version"] != "repo-harness-doc-sync-v1":
        fail("unsupported documentation inventory contract version")
    if value["audit_state_path"] != ".harness/baseline-receipt.json":
        fail("audit_state_path must name the Harness baseline receipt")

    required = value["required_paths"]
    if (
        not isinstance(required, list)
        or not required
        or not all(isinstance(item, str) and item for item in required)
        or len(required) != len(set(required))
    ):
        fail("required_paths must be a unique non-empty string list")
    for index, raw in enumerate(required):
        relative = canonical_relative(raw, f"required_paths[{index}]")
        bounded_path(root, relative, f"required_paths[{index}]")

    entries = value["entrypoint_links"]
    if not isinstance(entries, list) or not entries:
        fail("entrypoint_links must be a non-empty list")
    seen_sources: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"source", "targets"}:
            fail(f"entrypoint_links[{index}] must contain source and targets")
        source_raw = entry["source"]
        source_relative = canonical_relative(
            source_raw,
            f"entrypoint_links[{index}].source",
        )
        source = bounded_path(
            root,
            source_relative,
            f"entrypoint_links[{index}].source",
            require_file=True,
        )
        if source_raw in seen_sources:
            fail(f"entrypoint_links source is duplicated: {source_raw}")
        seen_sources.add(source_raw)
        targets = entry["targets"]
        if (
            not isinstance(targets, list)
            or not targets
            or not all(isinstance(item, str) and item for item in targets)
            or len(targets) != len(set(targets))
        ):
            fail(
                f"entrypoint_links[{index}].targets must be a unique "
                "non-empty string list"
            )
        actual_links = link_targets(source, root)
        for target_index, raw_target in enumerate(targets):
            target_relative = canonical_relative(
                raw_target,
                f"entrypoint_links[{index}].targets[{target_index}]",
                allow_parent=True,
            )
            target = (source.parent / Path(*target_relative.parts)).resolve(strict=False)
            try:
                relative_to_root = PurePosixPath(
                    target.relative_to(root.resolve()).as_posix()
                )
            except ValueError:
                fail(
                    f"entrypoint_links[{index}].targets[{target_index}] escapes "
                    "the repository"
                )
            if target not in actual_links:
                fail(f"entrypoint {source_raw} does not link to {raw_target}")
            bounded_path(
                root,
                relative_to_root,
                f"entrypoint_links[{index}].targets[{target_index}]",
            )


def self_test(value: dict[str, Any]) -> None:
    fixtures: list[tuple[str, dict[str, Any]]] = []
    missing_path = copy.deepcopy(value)
    missing_path["required_paths"].append("docs/does-not-exist.md")
    fixtures.append(("missing required path", missing_path))
    missing_link = copy.deepcopy(value)
    missing_link["entrypoint_links"][0]["targets"].append(
        "docs/does-not-exist.md"
    )
    fixtures.append(("missing entrypoint link", missing_link))
    for label, fixture in fixtures:
        try:
            validate(fixture)
        except DocsError:
            continue
        fail(f"negative self-test unexpectedly passed: {label}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        value = json.loads((ROOT / RULES_PATH).read_text(encoding="utf-8"))
        validate(value)
        if args.self_test:
            self_test(value)
    except (OSError, UnicodeError, json.JSONDecodeError, DocsError) as exc:
        print(f"documentation inventory failed: {exc}", file=sys.stderr)
        return 1
    print("documentation inventory passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
