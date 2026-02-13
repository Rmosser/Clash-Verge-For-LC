#!/usr/bin/env python3
"""
Ensure a rule exists to avoid proxying generic IPv6 destinations when nodes are V4-only egress.

We insert:
  - IP-CIDR6,::/0,REJECT,no-resolve

right before:
  - GEOIP,CN,DIRECT
or, if missing, before:
  - MATCH,PROXY
"""

from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path

RULE = "- IP-CIDR6,::/0,REJECT,no-resolve"


def ensure_rule(text: str) -> tuple[str, bool]:
    if RULE in text:
        return text, False

    lines = text.splitlines(keepends=True)

    insert_at = None
    for i, ln in enumerate(lines):
        if ln.rstrip("\n") == "- GEOIP,CN,DIRECT":
            insert_at = i
            break
    if insert_at is None:
        for i, ln in enumerate(lines):
            if ln.rstrip("\n") == "- MATCH,PROXY":
                insert_at = i
                break
    if insert_at is None:
        raise SystemExit("Cannot find GEOIP,CN,DIRECT or MATCH,PROXY to anchor insertion")

    lines.insert(insert_at, RULE + "\n")
    return "".join(lines), True


def remove_rule(text: str) -> tuple[str, bool]:
    if RULE not in text:
        return text, False
    out = "\n".join([ln for ln in text.splitlines() if ln != RULE]) + "\n"
    return out, True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()

    p = Path(args.in_path)
    text = p.read_text(encoding="utf-8")

    if args.backup:
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = p.with_suffix(p.suffix + f".bak.{ts}")
        bak.write_text(text, encoding="utf-8")

    if args.remove:
        out, changed = remove_rule(text)
    else:
        out, changed = ensure_rule(text)

    if not out.endswith("\n"):
        out += "\n"
    p.write_text(out, encoding="utf-8")
    print(f"OK: {'removed' if args.remove else 'ensured'} rule (changed={changed}) in {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

