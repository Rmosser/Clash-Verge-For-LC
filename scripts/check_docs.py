#!/usr/bin/env python3
"""Validate the repository's context map and local Markdown links."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "doc-sync-rules.json"
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
LOCAL_ABSOLUTE_RE = re.compile(r"(?:file://|/Users/)")
VENDOR_BOUNDARY = (
    ROOT / "src" / "mihomo-dashboard-app" / "vendor" / "clash-verge-rev" / "README.local.txt"
)


def fail(message: str) -> None:
    print(f"check_docs: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_manifest() -> dict[str, object]:
    try:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing manifest: {MANIFEST.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {MANIFEST.relative_to(ROOT)}: {exc}")
    if not isinstance(payload, dict):
        fail("manifest top-level value must be an object")
    return payload


def path_from_root(relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        fail(f"manifest path must be relative: {relative!r}")
    candidate = (ROOT / relative).resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError:
        fail(f"manifest path escapes repository: {relative!r}")
    return candidate


def local_links(markdown: Path) -> list[tuple[str, Path]]:
    links: list[tuple[str, Path]] = []
    for match in LINK_RE.finditer(markdown.read_text(encoding="utf-8")):
        raw = unquote(match.group(1).split("#", 1)[0].strip())
        if not raw or raw.startswith(("http://", "https://", "mailto:")):
            continue
        target = (markdown.parent / raw).resolve()
        try:
            target.relative_to(ROOT)
        except ValueError:
            fail(f"link escapes repository: {markdown.relative_to(ROOT)} -> {raw}")
        links.append((raw, target))
    return links


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="run the full documentation check")
    parser.parse_args()

    manifest = load_manifest()
    required = manifest.get("required_paths")
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        fail("required_paths must be a list of strings")
    for relative in required:
        if not path_from_root(relative).exists():
            fail(f"missing required path: {relative}")

    markdown_paths = manifest.get("markdown_paths")
    if not isinstance(markdown_paths, list) or not all(
        isinstance(item, str) for item in markdown_paths
    ):
        fail("markdown_paths must be a list of strings")
    for relative in markdown_paths:
        markdown = path_from_root(relative)
        if not markdown.is_file():
            fail(f"markdown path is not a file: {relative}")
        if LOCAL_ABSOLUTE_RE.search(markdown.read_text(encoding="utf-8")):
            fail(f"non-portable local path in markdown: {relative}")
        for raw, target in local_links(markdown):
            if not target.exists():
                fail(f"broken link: {relative} -> {raw}")

    vendor_boundary = VENDOR_BOUNDARY.read_text(encoding="utf-8")
    if "not local repository authority" not in vendor_boundary or "complete upstream repository" not in vendor_boundary:
        fail("vendor README.local.txt must explain the partial upstream snapshot boundary")

    entries = manifest.get("entrypoint_links")
    if not isinstance(entries, list):
        fail("entrypoint_links must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            fail("entrypoint_links entries must be objects")
        source_value = entry.get("source")
        targets = entry.get("targets")
        if not isinstance(source_value, str) or not isinstance(targets, list):
            fail("entrypoint link entries require source and targets")
        source = path_from_root(source_value)
        links = {target for _, target in local_links(source)}
        for target_value in targets:
            if not isinstance(target_value, str):
                fail(f"entrypoint target must be a string: {source_value}")
            target = (source.parent / target_value).resolve()
            if target not in links:
                fail(f"entrypoint link missing: {source_value} -> {target_value}")

    print("Documentation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
