#!/usr/bin/env python3
"""
Patch a mihomo (Clash Meta) config in-place (or to an output file) without
printing proxy credentials.
"""

from __future__ import annotations

import argparse
import re
import secrets
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

    # Anchor immediately after the controller secret line (before proxies:), so
    # we don't touch any credential-bearing sections.
    m = re.search(r"^secret:\s*.*$", text, flags=re.M)
    if not m:
        raise SystemExit("Cannot find secret line to anchor TUN insertion (add secret: first)")

    insert_at = m.end()
    return text[:insert_at] + TUN_BLOCK + text[insert_at:], True


def _yaml_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _parse_yaml_scalar(value: str) -> str:
    """
    Best-effort parsing for a single-line YAML scalar.

    We keep this dependency-free on purpose.
    """

    value = value.strip()
    if not value or value == "null":
        return ""

    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return value[1:-1].replace("''", "'")
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return value[1:-1]

    # Unquoted scalar: strip inline comments.
    value = value.split("#", 1)[0].strip()
    return value


def get_secret(text: str) -> str | None:
    m = re.search(r"^secret:\s*(.*?)\s*$", text, flags=re.M)
    if not m:
        return None
    return _parse_yaml_scalar(m.group(1))


def set_secret(text: str, secret_value: str, *, force: bool) -> tuple[str, bool, str]:
    current = get_secret(text)
    if current and not force:
        return text, False, current

    rendered = f"secret: {_yaml_single_quote(secret_value)}"

    if current is None:
        # Prefer placing after external-controller for readability.
        m = re.search(r"^external-controller:\s*.*$", text, flags=re.M)
        if m:
            insert_at = m.end()
            return text[:insert_at] + "\n" + rendered + text[insert_at:], True, secret_value

        # Fallback: prepend at top.
        return rendered + "\n" + text, True, secret_value

    # Replace existing secret line.
    out, n = re.subn(r"^secret:\s*.*$", rendered, text, flags=re.M, count=1)
    return out, n > 0, secret_value


def ensure_secret(text: str) -> tuple[str, bool, str]:
    current = get_secret(text)
    if current:
        return text, False, current
    generated = secrets.token_hex(16)
    return set_secret(text, generated, force=True)


def set_tun_enabled(text: str, enabled: bool) -> tuple[str, bool]:
    """
    Set tun.enable = true/false.

    If enabling and the tun block is missing, insert a conservative tun: block.
    If disabling and the tun block is missing, do nothing.
    """

    if not re.search(r"^tun:\s*$", text, flags=re.M):
        if not enabled:
            return text, False
        return ensure_tun_block(text)

    lines = text.splitlines(keepends=True)

    # Find "tun:" at top-level.
    tun_i = None
    for i, line in enumerate(lines):
        if line.rstrip("\n") == "tun:":
            tun_i = i
            break
    if tun_i is None:
        return text, False

    desired = "true" if enabled else "false"
    desired_line = f"  enable: {desired}\n"

    enable_i = None
    for i in range(tun_i + 1, len(lines)):
        if re.match(r"^[^\\s].+:\\s*$", lines[i]):
            break
        if lines[i].startswith("  enable:"):
            enable_i = i
            break

    if enable_i is None:
        lines.insert(tun_i + 1, desired_line)
        return "".join(lines), True

    if lines[enable_i] == desired_line:
        return text, False

    lines[enable_i] = desired_line
    return "".join(lines), True


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
        "--ensure-secret",
        action="store_true",
        help="Ensure `secret:` is non-empty (generates a random secret if missing/empty)",
    )
    parser.add_argument(
        "--set-secret",
        default=None,
        help="Set `secret:` to this value (overwrites current secret)",
    )
    parser.add_argument(
        "--secret-out",
        default=None,
        help="Write the effective secret (no quotes) to this path",
    )
    parser.add_argument(
        "--set-tun-enabled",
        choices=["true", "false"],
        default=None,
        help="Set tun.enable to true/false (adds tun block if missing and enabling)",
    )
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
    if args.set_secret is not None:
        text, did, _ = set_secret(text, args.set_secret, force=True)
        changed = changed or did
    elif args.ensure_secret:
        text, did, _ = ensure_secret(text)
        changed = changed or did

    if args.add_forced:
        text, did = ensure_forced_proxy_rules(text)
        changed = changed or did
    if args.add_tun:
        text, did = ensure_tun_block(text)
        changed = changed or did
    if args.set_tun_enabled is not None:
        text, did = set_tun_enabled(text, args.set_tun_enabled == "true")
        changed = changed or did
    if args.ensure_tun_excludes:
        text, did = ensure_tun_excludes(text)
        changed = changed or did

    if not text.endswith("\n"):
        text += "\n"

    out_path.write_text(text, encoding="utf-8")

    if args.secret_out:
        secret_value = get_secret(text) or ""
        Path(args.secret_out).write_text(secret_value + "\n", encoding="utf-8")

    print(f"Wrote: {out_path} (changed={changed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
