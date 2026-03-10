#!/usr/bin/env python3
from __future__ import annotations

import base64
import copy
import datetime as dt
import gzip
import json
import mimetypes
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


APP_VERSION = os.environ.get("MIHOMO_VERGE_APP_VERSION", "2.4.7-webport.0")
APP_START = time.time()

BIND = os.environ.get("VERGE_API_BIND", "172.18.0.1:9091")
if ":" in BIND:
    BIND_HOST, BIND_PORT_RAW = BIND.rsplit(":", 1)
else:
    BIND_HOST, BIND_PORT_RAW = BIND, "9091"

HOST = BIND_HOST.strip() or "172.18.0.1"
PORT = int(BIND_PORT_RAW)

DATA_ROOT = Path("/var/lib/mihomo/verge")
PROFILES_DIR = DATA_ROOT / "profiles"
BACKUPS_DIR = DATA_ROOT / "backups"
ICONS_DIR = DATA_ROOT / "icons"
LOGS_DIR = DATA_ROOT / "logs"
VERGE_CONFIG_PATH = DATA_ROOT / "verge.json"
PROFILES_CONFIG_PATH = DATA_ROOT / "profiles.json"
OVERLAY_JSON_PATH = DATA_ROOT / "system-overlay.json"
OVERLAY_YAML_PATH = DATA_ROOT / "system-overlay.yaml"
DNS_CONFIG_PATH = DATA_ROOT / "dns-config.json"
PROXY_CHAIN_PATH = DATA_ROOT / "proxy-chain.json"
OPERATIONS_LOG_PATH = LOGS_DIR / "operations.log"
VERGE_API_SECRET_PATH = Path(
    os.environ.get("VERGE_API_SECRET_FILE", "/etc/mihomo/verge-api.secret")
)

MIHOMO_CONFIG_PATH = Path("/etc/mihomo/config.yaml")
MIHOMO_STATE_DIR = Path("/var/lib/mihomo")
MIHOMO_BIN = Path("/usr/local/bin/mihomo")
MMDB_PATH = MIHOMO_STATE_DIR / "Country.mmdb"
CONTROLLER_URL = "http://172.18.0.1:9090"

DEFAULT_CONTROLLER_CORS = {
    "allow-private-network": True,
    "allow-origins": ["*"],
}

DEFAULT_ROUTE_EXCLUDES = [
    "6.6.6.6/32",
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "100.64.0.0/10",
    "224.0.0.0/4",
    "255.255.255.255/32",
    "::1/128",
    "2000::6666/128",
    "fc00::/7",
    "fe80::/10",
    "ff00::/8",
    "fc03:1136:3800::/40",
]

DEFAULT_TUN_CONFIG = {
    "enable": True,
    "stack": "system",
    "auto-route": True,
    "auto-detect-interface": True,
    "strict-route": True,
    "route-exclude-address": DEFAULT_ROUTE_EXCLUDES,
}

DEFAULT_DNS_CONFIG = {
    "enable": True,
    "listen": "127.0.0.1:1053",
    "ipv6": True,
    "enhanced-mode": "redir-host",
    "use-hosts": True,
    "respect-rules": True,
    "default-nameserver": ["192.168.1.1", "223.5.5.5", "119.29.29.29"],
    "proxy-server-nameserver": ["192.168.1.1", "223.5.5.5", "119.29.29.29"],
    "nameserver": [
        "https://1.1.1.1/dns-query",
        "https://1.0.0.1/dns-query",
    ],
    "nameserver-policy": {
        "+.heiyu.space": ["192.168.1.1", "fe80::1"],
        "+.lazycat.cloud": ["192.168.1.1", "fe80::1"],
    },
}

DEFAULT_HOME_CARDS = {
    "clash": True,
    "proxy": True,
    "traffic": True,
    "memory": True,
    "connections": True,
    "system": True,
    "ip": True,
}

DEFAULT_VERGE_CONFIG = {
    "language": "zh",
    "theme_mode": "system",
    "clash_core": "verge-mihomo",
    "traffic_graph": True,
    "enable_memory_usage": True,
    "enable_group_icon": True,
    "enable_tun_mode": True,
    "enable_dns_settings": True,
    "enable_external_controller": True,
    "enable_system_proxy": False,
    "proxy_auto_config": False,
    "default_latency_test": "http://cp.cloudflare.com",
    "default_latency_timeout": 5000,
    "enable_auto_backup_schedule": False,
    "auto_backup_interval_hours": 24,
    "auto_backup_on_change": False,
    "web_ui_list": ["clash-verge-web", "metacubexd", "yacd-meta"],
    "home_cards": DEFAULT_HOME_CARDS,
}

DEFAULT_UNLOCK_ITEMS = [
    {"name": "ChatGPT", "status": "Pending"},
    {"name": "Claude", "status": "Pending"},
    {"name": "Gemini", "status": "Pending"},
    {"name": "Netflix", "status": "Pending"},
    {"name": "Disney+", "status": "Pending"},
    {"name": "Prime Video", "status": "Pending"},
    {"name": "YouTube Premium", "status": "Pending"},
    {"name": "Spotify", "status": "Pending"},
]

UNLOCK_TEST_URLS = {
    "ChatGPT": "https://chat.openai.com/cdn-cgi/trace",
    "Claude": "https://claude.ai/",
    "Gemini": "https://gemini.google.com/",
    "Netflix": "https://www.netflix.com/title/80018499",
    "Disney+": "https://www.disneyplus.com/",
    "Prime Video": "https://www.primevideo.com/",
    "YouTube Premium": "https://www.youtube.com/premium",
    "Spotify": "https://open.spotify.com/",
}

RUNTIME_RELEVANT_VERGE_KEYS = {
    "enable_dns_settings",
    "enable_tun_mode",
    "enable_external_controller",
    "verge_mixed_port",
    "verge_socks_port",
    "verge_port",
    "verge_redir_port",
    "verge_tproxy_port",
    "verge_socks_enabled",
    "verge_http_enabled",
    "verge_redir_enabled",
    "verge_tproxy_enabled",
}


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_now() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def ensure_dirs() -> None:
    for path in (DATA_ROOT, PROFILES_DIR, BACKUPS_DIR, ICONS_DIR, LOGS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def append_operation_log(message: str) -> None:
    ensure_dirs()
    with OPERATIONS_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{iso_now()}] {message}\n")


def atomic_write_bytes(path: Path, payload: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=str(path.parent)) as handle:
        handle.write(payload)
        tmp_name = handle.name
    if mode is not None:
        os.chmod(tmp_name, mode)
    os.replace(tmp_name, path)


def atomic_write_text(path: Path, text: str, mode: int | None = None) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return copy.deepcopy(default)


