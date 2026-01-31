#!/usr/bin/env python3
"""
Patch a mihomo (Clash Meta) config in-place (or to an output file) without
printing proxy credentials.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


FORCED_PROXY_RULES = [
    "- DOMAIN-SUFFIX,openai.com,PROXY",
    "- DOMAIN-SUFFIX,chatgpt.com,PROXY",
    "- DOMAIN-SUFFIX,oaistatic.com,PROXY",
    "- DOMAIN-SUFFIX,oaiusercontent.com,PROXY",
    "- DOMAIN-SUFFIX,anthropic.com,PROXY",
    "- DOMAIN-SUFFIX,claude.ai,PROXY",
]


TUN_BLOCK = """\

tun:
  enable: true
  stack: system
  auto-route: true
  auto-detect-interface: true
  strict-route: true
  route-exclude-address:
    - 6.6.6.6/32
    - 127.0.0.0/8
    - 10.0.0.0/8
    - 172.16.0.0/12
    - 192.168.0.0/16
    - 169.254.0.0/16
    - 100.64.0.0/10
    - 224.0.0.0/4
    - 255.255.255.255/32
    - ::1/128
    - 2000::6666/128
    - fc00::/7
    - fe80::/10
    - ff00::/8
    - fc03:1136:3800::/40
"""

REQUIRED_TUN_EXCLUDES = [
    "6.6.6.6/32",
    "2000::6666/128",
    "fc03:1136:3800::/40",
]


def _insert_after_first(text: str, anchor: str, insert: str) -> tuple[str, bool]:
    if anchor not in text:
        return text, False
    return text.replace(anchor, anchor + insert, 1), True


def ensure_forced_proxy_rules(text: str) -> tuple[str, bool]:
    if any(rule in text for rule in FORCED_PROXY_RULES):
        return text, False

    insert = "\n" + "\n".join(FORCED_PROXY_RULES)

    # Prefer placing after our DIRECT-safe domains.
    for anchor in (
        "- DOMAIN-SUFFIX,lazycat.cloud,DIRECT",
        "- DOMAIN-SUFFIX,heiyu.space,DIRECT",
    ):
        out, ok = _insert_after_first(text, anchor, insert)
        if ok:
            return out, True

    # Fallback: insert right after the rules: header.
    m = re.search(r"^rules:\s*$", text, flags=re.M)
    if not m:
        raise SystemExit("Cannot find rules: section to insert forced proxy rules")
    insert_at = m.end()
    return text[:insert_at] + insert + text[insert_at:], True


def ensure_tun_block(text: str) -> tuple[str, bool]:
    if re.search(r"^tun:\s*$", text, flags=re.M):
        return text, False

    # Anchor immediately after secret: '' line which is before proxies:
    # and doesn't expose any credentials.
    secret_patterns = [
        r"^secret:\s*''\s*$",
        r'^secret:\s*""\s*$',
        r"^secret:\s*null\s*$",
    ]

    m = None
    for pat in secret_patterns:
        m = re.search(pat, text, flags=re.M)
        if m:
            break
    if not m:
        raise SystemExit("Cannot find secret line to anchor TUN insertion")

    insert_at = m.end()
    return text[:insert_at] + TUN_BLOCK + text[insert_at:], True


def ensure_tun_excludes(text: str) -> tuple[str, bool]:
    """
    Ensure tun.route-exclude-address contains required bypasses.

    This is an indentation-based patcher to avoid YAML deps on the target host.
    """

    if not re.search(r"^tun:\s*$", text, flags=re.M):
        return text, False

    lines = text.splitlines(keepends=True)

    # Find "tun:" at top-level.
    tun_i = None
    for i, line in enumerate(lines):
        if line.rstrip("\n") == "tun:":
            tun_i = i
            break
    if tun_i is None:
        return text, False

    # Find "  route-exclude-address:" within the tun block.
    route_i = None
    for i in range(tun_i + 1, len(lines)):
        # Stop if we hit next top-level key.
        if re.match(r"^[^\\s].+:\\s*$", lines[i]):
            break
        if lines[i].rstrip("\n") == "  route-exclude-address:":
            route_i = i
            break
    if route_i is None:
        return text, False

    item_prefix = "    - "
    start = route_i + 1
    end = start
    while end < len(lines) and lines[end].startswith(item_prefix):
        end += 1

    existing = set()
    for line in lines[start:end]:
        existing.add(line.rstrip("\n"))

    missing = [addr for addr in REQUIRED_TUN_EXCLUDES if f"{item_prefix}{addr}" not in existing]
    if not missing:
        return text, False

    insert_lines = [f"{item_prefix}{addr}\n" for addr in missing]
    lines[end:end] = insert_lines
    return "".join(lines), True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", required=True, help="Input config.yaml")
    parser.add_argument("--out", dest="out_path", required=True, help="Output path")
    parser.add_argument("--add-forced", action="store_true", help="Insert forced PROXY domain rules")
    parser.add_argument("--add-tun", action="store_true", help="Insert a conservative tun: block")
    parser.add_argument(
        "--ensure-tun-excludes",
        action="store_true",
        help="Ensure tun.route-exclude-address contains required bypasses",
    )
    args = parser.parse_args()

    in_path = Path(args.in_path)
    out_path = Path(args.out_path)

    text = in_path.read_text(encoding="utf-8")

    changed = False
    if args.add_forced:
        text, did = ensure_forced_proxy_rules(text)
        changed = changed or did
    if args.add_tun:
        text, did = ensure_tun_block(text)
        changed = changed or did
    if args.ensure_tun_excludes:
        text, did = ensure_tun_excludes(text)
        changed = changed or did

    if not text.endswith("\n"):
        text += "\n"

    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote: {out_path} (changed={changed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
