#!/usr/bin/env python3
"""Validate the repository-owned documentation inventory and entrypoint links."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import stat
import string
import sys
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple


ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = "docs/doc-sync-rules.json"
REFERENCE_DEFINITION_RE = re.compile(
    r"^[ ]{0,3}\[(?P<label>(?:\\[^\n]|[^\\\[\]\n])+)\]:[ \t]*"
    r"(?P<destination><[^>\n]+>|[^ \t\n]+)"
    r"(?:[ \t]+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?[ \t]*$"
)
REFERENCE_DEFINITION_PREFIX_RE = re.compile(
    r"^[ ]{0,3}\[(?:\\[^\n]|[^\\\[\]\n])+\]:"
)
FULL_REFERENCE_LINK_RE = re.compile(
    r"(?P<image>!)?\[(?P<text>(?:\\[^\n]|[^\\\]\n])*)\]"
    r"\[(?P<label>(?:\\[^\n]|[^\\\[\]\n])*)\]"
)
SHORTCUT_REFERENCE_LINK_RE = re.compile(
    r"(?P<image>!)?\[(?P<label>(?:\\[^\n]|[^\\\[\]\n])+)\](?![\[(])"
)
COMMONMARK_AUTOLINK_RE = re.compile(
    r"<(?:"
    r"[A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\x00-\x20]*"
    r"|[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?"
    r")>"
)
HTML_ATTRIBUTE = (
    r"[A-Za-z_:][A-Za-z0-9_.:-]*"
    r"(?:[ \t]*=[ \t]*(?:[^ \t\n\"'=<>`]+|'[^']*'|\"[^\"]*\"))?"
)
INLINE_HTML_TAG_RE = re.compile(
    rf"</?[A-Za-z][A-Za-z0-9-]*(?:[ \t]+{HTML_ATTRIBUTE})*[ \t]*/?>"
)
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
    rf"</?(?:script|pre|style|textarea)(?=[ \t>/]|$)|"
    rf"</?(?:{COMMONMARK_BLOCK_TAGS})(?=[ \t>/]|$)|"
    r"<\?|<![A-Z]|<!\[CDATA\[|"
    r"</?[A-Za-z][A-Za-z0-9-]*(?:[ \t]+[^<>\r\n]*)?/?[ \t]*>[ \t]*$"
    r")",
    re.IGNORECASE,
)


class DocsError(ValueError):
    pass


class InlineLinkCandidate(NamedTuple):
    start: int
    end: int
    opening_bracket: int
    closing_bracket: int
    image: bool
    destination: str


def fail(message: str) -> None:
    raise DocsError(message)


def reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            fail(f"{RULES_PATH} contains duplicate JSON key: {key}")
        value[key] = item
    return value


def strict_json_loads(text: str) -> Any:
    return json.loads(text, object_pairs_hook=reject_duplicate_json_keys)


def indentation_columns(line: str) -> int:
    columns = 0
    for character in line:
        if character == " ":
            columns += 1
        elif character == "\t":
            columns += 4 - (columns % 4)
        else:
            break
    return columns


def strip_commonmark_container_prefixes(line: str) -> tuple[str, bool]:
    normalized = line
    changed = False
    while True:
        previous = normalized
        normalized = re.sub(r"^[ \t]{0,3}>[ \t]?", "", normalized, count=1)
        normalized = re.sub(
            r"^[ \t]{0,3}(?:[-+*]|\d{1,9}[.)])(?:[ \t]+|$)",
            "",
            normalized,
            count=1,
        )
        if normalized == previous:
            return normalized, changed
        changed = True


def strip_code_spans(text: str) -> str:
    output: list[str] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] != "`":
            output.append(text[cursor])
            cursor += 1
            continue
        run_end = cursor
        while run_end < len(text) and text[run_end] == "`":
            run_end += 1
        delimiter = text[cursor:run_end]
        search = run_end
        closing = -1
        while True:
            candidate = text.find(delimiter, search)
            if candidate < 0:
                break
            before_is_tick = candidate > 0 and text[candidate - 1] == "`"
            after = candidate + len(delimiter)
            after_is_tick = after < len(text) and text[after] == "`"
            if not before_is_tick and not after_is_tick:
                closing = candidate
                break
            search = candidate + 1
        if closing < 0:
            output.append(delimiter)
            cursor = run_end
            continue
        span_end = closing + len(delimiter)
        output.append(
            "".join(
                character if character in {"\n", "\r"} else " "
                for character in text[cursor:span_end]
            )
        )
        cursor = span_end
    return "".join(output)


def strip_inline_code_and_html_comments(text: str) -> str:
    output: list[str] = []
    cursor = 0
    while cursor < len(text):
        if text.startswith("<!--", cursor):
            end = text.find("-->", cursor + 4)
            if end < 0:
                fail("documentation contains a malformed HTML comment")
            output.append("\n" * text[cursor : end + 3].count("\n"))
            cursor = end + 3
            continue
        if text.startswith("-->", cursor):
            fail("documentation contains a malformed HTML comment")
        if text[cursor] == "`" and not markdown_character_is_escaped(text, cursor):
            run_end = cursor + 1
            while run_end < len(text) and text[run_end] == "`":
                run_end += 1
            delimiter = text[cursor:run_end]
            search = run_end
            span_end = -1
            while True:
                closing = text.find(delimiter, search)
                if closing < 0:
                    break
                after = closing + len(delimiter)
                if (
                    not markdown_character_is_escaped(text, closing)
                    and (closing == 0 or text[closing - 1] != "`")
                    and (after == len(text) or text[after] != "`")
                ):
                    span_end = after
                    output.append(
                        "\n" * text[cursor:span_end].count("\n")
                    )
                    break
                search = closing + 1
            if span_end >= 0:
                cursor = span_end
                continue
            output.append(delimiter)
            cursor = run_end
            continue
        output.append(text[cursor])
        cursor += 1
    return "".join(output)


def visible_markdown(text: str) -> str:
    def contains_multiline_html_tag(value: str) -> bool:
        cursor = 0
        while cursor < len(value):
            opening = value.find("<", cursor)
            if opening < 0:
                return False
            tag = opening + 1
            if tag < len(value) and value[tag] == "/":
                tag += 1
            if tag >= len(value) or not value[tag].isalpha():
                cursor = opening + 1
                continue
            while tag < len(value) and (
                value[tag].isalnum() or value[tag] == "-"
            ):
                tag += 1
            if (
                tag < len(value)
                and value[tag] not in " \t/>"
                and value[tag] not in "\r\n"
            ):
                cursor = opening + 1
                continue
            quote: str | None = None
            scan = tag
            while scan < len(value):
                character = value[scan]
                if character in "\r\n":
                    return True
                if quote is not None:
                    if character == quote:
                        quote = None
                elif character in {'"', "'"}:
                    quote = character
                elif character == ">":
                    break
                scan += 1
            cursor = scan + 1
        return False

    lines: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        container_content, has_container = strip_commonmark_container_prefixes(
            content
        )
        if has_container and (
            re.match(r"^[ \t]{0,3}(`{3,}|~{3,})", container_content)
            or (
                container_content.strip()
                and indentation_columns(container_content) >= 4
            )
        ):
            fail("documentation contains code inside a Markdown container")
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
        lines.append(line)
    if fence is not None:
        fail("documentation contains an unterminated fenced code block")
    visible = strip_inline_code_and_html_comments("".join(lines))
    if contains_multiline_html_tag(visible):
        fail("documentation contains multiline inline HTML")
    if any(
        RAW_HTML_BLOCK_START_RE.match(
            strip_commonmark_container_prefixes(line)[0]
        )
        for line in visible.splitlines()
    ):
        fail("documentation contains raw HTML block markup")
    return visible


def markdown_character_is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def markdown_unescape(label: str) -> str:
    output: list[str] = []
    cursor = 0
    while cursor < len(label):
        if (
            label[cursor] == "\\"
            and cursor + 1 < len(label)
            and label[cursor + 1] in string.punctuation
        ):
            output.append(label[cursor + 1])
            cursor += 2
            continue
        output.append(label[cursor])
        cursor += 1
    return "".join(output)


def normalized_reference_label(label: str) -> str:
    return " ".join(markdown_unescape(label).split()).casefold()


def inline_whitespace_end(text: str, cursor: int) -> int | None:
    line_endings = 0
    while cursor < len(text) and text[cursor].isspace():
        if text[cursor] == "\r":
            line_endings += 1
            cursor += 1
            if cursor < len(text) and text[cursor] == "\n":
                cursor += 1
        elif text[cursor] == "\n":
            line_endings += 1
            cursor += 1
        else:
            cursor += 1
        if line_endings > 1:
            return None
    return cursor


def inline_link_end_after_title(
    text: str,
    cursor: int,
) -> int | None:
    whitespace_start = cursor
    cursor = inline_whitespace_end(text, cursor)
    if cursor is None:
        return None
    if cursor < len(text) and text[cursor] == ")":
        return cursor + 1
    if cursor == whitespace_start:
        return None
    if cursor >= len(text) or text[cursor] not in {'"', "'", "("}:
        return None
    opening = text[cursor]
    closing = ")" if opening == "(" else opening
    cursor += 1
    while cursor < len(text):
        if text[cursor] in "\r\n":
            return None
        if (
            text[cursor] == "\\"
            and cursor + 1 < len(text)
            and text[cursor + 1] in string.punctuation
        ):
            cursor += 2
            continue
        if text[cursor] == closing:
            cursor += 1
            break
        cursor += 1
    else:
        return None
    cursor = inline_whitespace_end(text, cursor)
    if cursor is not None and cursor < len(text) and text[cursor] == ")":
        return cursor + 1
    return None


def inline_link_tail(
    text: str,
    cursor: int,
) -> tuple[int, str] | None:
    if cursor >= len(text) or text[cursor] != "(":
        return None
    cursor = inline_whitespace_end(text, cursor + 1)
    if cursor is None or cursor >= len(text):
        return None
    destination_start = cursor
    if text[cursor] == "<":
        cursor += 1
        while cursor < len(text):
            if text[cursor] in "\r\n<":
                return None
            if text[cursor] == ">":
                destination = text[destination_start : cursor + 1]
                end = inline_link_end_after_title(text, cursor + 1)
                return (end, destination) if end is not None else None
            cursor += 1
        return None
    depth = 0
    while cursor < len(text):
        character = text[cursor]
        if (
            character == "\\"
            and cursor + 1 < len(text)
            and text[cursor + 1] in string.punctuation
        ):
            cursor += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                return cursor + 1, text[destination_start:cursor]
            depth -= 1
        elif character.isspace():
            if depth != 0:
                return None
            end = inline_link_end_after_title(text, cursor)
            if end is None:
                return None
            return end, text[destination_start:cursor]
        elif character in "<>":
            return None
        cursor += 1
    return None


def inline_link_candidates(
    text: str,
) -> list[InlineLinkCandidate]:
    """Return balanced CommonMark inline candidates with nested-link filtering."""

    candidates: list[InlineLinkCandidate] = []
    cursor = 0
    while cursor < len(text):
        bracket = text.find("[", cursor)
        if bracket < 0:
            break

        depth = 1
        label_cursor = bracket + 1
        while label_cursor < len(text):
            character = text[label_cursor]
            if not markdown_character_is_escaped(text, label_cursor):
                if character == "[":
                    depth += 1
                elif character == "]":
                    depth -= 1
                    if depth == 0:
                        break
            label_cursor += 1
        if depth != 0:
            cursor = bracket + 1
            continue

        tail = inline_link_tail(text, label_cursor + 1)
        if tail is None:
            cursor = bracket + 1
            continue

        has_image_prefix = bracket > 0 and text[bracket - 1] == "!"
        image = bool(
            has_image_prefix
            and not markdown_character_is_escaped(text, bracket - 1)
        )
        start = bracket - 1 if has_image_prefix else bracket
        candidates.append(
            InlineLinkCandidate(
                start,
                tail[0],
                bracket,
                label_cursor,
                image,
                tail[1].strip(),
            )
        )
        cursor = bracket + 1

    filtered: list[InlineLinkCandidate] = []
    for candidate in candidates:
        inside_image = any(
            outer.image
            and outer.opening_bracket < candidate.opening_bracket
            and candidate.end <= outer.closing_bracket
            for outer in candidates
        )
        if inside_image:
            continue
        nested_link = any(
            not inner.image
            and not markdown_character_is_escaped(
                text,
                inner.opening_bracket,
            )
            and candidate.opening_bracket < inner.opening_bracket
            and inner.end <= candidate.closing_bracket
            for inner in candidates
        )
        if nested_link:
            continue
        filtered.append(candidate)
    return filtered


def raw_link_targets(text: str) -> list[str]:
    visible = visible_markdown(text)
    definitions: dict[str, str] = {}
    content_lines: list[str] = []
    for line in visible.splitlines():
        definition = REFERENCE_DEFINITION_RE.fullmatch(line)
        if definition:
            label = normalized_reference_label(definition.group("label"))
            if not label or label in definitions:
                fail("documentation has an empty or duplicate reference label")
            definitions[label] = definition.group("destination")
            content_lines.append("")
            continue
        if REFERENCE_DEFINITION_PREFIX_RE.match(line):
            fail("documentation has an unsupported reference definition")
        content_lines.append(line)
    content = "\n".join(content_lines)
    angle_spans = sorted(
        {
            match.span()
            for pattern in (COMMONMARK_AUTOLINK_RE, INLINE_HTML_TAG_RE)
            for match in pattern.finditer(content)
        }
    )
    reference_characters = list(content)
    for start, end in angle_spans:
        reference_characters[start:end] = " " * (end - start)
    reference_content = "".join(reference_characters)

    full_references: list[tuple[re.Match[str], str]] = []
    full_reference_spans: list[tuple[int, int]] = []
    for match in FULL_REFERENCE_LINK_RE.finditer(reference_content):
        full_reference_spans.append(match.span())
        bracket = match.start() + (1 if match.group("image") else 0)
        image = bool(
            match.group("image")
            and not markdown_character_is_escaped(
                reference_content,
                match.start(),
            )
        )
        if image or markdown_character_is_escaped(reference_content, bracket):
            continue
        label = match.group("label") or match.group("text")
        destination = definitions.get(normalized_reference_label(label))
        if destination is not None:
            full_references.append((match, destination.strip()))

    shortcut_references: list[tuple[re.Match[str], str]] = []
    for match in SHORTCUT_REFERENCE_LINK_RE.finditer(reference_content):
        if any(
            start <= match.start() and match.end() <= end
            for start, end in full_reference_spans
        ):
            continue
        bracket = match.start() + (1 if match.group("image") else 0)
        image = bool(
            match.group("image")
            and not markdown_character_is_escaped(
                reference_content,
                match.start(),
            )
        )
        if image or markdown_character_is_escaped(reference_content, bracket):
            continue
        destination = definitions.get(
            normalized_reference_label(match.group("label"))
        )
        if destination is not None:
            shortcut_references.append((match, destination.strip()))

    resolved_reference_spans = [
        match.span()
        for match, _ in full_references + shortcut_references
    ]

    def label_contains_resolved_reference(
        candidate: InlineLinkCandidate,
    ) -> bool:
        label = reference_content[
            candidate.opening_bracket + 1 : candidate.closing_bracket
        ]
        full_spans: list[tuple[int, int]] = []
        for match in FULL_REFERENCE_LINK_RE.finditer(label):
            full_spans.append(match.span())
            reference_label = match.group("label") or match.group("text")
            if (
                definitions.get(
                    normalized_reference_label(reference_label)
                )
                is not None
            ):
                return True
        for match in SHORTCUT_REFERENCE_LINK_RE.finditer(label):
            if any(
                start <= match.start() and match.end() <= end
                for start, end in full_spans
            ):
                continue
            if (
                definitions.get(
                    normalized_reference_label(match.group("label"))
                )
                is not None
            ):
                return True
        return False

    raw_targets: list[str] = []
    occupied_spans: list[tuple[int, int]] = []
    for candidate in inline_link_candidates(content):
        if any(
            start <= candidate.opening_bracket < end
            or start <= candidate.closing_bracket < end
            for start, end in angle_spans
        ):
            continue
        if candidate.image or markdown_character_is_escaped(
            content,
            candidate.opening_bracket,
        ):
            continue
        if any(
            candidate.opening_bracket < start
            and end <= candidate.closing_bracket
            for start, end in resolved_reference_spans
        ) or label_contains_resolved_reference(candidate):
            continue
        occupied_spans.append((candidate.start, candidate.end))
        raw_targets.append(candidate.destination)
    for match, destination in full_references:
        occupied_spans.append(match.span())
        raw_targets.append(destination)
    for match, destination in shortcut_references:
        if any(
            start <= match.start() and match.end() <= end
            for start, end in occupied_spans
        ):
            continue
        raw_targets.append(destination)
    return raw_targets


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


def read_regular_no_symlink_text(
    root: Path,
    relative: PurePosixPath,
    label: str,
) -> str:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        fail(f"{label} cannot be opened safely on this platform")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        directory_flags |= os.O_CLOEXEC
        file_flags |= os.O_CLOEXEC

    directory_fds: list[int] = []
    file_fd = -1
    try:
        current_fd = os.open(root, directory_flags)
        directory_fds.append(current_fd)
        for part in relative.parts[:-1]:
            current_fd = os.open(
                part,
                directory_flags,
                dir_fd=current_fd,
            )
            directory_fds.append(current_fd)
        file_fd = os.open(
            relative.parts[-1],
            file_flags,
            dir_fd=current_fd,
        )
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            fail(f"{label} must be a regular no-symlink file")
        with os.fdopen(file_fd, "r", encoding="utf-8") as handle:
            file_fd = -1
            return handle.read()
    except OSError as exc:
        fail(f"cannot safely read {label}: {exc}")
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        for directory_fd in reversed(directory_fds):
            os.close(directory_fd)


def load_rules(root: Path = ROOT) -> Any:
    relative = canonical_relative(RULES_PATH, "documentation rules path")
    text = read_regular_no_symlink_text(root, relative, RULES_PATH)
    return strict_json_loads(text)


def link_targets(source: Path, root: Path) -> set[Path]:
    try:
        raw_targets = raw_link_targets(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read {source.relative_to(root).as_posix()}: {exc}")
    targets: set[Path] = set()
    for raw in raw_targets:
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1].strip()
        if raw.startswith(("http://", "https://", "mailto:", "#")):
            continue
        raw = raw.split("#", 1)[0]
        if not raw:
            continue
        target = canonical_relative(raw, "Markdown link", allow_parent=True)
        resolved = (source.parent / Path(*target.parts)).resolve(strict=False)
        try:
            relative_to_root = PurePosixPath(
                resolved.relative_to(root.resolve()).as_posix()
            )
        except ValueError:
            fail(
                f"Markdown link escapes the repository in "
                f"{source.relative_to(root).as_posix()}: {raw}"
            )
        bounded_path(
            root,
            relative_to_root,
            f"Markdown link target from {source.relative_to(root).as_posix()}",
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
    for label, hidden in (
        (
            "container fence",
            "> ```\n> [hidden](docs/index.md)\n> ```\n",
        ),
        (
            "multiline code span",
            "`start\n[hidden](docs/index.md)\nend`\n",
        ),
    ):
        try:
            targets = raw_link_targets(hidden)
        except DocsError:
            continue
        if not targets:
            continue
        fail(f"negative self-test exposed a link inside {label}")
    nested = "[documentation [index]](docs/index.md)\n"
    if raw_link_targets(nested) != ["docs/index.md"]:
        fail("positive self-test rejected a nested inline-link label")
    balanced = "[documentation](docs/index_(advanced).md)\n"
    if raw_link_targets(balanced) != ["docs/index_(advanced).md"]:
        fail("positive self-test rejected a balanced inline destination")
    if raw_link_targets("<https://example.com>\n"):
        fail("URI autolink was treated as a repository link")
    try:
        raw_link_targets(
            '<span\n title="[documentation](docs/index.md)">text</span>\n'
        )
    except DocsError:
        pass
    else:
        fail("negative self-test accepted multiline inline HTML")
    nested_reference = (
        "[Outer [Inner][inside]](docs/index.md)\n"
        "[inside]: docs/inside.md\n"
    )
    if raw_link_targets(nested_reference) != ["docs/inside.md"]:
        fail("nested full-reference link precedence self-test failed")
    nested_shortcut = (
        "[Outer [Inner]](docs/index.md)\n"
        "[Inner]: docs/inside.md\n"
    )
    if raw_link_targets(nested_shortcut) != ["docs/inside.md"]:
        fail("nested shortcut-reference link precedence self-test failed")
    nested_image = "![documentation [image]](docs/missing.md)\n"
    if raw_link_targets(nested_image):
        fail("negative self-test treated a nested image as navigation")
    try:
        strict_json_loads('{"required_paths": [], "required_paths": []}')
    except DocsError:
        pass
    else:
        fail("negative self-test accepted a duplicate JSON key")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        value = load_rules(ROOT)
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