def save_json(path: Path, data: Any, mode: int | None = None) -> None:
    atomic_write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        mode,
    )


def deep_merge(base: Any, patch: Any) -> Any:
    if not isinstance(base, dict) or not isinstance(patch, dict):
        return copy.deepcopy(patch)
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def yaml_quote(value: str) -> str:
    if value == "":
        return "''"
    if re.fullmatch(r"[A-Za-z0-9._:/@+-]+", value):
        return value
    return "'" + value.replace("'", "''") + "'"


def render_yaml_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return yaml_quote(str(value))


def render_yaml_value(value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        if not value:
            return [prefix + "{}"]
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(render_yaml_value(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {render_yaml_scalar(item)}")
        return lines
    if isinstance(value, list):
        if not value:
            return [prefix + "[]"]
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                nested = render_yaml_value(item, indent + 2)
                first = nested[0].lstrip()
                lines.append(f"{prefix}- {first}")
                lines.extend(nested[1:])
            else:
                lines.append(f"{prefix}- {render_yaml_scalar(item)}")
        return lines
    return [prefix + render_yaml_scalar(value)]


def render_top_level_yaml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            lines.append(f"{key}:")
            lines.extend(render_yaml_value(value, 2))
        else:
            lines.append(f"{key}: {render_yaml_scalar(value)}")
    return "\n".join(lines).rstrip() + "\n"


def top_level_block_range(text: str, key: str) -> tuple[int, int] | None:
    lines = text.splitlines(keepends=True)
    start = None
    key_prefix = f"{key}:"
    for idx, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if stripped.startswith(key_prefix) and not stripped.startswith((" ", "\t")):
            start = idx
            break
    if start is None:
        return None
    end = start + 1
    while end < len(lines):
        stripped = lines[end].rstrip("\n")
        if not stripped:
            end += 1
            continue
        if lines[end].startswith((" ", "\t")):
            end += 1
            continue
        break
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    return offsets[start], offsets[end]


def set_top_level_value(text: str, key: str, value: Any) -> str:
    if isinstance(value, (dict, list)):
        block = f"{key}:\n" + "\n".join(render_yaml_value(value, 2)) + "\n"
    else:
        block = f"{key}: {render_yaml_scalar(value)}\n"
    rng = top_level_block_range(text, key)
    if rng is None:
        if text and not text.endswith("\n"):
            text += "\n"
        anchor = None
        for candidate in ("proxies", "proxy-groups", "rules"):
            anchor = top_level_block_range(text, candidate)
            if anchor:
                break
        if anchor is None:
            return text + ("\n" if text and not text.endswith("\n\n") else "") + block
        return text[: anchor[0]] + block + ("\n" if not block.endswith("\n\n") else "") + text[anchor[0] :]
    return text[: rng[0]] + block + text[rng[1] :]


def remove_top_level_key(text: str, key: str) -> str:
    rng = top_level_block_range(text, key)
    if rng is None:
        return text
    return text[: rng[0]] + text[rng[1] :]


def parse_yaml_scalar(value: str) -> str:
    value = value.strip()
    if not value or value == "null":
        return ""
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return value[1:-1].replace("''", "'")
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return value[1:-1]
    return value.split("#", 1)[0].strip()


def extract_scalar(text: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:\s*(.*?)\s*$", text, flags=re.M)
    if not match:
        return None
    return parse_yaml_scalar(match.group(1))


def extract_bool(text: str, key: str) -> bool | None:
    value = extract_scalar(text, key)
    if value is None:
        return None
    if value.lower() in ("true", "yes", "on"):
        return True
    if value.lower() in ("false", "no", "off"):
        return False
    return None


def extract_int(text: str, key: str) -> int | None:
    value = extract_scalar(text, key)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def controller_secret() -> str:
    text = MIHOMO_CONFIG_PATH.read_text(encoding="utf-8") if MIHOMO_CONFIG_PATH.exists() else ""
    current = extract_scalar(text, "secret")
    if current:
        return current
    generated = secrets.token_hex(16)
    updated = set_top_level_value(text, "secret", generated)
    atomic_write_text(MIHOMO_CONFIG_PATH, updated, 0o640)
    return generated


def verge_api_secret() -> str:
    if VERGE_API_SECRET_PATH.exists():
        value = VERGE_API_SECRET_PATH.read_text(encoding="utf-8").strip()
        if value:
            return value
    generated = secrets.token_hex(16)
    atomic_write_text(VERGE_API_SECRET_PATH, generated + "\n", 0o600)
    return generated


def controller_headers() -> dict[str, str]:
    secret = controller_secret()
    if secret:
        return {"Authorization": f"Bearer {secret}"}
    return {}


def controller_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 15,
) -> Any:
    body = None
    headers = controller_headers()
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        CONTROLLER_URL + path,
        method=method,
        data=body,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read()
        if "application/json" in content_type:
            return json.loads(raw.decode("utf-8"))
        return raw.decode("utf-8", errors="replace")


def run_command(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=True,
        text=True,
    )


def read_os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def current_system_info_text() -> str:
    data = read_os_release()
    name = data.get("NAME", platform.system())
    version = data.get("VERSION", platform.version())
    kernel = platform.release()
    return "\n".join(
        [
            f"System Name: {name}",
            f"System Version: {version}",
            f"Kernel Version: {kernel}",
        ]
    )


def file_is_allowed(path: Path) -> bool:
    resolved = path.resolve()
    allowed_prefixes = [
        DATA_ROOT.resolve(),
        MIHOMO_CONFIG_PATH.resolve(),
        MIHOMO_STATE_DIR.resolve(),
    ]
    for prefix in allowed_prefixes:
        try:
            resolved.relative_to(prefix)
            return True
        except ValueError:
            continue
    return resolved == MIHOMO_CONFIG_PATH.resolve()


def read_registered_upload(payload: Any) -> tuple[str, bytes] | None:
    if not isinstance(payload, dict) or not payload.get("__registeredFile"):
        return None
    name = str(payload.get("name") or "upload.bin")
    content_b64 = str(payload.get("content_b64") or "")
    return name, base64.b64decode(content_b64)


def maybe_bytes_from_arg(value: Any) -> tuple[str, bytes] | None:
    uploaded = read_registered_upload(value)
    if uploaded:
        return uploaded
    if isinstance(value, str):
        path = Path(value)
        if path.exists():
            return path.name, path.read_bytes()
    return None


def save_overlay(data: dict[str, Any]) -> None:
    save_json(OVERLAY_JSON_PATH, data)
    atomic_write_text(OVERLAY_YAML_PATH, render_top_level_yaml(data))


def load_overlay() -> dict[str, Any]:
    return load_json(OVERLAY_JSON_PATH, {})


def load_dns_config() -> dict[str, Any]:
    return load_json(DNS_CONFIG_PATH, DEFAULT_DNS_CONFIG)


def save_dns_config_state(data: dict[str, Any]) -> None:
    merged = deep_merge(DEFAULT_DNS_CONFIG, data)
    save_json(DNS_CONFIG_PATH, merged)


def normalize_dns_config(data: dict[str, Any], enabled: bool) -> dict[str, Any]:
    merged = deep_merge(DEFAULT_DNS_CONFIG, data)
    merged["enable"] = enabled
    policy = merged.setdefault("nameserver-policy", {})
    policy["+.heiyu.space"] = ["192.168.1.1", "fe80::1"]
    policy["+.lazycat.cloud"] = ["192.168.1.1", "fe80::1"]
    return merged


def normalize_tun_config(data: dict[str, Any], enabled: bool) -> dict[str, Any]:
    merged = deep_merge(DEFAULT_TUN_CONFIG, data)
    merged["enable"] = enabled
    merged["route-exclude-address"] = list(
        dict.fromkeys(
            list(DEFAULT_ROUTE_EXCLUDES)
            + list(merged.get("route-exclude-address") or [])
        )
    )
    return merged


def default_profile_name(url: str | None = None) -> str:
    if url:
        parsed = urllib.parse.urlparse(url)
        tail = Path(parsed.path).name or parsed.netloc
        if tail:
            return tail
    return f"Profile {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def default_profile_option() -> dict[str, Any]:
    return {
        "with_proxy": True,
        "self_proxy": False,
        "allow_auto_update": True,
        "update_interval": 24,
        "timeout_seconds": 20,
    }


def get_profiles_state() -> dict[str, Any]:
    return load_json(PROFILES_CONFIG_PATH, {"current": "", "items": []})


def save_profiles_state(data: dict[str, Any]) -> None:
    save_json(PROFILES_CONFIG_PATH, data)


def profile_path(uid: str) -> Path:
    return PROFILES_DIR / f"{uid}.yaml"


def detect_bootstrap_verge_config() -> dict[str, Any]:
    runtime_text = MIHOMO_CONFIG_PATH.read_text(encoding="utf-8") if MIHOMO_CONFIG_PATH.exists() else ""
    try:
        runtime = controller_request("GET", "/configs")
    except Exception:
        runtime = {}
    mixed_port = runtime.get("mixed-port") or extract_int(runtime_text, "mixed-port") or 7890
    socks_port = runtime.get("socks-port") or extract_int(runtime_text, "socks-port") or 7891
    http_port = runtime.get("port") or extract_int(runtime_text, "port") or 7892
    redir_port = runtime.get("redir-port") or extract_int(runtime_text, "redir-port") or 7893
    tproxy_port = runtime.get("tproxy-port") or extract_int(runtime_text, "tproxy-port") or 7894
    detected = copy.deepcopy(DEFAULT_VERGE_CONFIG)
    detected.update(
        {
            "verge_mixed_port": mixed_port,
            "verge_socks_port": socks_port,
            "verge_port": http_port,
            "verge_redir_port": redir_port,
            "verge_tproxy_port": tproxy_port,
            "verge_socks_enabled": bool(runtime.get("socks-port") or extract_scalar(runtime_text, "socks-port")),
            "verge_http_enabled": bool(runtime.get("port") or extract_scalar(runtime_text, "port")),
            "verge_redir_enabled": bool(runtime.get("redir-port") or extract_scalar(runtime_text, "redir-port")),
            "verge_tproxy_enabled": bool(runtime.get("tproxy-port") or extract_scalar(runtime_text, "tproxy-port")),
            "enable_tun_mode": extract_bool(runtime_text, "enable") if top_level_block_range(runtime_text, "tun") else True,
            "enable_dns_settings": extract_bool(runtime_text, "enable") if top_level_block_range(runtime_text, "dns") else True,
        }
    )
    return detected


def ensure_state() -> None:
    ensure_dirs()
    verge_api_secret()

    if not VERGE_CONFIG_PATH.exists():
        save_json(VERGE_CONFIG_PATH, detect_bootstrap_verge_config())

    if not DNS_CONFIG_PATH.exists():
        save_json(DNS_CONFIG_PATH, DEFAULT_DNS_CONFIG)

    if not OVERLAY_JSON_PATH.exists():
        save_overlay({})

    if not PROXY_CHAIN_PATH.exists():
        save_json(PROXY_CHAIN_PATH, {"items": []})

    if not PROFILES_CONFIG_PATH.exists():
        uid = "bootstrap-" + uuid.uuid4().hex[:8]
        source_text = (
            MIHOMO_CONFIG_PATH.read_text(encoding="utf-8")
            if MIHOMO_CONFIG_PATH.exists()
            else "mixed-port: 7890\nmode: rule\n"
        )
        atomic_write_text(profile_path(uid), source_text)
        save_profiles_state(
            {
                "current": uid,
                "items": [
                    {
                        "uid": uid,
                        "type": "local",
                        "name": "Migrated Profile",
                        "desc": "Imported from current /etc/mihomo/config.yaml",
                        "file": str(profile_path(uid)),
                        "updated": now_ms(),
                        "selected": [],
                        "option": default_profile_option(),
                    }
                ],
            }
        )


def get_verge_config_state() -> dict[str, Any]:
    ensure_state()
    return load_json(VERGE_CONFIG_PATH, DEFAULT_VERGE_CONFIG)


def save_verge_config_state(data: dict[str, Any]) -> None:
    save_json(VERGE_CONFIG_PATH, data)


def current_profile_item() -> dict[str, Any]:
    profiles = get_profiles_state()
    current = profiles.get("current")
    for item in profiles.get("items") or []:
        if item.get("uid") == current:
            return item
    raise RuntimeError("current profile not found")


def render_proxy_chain_yaml(items: list[str]) -> str:
    block = {"proxies": [{"name": item, "type": "relay"} for item in items]}
    return render_top_level_yaml(block)


def build_runtime_text(item: dict[str, Any] | None = None) -> tuple[str, str]:
    ensure_state()
    item = item or current_profile_item()
    base = profile_path(str(item["uid"])).read_text(encoding="utf-8")
    overlay = load_overlay()
    verge = get_verge_config_state()
    text = base if base.endswith("\n") else base + "\n"

    for key in (
        "mode",
        "ipv6",
        "allow-lan",
        "log-level",
        "unified-delay",
        "external-controller-cors",
        "tunnels",
    ):
        if key in overlay:
            text = set_top_level_value(text, key, overlay[key])

    mixed_port = overlay.get("mixed-port", verge.get("verge_mixed_port"))
    if mixed_port:
        text = set_top_level_value(text, "mixed-port", mixed_port)

    optional_ports = [
        ("socks-port", "verge_socks_enabled", "verge_socks_port"),
        ("port", "verge_http_enabled", "verge_port"),
        ("redir-port", "verge_redir_enabled", "verge_redir_port"),
        ("tproxy-port", "verge_tproxy_enabled", "verge_tproxy_port"),
    ]
    for yaml_key, enabled_key, port_key in optional_ports:
        port_value = overlay.get(yaml_key, verge.get(port_key))
        if verge.get(enabled_key):
            if port_value:
                text = set_top_level_value(text, yaml_key, port_value)
        else:
            text = remove_top_level_key(text, yaml_key)

    controller_secret_value = (
        overlay.get("secret")
        or extract_scalar(text, "secret")
        or controller_secret()
    )
    text = set_top_level_value(text, "external-controller", "172.18.0.1:9090")
    text = set_top_level_value(text, "secret", controller_secret_value)
    text = set_top_level_value(
        text,
        "external-controller-cors",
        deep_merge(DEFAULT_CONTROLLER_CORS, overlay.get("external-controller-cors") or {}),
    )

    tun_overlay = overlay.get("tun") if isinstance(overlay.get("tun"), dict) else {}
    tun_enabled = bool(verge.get("enable_tun_mode", True))
    text = set_top_level_value(text, "tun", normalize_tun_config(tun_overlay, tun_enabled))

    dns_config = normalize_dns_config(load_dns_config(), bool(verge.get("enable_dns_settings", True)))
    text = set_top_level_value(text, "dns", dns_config)

    return text if text.endswith("\n") else text + "\n", controller_secret_value


def wait_for_controller(timeout: int = 12) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            controller_request("GET", "/version", timeout=4)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"mihomo controller probe failed: {last_error}")


def apply_current_profile() -> None:
    item = current_profile_item()
    new_text, _ = build_runtime_text(item)
    previous = MIHOMO_CONFIG_PATH.read_text(encoding="utf-8") if MIHOMO_CONFIG_PATH.exists() else ""
    atomic_write_text(MIHOMO_CONFIG_PATH, new_text, 0o640)
    try:
        if MIHOMO_BIN.exists():
            run_command(
                [
                    str(MIHOMO_BIN),
                    "-t",
                    "-d",
                    str(MIHOMO_STATE_DIR),
                    "-f",
                    str(MIHOMO_CONFIG_PATH),
                ]
            )
        run_command(["systemctl", "restart", "mihomo"])
        wait_for_controller()
        append_operation_log(f"applied profile {item['uid']}")
    except Exception:
        atomic_write_text(MIHOMO_CONFIG_PATH, previous, 0o640)
        run_command(["systemctl", "restart", "mihomo"], check=False)
        raise


def fetch_remote_profile(url: str, option: dict[str, Any] | None = None) -> tuple[str, dict[str, int]]:
    option = option or {}
    timeout = int(option.get("timeout_seconds") or 20)
    handlers: list[Any] = []
    if option.get("self_proxy"):
        verge = get_verge_config_state()
        proxy_port = verge.get("verge_mixed_port") or 7890
        proxy_url = f"http://127.0.0.1:{proxy_port}"
        handlers.append(
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        )
    elif option.get("with_proxy") is False:
        handlers.append(urllib.request.ProxyHandler({}))

    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": str(option.get("user_agent") or "clash-verge-webport/1.0")
        },
    )
    with opener.open(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8", errors="replace")
        info = parse_subscription_userinfo(
            response.headers.get("subscription-userinfo", "")
        )
    return payload, info


def parse_subscription_userinfo(header_value: str) -> dict[str, int]:
    values = {"upload": 0, "download": 0, "total": 0, "expire": 0}
    for part in header_value.split(";"):
        if "=" not in part:
            continue
        key, value = [item.strip().lower() for item in part.split("=", 1)]
        try:
            numeric = int(value)
        except ValueError:
            continue
        if key in values:
            values[key] = numeric
    return values


def create_profile_item(item: dict[str, Any], file_data: str | None) -> dict[str, Any]:
    ensure_state()
    profiles = get_profiles_state()
    uid = item.get("uid") or uuid.uuid4().hex
    profile_type = item.get("type") or "local"
    name = item.get("name") or default_profile_name(item.get("url"))
    option = deep_merge(default_profile_option(), item.get("option") or {})
    extra = {"upload": 0, "download": 0, "total": 0, "expire": 0}

    if file_data is None and profile_type == "remote" and item.get("url"):
        file_data, extra = fetch_remote_profile(str(item["url"]), option)
    if file_data is None:
        raise RuntimeError("profile content is required")

    path = profile_path(uid)
    atomic_write_text(path, file_data)
    record = {
        "uid": uid,
        "type": profile_type,
        "name": name,
        "desc": item.get("desc") or "",
        "file": str(path),
        "url": item.get("url") or "",
        "updated": now_ms(),
        "selected": item.get("selected") or [],
        "extra": extra,
        "option": option,
        "home": item.get("home") or "",
    }
    profiles.setdefault("items", []).append(record)
    if not profiles.get("current"):
        profiles["current"] = uid
    save_profiles_state(profiles)
    return record


def update_profile_file(uid: str, file_data: str) -> None:
    atomic_write_text(profile_path(uid), file_data)
    profiles = get_profiles_state()
    for item in profiles.get("items") or []:
        if item.get("uid") == uid:
            item["updated"] = now_ms()
            break
    save_profiles_state(profiles)
    if profiles.get("current") == uid:
        apply_current_profile()


def patch_profile_record(uid: str, patch: dict[str, Any]) -> dict[str, Any]:
    profiles = get_profiles_state()
    for item in profiles.get("items") or []:
        if item.get("uid") == uid:
            item.update(copy.deepcopy(patch))
            save_profiles_state(profiles)
            return item
    raise RuntimeError(f"profile not found: {uid}")


def delete_profile_record(uid: str) -> None:
    profiles = get_profiles_state()
    items = [item for item in profiles.get("items") or [] if item.get("uid") != uid]
    profiles["items"] = items
    if profile_path(uid).exists():
        profile_path(uid).unlink()
    if profiles.get("current") == uid:
        profiles["current"] = items[0]["uid"] if items else ""
    save_profiles_state(profiles)
    if profiles.get("current"):
        apply_current_profile()


def list_local_backups() -> list[dict[str, Any]]:
    ensure_dirs()
    rows = []
    for path in sorted(BACKUPS_DIR.glob("*.zip"), reverse=True):
        stat = path.stat()
        rows.append(
            {
                "filename": path.name,
                "path": str(path),
                "last_modified": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "content_length": stat.st_size,
            }
        )
    return rows


def add_dir_to_zip(handle: zipfile.ZipFile, source: Path, arc_prefix: str) -> None:
    if not source.exists():
        return
    for path in sorted(source.rglob("*")):
        if path.is_dir():
            continue
        handle.write(path, f"{arc_prefix}/{path.relative_to(source)}")


def create_backup_archive(target: Path) -> None:
    ensure_state()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in (
            VERGE_CONFIG_PATH,
            PROFILES_CONFIG_PATH,
            OVERLAY_JSON_PATH,
            OVERLAY_YAML_PATH,
            DNS_CONFIG_PATH,
            MIHOMO_CONFIG_PATH,
        ):
            if path.exists():
                archive.write(path, path.name)
        if VERGE_API_SECRET_PATH.exists():
            archive.write(VERGE_API_SECRET_PATH, "verge-api.secret")
        add_dir_to_zip(archive, PROFILES_DIR, "profiles")
        add_dir_to_zip(archive, ICONS_DIR, "icons")


def restore_backup_archive(source: Path) -> None:
    ensure_state()
    with zipfile.ZipFile(source, "r") as archive:
        archive.extractall(DATA_ROOT / "_restore_tmp")
    restore_root = DATA_ROOT / "_restore_tmp"
    try:
        for name, destination in (
            ("verge.json", VERGE_CONFIG_PATH),
            ("profiles.json", PROFILES_CONFIG_PATH),
            ("system-overlay.json", OVERLAY_JSON_PATH),
            ("system-overlay.yaml", OVERLAY_YAML_PATH),
            ("dns-config.json", DNS_CONFIG_PATH),
            ("config.yaml", MIHOMO_CONFIG_PATH),
        ):
            source_path = restore_root / name
            if source_path.exists():
                atomic_write_bytes(destination, source_path.read_bytes())
        if (restore_root / "verge-api.secret").exists():
            atomic_write_bytes(
                VERGE_API_SECRET_PATH,
                (restore_root / "verge-api.secret").read_bytes(),
                0o600,
            )

        shutil.rmtree(PROFILES_DIR, ignore_errors=True)
        shutil.rmtree(ICONS_DIR, ignore_errors=True)
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        ICONS_DIR.mkdir(parents=True, exist_ok=True)
        if (restore_root / "profiles").exists():
            shutil.copytree(restore_root / "profiles", PROFILES_DIR, dirs_exist_ok=True)
        if (restore_root / "icons").exists():
            shutil.copytree(restore_root / "icons", ICONS_DIR, dirs_exist_ok=True)
    finally:
        shutil.rmtree(restore_root, ignore_errors=True)
    apply_current_profile()


def webdav_config() -> tuple[str, str, str]:
    verge = get_verge_config_state()
    url = str(verge.get("webdav_url") or "").rstrip("/")
    username = str(verge.get("webdav_username") or "")
    password = str(verge.get("webdav_password") or "")
    if not url:
        raise RuntimeError("webdav url is not configured")
    return url, username, password


def webdav_request(
    method: str,
    url: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, Any]:
    _, username, password = webdav_config()
    request_headers = headers.copy() if headers else {}
    if username or password:
        basic = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        request_headers["Authorization"] = f"Basic {basic}"
    request = urllib.request.Request(url, method=method, data=body, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers


def list_webdav_backups() -> list[dict[str, Any]]:
    url, _, _ = webdav_config()
    status, body, _ = webdav_request(
        "PROPFIND",
        url,
        body=(
            b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
            b"<d:getlastmodified/><d:getcontentlength/><d:getcontenttype/><d:getetag/>"
            b"</d:prop></d:propfind>"
        ),
        headers={"Depth": "1", "Content-Type": "application/xml"},
    )
    if status >= 400:
        raise RuntimeError(f"webdav list failed: {status}")
    root = ET.fromstring(body)
    ns = {"d": "DAV:"}
    rows = []
    for response in root.findall("d:response", ns):
        href = response.findtext("d:href", default="", namespaces=ns)
        if href.rstrip("/").endswith("/"):
            continue
        filename = urllib.parse.unquote(href.rstrip("/").split("/")[-1])
        if not filename.endswith(".zip"):
            continue
        rows.append(
            {
                "filename": filename,
                "href": href,
                "last_modified": response.findtext(".//d:getlastmodified", default="", namespaces=ns),
                "content_length": int(response.findtext(".//d:getcontentlength", default="0", namespaces=ns) or 0),
                "content_type": response.findtext(".//d:getcontenttype", default="application/zip", namespaces=ns),
                "tag": response.findtext(".//d:getetag", default="", namespaces=ns),
            }
        )
    return rows


def current_region() -> str | None:
    try:
        request = urllib.request.Request(
            "https://ipinfo.io/json",
            headers={"User-Agent": "clash-verge-webport/1.0"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("country")
    except Exception:
        return None


def check_unlock_status() -> list[dict[str, Any]]:
    region = current_region()
    results = []
    for item in DEFAULT_UNLOCK_ITEMS:
        url = UNLOCK_TEST_URLS.get(item["name"], "https://example.com/")
        status = "Failed"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "clash-verge-webport/1.0"})
            with urllib.request.urlopen(request, timeout=12) as response:
                status = "Yes" if response.status < 400 else "No"
        except Exception:
            status = "Failed (Network Connection)"
        results.append(
            {
                "name": item["name"],
                "status": status,
                "region": region,
                "check_time": iso_now(),
            }
        )
    return results


def network_interfaces_info() -> list[dict[str, Any]]:
    try:
        result = run_command(["ip", "-j", "addr", "show"])
        payload = json.loads(result.stdout)
    except Exception:
        return []
    rows = []
    for item in payload:
        addrs = []
        for addr in item.get("addr_info", []):
            if addr.get("family") == "inet":
                addrs.append({"V4": {"ip": addr.get("local", ""), "netmask": str(addr.get("prefixlen", ""))}})
            if addr.get("family") == "inet6":
                addrs.append({"V6": {"ip": addr.get("local", ""), "netmask": str(addr.get("prefixlen", ""))}})
        rows.append(
            {
                "name": item.get("ifname"),
                "addr": addrs,
                "mac_addr": item.get("address"),
                "index": item.get("ifindex", 0),
            }
        )
    return rows


def port_in_use(port: int) -> bool:
    try:
        result = run_command(["ss", "-ltnup"])
        return f":{port} " in result.stdout or f":{port}\n" in result.stdout
    except Exception:
        for host in ("127.0.0.1", "172.18.0.1"):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                if sock.connect_ex((host, port)) == 0:
                    return True
        return False


def upgrade_core_release(channel: str) -> None:
    arch = platform.machine()
    asset_arch = {
        "x86_64": "amd64-compatible",
        "aarch64": "arm64",
        "arm64": "arm64",
        "armv7l": "armv7",
        "i386": "386",
        "i686": "386",
    }.get(arch)
    if not asset_arch:
        raise RuntimeError(f"unsupported architecture: {arch}")

    if channel == "verge-mihomo-alpha":
        api_url = "https://api.github.com/repos/MetaCubeX/mihomo/releases"
        request = urllib.request.Request(api_url, headers={"User-Agent": "clash-verge-webport/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            releases = json.loads(response.read().decode("utf-8"))
        release = next((item for item in releases if item.get("prerelease")), None)
        if not release:
            raise RuntimeError("no prerelease mihomo release found")
        tag = release["tag_name"]
    else:
        api_url = "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest"
        request = urllib.request.Request(api_url, headers={"User-Agent": "clash-verge-webport/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        tag = payload["tag_name"]

    asset = f"mihomo-linux-{asset_arch}-{tag}.gz"
    url = f"https://github.com/MetaCubeX/mihomo/releases/download/{tag}/{asset}"
    with urllib.request.urlopen(url, timeout=60) as response:
        compressed = response.read()
    binary = gzip.decompress(compressed)
    rollback_dir = MIHOMO_STATE_DIR / "rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    if MIHOMO_BIN.exists():
        shutil.copy2(MIHOMO_BIN, rollback_dir / f"mihomo.{int(time.time())}.bak")
    atomic_write_bytes(MIHOMO_BIN, binary, 0o755)
    run_command(["systemctl", "restart", "mihomo"])
    wait_for_controller()


def update_geo_data() -> None:
    url = "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/country.mmdb"
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read()
    atomic_write_bytes(MMDB_PATH, payload, 0o644)


def public_config_payload() -> dict[str, Any]:
    return {
        "secret": controller_secret(),
        "vergeApiSecret": verge_api_secret(),
        "mihomoBaseUrl": "/api",
        "vergeApiBaseUrl": "/verge-api",
        "appVersion": APP_VERSION,
    }


def invoke_command(cmd: str, args: dict[str, Any]) -> Any:
    ensure_state()

    if cmd == "get_profiles":
        return get_profiles_state()

    if cmd == "create_profile":
        item = args.get("item") or {}
        file_data = args.get("fileData")
        create_profile_item(item, file_data)
        return None

    if cmd == "import_profile":
        url = str(args.get("url") or "")
        option = args.get("option") or default_profile_option()
        create_profile_item({"type": "remote", "url": url, "option": option}, None)
        return None

    if cmd == "view_profile":
        uid = str(args.get("index") or "")
        return {
            "filename": f"{uid}.yaml",
            "content": profile_path(uid).read_text(encoding="utf-8"),
            "content_type": "text/plain; charset=utf-8",
        }

    if cmd == "read_profile_file":
        uid = str(args.get("index") or "")
        return profile_path(uid).read_text(encoding="utf-8")

    if cmd == "save_profile_file":
        uid = str(args.get("index") or "")
        update_profile_file(uid, str(args.get("fileData") or ""))
        return None

    if cmd == "patch_profile":
        uid = str(args.get("index") or "")
        patch_profile_record(uid, args.get("profile") or {})
        return None

    if cmd == "update_profile":
        uid = str(args.get("index") or "")
        profiles = get_profiles_state()
        item = next((entry for entry in profiles.get("items") or [] if entry.get("uid") == uid), None)
        if not item:
            raise RuntimeError("profile not found")
        if item.get("type") == "remote" and item.get("url"):
            payload, extra = fetch_remote_profile(str(item["url"]), args.get("option") or item.get("option"))
            atomic_write_text(profile_path(uid), payload)
            item["updated"] = now_ms()
            item["extra"] = extra
            save_profiles_state(profiles)
            if profiles.get("current") == uid:
                apply_current_profile()
        return None

    if cmd == "delete_profile":
        delete_profile_record(str(args.get("index") or ""))
        return None

    if cmd == "reorder_profile":
        active_id = str(args.get("activeId") or "")
        over_id = str(args.get("overId") or "")
        profiles = get_profiles_state()
        items = profiles.get("items") or []
        active_index = next((idx for idx, item in enumerate(items) if item.get("uid") == active_id), None)
        over_index = next((idx for idx, item in enumerate(items) if item.get("uid") == over_id), None)
        if active_index is None or over_index is None:
            return None
        item = items.pop(active_index)
        items.insert(over_index, item)
        profiles["items"] = items
        save_profiles_state(profiles)
        return None

    if cmd == "patch_profiles_config":
        profiles = get_profiles_state()
        patch = args.get("profiles") or {}
        if "items" in patch and isinstance(patch["items"], list):
            profiles["items"] = patch["items"]
        changed_current = False
        if "current" in patch and patch["current"] != profiles.get("current"):
            profiles["current"] = patch["current"]
            changed_current = True
        save_profiles_state(profiles)
        if changed_current:
            apply_current_profile()
        return True

    if cmd == "enhance_profiles":
        if get_profiles_state().get("current"):
            apply_current_profile()
        return None

    if cmd == "get_clash_info":
        runtime = controller_request("GET", "/configs")
        return {
            "mixed_port": runtime.get("mixed-port"),
            "socks_port": runtime.get("socks-port"),
            "redir_port": runtime.get("redir-port"),
            "tproxy_port": runtime.get("tproxy-port"),
            "port": runtime.get("port"),
            "server": "172.18.0.1:9090",
            "secret": controller_secret(),
        }

    if cmd == "get_runtime_config":
        return controller_request("GET", "/configs")

    if cmd == "get_runtime_yaml":
        text, _ = build_runtime_text()
        return text

    if cmd == "get_runtime_exists":
        rows = []
        for path in (
            MIHOMO_CONFIG_PATH,
            VERGE_CONFIG_PATH,
            PROFILES_CONFIG_PATH,
            OVERLAY_YAML_PATH,
            DNS_CONFIG_PATH,
        ):
            if path.exists():
                rows.append(str(path))
        return rows

    if cmd == "get_runtime_logs":
        if not OPERATIONS_LOG_PATH.exists():
            return {}
        rows = []
        for line in OPERATIONS_LOG_PATH.read_text(encoding="utf-8").splitlines()[-200:]:
            match = re.match(r"^\[(.*?)\]\s+(.*)$", line)
            if match:
                rows.append([match.group(1), match.group(2)])
        return {"Script": rows}

    if cmd == "get_runtime_proxy_chain_config":
        chain = load_json(PROXY_CHAIN_PATH, {"items": []})
        return render_proxy_chain_yaml(chain.get("items") or [])

    if cmd == "update_proxy_chain_config_in_runtime":
        items = args.get("proxyChainConfig")
        if items is None:
            save_json(PROXY_CHAIN_PATH, {"items": []})
        else:
            save_json(PROXY_CHAIN_PATH, {"items": list(items)})
        return None

    if cmd == "patch_clash_config":
        payload = args.get("payload") or {}
        overlay = deep_merge(load_overlay(), payload)
        if "external-controller" in overlay:
            overlay["external-controller"] = "172.18.0.1:9090"
        save_overlay(overlay)
        apply_current_profile()
        return {"secret": controller_secret()}

    if cmd == "patch_clash_mode":
        overlay = load_overlay()
        overlay["mode"] = args.get("payload") or "rule"
        save_overlay(overlay)
        apply_current_profile()
        return None

    if cmd == "get_clash_logs":
        try:
            result = run_command(["journalctl", "-u", "mihomo", "-n", "300", "--no-pager"])
            return result.stdout.splitlines()
        except Exception:
            return []

    if cmd == "clear_logs":
        atomic_write_text(OPERATIONS_LOG_PATH, "")
        return None

    if cmd == "get_verge_config":
        return get_verge_config_state()

    if cmd == "patch_verge_config":
        current = get_verge_config_state()
        payload = args.get("payload") or {}
        merged = deep_merge(current, payload)
        save_verge_config_state(merged)
        if RUNTIME_RELEVANT_VERGE_KEYS.intersection(payload.keys()):
            apply_current_profile()
        return merged

    if cmd == "save_dns_config":
        save_dns_config_state(args.get("dnsConfig") or {})
        return None

    if cmd == "apply_dns_config":
        verge = get_verge_config_state()
        verge["enable_dns_settings"] = bool(args.get("apply"))
        save_verge_config_state(verge)
        apply_current_profile()
        return None

    if cmd == "get_sys_proxy":
        verge = get_verge_config_state()
        port = verge.get("verge_mixed_port") or 7890
        return {
            "enable": bool(verge.get("enable_system_proxy")),
            "server": f"127.0.0.1:{port}",
            "bypass": verge.get("system_proxy_bypass")
            or "localhost,127.0.0.1,::1,.heiyu.space,.lazycat.cloud,172.18.0.1",
        }

    if cmd == "get_auto_proxy":
        verge = get_verge_config_state()
        port = verge.get("verge_mixed_port") or 7890
        return {
            "enable": bool(verge.get("proxy_auto_config")),
            "url": f"http://{socket.gethostname()}:{port}/proxy.pac",
        }

    if cmd == "get_auto_launch_status":
        return bool(get_verge_config_state().get("enable_auto_launch"))

    if cmd == "change_clash_core":
        verge = get_verge_config_state()
        verge["clash_core"] = args.get("clashCore") or "verge-mihomo"
        save_verge_config_state(verge)
        return None

    if cmd == "start_core":
        run_command(["systemctl", "start", "mihomo"])
        return None

    if cmd == "stop_core":
        run_command(["systemctl", "stop", "mihomo"])
        return None

    if cmd == "restart_core":
        run_command(["systemctl", "restart", "mihomo"])
        wait_for_controller()
        return None

    if cmd == "upgrade_core":
        upgrade_core_release(str(get_verge_config_state().get("clash_core") or "verge-mihomo"))
        return None

    if cmd == "update_geo":
        update_geo_data()
        return None

    if cmd == "copy_clash_env":
        verge = get_verge_config_state()
        port = verge.get("verge_mixed_port") or 7890
        return (
            f"HTTP_PROXY=http://127.0.0.1:{port}\n"
            f"HTTPS_PROXY=http://127.0.0.1:{port}\n"
            "NO_PROXY=localhost,127.0.0.1,::1,.heiyu.space,.lazycat.cloud,172.18.0.1\n"
        )

    if cmd == "get_app_dir":
        return str(DATA_ROOT)

    if cmd == "open_app_dir":
        return {"path": str(DATA_ROOT)}

    if cmd == "open_core_dir":
        return {"path": str(MIHOMO_BIN.parent)}

    if cmd == "open_logs_dir":
        return {"path": str(LOGS_DIR)}

    if cmd == "export_diagnostic_info":
        payload = {
            "generated_at": iso_now(),
            "system": current_system_info_text(),
            "verge": get_verge_config_state(),
            "profiles": get_profiles_state(),
            "runtime_config_path": str(MIHOMO_CONFIG_PATH),
        }
        return {
            "filename": "mihomo-verge-diagnostic.json",
            "download_name": "mihomo-verge-diagnostic.json",
            "content_type": "application/json",
            "content_b64": base64.b64encode(
                (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            ).decode("ascii"),
        }

    if cmd == "get_system_info":
        return current_system_info_text()

    if cmd == "copy_icon_file":
        icon_info = args.get("iconInfo") or {}
        name = str(icon_info.get("name") or "common")
        current_t = str(icon_info.get("current_t") or int(time.time()))
        previous_t = str(icon_info.get("previous_t") or "")
        upload = maybe_bytes_from_arg(args.get("path"))
        if not upload:
            raise RuntimeError("icon upload payload missing")
        filename, payload = upload
        ext = Path(filename).suffix.lower() or ".png"
        if previous_t:
            for candidate in ICONS_DIR.glob(f"{name}-{previous_t}.*"):
                candidate.unlink(missing_ok=True)
        target = ICONS_DIR / f"{name}-{current_t}{ext}"
        atomic_write_bytes(target, payload)
        return {"path": str(target)}

    if cmd == "download_icon_cache":
        url = str(args.get("url") or "")
        name = str(args.get("name") or "icon")
        request = urllib.request.Request(url, headers={"User-Agent": "clash-verge-webport/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read()
            content_type = response.headers.get("Content-Type", "")
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or Path(urllib.parse.urlparse(url).path).suffix or ".png"
        target = ICONS_DIR / f"{name}{ext}"
        atomic_write_bytes(target, payload)
        return str(target)

    if cmd == "get_network_interfaces":
        return [row.get("name") for row in network_interfaces_info() if row.get("name")]

    if cmd == "get_system_hostname":
        return socket.gethostname()

    if cmd == "get_network_interfaces_info":
        return network_interfaces_info()

    if cmd == "create_local_backup":
        filename = f"linux-{dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.zip"
        target = BACKUPS_DIR / filename
        create_backup_archive(target)
        return None

    if cmd == "delete_local_backup":
        (BACKUPS_DIR / str(args.get("filename") or "")).unlink(missing_ok=True)
        return None

    if cmd == "restore_local_backup":
        restore_backup_archive(BACKUPS_DIR / str(args.get("filename") or ""))
        return None

    if cmd == "import_local_backup":
        uploaded = maybe_bytes_from_arg(args.get("source"))
        if not uploaded:
            raise RuntimeError("backup file is required")
        filename, payload = uploaded
        temp = BACKUPS_DIR / f"import-{uuid.uuid4().hex}.zip"
        atomic_write_bytes(temp, payload)
        try:
            restore_backup_archive(temp)
        finally:
            temp.unlink(missing_ok=True)
        return filename

    if cmd == "export_local_backup":
        path = BACKUPS_DIR / str(args.get("filename") or "")
        return {
            "filename": str(path),
            "download_name": path.name,
            "content_type": "application/zip",
            "content_b64": base64.b64encode(path.read_bytes()).decode("ascii"),
        }

    if cmd == "list_local_backup":
        return list_local_backups()

    if cmd == "save_webdav_config":
        verge = get_verge_config_state()
        verge["webdav_url"] = args.get("url") or ""
        verge["webdav_username"] = args.get("username") or ""
        verge["webdav_password"] = args.get("password") or ""
        save_verge_config_state(verge)
        return None

    if cmd == "create_webdav_backup":
        url, _, _ = webdav_config()
        filename = f"linux-{dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.zip"
        temp = Path(tempfile.mkstemp(suffix=".zip")[1])
        try:
            create_backup_archive(temp)
            status, _, _ = webdav_request(
                "PUT",
                f"{url}/{urllib.parse.quote(filename)}",
                body=temp.read_bytes(),
                headers={"Content-Type": "application/zip"},
            )
            if status >= 400:
                raise RuntimeError(f"webdav upload failed: {status}")
        finally:
            temp.unlink(missing_ok=True)
        return None

    if cmd == "list_webdav_backup":
        return list_webdav_backups()

    if cmd == "delete_webdav_backup":
        url, _, _ = webdav_config()
        status, _, _ = webdav_request("DELETE", f"{url}/{urllib.parse.quote(str(args.get('filename') or ''))}")
        if status >= 400:
            raise RuntimeError(f"webdav delete failed: {status}")
        return None

    if cmd == "restore_webdav_backup":
        url, _, _ = webdav_config()
        filename = str(args.get("filename") or "")
        status, payload, _ = webdav_request("GET", f"{url}/{urllib.parse.quote(filename)}")
        if status >= 400:
            raise RuntimeError(f"webdav download failed: {status}")
        temp = Path(tempfile.mkstemp(suffix=".zip")[1])
        try:
            atomic_write_bytes(temp, payload)
            restore_backup_archive(temp)
        finally:
            temp.unlink(missing_ok=True)
        return None

    if cmd == "script_validate_notice":
        return None

    if cmd == "validate_script_file":
        return True

    if cmd == "get_running_mode":
        return "Service"

    if cmd == "get_app_uptime":
        return int(time.time() - APP_START)

    if cmd in {"install_service", "uninstall_service", "reinstall_service", "repair_service"}:
        return None

    if cmd == "is_service_available":
        return True

    if cmd in {"entry_lightweight_mode", "exit_lightweight_mode"}:
        return None

    if cmd == "app_is_admin":
        return os.geteuid() == 0

    if cmd == "get_next_update_time":
        uid = str(args.get("uid") or "")
        profiles = get_profiles_state()
        item = next((entry for entry in profiles.get("items") or [] if entry.get("uid") == uid), None)
        if not item:
            return None
        interval = int(((item.get("option") or {}).get("update_interval")) or 0)
        updated = int(item.get("updated") or 0)
        if interval <= 0 or updated <= 0:
            return None
        return updated + interval * 3600 * 1000

    if cmd == "is_port_in_use":
        return port_in_use(int(args.get("port") or 0))

    if cmd == "clash_api_get_proxy_delay":
        name = urllib.parse.quote(str(args.get("name") or ""))
        url = urllib.parse.quote(str(args.get("url") or "http://cp.cloudflare.com"), safe="")
        timeout = int(args.get("timeout") or 10000)
        return controller_request("GET", f"/proxies/{name}/delay?timeout={timeout}&url={url}")

    if cmd == "test_delay":
        started = time.time()
        request = urllib.request.Request(str(args.get("url") or "http://cp.cloudflare.com"))
        with urllib.request.urlopen(request, timeout=12):
            pass
        return int((time.time() - started) * 1000)

    if cmd == "get_unlock_items":
        return DEFAULT_UNLOCK_ITEMS

    if cmd == "check_media_unlock":
        return check_unlock_status()

    if cmd == "open_web_url":
        return None

    if cmd == "sync_tray_proxy_selection":
        return None

    if cmd == "get_portable_flag":
        return False

    return None


class VergeApiHandler(BaseHTTPRequestHandler):
    server_version = "MihomoVergeAPI/1.0"

    def do_GET(self) -> None:
        self.route_request()

    def do_HEAD(self) -> None:
        self.route_request(head_only=True)

    def do_POST(self) -> None:
        self.route_request()

    def send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_bytes(self, payload: bytes, content_type: str, status: int = 200, head_only: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def send_text(self, text: str, status: int = 200) -> None:
        self.send_bytes(text.encode("utf-8"), "text/plain; charset=utf-8", status)

    def authenticate(self, allow_query_token: bool = False) -> bool:
        expected = verge_api_secret()
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:].strip() == expected:
            return True
        if allow_query_token:
            parsed = urllib.parse.urlparse(self.path)
            token = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
            if token == expected:
                return True
        return False

    def route_request(self, head_only: bool = False) -> None:
        ensure_state()
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/healthz":
            self.send_json({"ok": True, "time": iso_now()})
            return

        if parsed.path == "/public-config":
            if not self.authenticate(allow_query_token=True):
                self.send_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
                return
            self.send_json(public_config_payload())
            return

        if parsed.path == "/file":
            if not self.authenticate(allow_query_token=True):
                self.send_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
                return
            raw_path = urllib.parse.parse_qs(parsed.query).get("path", [""])[0]
            target = Path(raw_path)
            if not target.exists() or not file_is_allowed(target):
                self.send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self.send_bytes(target.read_bytes(), content_type, head_only=head_only)
            return

        if parsed.path == "/invoke" and self.command == "POST":
            if not self.authenticate():
                self.send_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                result = invoke_command(str(payload.get("cmd") or ""), payload.get("args") or {})
                self.send_json(result if result is not None else None)
            except Exception as exc:
                append_operation_log(f"invoke error: {exc}")
                self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self.send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        append_operation_log(format % args)


def main() -> int:
    ensure_state()
    append_operation_log(f"starting verge api on {HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), VergeApiHandler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
