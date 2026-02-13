#!/usr/bin/env python3
"""
Dependency-free patcher: restrict proxy-groups.AUTO.proxies to a given list.

We deliberately avoid YAML libs here so this can run on a minimal dev machine.
"""

from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path


def _find_line(lines: list[str], predicate) -> int | None:
    for i, line in enumerate(lines):
        if predicate(line):
            return i
    return None


def patch_auto_group(text: str, desired: list[str]) -> tuple[str, dict]:
    """
    Returns (patched_text, summary_dict).
    """
    lines = text.splitlines(keepends=True)

    auto_i = _find_line(lines, lambda s: s.rstrip("\n") == "- name: AUTO")
    if auto_i is None:
        raise SystemExit("Cannot find proxy group: - name: AUTO")

    # Find the end of this group (next "- name:" at top-level list)
    end_i = None
    for i in range(auto_i + 1, len(lines)):
        if lines[i].startswith("- name: "):
            end_i = i
            break
    if end_i is None:
        end_i = len(lines)

    proxies_i = None
    for i in range(auto_i + 1, end_i):
        if lines[i].rstrip("\n") == "  proxies:":
            proxies_i = i
            break
    if proxies_i is None:
        raise SystemExit("AUTO group missing expected '  proxies:' field")

    item_prefix = "  - "
    start = proxies_i + 1
    end = start
    while end < end_i and lines[end].startswith(item_prefix):
        end += 1

    existing = [ln[len(item_prefix) :].rstrip("\n") for ln in lines[start:end]]
    desired_set = set(desired)
    # Preserve original order where possible.
    new_list = [x for x in existing if x in desired_set]
    for x in desired:
        if x not in new_list:
            new_list.append(x)

    if not new_list:
        raise SystemExit("Refusing to write an empty AUTO.proxies list (desired list is empty)")

    new_lines = [f"{item_prefix}{name}\n" for name in new_list]
    lines[start:end] = new_lines

    return (
        "".join(lines),
        {
            "auto_proxies_prev_count": len(existing),
            "auto_proxies_new_count": len(new_list),
            "auto_proxies_prev_head": existing[:5],
            "auto_proxies_new_head": new_list[:5],
        },
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", default=None)
    ap.add_argument("--backup", action="store_true", help="Write a timestamped .bak next to input")
    ap.add_argument(
        "--proxies",
        required=True,
        help="Comma-separated proxy names (must match the ones in the config).",
    )
    args = ap.parse_args()

    in_path = Path(args.in_path)
    out_path = Path(args.out_path) if args.out_path else in_path

    desired = [p.strip() for p in args.proxies.split(",") if p.strip()]
    if not desired:
        raise SystemExit("--proxies is empty")

    text = in_path.read_text(encoding="utf-8")

    if args.backup:
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = in_path.with_suffix(in_path.suffix + f".bak.{ts}")
        bak.write_text(text, encoding="utf-8")

    patched, summary = patch_auto_group(text, desired)
    if not patched.endswith("\n"):
        patched += "\n"
    out_path.write_text(patched, encoding="utf-8")

    print(f"OK: patched AUTO.proxies in {out_path}")
    for k, v in summary.items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

