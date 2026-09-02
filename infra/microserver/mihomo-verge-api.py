#!/usr/bin/env python3
from __future__ import annotations

import base64
import concurrent.futures
from contextvars import ContextVar
import copy
import datetime as dt
import hashlib
import gzip
import grp
import io
import json
import mimetypes
import os
import platform
import re
import secrets
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
import zipfile
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any

MODULE_DIR = str(Path(__file__).resolve().parent)
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)
from mihomo_core_updater import DEFAULT_STABLE_TAG, upgrade_core


APP_VERSION = os.environ.get("MIHOMO_VERGE_APP_VERSION", "2.5.2-webport.0")
BUILD_ID = os.environ.get("MIHOMO_VERGE_BUILD_ID", "")
GIT_COMMIT = os.environ.get("MIHOMO_VERGE_GIT_COMMIT", "")
PACKAGE_FINGERPRINT = os.environ.get("MIHOMO_VERGE_PACKAGE_FINGERPRINT", "")
RUNTIME_CONTRACT_ENV_PATH = os.environ.get("MIHOMO_VERGE_RUNTIME_CONTRACT_PATH", "")
APP_START = time.time()
ENSURING_EMPTY_RUNTIME = False
RUNTIME_CONTRACT_CACHE: dict[str, Any] | None = None
PROFILE_MAX_BYTES = int(
    os.environ.get("MIHOMO_VERGE_PROFILE_MAX_BYTES", str(12 * 1024 * 1024))
)
PROFILE_MUTATION_LOCK = threading.Lock()

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
RUNTIME_PROFILE_HEALTH_PATH = DATA_ROOT / "runtime-profile-health.json"
OPERATIONS_LOG_PATH = LOGS_DIR / "operations.log"
VERGE_API_SECRET_PATH = Path(
    os.environ.get("VERGE_API_SECRET_FILE", "/etc/mihomo/verge-api.secret")
)
RESTORE_TRANSACTION_PATH = DATA_ROOT / "restore-transaction.json"
ALERT_OUTBOX_PATH = Path(
    os.environ.get("MIHOMO_ALERT_OUTBOX", str(LOGS_DIR / "alerts.jsonl"))
)
ALERT_STATE_PATH = Path(
    os.environ.get("MIHOMO_ALERT_STATE", str(LOGS_DIR / "alert-state.json"))
)
ALERT_WEBHOOK_URL = os.environ.get("MIHOMO_ALERT_WEBHOOK_URL", "").strip()
ALERT_COOLDOWN_SECONDS = max(
    0,
    int(os.environ.get("MIHOMO_ALERT_COOLDOWN_SECONDS", "300")),
)
ALERT_WEBHOOK_TIMEOUT_SECONDS = max(
    1,
    int(os.environ.get("MIHOMO_ALERT_WEBHOOK_TIMEOUT_SECONDS", "5")),
)
HEALTH_WATCH_INTERVAL_SECONDS = max(
    0,
    int(os.environ.get("MIHOMO_HEALTH_WATCH_INTERVAL_SECONDS", "0")),
)

LOG_CONTEXT: ContextVar[dict[str, str] | None] = ContextVar(
    "mihomo_verge_log_context", default=None
)
OPERATIONS_LOG_LOCK = threading.Lock()
RESTORE_LOCK = threading.RLock()
ALERT_LOCK = threading.RLock()
HEALTH_WATCH_STOP = threading.Event()

SENSITIVE_QUERY_PARAMETER_RE = re.compile(
    r"([?&](?:token|access_token|api_key|apikey|key|secret|password|passwd|auth|authorization|cookie|webhook)=)[^&#\s]*",
    re.IGNORECASE,
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"((?:token|access_token|api_key|apikey|key|secret|password|passwd|auth|authorization|cookie|webhook)\b\s*[:=]\s*)([^,;\s}\]]+)",
    re.IGNORECASE,
)
BEARER_RE = re.compile(r"(\bBearer\s+)[^\s]+", re.IGNORECASE)
BASIC_RE = re.compile(r"(\bBasic\s+)[^\s]+", re.IGNORECASE)
COOKIE_HEADER_RE = re.compile(
    r"(\bCookie:\s*)[^\s\r\n;]+(?:;\s*[^\s\r\n;]+)*", re.IGNORECASE
)
URL_USERINFO_RE = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^/\s@]+@", re.IGNORECASE)

MIHOMO_CONFIG_PATH = Path("/etc/mihomo/config.yaml")
MIHOMO_STATE_DIR = Path("/var/lib/mihomo")
MIHOMO_BIN = Path("/usr/local/bin/mihomo")
MMDB_PATH = MIHOMO_STATE_DIR / "Country.mmdb"
EMPTY_RESET_SENTINEL_PATH = MIHOMO_STATE_DIR / ".verge-clean-reset"
CONTROLLER_URL = "http://172.18.0.1:9090"

RESTORE_FILE_TARGETS = (
    ("verge.json", VERGE_CONFIG_PATH),
    ("profiles.json", PROFILES_CONFIG_PATH),
    ("system-overlay.json", OVERLAY_JSON_PATH),
    ("system-overlay.yaml", OVERLAY_YAML_PATH),
    ("dns-config.json", DNS_CONFIG_PATH),
    ("config.yaml", MIHOMO_CONFIG_PATH),
    ("verge-api.secret", VERGE_API_SECRET_PATH),
)
RESTORE_DIRECTORY_TARGETS = (
    ("profiles", PROFILES_DIR),
    ("icons", ICONS_DIR),
)
RESTORE_REQUIRED_MEMBERS = {
    "verge.json",
    "profiles.json",
    "config.yaml",
    "verge-api.secret",
    "profiles",
}
RESTORE_MAX_MEMBER_BYTES = max(
    1024,
    int(os.environ.get("MIHOMO_RESTORE_MAX_MEMBER_BYTES", str(64 * 1024 * 1024))),
)
RESTORE_MAX_TOTAL_BYTES = max(
    RESTORE_MAX_MEMBER_BYTES,
    int(os.environ.get("MIHOMO_RESTORE_MAX_TOTAL_BYTES", str(256 * 1024 * 1024))),
)

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
    "45.63.83.38/32",
    "45.32.130.255/32",
    "95.179.192.146/32",
    "139.84.241.187/32",
    "141.11.139.150/32",
    "110.42.109.179/32",
    "183.136.206.164/32",
    "114.66.59.177/32",
    "110.42.42.48/32",
    "139.180.182.231/32",
    "45.32.239.193/32",
    "107.172.76.12/32",
]

DEFAULT_TUN_CONFIG = {
    "enable": True,
    "stack": "system",
    "auto-route": True,
    "auto-detect-interface": True,
    "strict-route": True,
    "route-exclude-address": DEFAULT_ROUTE_EXCLUDES,
}

PUBLIC_DNS_SERVERS = ["223.5.5.5", "119.29.29.29"]
DEFAULT_DOH_SERVERS = [
    "https://dns.alidns.com/dns-query",
    "https://doh.pub/dns-query",
]
LEGACY_DOH_SERVERS = {
    "https://1.1.1.1/dns-query",
    "https://1.0.0.1/dns-query",
}
DNS_POLICY_DOMAINS = ("+.heiyu.space", "+.lazycat.cloud", "+.baidu.com")
LEGACY_DIRECT_DNS_SERVERS = {"192.168.1.1", "fe80::1"}

LEGACY_DIRECT_DNS_POLICY_KEYS = (
    "+.lazycat.cloud",
    "+.lazycat.cloud.lan",
    "+.heiyu.space.lan",
)

LAZYCAT_AUTH_COOKIE_NAMES = ("HC-Auth-Token",)

DEFAULT_HOME_CARDS = {
    "profile": True,
    "proxy": True,
    "network": True,
    "mode": True,
    "traffic": True,
    "test": True,
    "ip": True,
    "clashinfo": True,
    "systeminfo": True,
}

HOME_CARD_ALIASES = {
    "clash": "clashinfo",
    "system": "systeminfo",
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

DEFAULT_RUNTIME_PROFILE_HEALTH = {
    "status": "ready",
    "activeProfileId": "",
    "lastGoodProfileId": "",
    "lastAppliedAt": "",
    "lastError": "",
    "providerCounts": {},
}

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

IP_INFO_SERVICES = [
    {"name": "ip.sb", "url": "https://api.ip.sb/geoip"},
    {"name": "ipapi.co", "url": "https://ipapi.co/json"},
    {"name": "ipapi.is", "url": "https://api.ipapi.is/"},
    {"name": "ipwho.is", "url": "https://ipwho.is/"},
    {"name": "skk.moe", "url": "https://ip.api.skk.moe/cf-geoip"},
    {"name": "geojs", "url": "https://get.geojs.io/v1/ip/geo.json"},
]

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

DEFAULT_RUNTIME_CONTRACT = {
    "platform": "lazycat-web",
    "appVersion": APP_VERSION,
    "buildId": BUILD_ID or APP_VERSION,
    "gitCommit": GIT_COMMIT or "unknown",
    "apiSchemaVersion": "2026.08-lzc-v2",
    "uiSchemaVersion": "2026.08-lzc-v2",
    "packageFingerprint": PACKAGE_FINGERPRINT
    or f"cloud.lazycat.app.clash-verge-for-lc/{APP_VERSION}",
    "capabilities": {
        "externalOpen": {
            "mode": "enabled",
            "reason": "LazyCat Web 版会在浏览器新标签页中打开外部链接。",
        },
        "clipboard": {
            "mode": "enabled",
            "reason": "LazyCat Web 版支持复制内容到浏览器剪贴板。",
        },
        "download": {
            "mode": "enabled",
            "reason": "LazyCat Web 版会通过浏览器下载文件。",
        },
        "systemProxy": {
            "mode": "disabled",
            "reason": "LazyCat 微服 Web 版不支持接管宿主机系统代理，请使用虚拟网卡模式（TUN）或显式代理入口。",
        },
        "runtimeProfile": {
            "mode": "enabled",
            "reason": "当前运行态已绑定活动配置文件。",
            "label": "活动配置",
        },
        "filePicker": {
            "mode": "degraded",
            "reason": "LazyCat Web 版使用浏览器文件选择器代替桌面文件对话框。",
            "label": "浏览器文件选择器",
            "fallback": "browser-file-picker",
        },
        "directoryOpen": {
            "mode": "degraded",
            "reason": "LazyCat Web 版无法直接打开宿主机目录，将改为复制目录路径。",
            "label": "复制路径",
            "fallback": "copy-path",
        },
        "devtools": {
            "mode": "disabled",
            "reason": "请使用浏览器 DevTools。",
            "label": "浏览器 DevTools",
        },
        "lightweightMode": {
            "mode": "disabled",
            "reason": "LazyCat Web 版不支持桌面轻量模式，请使用桌面版 Clash Verge。",
        },
        "systemService": {
            "mode": "disabled",
            "reason": "LazyCat Web 版不支持安装、卸载或修复本机系统服务。",
        },
        "windowDecorations": {
            "mode": "disabled",
            "reason": "LazyCat Web 版不支持原生窗口装饰。",
        },
        "tray": {
            "mode": "disabled",
            "reason": "LazyCat Web 版不支持系统托盘能力。",
        },
    },
}


def unique_preserve_order(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def parse_dns_server_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return unique_preserve_order(re.split(r"[\s,]+", raw.strip()))


def detect_direct_dns_servers() -> list[str]:
    configured = parse_dns_server_list(os.environ.get("MIHOMO_DIRECT_DNS_SERVERS"))
    if configured:
        return configured

    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    for line in result.stdout.splitlines():
        match = re.search(r"\bvia\s+(\S+)", line)
        if match:
            return [match.group(1)]
    return []


def build_default_dns_config() -> dict[str, Any]:
    direct_dns_servers = detect_direct_dns_servers()
    bootstrap_servers = unique_preserve_order(direct_dns_servers + PUBLIC_DNS_SERVERS)

    config: dict[str, Any] = {
        "enable": True,
        "listen": "127.0.0.1:1053",
        "ipv6": True,
        "enhanced-mode": "redir-host",
        "use-hosts": True,
        "respect-rules": True,
        "default-nameserver": bootstrap_servers,
        "proxy-server-nameserver": bootstrap_servers,
        "nameserver": list(DEFAULT_DOH_SERVERS),
        "nameserver-policy": {},
    }

    if direct_dns_servers:
        config["nameserver-policy"] = {
            domain: list(direct_dns_servers) for domain in DNS_POLICY_DOMAINS
        }

    return config


def build_default_dns_state() -> dict[str, Any]:
    return {
        "dns": build_default_dns_config(),
        "hosts": {},
    }


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_now() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def runtime_contract_candidate_paths() -> list[Path]:
    paths: list[Path] = []
    if RUNTIME_CONTRACT_ENV_PATH:
        paths.append(Path(RUNTIME_CONTRACT_ENV_PATH))
    paths.append(Path(__file__).with_name("runtime-contract.json"))
    paths.append(
        Path(__file__).resolve().parents[2]
        / "src"
        / "mihomo-dashboard-app"
        / "runtime-contract.json"
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        marker = str(path)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(path)
    return unique


def load_runtime_contract() -> dict[str, Any]:
    global RUNTIME_CONTRACT_CACHE
    if RUNTIME_CONTRACT_CACHE is not None:
        return copy.deepcopy(RUNTIME_CONTRACT_CACHE)

    contract = copy.deepcopy(DEFAULT_RUNTIME_CONTRACT)
    for path in runtime_contract_candidate_paths():
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            append_operation_log(f"failed to read runtime contract from {path}: {exc}")
            continue
        if isinstance(payload, dict):
            contract.update(payload)
            capabilities = payload.get("capabilities")
            if isinstance(capabilities, dict):
                contract["capabilities"] = capabilities
            break

    if BUILD_ID:
        contract["buildId"] = BUILD_ID
    if GIT_COMMIT:
        contract["gitCommit"] = GIT_COMMIT
    if PACKAGE_FINGERPRINT:
        contract["packageFingerprint"] = PACKAGE_FINGERPRINT
    if APP_VERSION:
        contract["appVersion"] = APP_VERSION

    RUNTIME_CONTRACT_CACHE = contract
    return copy.deepcopy(contract)


def ensure_dirs() -> None:
    for path in (DATA_ROOT, PROFILES_DIR, BACKUPS_DIR, ICONS_DIR, LOGS_DIR):
        path.mkdir(parents=True, exist_ok=True)
    ALERT_OUTBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _fsync_directory(path: Path) -> None:
    """Persist an atomic rename when the underlying filesystem supports it."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def sanitize_log_text(message: object) -> str:
    """Remove credentials from operation messages and HTTP request lines."""
    text = str(message)
    text = URL_USERINFO_RE.sub(r"\1<redacted>@", text)
    text = SENSITIVE_QUERY_PARAMETER_RE.sub(r"\1<redacted>", text)
    text = BEARER_RE.sub(r"\1<redacted>", text)
    text = BASIC_RE.sub(r"\1<redacted>", text)
    text = COOKIE_HEADER_RE.sub(r"\1<redacted>", text)
    return SENSITIVE_ASSIGNMENT_RE.sub(r"\1<redacted>", text)


def profile_uid_for_log(raw: object) -> str:
    """Correlate a profile without persisting the profile identifier itself."""
    value = str(raw).strip()
    if not value:
        return "<empty>"
    return "uid_hash=" + hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]


def set_log_context(**updates: object) -> None:
    context = dict(LOG_CONTEXT.get() or {})
    for key, value in updates.items():
        if value is not None and str(value):
            context[key] = str(value)
    LOG_CONTEXT.set(context)


def _log_context_prefix() -> str:
    context = LOG_CONTEXT.get() or {}
    fields = []
    if context.get("request_id"):
        fields.append(f"request_id={context['request_id']}")
    if context.get("command"):
        fields.append(f"command={sanitize_log_text(context['command'])}")
    if context.get("profile_uid"):
        fields.append(f"profile_uid={profile_uid_for_log(context['profile_uid'])}")
    if context.get("stage"):
        fields.append(f"stage={sanitize_log_text(context['stage'])}")
    return f"[{ ' '.join(fields) }] " if fields else ""


def append_operation_log(message: str, *, error: BaseException | None = None) -> None:
    ensure_dirs()
    rendered = sanitize_log_text(message)
    if error is not None:
        traceback_text = " | ".join(
            line.strip()
            for line in traceback.format_exception(error)
            if line.strip()
        )
        rendered = f"{rendered}; cause={sanitize_log_text(traceback_text)}"
    line = f"[{iso_now()}] {_log_context_prefix()}{rendered}\n"
    with OPERATIONS_LOG_LOCK:
        with OPERATIONS_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line)


def atomic_write_bytes(path: Path, payload: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=str(path.parent)) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        tmp_name = handle.name
    if mode is not None:
        os.chmod(tmp_name, mode)
    os.replace(tmp_name, path)
    _fsync_directory(path.parent)


def atomic_write_text(path: Path, text: str, mode: int | None = None) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode)


def _append_alert_event(event: dict[str, Any]) -> None:
    """Append one durable alert/outbox event and fsync it before returning."""
    ensure_dirs()
    line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
    with ALERT_LOCK:
        with ALERT_OUTBOX_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())


def _alert_state() -> dict[str, Any]:
    if not ALERT_STATE_PATH.exists():
        return {}
    try:
        loaded = json.loads(ALERT_STATE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        append_operation_log("alert state load failed", error=exc)
        return {}
    return loaded if isinstance(loaded, dict) else {}


def record_runtime_alert(
    component: str,
    status: str,
    details: str = "",
) -> dict[str, Any] | None:
    """Persist transition alerts; repeated health polls are cooldown limited."""
    component = re.sub(r"[^a-z0-9_.-]", "_", str(component).lower()) or "runtime"
    status = str(status).lower()
    if status not in {"ok", "degraded"}:
        status = "degraded"
    now = time.time()
    with ALERT_LOCK:
        state = _alert_state()
        previous = state.get(component) if isinstance(state.get(component), dict) else {}
        previous_status = str(previous.get("status") or "")
        try:
            last_emitted = float(previous.get("lastEmittedAt") or 0)
        except (TypeError, ValueError):
            last_emitted = 0.0
        if not previous_status and status == "ok":
            state[component] = {
                "status": status,
                "lastEmittedAt": 0,
                "lastEventId": "",
            }
            atomic_write_text(
                ALERT_STATE_PATH,
                json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                0o600,
            )
            return None
        if previous_status == "ok" and status == "ok":
            return None
        changed = previous_status != status
        if not changed and now - last_emitted < ALERT_COOLDOWN_SECONDS:
            return None
        event = {
            "id": uuid.uuid4().hex,
            "createdAt": iso_now(),
            "component": component,
            "status": status,
            "details": sanitize_log_text(details)[:1000],
            "delivery": "pending" if ALERT_WEBHOOK_URL else "disabled",
        }
        # Keep the state update and the durable event ordered: a crash can
        # duplicate an alert, but can never suppress the first durable event.
        _append_alert_event(event)
        state[component] = {
            "status": status,
            "lastEmittedAt": now,
            "lastEventId": event["id"],
        }
        atomic_write_text(
            ALERT_STATE_PATH,
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            0o600,
        )
    return event


def flush_alert_outbox() -> None:
    """Best-effort delivery of pending alerts; the outbox remains the receipt."""
    if not ALERT_WEBHOOK_URL or not ALERT_OUTBOX_PATH.exists():
        return
    # Health requests and the background watcher can flush concurrently.  Keep
    # one sender in flight so a slow endpoint cannot produce duplicate POSTs
    # for the same durable alert event.
    with ALERT_LOCK:
        try:
            events = [
                json.loads(line)
                for line in ALERT_OUTBOX_PATH.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except Exception as exc:
            append_operation_log("alert outbox load failed", error=exc)
            return
        delivered = {
            str(event.get("alertId"))
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "delivery"
            and event.get("status") == "delivered"
        }
        for event in events:
            if not isinstance(event, dict) or not event.get("id"):
                continue
            if event.get("delivery") != "pending" or str(event["id"]) in delivered:
                continue
            payload = json.dumps(
                {
                    "id": event["id"],
                    "createdAt": event.get("createdAt"),
                    "component": event.get("component"),
                    "status": event.get("status"),
                    "details": event.get("details", ""),
                },
                ensure_ascii=False,
            ).encode("utf-8")
            request = urllib.request.Request(
                ALERT_WEBHOOK_URL,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "mihomo-verge-api-alert/1.0",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=ALERT_WEBHOOK_TIMEOUT_SECONDS,
                ) as response:
                    if not (200 <= int(response.status) < 300):
                        raise RuntimeError(f"alert endpoint returned HTTP {response.status}")
            except Exception as exc:
                append_operation_log("alert delivery failed", error=exc)
                continue
            _append_alert_event(
                {
                    "type": "delivery",
                    "alertId": event["id"],
                    "status": "delivered",
                    "createdAt": iso_now(),
                }
            )


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        append_operation_log(
            f"state load failed path={path} error={type(exc).__name__}",
            error=exc,
        )
        return copy.deepcopy(default)


def save_json(path: Path, data: Any, mode: int | None = None) -> None:
    atomic_write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        mode,
    )


def normalize_runtime_profile_health(raw: Any) -> dict[str, Any]:
    state = copy.deepcopy(DEFAULT_RUNTIME_PROFILE_HEALTH)
    if not isinstance(raw, dict):
        return state

    status = str(raw.get("status") or state["status"]).strip().lower()
    state["status"] = status if status in {"ready", "degraded"} else "ready"
    for key in ("activeProfileId", "lastGoodProfileId", "lastAppliedAt", "lastError"):
        state[key] = str(raw.get(key) or "")

    provider_counts = raw.get("providerCounts")
    if isinstance(provider_counts, dict):
        normalized_counts: dict[str, int] = {}
        for key, value in provider_counts.items():
            try:
                normalized_counts[str(key)] = max(0, int(value))
            except Exception:
                continue
        state["providerCounts"] = normalized_counts
    return state


def get_runtime_profile_health_state() -> dict[str, Any]:
    ensure_dirs()
    loaded = load_json(RUNTIME_PROFILE_HEALTH_PATH, DEFAULT_RUNTIME_PROFILE_HEALTH)
    normalized = normalize_runtime_profile_health(loaded)
    if normalized != loaded:
        save_json(RUNTIME_PROFILE_HEALTH_PATH, normalized)
    return normalized


def save_runtime_profile_health_state(state: dict[str, Any]) -> None:
    save_json(
        RUNTIME_PROFILE_HEALTH_PATH,
        normalize_runtime_profile_health(state),
    )


class ApiError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = HTTPStatus.BAD_REQUEST,
        layer: str = "verge-api",
        recoverable: bool = False,
        warning: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.layer = layer
        self.recoverable = recoverable
        self.warning = warning


def validation_valid(data: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "valid"}
    if data is not None:
        result["data"] = data
    return result


def validation_invalid(exc: Exception, *, fallback_code: str) -> dict[str, Any]:
    if isinstance(exc, ApiError):
        kind = exc.code
        message = exc.message
    else:
        kind = fallback_code
        message = str(exc)
    return {
        "status": "invalid",
        "kind": kind,
        "message": message,
    }


def error_envelope(
    code: str,
    message: str,
    *,
    layer: str = "verge-api",
    recoverable: bool = False,
    warning: dict[str, Any] | None = None,
    data: Any = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "layer": layer,
        "recoverable": recoverable,
    }
    if warning is not None:
        payload["warning"] = warning
    if data is not None:
        payload["data"] = data
    return payload


def exception_envelope(exc: Exception, default_code: str = "COMMAND_FAILED") -> tuple[dict[str, Any], int]:
    if isinstance(exc, ApiError):
        return (
            error_envelope(
                exc.code,
                exc.message,
                layer=exc.layer,
                recoverable=exc.recoverable,
                warning=exc.warning,
            ),
            int(exc.status),
        )
    return (
        error_envelope(default_code, str(exc), layer="verge-api", recoverable=False),
        int(HTTPStatus.BAD_REQUEST),
    )


def ensure_mihomo_config_owner(path: Path) -> None:
    gid = 0
    try:
        gid = grp.getgrnam("mihomo").gr_gid
    except KeyError:
        if path.exists():
            gid = path.stat().st_gid
    os.chown(path, 0, gid)


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

    def is_top_level_mapping_key(line: str) -> bool:
        stripped = line.rstrip("\n")
        if not stripped or stripped.startswith((" ", "\t", "-")):
            return False
        head, sep, _ = stripped.partition(":")
        return bool(sep and head)

    for idx, line in enumerate(lines):
        stripped = line.rstrip("\n")
        head, sep, _ = stripped.partition(":")
        if sep and head == key and not line.startswith((" ", "\t")):
            start = idx
            break
    if start is None:
        return None
    end = start + 1
    while end < len(lines):
        line = lines[end]
        stripped = line.rstrip("\n")
        if not stripped:
            end += 1
            continue
        if line.startswith((" ", "\t")):
            end += 1
            continue
        if stripped.startswith("-"):
            end += 1
            continue
        if is_top_level_mapping_key(line):
            break
        end += 1
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


MIHOMO_JOURNAL_LINE_PATTERN = re.compile(
    r'^time=".+?"\s+level=(debug|info|warning|warn|error|err)\s+msg=".*"$',
    re.IGNORECASE,
)


def filter_mihomo_journal_lines(lines: list[str]) -> list[str]:
    rows: list[str] = []
    for line in lines:
        text = str(line or "").strip()
        if not text:
            continue
        if MIHOMO_JOURNAL_LINE_PATTERN.match(text):
            rows.append(text)
    return rows


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


def parse_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, str):
            digits = re.sub(r"^[A-Za-z]+", "", value)
            return int(digits)
        return int(value)
    except Exception:
        return default


def parse_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


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


def get_clash_mode() -> str | None:
    overlay_mode = load_overlay().get("mode")
    if isinstance(overlay_mode, str) and overlay_mode.strip():
        return overlay_mode.strip()
    try:
        runtime = controller_request("GET", "/configs", timeout=6)
    except Exception:
        return None
    if isinstance(runtime, dict):
        mode = runtime.get("mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
    return None


def get_runtime_proxy_group_order() -> list[str]:
    try:
        runtime = controller_request("GET", "/configs", timeout=6)
    except Exception:
        runtime = {}

    if isinstance(runtime, dict):
        groups = runtime.get("proxy-groups")
        if isinstance(groups, list):
            names = [
                str(item.get("name")).strip()
                for item in groups
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            ]
            if names:
                return unique_preserve_order(names)

    if not MIHOMO_CONFIG_PATH.exists():
        return []
    names: list[str] = []
    in_group_block = False
    for line in MIHOMO_CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        if line == "proxy-groups:" or line.startswith("proxy-groups:"):
            in_group_block = True
            continue
        if in_group_block and line and not line.startswith((" ", "\t")):
            break
        if in_group_block:
            match = re.match(r"^\s*-\s+name:\s*(.*?)\s*$", line)
            if match:
                name = parse_yaml_scalar(match.group(1))
                if name:
                    names.append(name)
    return unique_preserve_order(names)


def load_dns_config() -> dict[str, Any]:
    return load_dns_state()["dns"]


def normalize_dns_state(raw: Any) -> tuple[dict[str, Any], bool]:
    changed = False
    dns_raw: Any = {}
    hosts_raw: Any = {}

    if isinstance(raw, dict) and ("dns" in raw or "hosts" in raw):
        dns_raw = raw.get("dns")
        hosts_raw = raw.get("hosts")
        if dns_raw is None:
            dns_raw = {}
        if hosts_raw is None:
            hosts_raw = {}
        if not isinstance(dns_raw, dict) or not isinstance(hosts_raw, dict):
            changed = True
    elif isinstance(raw, dict):
        dns_raw = raw
        hosts_raw = {}
        changed = True
    elif raw is not None:
        changed = True

    if not isinstance(dns_raw, dict):
        dns_raw = {}
    if not isinstance(hosts_raw, dict):
        hosts_raw = {}

    normalized = {
        "dns": deep_merge(build_default_dns_config(), dns_raw),
        "hosts": copy.deepcopy(hosts_raw),
    }
    if raw != normalized:
        changed = True
    return normalized, changed


def load_dns_state() -> dict[str, Any]:
    loaded = load_json(DNS_CONFIG_PATH, build_default_dns_state())
    normalized, changed = normalize_dns_state(loaded)
    if changed:
        save_json(DNS_CONFIG_PATH, normalized)
    return normalized


def load_dns_hosts() -> dict[str, Any]:
    return load_dns_state()["hosts"]


def save_dns_config_state(data: dict[str, Any]) -> None:
    normalized, _ = normalize_dns_state(data)
    save_json(DNS_CONFIG_PATH, normalized)


def normalize_dns_config(data: dict[str, Any], enabled: bool) -> dict[str, Any]:
    defaults = build_default_dns_config()
    merged = deep_merge(defaults, data)
    merged["enable"] = enabled
    direct_dns_servers = detect_direct_dns_servers()
    bootstrap_servers = unique_preserve_order(direct_dns_servers + PUBLIC_DNS_SERVERS)

    current_default_nameserver = list(merged.get("default-nameserver") or [])
    current_proxy_nameserver = list(merged.get("proxy-server-nameserver") or [])
    if not current_default_nameserver or LEGACY_DIRECT_DNS_SERVERS.intersection(
        current_default_nameserver
    ):
        merged["default-nameserver"] = bootstrap_servers
    if not current_proxy_nameserver or LEGACY_DIRECT_DNS_SERVERS.intersection(
        current_proxy_nameserver
    ):
        merged["proxy-server-nameserver"] = bootstrap_servers

    current_nameserver = list(merged.get("nameserver") or [])
    if not current_nameserver or set(current_nameserver).issubset(LEGACY_DOH_SERVERS):
        merged["nameserver"] = list(DEFAULT_DOH_SERVERS)

    policy = copy.deepcopy(merged.get("nameserver-policy") or {})
    for key in LEGACY_DIRECT_DNS_POLICY_KEYS:
        policy.pop(key, None)
    if direct_dns_servers:
        for domain in DNS_POLICY_DOMAINS:
            policy[domain] = list(direct_dns_servers)
    else:
        for domain in DNS_POLICY_DOMAINS:
            existing = list(policy.get(domain) or [])
            if LEGACY_DIRECT_DNS_SERVERS.intersection(existing):
                policy.pop(domain, None)
    merged["nameserver-policy"] = policy
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
        tail = urllib.parse.unquote(Path(parsed.path).name or parsed.netloc)
        if tail:
            return tail
    return f"Profile {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def normalize_profile_name_candidate(raw: str | None) -> str | None:
    if raw is None:
        return None
    candidate = urllib.parse.unquote(str(raw).strip().strip('"').strip("'"))
    candidate = Path(candidate).name.strip()
    if not candidate:
        return None
    if len(candidate) > 128:
        candidate = candidate[:128].strip()
    return candidate or None


def parse_content_disposition_filename(header_value: str) -> str | None:
    if not header_value:
        return None
    encoded = re.search(r"""filename\*\s*=\s*([^;]+)""", header_value, flags=re.I)
    if encoded:
        value = encoded.group(1).strip().strip('"')
        if "''" in value:
            _, value = value.split("''", 1)
        return normalize_profile_name_candidate(value)

    plain = re.search(r"""filename\s*=\s*("?)([^";]+)\1""", header_value, flags=re.I)
    if plain:
        return normalize_profile_name_candidate(plain.group(2))
    return None


def resolve_remote_profile_name_hint(
    url: str,
    headers: dict[str, str],
) -> str | None:
    if headers.get("profile-title"):
        name = normalize_profile_name_candidate(headers.get("profile-title"))
        if name:
            return name

    disposition_name = parse_content_disposition_filename(
        headers.get("content-disposition", "")
    )
    if disposition_name:
        return disposition_name

    return normalize_profile_name_candidate(default_profile_name(url))


def default_profile_option() -> dict[str, Any]:
    return {
        "with_proxy": True,
        "self_proxy": False,
        "allow_auto_update": True,
        "update_interval": 24,
        "timeout_seconds": 20,
    }


def profile_import_transport(option: dict[str, Any]) -> str:
    if option.get("self_proxy"):
        return "self_proxy"
    if option.get("with_proxy") is False:
        return "direct"
    return "system"


def sanitize_profile_url(url: str) -> str:
    """Keep diagnostics useful without retaining userinfo or query secrets."""
    try:
        parsed = urllib.parse.urlsplit(str(url))
        hostname = parsed.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        port = ""
        try:
            if parsed.port is not None:
                port = f":{parsed.port}"
        except ValueError:
            port = ""
        netloc = f"{hostname}{port}"
        return urllib.parse.urlunsplit(
            (parsed.scheme.lower(), netloc, parsed.path or "/", "", "")
        )
    except Exception:
        return "<invalid-profile-url>"


def profile_url_credentials(url: str) -> tuple[str, str | None, str | None]:
    parsed = urllib.parse.urlsplit(str(url))
    username = parsed.username
    password = parsed.password

    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    port = ""
    try:
        if parsed.port is not None:
            port = f":{parsed.port}"
    except ValueError:
        pass

    # Keep the complete query for tokenized subscriptions, while removing
    # userinfo from the URL because credentials are sent explicitly below.
    transport_url = urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            f"{hostname}{port}",
            parsed.path or "/",
            parsed.query,
            "",
        )
    )
    if username is None:
        return transport_url, None, None

    username = urllib.parse.unquote(username)
    password = urllib.parse.unquote(password or "")
    return transport_url, username, password


def profile_url_origin(url: str) -> tuple[str, str, int | None]:
    parsed = urllib.parse.urlsplit(str(url))
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


class ProfileRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        if profile_url_origin(req.full_url) != profile_url_origin(newurl):
            for key in list(redirected.headers):
                if key.lower() == "authorization":
                    del redirected.headers[key]
            for key in list(redirected.unredirected_hdrs):
                if key.lower() == "authorization":
                    del redirected.unredirected_hdrs[key]
        return redirected


def profile_tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def read_profile_response_payload(response: Any) -> str:
    read_limit = max(0, PROFILE_MAX_BYTES) + 1
    raw = response.read(read_limit)
    if not isinstance(raw, (bytes, bytearray)):
        raw = str(raw).encode("utf-8")
    payload_bytes = bytes(raw)
    if len(payload_bytes) > PROFILE_MAX_BYTES:
        raise ApiError(
            "PROFILE_CONTENT_TOO_LARGE",
            "订阅内容超过大小限制。",
            status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            layer="profile-import",
            recoverable=True,
        )

    encoding = str(response.headers.get("Content-Encoding", "")).lower()
    if "gzip" in encoding or payload_bytes.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(payload_bytes)) as stream:
                payload_bytes = stream.read(read_limit)
        except (OSError, EOFError) as exc:
            raise ApiError(
                "PROFILE_CONTENT_INVALID",
                "订阅 gzip 内容无法解压。",
                status=HTTPStatus.BAD_REQUEST,
                layer="profile-import",
                recoverable=True,
            ) from exc

    if len(payload_bytes) > PROFILE_MAX_BYTES:
        raise ApiError(
            "PROFILE_CONTENT_TOO_LARGE",
            "订阅内容超过大小限制。",
            status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            layer="profile-import",
            recoverable=True,
        )

    content_type = str(response.headers.get("Content-Type", "")).lower()
    charset_match = re.search(r"charset=\s*['\"]?([\w.-]+)", content_type)
    charset = charset_match.group(1) if charset_match else "utf-8"
    try:
        return payload_bytes.decode(charset, errors="replace")
    except LookupError:
        return payload_bytes.decode("utf-8", errors="replace")


def looks_like_html_payload(payload: str) -> bool:
    sample = payload.lstrip().lower()
    return sample.startswith("<!doctype html") or sample.startswith("<html")


def top_level_block_has_content(text: str, key: str) -> bool:
    block_range = top_level_block_range(text, key)
    if block_range is None:
        return False

    block_text = text[block_range[0] : block_range[1]].strip()
    if not block_text:
        return False

    inline = re.match(rf"^{re.escape(key)}\s*:\s*(.*)$", block_text)
    if inline and "\n" not in block_text:
        value = inline.group(1).strip()
        return value not in ("", "[]", "{}", "null")

    lines = block_text.splitlines()
    if len(lines) <= 1:
        return False

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return True
    return False


def validate_remote_profile_payload(
    payload: str,
    *,
    content_type: str,
    source_url: str,
) -> dict[str, Any]:
    source_url = sanitize_profile_url(source_url)
    normalized = payload.lstrip("\ufeff")
    lowered_ct = content_type.lower()
    if "text/html" in lowered_ct or looks_like_html_payload(normalized):
        raise ApiError(
            "PROFILE_HTML_LOGIN_PAGE",
            "订阅链接返回了登录页/HTML 内容，请改用可直接下载 YAML 的订阅链接。",
            status=HTTPStatus.BAD_REQUEST,
            layer="profile-import",
            recoverable=True,
            warning={"url": source_url, "contentType": content_type},
        )

    if not normalized.strip():
        raise ApiError(
            "PROFILE_CONTENT_INVALID",
            "订阅内容为空，请检查订阅链接是否有效。",
            status=HTTPStatus.BAD_REQUEST,
            layer="profile-import",
            recoverable=True,
            warning={"url": source_url, "contentType": content_type},
        )

    has_proxy_groups = top_level_block_range(normalized, "proxy-groups") is not None
    has_rules = top_level_block_range(normalized, "rules") is not None
    has_proxies = top_level_block_has_content(normalized, "proxies")
    has_proxy_providers = top_level_block_has_content(normalized, "proxy-providers")
    has_node_source = has_proxies or has_proxy_providers

    if not has_proxy_groups or not has_rules or not has_node_source:
        missing: list[str] = []
        if not has_proxy_groups:
            missing.append("proxy-groups")
        if not has_rules:
            missing.append("rules")
        if not has_node_source:
            missing.append("proxies/proxy-providers")
        raise ApiError(
            "PROFILE_CONTENT_INVALID",
            f"订阅内容缺少必需段落: {', '.join(missing)}",
            status=HTTPStatus.BAD_REQUEST,
            layer="profile-import",
            recoverable=True,
            warning={
                "url": source_url,
                "contentType": content_type,
                "summary": {
                    "hasProxyGroups": has_proxy_groups,
                    "hasRules": has_rules,
                    "hasProxies": has_proxies,
                    "hasProxyProviders": has_proxy_providers,
                },
            },
        )

    return {
        "hasProxyGroups": has_proxy_groups,
        "hasRules": has_rules,
        "hasProxies": has_proxies,
        "hasProxyProviders": has_proxy_providers,
    }


def normalize_profiles_state(raw: Any) -> tuple[dict[str, Any], bool]:
    if not isinstance(raw, dict):
        return {"current": "", "items": []}, True

    normalized = copy.deepcopy(raw)
    changed = False
    items = normalized.get("items")
    if not isinstance(items, list):
        items = []
        changed = True
    normalized["items"] = items

    current = normalized.get("current")
    if not isinstance(current, str):
        current = str(current or "")
        changed = True

    filtered_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("uid"):
            changed = True
            continue
        uid = str(item.get("uid"))
        if not profile_path(uid).exists():
            changed = True
            continue
        filtered_items.append(item)

    if filtered_items != items:
        normalized["items"] = filtered_items
        items = filtered_items
        changed = True

    valid_ids = [str(item.get("uid")) for item in items]
    if current and current not in valid_ids:
        current = valid_ids[0] if valid_ids else ""
        changed = True
    elif not current and valid_ids:
        current = valid_ids[0]
        changed = True

    normalized["current"] = current
    return normalized, changed


def get_profiles_state() -> dict[str, Any]:
    loaded = load_json(PROFILES_CONFIG_PATH, {"current": "", "items": []})
    normalized, changed = normalize_profiles_state(loaded)
    if changed:
        save_json(PROFILES_CONFIG_PATH, normalized)
    return normalized


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


def normalize_home_cards(value: Any) -> tuple[dict[str, bool], bool]:
    changed = False
    normalized: dict[str, bool] = {}

    if isinstance(value, dict):
        for raw_key, raw_value in value.items():
            key = HOME_CARD_ALIASES.get(str(raw_key), str(raw_key))
            if key not in DEFAULT_HOME_CARDS:
                changed = True
                continue
            if key != raw_key:
                changed = True
            normalized[key] = bool(raw_value)
    else:
        changed = value is not None

    for key, default in DEFAULT_HOME_CARDS.items():
        if key not in normalized:
            normalized[key] = default
            changed = True

    if normalized != value:
        changed = True

    return normalized, changed


def normalize_verge_config_state(raw: Any) -> tuple[dict[str, Any], bool]:
    if not isinstance(raw, dict):
        return copy.deepcopy(DEFAULT_VERGE_CONFIG), True

    normalized = copy.deepcopy(raw)
    changed = False
    home_cards, home_cards_changed = normalize_home_cards(normalized.get("home_cards"))
    normalized["home_cards"] = home_cards
    changed = changed or home_cards_changed
    if normalized.get("enable_system_proxy") is not False:
        normalized["enable_system_proxy"] = False
        changed = True
    return normalized, changed


def ensure_state() -> None:
    global ENSURING_EMPTY_RUNTIME
    ensure_dirs()
    cleanup_restore_orphans()
    restore_reconciled = reconcile_restore_transaction()
    verge_api_secret()
    initialized_empty_state = False

    if not VERGE_CONFIG_PATH.exists():
        save_json(VERGE_CONFIG_PATH, detect_bootstrap_verge_config())

    if not DNS_CONFIG_PATH.exists():
        save_json(DNS_CONFIG_PATH, build_default_dns_state())

    if not OVERLAY_JSON_PATH.exists():
        save_overlay({})

    if not PROXY_CHAIN_PATH.exists():
        save_json(PROXY_CHAIN_PATH, {"items": []})

    if not PROFILES_CONFIG_PATH.exists():
        if EMPTY_RESET_SENTINEL_PATH.exists():
            save_profiles_state({"current": "", "items": []})
            EMPTY_RESET_SENTINEL_PATH.unlink(missing_ok=True)
            append_operation_log("initialized empty verge state after clean reset")
            initialized_empty_state = True
        else:
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

    profiles = get_profiles_state()
    if (
        profiles_explicitly_empty(profiles)
        and not ENSURING_EMPTY_RUNTIME
        and empty_runtime_requires_repair()
    ):
        ENSURING_EMPTY_RUNTIME = True
        try:
            apply_empty_profile_runtime()
            if initialized_empty_state:
                append_operation_log("repaired empty runtime controller after clean reset")
            else:
                append_operation_log(
                    "reconciled stale mihomo runtime with empty profile state"
                )
        finally:
            ENSURING_EMPTY_RUNTIME = False

    if restore_reconciled and not ENSURING_EMPTY_RUNTIME:
        ENSURING_EMPTY_RUNTIME = True
        try:
            apply_runtime_for_current_or_empty_state()
            record_runtime_alert("restore", "ok", "startup restore reconciliation completed")
        except Exception as exc:
            record_runtime_alert("restore", "degraded", str(exc))
            append_operation_log("startup restore runtime reconciliation failed", error=exc)
            raise
        finally:
            ENSURING_EMPTY_RUNTIME = False


def get_verge_config_state() -> dict[str, Any]:
    ensure_state()
    loaded = load_json(VERGE_CONFIG_PATH, DEFAULT_VERGE_CONFIG)
    normalized, changed = normalize_verge_config_state(loaded)
    if changed:
        save_json(VERGE_CONFIG_PATH, normalized)
    return normalized


def save_verge_config_state(data: dict[str, Any]) -> None:
    normalized, _ = normalize_verge_config_state(data)
    save_json(VERGE_CONFIG_PATH, normalized)


def current_mixed_port() -> int:
    try:
        runtime = controller_request("GET", "/configs", timeout=6)
    except Exception:
        runtime = {}
    return parse_int(runtime.get("mixed-port") or get_verge_config_state().get("verge_mixed_port") or 7890, 7890)


def mihomo_proxy_url() -> str:
    return f"http://127.0.0.1:{current_mixed_port()}"


def build_mihomo_proxy_opener() -> urllib.request.OpenerDirector:
    proxy_url = mihomo_proxy_url()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    )


def proxy_request(
    url: str,
    *,
    timeout: int = 12,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        headers=headers
        or {"User-Agent": "clash-verge-webport/1.0"},
    )
    opener = build_mihomo_proxy_opener()
    with opener.open(request, timeout=timeout) as response:
        return int(response.status or 0), response.read()


def map_ip_info(service_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if service_name == "ip.sb":
        return {
            "ip": payload.get("ip") or "",
            "country_code": payload.get("country_code") or "",
            "country": payload.get("country") or "",
            "region": payload.get("region") or "",
            "city": payload.get("city") or "",
            "organization": payload.get("organization") or payload.get("isp") or "",
            "asn": parse_int(payload.get("asn")),
            "asn_organization": payload.get("asn_organization") or "",
            "longitude": parse_float(payload.get("longitude")),
            "latitude": parse_float(payload.get("latitude")),
            "timezone": payload.get("timezone") or "",
        }
    if service_name == "ipapi.co":
        return {
            "ip": payload.get("ip") or "",
            "country_code": payload.get("country_code") or "",
            "country": payload.get("country_name") or "",
            "region": payload.get("region") or "",
            "city": payload.get("city") or "",
            "organization": payload.get("org") or "",
            "asn": parse_int(payload.get("asn")),
            "asn_organization": payload.get("org") or "",
            "longitude": parse_float(payload.get("longitude")),
            "latitude": parse_float(payload.get("latitude")),
            "timezone": payload.get("timezone") or "",
        }
    if service_name == "ipapi.is":
        location = payload.get("location") or {}
        asn = payload.get("asn") or {}
        company = payload.get("company") or {}
        return {
            "ip": payload.get("ip") or "",
            "country_code": location.get("country_code") or "",
            "country": location.get("country") or "",
            "region": location.get("state") or "",
            "city": location.get("city") or "",
            "organization": asn.get("org") or company.get("name") or "",
            "asn": parse_int(asn.get("asn")),
            "asn_organization": asn.get("org") or "",
            "longitude": parse_float(location.get("longitude")),
            "latitude": parse_float(location.get("latitude")),
            "timezone": location.get("timezone") or "",
        }
    if service_name == "ipwho.is":
        connection = payload.get("connection") or {}
        timezone = payload.get("timezone") or {}
        return {
            "ip": payload.get("ip") or "",
            "country_code": payload.get("country_code") or "",
            "country": payload.get("country") or "",
            "region": payload.get("region") or "",
            "city": payload.get("city") or "",
            "organization": connection.get("org") or connection.get("isp") or "",
            "asn": parse_int(connection.get("asn")),
            "asn_organization": connection.get("isp") or "",
            "longitude": parse_float(payload.get("longitude")),
            "latitude": parse_float(payload.get("latitude")),
            "timezone": timezone.get("id") or "",
        }
    if service_name == "skk.moe":
        return {
            "ip": payload.get("ip") or "",
            "country_code": payload.get("country") or "",
            "country": payload.get("country") or "",
            "region": payload.get("region") or "",
            "city": payload.get("city") or "",
            "organization": payload.get("asOrg") or "",
            "asn": parse_int(payload.get("asn")),
            "asn_organization": payload.get("asOrg") or "",
            "longitude": parse_float(payload.get("longitude")),
            "latitude": parse_float(payload.get("latitude")),
            "timezone": payload.get("timezone") or "",
        }
    return {
        "ip": payload.get("ip") or "",
        "country_code": payload.get("country_code") or "",
        "country": payload.get("country") or "",
        "region": payload.get("region") or "",
        "city": payload.get("city") or "",
        "organization": payload.get("organization_name") or "",
        "asn": parse_int(payload.get("asn")),
        "asn_organization": payload.get("organization_name") or "",
        "longitude": parse_float(payload.get("longitude")),
        "latitude": parse_float(payload.get("latitude")),
        "timezone": payload.get("timezone") or "",
    }


def classify_network_error(exc: Exception) -> tuple[str, str]:
    message = str(exc).lower()
    if isinstance(exc, urllib.error.HTTPError):
        return "upstream_http_error", f"上游 IP 服务返回 HTTP {exc.code}"
    if isinstance(exc, (socket.timeout, TimeoutError)) or "timed out" in message:
        return "timeout", "通过 Mihomo 获取出口 IP 超时"
    if "eof" in message or "ssl" in message or "handshake" in message:
        return "proxy_connect_error", "通过 Mihomo 获取出口 IP 失败"
    return "network_error", "无法通过 Mihomo 获取出口 IP"


def classify_delay_error(exc: Exception) -> tuple[str, str]:
    message = str(exc).lower()
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 504:
            return "timeout", "延迟测试超时"
        if 400 <= exc.code < 500:
            return "target_unreachable", f"测试目标不可达（HTTP {exc.code}）"
        return "network_error", f"延迟测试失败（HTTP {exc.code}）"
    if isinstance(exc, (socket.timeout, TimeoutError)) or "timed out" in message:
        return "timeout", "延迟测试超时"
    if "name or service not known" in message or "no address associated" in message:
        return "target_unreachable", "测试目标不可达"
    return "network_error", "延迟测试失败"


def controller_delay_result(
    path: str,
    target: str,
    url: str,
    timeout: int,
) -> dict[str, Any]:
    query = urllib.parse.urlencode({"timeout": timeout, "url": url})
    try:
        result = controller_request("GET", f"{path}?{query}", timeout=max(1, timeout // 1000 + 2))
        delay = int((result or {}).get("delay") or 0)
        return {
            "target": target,
            "status": "success",
            "latencyMs": delay,
            "delay": delay,
        }
    except Exception as exc:
        error_code, error_message = classify_delay_error(exc)
        return {
            "target": target,
            "status": error_code,
            "delay": timeout if error_code == "timeout" else 1_000_000,
            "errorCode": error_code,
            "errorMessage": error_message,
        }


def classify_probe_error(exc: Exception) -> tuple[str, str]:
    message = str(exc).lower()
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 504:
            return "timeout", "检测超时"
        return "failed", f"检测失败（HTTP {exc.code}）"
    if isinstance(exc, (socket.timeout, TimeoutError)) or "timed out" in message:
        return "timeout", "检测超时"
    return "failed", "网络请求失败"


def to_public_probe_code(code: str) -> str:
    mapping = {
        "success": "OK",
        "timeout": "TIMEOUT",
        "proxy_connect_error": "UPSTREAM_TLS",
        "upstream_http_error": "TARGET_BLOCKED",
        "network_error": "PROXY_UNREACHABLE",
        "target_unreachable": "TARGET_BLOCKED",
        "failed": "UNKNOWN",
    }
    return mapping.get(code, "UNKNOWN")


def classify_public_probe_error(exc: Exception) -> tuple[str, str]:
    message = str(exc).lower()
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (401, 403, 451):
            return "TARGET_BLOCKED", f"检测目标返回 HTTP {exc.code}"
        if exc.code == 504:
            return "TIMEOUT", "检测超时"
        if 400 <= exc.code < 500:
            return "TARGET_BLOCKED", f"检测目标返回 HTTP {exc.code}"
        return "UNKNOWN", f"检测目标返回 HTTP {exc.code}"
    if isinstance(exc, (socket.timeout, TimeoutError)) or "timed out" in message:
        return "TIMEOUT", "检测超时"
    if "eof" in message or "ssl" in message or "handshake" in message:
        return "UPSTREAM_TLS", "通过 Mihomo 建立 TLS 连接失败"
    if "refused" in message or "unreachable" in message or "reset" in message:
        return "PROXY_UNREACHABLE", "当前代理链路不可达"
    return "UNKNOWN", "网络请求失败"


def runtime_probe_health() -> dict[str, Any]:
    try:
        version = controller_request("GET", "/version", timeout=4)
        if not isinstance(version, dict) or not str(version.get("version") or "").strip():
            raise RuntimeError("controller returned an invalid /version payload")
    except Exception as exc:
        result = {
            "status": "degraded",
            "checkedAt": iso_now(),
            "details": sanitize_log_text(str(exc))[:500],
        }
        record_runtime_alert("controller", "degraded", result["details"])
        flush_alert_outbox()
        return result
    result = {
        "status": "ok",
        "checkedAt": iso_now(),
        "version": str(version.get("version") or "unknown"),
    }
    record_runtime_alert("controller", "ok", result["version"])
    flush_alert_outbox()
    return result


def restore_transaction_status() -> dict[str, Any]:
    if not RESTORE_TRANSACTION_PATH.exists():
        return {"status": "ok"}
    transaction = load_json(RESTORE_TRANSACTION_PATH, {})
    if not isinstance(transaction, dict):
        return {"status": "degraded", "phase": "invalid"}
    return {
        "status": "degraded",
        "phase": str(transaction.get("phase") or "pending"),
        "generation": str(transaction.get("generation") or "unknown"),
    }


def healthz_payload() -> dict[str, Any]:
    controller = runtime_probe_health()
    restore = restore_transaction_status()
    ok = controller.get("status") == "ok" and restore.get("status") == "ok"
    if restore.get("status") != "ok":
        record_runtime_alert("restore", "degraded", str(restore.get("phase") or "pending"))
        flush_alert_outbox()
    else:
        record_runtime_alert("restore", "ok", "")
        flush_alert_outbox()
    return {
        "ok": ok,
        "status": "ok" if ok else "degraded",
        "time": iso_now(),
        "controller": controller,
        "restore": restore,
    }


def runtime_profile_provider_counts() -> dict[str, int]:
    try:
        payload = controller_request("GET", "/providers/proxies", timeout=6)
    except Exception:
        return {}

    providers = payload.get("providers") if isinstance(payload, dict) else {}
    counts: dict[str, int] = {}
    if not isinstance(providers, dict):
        return counts

    for name, item in providers.items():
        if not isinstance(item, dict):
            continue
        proxies = item.get("proxies") or []
        if isinstance(proxies, list):
            counts[str(name)] = len(proxies)
    return counts


def mark_runtime_profile_ready(active_profile_id: str) -> dict[str, Any]:
    state = get_runtime_profile_health_state()
    state["status"] = "ready"
    state["activeProfileId"] = active_profile_id
    if active_profile_id:
        state["lastGoodProfileId"] = active_profile_id
    state["lastAppliedAt"] = iso_now()
    state["lastError"] = ""
    state["providerCounts"] = runtime_profile_provider_counts()
    save_runtime_profile_health_state(state)
    return state


def mark_runtime_profile_degraded(error_message: str) -> dict[str, Any]:
    state = get_runtime_profile_health_state()
    state["status"] = "degraded"
    state["lastError"] = str(error_message or "")
    if not state.get("activeProfileId"):
        state["activeProfileId"] = str(state.get("lastGoodProfileId") or "")
    save_runtime_profile_health_state(state)
    return state


def runtime_info_payload() -> dict[str, Any]:
    contract = load_runtime_contract()
    profile_health = get_runtime_profile_health_state()
    capabilities = copy.deepcopy(
        contract.get("capabilities") or DEFAULT_RUNTIME_CONTRACT["capabilities"]
    )
    capabilities["systemProxy"] = {
        "mode": "disabled",
        "reason": "LazyCat 微服 Web 版不支持接管宿主机系统代理，请使用虚拟网卡模式（TUN）或显式代理入口。",
    }
    if get_profiles_state().get("current"):
        capabilities["runtimeProfile"] = {
            "mode": "enabled",
            "reason": "当前运行态已绑定活动配置文件。",
            "label": "活动配置",
        }
    else:
        capabilities["runtimeProfile"] = {
            "mode": "degraded",
            "reason": "当前没有活动配置文件；运行态修改会写入空配置运行态，需要持久配置时请先新建或选择配置。",
            "label": "空配置运行态",
        }
    return {
        "platform": str(contract.get("platform") or DEFAULT_RUNTIME_CONTRACT["platform"]),
        "appVersion": str(contract.get("appVersion") or APP_VERSION),
        "buildId": str(contract.get("buildId") or APP_VERSION),
        "gitCommit": str(contract.get("gitCommit") or "unknown"),
        "apiSchemaVersion": str(contract.get("apiSchemaVersion") or DEFAULT_RUNTIME_CONTRACT["apiSchemaVersion"]),
        "uiSchemaVersion": str(contract.get("uiSchemaVersion") or DEFAULT_RUNTIME_CONTRACT["uiSchemaVersion"]),
        "packageFingerprint": str(
            contract.get("packageFingerprint")
            or DEFAULT_RUNTIME_CONTRACT["packageFingerprint"]
        ),
        "capabilities": capabilities,
        "probeHealth": runtime_probe_health(),
        "profileHealth": profile_health,
        "restoreHealth": restore_transaction_status(),
        "alerting": {
            "enabled": bool(ALERT_WEBHOOK_URL),
            "outbox": str(ALERT_OUTBOX_PATH),
        },
    }


def runtime_contract_probe_payload() -> dict[str, Any]:
    """Return only non-sensitive contract fields for deployment validation."""
    contract = load_runtime_contract()
    capabilities = contract.get("capabilities") or DEFAULT_RUNTIME_CONTRACT["capabilities"]
    system_proxy = capabilities.get("systemProxy") if isinstance(capabilities, dict) else {}
    return {
        "platform": str(contract.get("platform") or DEFAULT_RUNTIME_CONTRACT["platform"]),
        "appVersion": str(contract.get("appVersion") or APP_VERSION),
        "buildId": str(contract.get("buildId") or APP_VERSION),
        "gitCommit": str(contract.get("gitCommit") or "unknown"),
        "apiSchemaVersion": str(
            contract.get("apiSchemaVersion")
            or DEFAULT_RUNTIME_CONTRACT["apiSchemaVersion"]
        ),
        "uiSchemaVersion": str(
            contract.get("uiSchemaVersion")
            or DEFAULT_RUNTIME_CONTRACT["uiSchemaVersion"]
        ),
        "packageFingerprint": str(
            contract.get("packageFingerprint")
            or DEFAULT_RUNTIME_CONTRACT["packageFingerprint"]
        ),
        "systemProxy": {
            "mode": str((system_proxy or {}).get("mode") or "disabled"),
        },
    }


def run_url_probe(target: str, timeout_ms: int = 12000) -> dict[str, Any]:
    started = time.time()
    try:
        status_code, _ = proxy_request(
            target,
            timeout=max(1, int(timeout_ms / 1000)),
            headers={"User-Agent": f"clash-verge-webport/{APP_VERSION}"},
        )
        duration_ms = int((time.time() - started) * 1000)
        return {
            "ok": True,
            "code": "OK",
            "message": "ok",
            "durationMs": duration_ms,
            "fromCache": False,
            "data": {
                "target": target,
                "status": "success",
                "latencyMs": duration_ms,
                "httpStatus": status_code,
            },
        }
    except Exception as exc:
        code, message = classify_public_probe_error(exc)
        duration_ms = int((time.time() - started) * 1000)
        status = "timeout" if code == "TIMEOUT" else "failed"
        return {
            "ok": True,
            "code": code,
            "message": message,
            "durationMs": duration_ms,
            "fromCache": False,
            "data": {
                "target": target,
                "status": status,
                "errorCode": code,
                "errorMessage": message,
            },
        }


def run_ip_info_probe() -> dict[str, Any]:
    started = time.time()
    result = get_ip_info()
    duration_ms = int((time.time() - started) * 1000)
    if result.get("status") == "success":
        return {
            "ok": True,
            "code": "OK",
            "message": "ok",
            "durationMs": duration_ms,
            "fromCache": False,
            "data": result,
        }
    public_code = to_public_probe_code(str(result.get("errorCode") or "network_error"))
    return {
        "ok": True,
        "code": public_code,
        "message": str(result.get("errorMessage") or "IP 信息加载失败"),
        "durationMs": duration_ms,
        "fromCache": False,
        "data": result,
    }


def run_unlock_probe(target: str | None = None, timeout_ms: int = 12000) -> dict[str, Any]:
    started = time.time()
    result = check_unlock_status(
        [target] if target else None,
        timeout_seconds=max(1, int(timeout_ms / 1000)),
    )
    duration_ms = int((time.time() - started) * 1000)
    summary = result.get("summary") or {}
    code = "OK"
    message = "ok"
    if summary.get("timeout"):
        code = "TIMEOUT"
        message = "部分解锁检测超时"
    elif summary.get("failed"):
        code = "UNKNOWN"
        message = "部分解锁检测失败"
    return {
        "ok": True,
        "code": code,
        "message": message,
        "durationMs": duration_ms,
        "fromCache": False,
        "data": result,
    }


def get_ip_info() -> dict[str, Any]:
    proxy_port = current_mixed_port()
    proxy_url = f"http://127.0.0.1:{proxy_port}"
    handlers = [
        urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}),
        urllib.request.HTTPSHandler(),
        urllib.request.HTTPHandler(),
    ]
    opener = urllib.request.build_opener(*handlers)
    last_error: Exception | None = None

    for service in IP_INFO_SERVICES:
        request = urllib.request.Request(
            service["url"],
            headers={
                "User-Agent": f"clash-verge-for-lc/{APP_VERSION}",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        try:
            with opener.open(request, timeout=12) as response:
                status_code = response.getcode() or 0
                if status_code < 200 or status_code >= 300:
                    raise RuntimeError(f"IP service {service['url']} returned {status_code}")
                payload = json.loads(response.read().decode("utf-8"))
            mapped = map_ip_info(str(service["name"]), payload)
            if not mapped.get("ip"):
                raise RuntimeError(f"IP service {service['url']} returned no ip")
            return {
                "status": "success",
                "payload": mapped,
                "lastFetchTs": now_ms(),
            }
        except Exception as exc:
            last_error = exc

    if last_error:
        error_code, error_message = classify_network_error(last_error)
    else:
        error_code, error_message = ("network_error", "没有可用的 IP 检测服务")
    return {
        "status": "error",
        "errorCode": error_code,
        "errorMessage": error_message,
    }


def current_profile_item() -> dict[str, Any]:
    profiles = get_profiles_state()
    current = profiles.get("current")
    items = profiles.get("items") or []
    for item in items:
        if item.get("uid") == current:
            return item

    if items:
        recovered = items[0]
        profiles["current"] = str(recovered.get("uid") or "")
        save_profiles_state(profiles)
        append_operation_log(
            "recovered missing current profile -> "
            f"profile_uid={profile_uid_for_log(profiles['current'])}"
        )
        return recovered

    raise ApiError(
        "NO_PROFILE_AVAILABLE",
        "当前没有可用的配置文件，已切换为空配置运行态。",
        recoverable=True,
    )


def build_runtime_text_for_current_or_empty_state(
    *,
    overlay_state: dict[str, Any] | None = None,
    verge_state: dict[str, Any] | None = None,
    dns_state: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any] | None]:
    profiles = get_profiles_state()
    current_uid = str(profiles.get("current") or "")
    if current_uid:
        item = current_profile_item()
        text, secret = build_runtime_text(
            item=item,
            overlay_state=overlay_state,
            verge_state=verge_state,
            dns_state=dns_state,
        )
        return text, secret, item

    text, secret = build_runtime_text(
        base_text=empty_profile_runtime_text(),
        overlay_state=overlay_state,
        verge_state=verge_state,
        dns_state=dns_state,
    )
    return text, secret, None


def profiles_explicitly_empty(profiles: dict[str, Any] | None = None) -> bool:
    state = profiles if isinstance(profiles, dict) else get_profiles_state()
    return not state.get("current") and not (state.get("items") or [])


def render_proxy_chain_yaml(items: list[str]) -> str:
    block = {"proxies": [{"name": item, "type": "relay"} for item in items]}
    return render_top_level_yaml(block)


def empty_profile_runtime_text() -> str:
    return render_top_level_yaml(
        {
            "mixed-port": 7890,
            "allow-lan": False,
            "bind-address": "127.0.0.1",
            "mode": "rule",
            "log-level": "info",
            "ipv6": True,
            "proxy-groups": [
                {
                    "name": "PROXY",
                    "type": "select",
                    "proxies": ["DIRECT"],
                }
            ],
            "rules": [
                "DOMAIN-SUFFIX,heiyu.space,DIRECT",
                "DOMAIN-SUFFIX,lazycat.cloud,DIRECT",
                "MATCH,DIRECT",
            ],
        }
    )


def empty_runtime_has_stale_profile_payload(runtime_text: str) -> bool:
    for key in ("proxies", "proxy-providers"):
        block_range = top_level_block_range(runtime_text, key)
        if block_range is None:
            continue
        block_text = runtime_text[block_range[0] : block_range[1]].strip()
        if block_text and block_text != f"{key}:":
            return True
    return False


def empty_runtime_requires_repair() -> bool:
    if not MIHOMO_CONFIG_PATH.exists():
        return True

    runtime_text = MIHOMO_CONFIG_PATH.read_text(encoding="utf-8")
    controller = extract_scalar(runtime_text, "external-controller")
    secret = extract_scalar(runtime_text, "secret")
    if controller != "172.18.0.1:9090" or not secret:
        return True

    if empty_runtime_has_stale_profile_payload(runtime_text):
        return True

    try:
        controller_request("GET", "/version", timeout=3)
    except Exception:
        return True
    return False


def build_runtime_text(
    item: dict[str, Any] | None = None,
    base_text: str | None = None,
    overlay_state: dict[str, Any] | None = None,
    verge_state: dict[str, Any] | None = None,
    dns_state: dict[str, Any] | None = None,
) -> tuple[str, str]:
    ensure_state()
    if base_text is None:
        item = item or current_profile_item()
        base_text = profile_path(str(item["uid"])).read_text(encoding="utf-8")
    overlay = copy.deepcopy(overlay_state) if overlay_state is not None else load_overlay()
    verge = copy.deepcopy(verge_state) if verge_state is not None else get_verge_config_state()
    text = base_text if base_text.endswith("\n") else base_text + "\n"

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

    raw_dns_state = dns_state if dns_state is not None else load_dns_state()
    effective_dns_state, _ = normalize_dns_state(raw_dns_state)
    dns_config = normalize_dns_config(
        effective_dns_state.get("dns") or {},
        bool(verge.get("enable_dns_settings", True)),
    )
    text = set_top_level_value(text, "dns", dns_config)
    hosts_config = copy.deepcopy(effective_dns_state.get("hosts") or {})
    if hosts_config:
        text = set_top_level_value(text, "hosts", hosts_config)
    else:
        text = remove_top_level_key(text, "hosts")

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


def apply_runtime_text(new_text: str, log_message: str) -> None:
    previous = MIHOMO_CONFIG_PATH.read_text(encoding="utf-8") if MIHOMO_CONFIG_PATH.exists() else ""
    previous_stat = MIHOMO_CONFIG_PATH.stat() if MIHOMO_CONFIG_PATH.exists() else None
    atomic_write_text(MIHOMO_CONFIG_PATH, new_text, 0o640)
    ensure_mihomo_config_owner(MIHOMO_CONFIG_PATH)
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
        append_operation_log(log_message)
    except Exception as exc:
        append_operation_log(
            "runtime apply failed; restoring previous Mihomo configuration",
            error=exc,
        )
        atomic_write_text(MIHOMO_CONFIG_PATH, previous, 0o640)
        if previous_stat is not None:
            ensure_mihomo_config_owner(MIHOMO_CONFIG_PATH)
        try:
            rollback = run_command(["systemctl", "restart", "mihomo"], check=False)
        except Exception as rollback_exc:
            append_operation_log(
                "Mihomo configuration rollback restart failed",
                error=rollback_exc,
            )
        else:
            if rollback.returncode == 0:
                append_operation_log("Mihomo configuration rollback restart succeeded")
            else:
                append_operation_log(
                    f"Mihomo configuration rollback restart failed returncode={rollback.returncode}"
                )
        raise


def apply_current_profile() -> None:
    item = current_profile_item()
    new_text, _ = build_runtime_text(item)
    try:
        set_log_context(profile_uid=item["uid"], stage="apply")
        apply_runtime_text(
            new_text,
            f"applied profile profile_uid={profile_uid_for_log(item['uid'])}",
        )
    except Exception as exc:
        mark_runtime_profile_degraded(f"应用活动配置失败: {exc}")
        raise
    mark_runtime_profile_ready(str(item["uid"]))


def apply_empty_profile_runtime() -> None:
    new_text, _ = build_runtime_text(base_text=empty_profile_runtime_text())
    try:
        apply_runtime_text(new_text, "applied empty runtime profile")
    except Exception as exc:
        mark_runtime_profile_degraded(f"应用空运行态失败: {exc}")
        raise
    mark_runtime_profile_ready("")


def apply_runtime_for_current_or_empty_state() -> None:
    new_text, _, item = build_runtime_text_for_current_or_empty_state()
    try:
        if item:
            set_log_context(profile_uid=item["uid"], stage="apply")
            apply_runtime_text(
                new_text,
                f"applied profile profile_uid={profile_uid_for_log(item['uid'])}",
            )
        else:
            set_log_context(stage="apply")
            apply_runtime_text(new_text, "applied empty runtime profile")
    except Exception as exc:
        mark_runtime_profile_degraded(f"应用运行时配置失败: {exc}")
        raise
    mark_runtime_profile_ready(str(item["uid"]) if item else "")


def fetch_remote_profile(
    url: str, option: dict[str, Any] | None = None
) -> tuple[str, dict[str, int], dict[str, Any]]:
    option = option or {}
    timeout = int(option.get("timeout_seconds") or 20)
    transport = profile_import_transport(option)
    request_url, username, password = profile_url_credentials(url)
    diagnostic_url = sanitize_profile_url(request_url)
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
    handlers.extend(
        [
            ProfileRedirectHandler(),
            urllib.request.HTTPSHandler(context=profile_tls_context()),
        ]
    )

    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        request_url,
        headers={
            "User-Agent": str(option.get("user_agent") or "clash-verge-webport/1.0")
        },
    )
    if username is not None:
        basic = base64.b64encode(
            f"{username}:{password or ''}".encode("utf-8")
        ).decode("ascii")
        request.add_header("Authorization", f"Basic {basic}")
    started = now_ms()
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = read_profile_response_payload(response)
            info = parse_subscription_userinfo(
                response.headers.get("subscription-userinfo", "")
            )
            headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
            content_type = headers.get("content-type", "")
            validation = validate_remote_profile_payload(
                payload,
                content_type=content_type,
                source_url=request_url,
            )
            name_hint = resolve_remote_profile_name_hint(request_url, headers)
            elapsed_ms = max(0, now_ms() - started)
            metadata = {
                "url": diagnostic_url,
                "transport": transport,
                "timeoutSeconds": timeout,
                "elapsedMs": elapsed_ms,
                "statusCode": int(response.getcode() or 0),
                "contentType": content_type,
                "profileNameHint": name_hint,
                "validation": validation,
            }
            return payload, info, metadata
    except urllib.error.HTTPError as exc:
        status_code = int(exc.code or 0)
        api_status = (
            HTTPStatus.BAD_REQUEST
            if 400 <= status_code < 500
            else HTTPStatus.BAD_GATEWAY
        )
        raise ApiError(
            "PROFILE_FETCH_HTTP_ERROR",
            f"订阅链接返回 HTTP {status_code}",
            status=api_status,
            layer="profile-import",
            recoverable=True,
            warning={
                "url": diagnostic_url,
                "transport": transport,
                "statusCode": status_code,
            },
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise ApiError(
            "PROFILE_FETCH_TIMEOUT",
            f"订阅拉取超时（{timeout}s）",
            status=HTTPStatus.GATEWAY_TIMEOUT,
            layer="profile-import",
            recoverable=True,
            warning={"url": diagnostic_url, "transport": transport},
        ) from exc
    except ssl.SSLError as exc:
        raise ApiError(
            "PROFILE_FETCH_TLS_ERROR",
            "订阅服务器 TLS 握手失败。",
            status=HTTPStatus.BAD_GATEWAY,
            layer="profile-import",
            recoverable=True,
            warning={"url": diagnostic_url, "transport": transport},
        ) from exc
    except urllib.error.URLError as exc:
        reason_text = str(exc.reason or "").lower()
        if isinstance(exc.reason, ssl.SSLError) or any(
            token in reason_text for token in ("ssl", "tls", "handshake", "certificate")
        ):
            raise ApiError(
                "PROFILE_FETCH_TLS_ERROR",
                "订阅服务器 TLS 握手失败。",
                status=HTTPStatus.BAD_GATEWAY,
                layer="profile-import",
                recoverable=True,
                warning={"url": diagnostic_url, "transport": transport},
            ) from exc
        if isinstance(exc.reason, (socket.timeout, TimeoutError)) or (
            "timed out" in reason_text
        ):
            raise ApiError(
                "PROFILE_FETCH_TIMEOUT",
                f"订阅拉取超时（{timeout}s）",
                status=HTTPStatus.GATEWAY_TIMEOUT,
                layer="profile-import",
                recoverable=True,
                warning={"url": diagnostic_url, "transport": transport},
            ) from exc
        raise ApiError(
            "PROFILE_FETCH_NETWORK_ERROR",
            "订阅拉取失败，请检查网络或订阅链接。",
            status=HTTPStatus.BAD_GATEWAY,
            layer="profile-import",
            recoverable=True,
            warning={"url": diagnostic_url, "transport": transport},
        ) from exc
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(
            "PROFILE_FETCH_NETWORK_ERROR",
            "订阅拉取失败，请检查网络或订阅链接。",
            status=HTTPStatus.BAD_GATEWAY,
            layer="profile-import",
            recoverable=True,
            warning={"url": diagnostic_url, "transport": transport},
        ) from exc


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


def create_profile_item(
    item: dict[str, Any], file_data: str | None
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    ensure_state()
    profiles = get_profiles_state()
    uid = item.get("uid") or uuid.uuid4().hex
    profile_type = item.get("type") or "local"
    name = item.get("name")
    option = deep_merge(default_profile_option(), item.get("option") or {})
    extra = {"upload": 0, "download": 0, "total": 0, "expire": 0}
    import_meta: dict[str, Any] | None = None

    if file_data is None and profile_type == "remote" and item.get("url"):
        file_data, extra, import_meta = fetch_remote_profile(str(item["url"]), option)
    if file_data is None:
        raise RuntimeError("profile content is required")

    if not name and import_meta:
        name = import_meta.get("profileNameHint")
    if not name:
        name = default_profile_name(item.get("url"))

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
    return record, import_meta


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
    previous_current = str(profiles.get("current") or "")
    items = [item for item in profiles.get("items") or [] if item.get("uid") != uid]
    profiles["items"] = items
    if profile_path(uid).exists():
        profile_path(uid).unlink()
    if previous_current == uid:
        profiles["current"] = items[0]["uid"] if items else ""
    profiles, _ = normalize_profiles_state(profiles)
    save_profiles_state(profiles)
    if profiles.get("current"):
        if previous_current == uid:
            apply_current_profile()
    elif previous_current == uid:
        apply_empty_profile_runtime()


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
    if source.is_symlink():
        raise RuntimeError(f"backup source must not be a symlink: {source}")
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"backup source contains a symlink: {path}")
        if path.is_dir():
            continue
        handle.write(path, f"{arc_prefix}/{path.relative_to(source)}")


def _restore_target_specs() -> tuple[tuple[str, Path], ...]:
    return RESTORE_FILE_TARGETS + RESTORE_DIRECTORY_TARGETS


def _restore_path_is_private(path: Path) -> bool:
    try:
        resolved = path.resolve()
        root = DATA_ROOT.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    return path.parent.resolve() == root and path.name.startswith(".restore-")


def _assert_no_symlinks(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError(f"restore path must not be a symlink: {path}")
    if not path.exists():
        return
    for root, directories, files in os.walk(path, followlinks=False):
        for name in (*directories, *files):
            candidate = Path(root) / name
            if candidate.is_symlink():
                raise RuntimeError(f"restore path contains a symlink: {candidate}")


def _remove_restore_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _zip_member_destination(payload_root: Path, name: str) -> Path:
    if "\\" in name:
        raise RuntimeError("restore archive contains a non-posix member")
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise RuntimeError(f"unsafe restore archive member: {name}")
    root_name = relative.parts[0]
    allowed_files = {item[0] for item in RESTORE_FILE_TARGETS}
    allowed_dirs = {item[0] for item in RESTORE_DIRECTORY_TARGETS}
    if len(relative.parts) == 1 and root_name in allowed_files:
        return payload_root / root_name
    if len(relative.parts) == 1 and root_name in allowed_dirs:
        return payload_root / root_name
    if len(relative.parts) > 1 and root_name in allowed_dirs:
        return payload_root.joinpath(*relative.parts)
    raise RuntimeError(f"unapproved restore archive member: {name}")


def _zip_info_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return stat.S_ISLNK(mode)


def _validate_restore_stage(stage: Path) -> dict[str, Any]:
    payload_root = stage / "payload"
    if not payload_root.is_dir() or payload_root.is_symlink():
        raise RuntimeError("restore staging payload is missing")
    _assert_no_symlinks(payload_root)
    present: dict[str, str] = {}
    for name, destination in _restore_target_specs():
        staged = payload_root / name
        if staged.is_symlink():
            raise RuntimeError(f"restore staging target is a symlink: {name}")
        if staged.exists():
            expected_type = "directory" if destination in dict(RESTORE_DIRECTORY_TARGETS).values() else "file"
            actual_type = "directory" if staged.is_dir() else "file" if staged.is_file() else "other"
            if actual_type != expected_type:
                raise RuntimeError(f"restore staging target type mismatch: {name}")
            present[name] = actual_type
    missing_required = RESTORE_REQUIRED_MEMBERS.difference(present)
    if missing_required:
        raise RuntimeError(
            "restore archive is missing required members: "
            + ", ".join(sorted(missing_required))
        )
    for name in ("verge.json", "profiles.json", "system-overlay.json", "dns-config.json"):
        path = payload_root / name
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise RuntimeError(f"restore JSON is invalid: {name}") from exc
            if not isinstance(loaded, dict):
                raise RuntimeError(f"restore JSON root must be an object: {name}")
    if not (payload_root / "config.yaml").read_text(encoding="utf-8").strip():
        raise RuntimeError("restore config.yaml is empty")
    if MIHOMO_BIN.is_file():
        result = run_command(
            [
                str(MIHOMO_BIN),
                "-t",
                "-d",
                str(payload_root),
                "-f",
                str(payload_root / "config.yaml"),
            ],
            check=False,
        )
        if result.returncode != 0:
            output = " ".join(
                part.strip() for part in (result.stdout, result.stderr) if part.strip()
            )
            raise RuntimeError(f"restore config validation failed: {output[:500]}")
    targets = {
        name: present.get(name, "missing") for name, _ in _restore_target_specs()
    }
    manifest = {"version": 1, "targets": targets}
    save_json(stage / "manifest.json", manifest, 0o600)
    return manifest


def _prepare_restore_stage(source: Path) -> Path:
    if not source.is_file() or source.is_symlink():
        raise RuntimeError(f"restore archive is not a regular file: {source}")
    if source.stat().st_size > RESTORE_MAX_TOTAL_BYTES:
        raise RuntimeError("restore archive is too large")
    stage = Path(tempfile.mkdtemp(prefix=".restore-staging-", dir=str(DATA_ROOT)))
    payload_root = stage / "payload"
    payload_root.mkdir(mode=0o700)
    total_size = 0
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(source, "r") as archive:
            for info in archive.infolist():
                name = info.filename.rstrip("/")
                if not name:
                    continue
                if name in seen:
                    raise RuntimeError(f"restore archive contains duplicate member: {name}")
                seen.add(name)
                destination = _zip_member_destination(payload_root, name)
                if _zip_info_is_symlink(info):
                    raise RuntimeError(f"restore archive contains a symlink: {name}")
                if info.is_dir():
                    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
                    continue
                member_size = int(info.file_size or 0)
                if member_size < 0 or member_size > RESTORE_MAX_MEMBER_BYTES:
                    raise RuntimeError(f"restore archive member is too large: {name}")
                total_size += member_size
                if total_size > RESTORE_MAX_TOTAL_BYTES:
                    raise RuntimeError("restore archive expands beyond the configured limit")
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with archive.open(info, "r") as source_handle, destination.open("xb") as target:
                    copied = 0
                    while True:
                        chunk = source_handle.read(min(1024 * 1024, RESTORE_MAX_MEMBER_BYTES + 1))
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > RESTORE_MAX_MEMBER_BYTES:
                            raise RuntimeError(f"restore archive member expands beyond the limit: {name}")
                        target.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
                mode = (info.external_attr >> 16) & 0o777
                if mode:
                    os.chmod(destination, mode)
        _validate_restore_stage(stage)
        return stage
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _capture_restore_snapshot(prefix: str) -> Path:
    snapshot = Path(tempfile.mkdtemp(prefix=prefix, dir=str(DATA_ROOT)))
    payload_root = snapshot / "payload"
    payload_root.mkdir(mode=0o700)
    targets: dict[str, str] = {}
    try:
        for name, destination in _restore_target_specs():
            if destination.is_symlink():
                raise RuntimeError(f"live restore target is a symlink: {destination}")
            staged = payload_root / name
            if not destination.exists():
                targets[name] = "missing"
                continue
            _assert_no_symlinks(destination)
            if destination.is_dir():
                targets[name] = "directory"
                shutil.copytree(destination, staged, copy_function=shutil.copy2)
            elif destination.is_file():
                targets[name] = "file"
                staged.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copy2(destination, staged)
            else:
                raise RuntimeError(f"unsupported live restore target: {destination}")
        save_json(snapshot / "manifest.json", {"version": 1, "targets": targets}, 0o600)
        _assert_no_symlinks(snapshot)
        return snapshot
    except BaseException:
        shutil.rmtree(snapshot, ignore_errors=True)
        raise


def _load_restore_snapshot(snapshot: Path) -> dict[str, Any]:
    if not _restore_path_is_private(snapshot) or not snapshot.is_dir():
        raise RuntimeError("restore transaction references an unsafe snapshot")
    manifest = load_json(snapshot / "manifest.json", {})
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise RuntimeError("restore transaction snapshot manifest is invalid")
    targets = manifest.get("targets")
    expected = {name for name, _ in _restore_target_specs()}
    if not isinstance(targets, dict) or set(targets) != expected:
        raise RuntimeError("restore transaction snapshot target set is invalid")
    for name, destination in _restore_target_specs():
        state = targets.get(name)
        staged = snapshot / "payload" / name
        if state == "missing":
            if staged.exists() or staged.is_symlink():
                raise RuntimeError(f"restore transaction missing target has payload: {name}")
            continue
        expected_type = "directory" if destination in dict(RESTORE_DIRECTORY_TARGETS).values() else "file"
        if state != expected_type or staged.is_symlink():
            raise RuntimeError(f"restore transaction target is invalid: {name}")
        if expected_type == "directory" and not staged.is_dir():
            raise RuntimeError(f"restore transaction directory is missing: {name}")
        if expected_type == "file" and not staged.is_file():
            raise RuntimeError(f"restore transaction file is missing: {name}")
    _assert_no_symlinks(snapshot)
    return manifest


def _replace_restore_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, dir=str(destination.parent)) as handle:
            temporary = Path(handle.name)
            with source.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, handle)
            handle.flush()
            os.fsync(handle.fileno())
        mode = stat.S_IMODE(source.stat().st_mode) or 0o600
        if destination == VERGE_API_SECRET_PATH:
            mode = 0o600
        os.chmod(temporary, mode)
        os.replace(temporary, destination)
        temporary = None
        _fsync_directory(destination.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _replace_restore_directory(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".restore-live-{uuid.uuid4().hex[:10]}-", dir=str(destination.parent))
    )
    temporary_payload = temporary / "payload"
    try:
        shutil.copytree(source, temporary_payload, copy_function=shutil.copy2)
        _assert_no_symlinks(temporary_payload)
        old_path = destination.parent / f".restore-old-{uuid.uuid4().hex[:10]}"
        if destination.exists() or destination.is_symlink():
            os.replace(destination, old_path)
        try:
            os.replace(temporary_payload, destination)
        except BaseException:
            if old_path.exists() and not destination.exists():
                os.replace(old_path, destination)
            raise
        finally:
            if old_path.exists() or old_path.is_symlink():
                _remove_restore_path(old_path)
        _fsync_directory(destination.parent)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _apply_restore_snapshot(snapshot: Path) -> None:
    manifest = _load_restore_snapshot(snapshot)
    targets = manifest["targets"]
    for name, destination in _restore_target_specs():
        state = targets[name]
        staged = snapshot / "payload" / name
        if state == "missing":
            if destination.exists() or destination.is_symlink():
                _remove_restore_path(destination)
            continue
        if state == "directory":
            _replace_restore_directory(staged, destination)
        else:
            _replace_restore_file(staged, destination)


def _write_restore_transaction(transaction: dict[str, Any]) -> None:
    save_json(RESTORE_TRANSACTION_PATH, transaction, 0o600)


def _cleanup_restore_transaction(transaction: dict[str, Any]) -> None:
    for key in ("stage", "previous"):
        value = transaction.get(key)
        if not isinstance(value, str):
            continue
        path = Path(value)
        if _restore_path_is_private(path):
            _remove_restore_path(path)
    RESTORE_TRANSACTION_PATH.unlink(missing_ok=True)
    _fsync_directory(RESTORE_TRANSACTION_PATH.parent)


def cleanup_restore_orphans() -> None:
    active: set[str] = set()
    if RESTORE_TRANSACTION_PATH.exists():
        try:
            transaction = json.loads(RESTORE_TRANSACTION_PATH.read_text(encoding="utf-8"))
        except Exception:
            # A malformed transaction is a fail-closed condition; preserve all
            # private staging data for manual recovery instead of deleting it.
            return
        if not isinstance(transaction, dict):
            return
        active = {str(transaction.get(key) or "") for key in ("stage", "previous")}
    for candidate in (DATA_ROOT.iterdir() if DATA_ROOT.exists() else ()):
        if not candidate.name.startswith((".restore-staging-", ".restore-previous-", ".restore-live-", ".restore-old-")):
            continue
        if str(candidate) in active:
            continue
        if _restore_path_is_private(candidate):
            _remove_restore_path(candidate)


def reconcile_restore_transaction() -> bool:
    """Roll back an interrupted restore before normal state initialization."""
    if not RESTORE_TRANSACTION_PATH.exists():
        return False
    with RESTORE_LOCK:
        transaction = load_json(RESTORE_TRANSACTION_PATH, {})
        if not isinstance(transaction, dict):
            raise RuntimeError("restore transaction is not a JSON object")
        phase = str(transaction.get("phase") or "")
        if phase in {"committed", "reconciled", "rolled_back"}:
            _cleanup_restore_transaction(transaction)
            return False
        if phase not in {"prepared", "applying", "applied", "rollback_failed"}:
            raise RuntimeError(f"restore transaction has unknown phase: {phase}")
        previous = Path(str(transaction.get("previous") or ""))
        _load_restore_snapshot(previous)
        _apply_restore_snapshot(previous)
        transaction["phase"] = "reconciled"
        transaction["reconciledAt"] = iso_now()
        _write_restore_transaction(transaction)
        _cleanup_restore_transaction(transaction)
        append_operation_log(
            f"reconciled interrupted restore generation={str(transaction.get('generation') or 'unknown')[:32]}"
        )
        record_runtime_alert("restore", "degraded", "interrupted restore rolled back on startup")
        return True


def create_backup_archive(target: Path) -> None:
    ensure_state()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=".backup-",
        suffix=".zip",
        dir=str(target.parent),
    )
    os.close(temporary_fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in (
                VERGE_CONFIG_PATH,
                PROFILES_CONFIG_PATH,
                OVERLAY_JSON_PATH,
                OVERLAY_YAML_PATH,
                DNS_CONFIG_PATH,
                MIHOMO_CONFIG_PATH,
            ):
                if path.exists():
                    if path.is_symlink():
                        raise RuntimeError(f"backup source must not be a symlink: {path}")
                    archive.write(path, path.name)
            if VERGE_API_SECRET_PATH.exists():
                if VERGE_API_SECRET_PATH.is_symlink():
                    raise RuntimeError("backup secret must not be a symlink")
                archive.write(VERGE_API_SECRET_PATH, "verge-api.secret")
            add_dir_to_zip(archive, PROFILES_DIR, "profiles")
            add_dir_to_zip(archive, ICONS_DIR, "icons")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)


def restore_backup_archive(source: Path) -> None:
    ensure_state()
    with RESTORE_LOCK:
        generation = uuid.uuid4().hex
        stage: Path | None = None
        previous: Path | None = None
        transaction: dict[str, Any] | None = None
        try:
            stage = _prepare_restore_stage(source)
            previous = _capture_restore_snapshot(".restore-previous-")
            transaction = {
                "version": 1,
                "generation": generation,
                "phase": "prepared",
                "createdAt": iso_now(),
                "source": source.name,
                "stage": str(stage),
                "previous": str(previous),
            }
            _write_restore_transaction(transaction)
            transaction["phase"] = "applying"
            _write_restore_transaction(transaction)
            _apply_restore_snapshot(stage)
            transaction["phase"] = "applied"
            _write_restore_transaction(transaction)
            apply_runtime_for_current_or_empty_state()
            transaction["phase"] = "committed"
            transaction["committedAt"] = iso_now()
            _write_restore_transaction(transaction)
            _cleanup_restore_transaction(transaction)
            record_runtime_alert("restore", "ok", generation)
            flush_alert_outbox()
        except BaseException as exc:
            details = sanitize_log_text(str(exc))[:500]
            record_runtime_alert("restore", "degraded", details or "restore interrupted")
            if transaction is not None and previous is not None:
                try:
                    transaction["phase"] = "rollback_failed"
                    _write_restore_transaction(transaction)
                    _apply_restore_snapshot(previous)
                    apply_runtime_for_current_or_empty_state()
                    transaction["phase"] = "rolled_back"
                    transaction["rolledBackAt"] = iso_now()
                    _write_restore_transaction(transaction)
                    _cleanup_restore_transaction(transaction)
                except BaseException as rollback_error:
                    append_operation_log("restore rollback failed", error=rollback_error)
            else:
                for orphan in (stage, previous):
                    if orphan is not None and _restore_path_is_private(orphan):
                        shutil.rmtree(orphan, ignore_errors=True)
            flush_alert_outbox()
            raise


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
        result = get_ip_info()
        if result.get("status") == "success":
            payload = result.get("payload") or {}
            country = payload.get("country_code") or payload.get("country")
            if isinstance(country, str) and country:
                return country
    except Exception:
        return None


def check_unlock_status(
    targets: list[str] | None = None,
    *,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    region = current_region()
    normalized_targets = (
        {item.strip().lower() for item in targets if item and item.strip()}
        if targets
        else None
    )
    summary = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "timeout": 0,
        "checkedAt": iso_now(),
    }
    probe_items = []
    for item in DEFAULT_UNLOCK_ITEMS:
        item_name = str(item["name"])
        if normalized_targets and item_name.strip().lower() not in normalized_targets:
            continue
        probe_items.append(item)

    def check_item(item: dict[str, Any]) -> dict[str, Any]:
        item_name = str(item["name"])
        url = UNLOCK_TEST_URLS.get(item["name"], "https://example.com/")
        status = "Failed"
        probe_status = "failed"
        message = ""
        try:
            response_status, _ = proxy_request(
                url,
                timeout=timeout_seconds,
                headers={"User-Agent": f"clash-verge-webport/{APP_VERSION}"},
            )
            if response_status < 400:
                status = "Yes"
                probe_status = "success"
            else:
                status = "No"
                probe_status = "failed"
                message = f"HTTP {response_status}"
        except Exception as exc:
            public_code, error_message = classify_public_probe_error(exc)
            if public_code == "TIMEOUT":
                probe_status = "timeout"
            else:
                probe_status = "failed"
            message = error_message
            status = "Failed"
        return {
            "name": item_name,
            "status": status,
            "probe_status": probe_status,
            "region": region,
            "check_time": iso_now(),
            "message": message,
        }

    if not probe_items:
        return {"items": [], "summary": summary}

    max_workers = min(len(probe_items), 8)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(check_item, probe_items))

    for result in results:
        if result["probe_status"] == "success":
            summary["success"] += 1
        elif result["probe_status"] == "timeout":
            summary["timeout"] += 1
        else:
            summary["failed"] += 1
        summary["total"] += 1

    return {"items": results, "summary": summary}


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


def upgrade_core_release(channel: str) -> dict[str, str]:
    release_channel = "alpha" if channel == "verge-mihomo-alpha" else "stable"
    tag = None if release_channel == "alpha" else DEFAULT_STABLE_TAG
    result = upgrade_core(
        channel=release_channel,
        tag=tag,
        binary=MIHOMO_BIN,
        state_dir=MIHOMO_STATE_DIR,
        config=MIHOMO_CONFIG_PATH,
        service="mihomo",
        controller_url=CONTROLLER_URL,
    )
    append_operation_log(
        f"mihomo core {result.get('STATUS', 'unknown')}: "
        f"{result.get('PREV_VERSION', 'none')} -> {result.get('TARGET_VERSION', 'unknown')}"
    )
    return result


def update_geo_data() -> None:
    url = "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/country.mmdb"
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read()
    atomic_write_bytes(MMDB_PATH, payload, 0o644)


def render_dns_config_content(state: dict[str, Any]) -> str:
    normalized, _ = normalize_dns_state(state)
    payload = {"dns": normalized["dns"]}
    hosts = normalized.get("hosts") or {}
    if hosts:
        payload["hosts"] = hosts
    return render_top_level_yaml(payload)


def validate_dns_state(state: dict[str, Any]) -> tuple[bool, str]:
    normalized, _ = normalize_dns_state(state)
    profiles = get_profiles_state()
    if profiles.get("current"):
        runtime_text, _ = build_runtime_text(dns_state=normalized)
    else:
        runtime_text, _ = build_runtime_text(
            base_text=empty_profile_runtime_text(),
            dns_state=normalized,
        )

    temp_path = Path(tempfile.mkstemp(prefix="mihomo-dns-validate-", suffix=".yaml")[1])
    try:
        atomic_write_text(temp_path, runtime_text, 0o600)
        if not MIHOMO_BIN.exists():
            return True, "mihomo binary missing; skipped validation"
        result = run_command(
            [
                str(MIHOMO_BIN),
                "-t",
                "-d",
                str(MIHOMO_STATE_DIR),
                "-f",
                str(temp_path),
            ],
            check=False,
        )
        output = "\n".join(
            part for part in (result.stdout.strip(), result.stderr.strip()) if part
        ).strip()
        if result.returncode == 0:
            return True, output or "ok"
        return False, output or f"mihomo config test failed: {result.returncode}"
    finally:
        temp_path.unlink(missing_ok=True)


def public_config_payload() -> dict[str, Any]:
    runtime_info = runtime_info_payload()
    return {
        "secret": controller_secret(),
        "vergeApiSecret": "",
        "mihomoBaseUrl": "/api",
        "vergeApiBaseUrl": "/verge-api",
        "appVersion": runtime_info["appVersion"],
        "runtimeInfo": runtime_info,
    }


def invoke_command(cmd: str, args: dict[str, Any]) -> Any:
    set_log_context(command=cmd)
    ensure_state()

    if cmd == "get_profiles":
        return get_profiles_state()

    if cmd == "get_clash_mode":
        return get_clash_mode()

    if cmd == "get_runtime_proxy_group_order":
        return get_runtime_proxy_group_order()

    if cmd == "create_profile":
        set_log_context(stage="write")
        item = args.get("item") or {}
        file_data = args.get("fileData")
        create_profile_item(item, file_data)
        return None

    if cmd == "import_profile":
        if not PROFILE_MUTATION_LOCK.acquire(blocking=False):
            return {"status": "busy"}
        url = str(args.get("url") or "")
        set_log_context(stage="fetch")
        option = args.get("option") or default_profile_option()
        try:
            profiles_before = get_profiles_state()
            previous_current = str(profiles_before.get("current") or "")
            record, import_meta = create_profile_item(
                {"type": "remote", "url": url, "option": option},
                None,
            )
            set_log_context(profile_uid=record.get("uid"), stage="write")
            profiles_after = get_profiles_state()
            current_uid = str(profiles_after.get("current") or "")
            activated_current = current_uid == str(record.get("uid") or "")
            return validation_valid(
                {
                    "profile": {
                        "uid": str(record.get("uid") or ""),
                        "name": str(record.get("name") or ""),
                        "url": str(record.get("url") or ""),
                    },
                    "activatedCurrent": activated_current,
                    "previousCurrent": previous_current,
                    "fetch": import_meta or {},
                    "validation": (import_meta or {}).get("validation") or {},
                }
            )
        except Exception as exc:
            append_operation_log("profile import failed", error=exc)
            return validation_invalid(exc, fallback_code="PROFILE_IMPORT_FAILED")
        finally:
            PROFILE_MUTATION_LOCK.release()

    if cmd == "view_profile":
        uid = str(args.get("index") or "")
        set_log_context(profile_uid=uid, stage="read")
        return {
            "filename": f"{uid}.yaml",
            "content": profile_path(uid).read_text(encoding="utf-8"),
            "content_type": "text/plain; charset=utf-8",
        }

    if cmd == "read_profile_file":
        uid = str(args.get("index") or "")
        set_log_context(profile_uid=uid, stage="read")
        return profile_path(uid).read_text(encoding="utf-8")

    if cmd == "save_profile_file":
        uid = str(args.get("index") or "")
        set_log_context(profile_uid=uid, stage="write")
        if not PROFILE_MUTATION_LOCK.acquire(blocking=False):
            return {"status": "busy"}
        path = profile_path(uid)
        previous_file = path.read_bytes() if path.exists() else None
        previous_profiles = get_profiles_state()
        try:
            update_profile_file(uid, str(args.get("fileData") or ""))
            return validation_valid()
        except Exception as exc:
            append_operation_log("profile file save/apply failed", error=exc)
            if previous_file is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write_bytes(path, previous_file)
            save_profiles_state(previous_profiles)
            return validation_invalid(exc, fallback_code="PROFILE_APPLY_FAILED")
        finally:
            PROFILE_MUTATION_LOCK.release()

    if cmd == "patch_profile":
        uid = str(args.get("index") or "")
        set_log_context(profile_uid=uid, stage="write")
        patch_profile_record(uid, args.get("profile") or {})
        return None

    if cmd == "update_profile":
        uid = str(args.get("index") or "")
        set_log_context(profile_uid=uid, stage="fetch")
        profiles = get_profiles_state()
        item = next((entry for entry in profiles.get("items") or [] if entry.get("uid") == uid), None)
        if not item:
            raise RuntimeError("profile not found")
        if item.get("type") == "remote" and item.get("url"):
            try:
                payload, extra, _ = fetch_remote_profile(
                    str(item["url"]), args.get("option") or item.get("option")
                )
            except Exception as exc:
                if profiles.get("current") == uid:
                    mark_runtime_profile_degraded(f"刷新活动订阅失败: {exc}")
                raise
            atomic_write_text(profile_path(uid), payload)
            set_log_context(stage="write")
            item["updated"] = now_ms()
            item["extra"] = extra
            save_profiles_state(profiles)
            if profiles.get("current") == uid:
                set_log_context(stage="apply")
                apply_current_profile()
        return None

    if cmd == "delete_profile":
        uid = str(args.get("index") or "")
        set_log_context(profile_uid=uid, stage="write")
        delete_profile_record(uid)
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
        if not PROFILE_MUTATION_LOCK.acquire(blocking=False):
            return {"status": "busy"}
        profiles_before = get_profiles_state()
        set_log_context(stage="write")
        try:
            profiles = copy.deepcopy(profiles_before)
            patch = args.get("profiles") or {}
            previous_current = str(profiles.get("current") or "")
            outcome: dict[str, Any] = validation_valid()
            explicit_empty_patch = (
                "items" in patch
                and patch.get("current") == ""
                and isinstance(patch.get("items"), list)
                and not patch.get("items")
            )
            if "items" in patch and isinstance(patch["items"], list):
                profiles["items"] = patch["items"]
            if "current" in patch and patch["current"] != profiles.get("current"):
                profiles["current"] = patch["current"]
            profiles, _ = normalize_profiles_state(profiles)
            save_profiles_state(profiles)
            if profiles.get("current") != previous_current:
                if profiles.get("current"):
                    set_log_context(profile_uid=profiles["current"], stage="apply")
                    apply_current_profile()
                elif explicit_empty_patch:
                    apply_empty_profile_runtime()
                else:
                    mark_runtime_profile_degraded(
                        "配置列表短暂进入空状态，继续保留上一次成功运行态。"
                    )
                    append_operation_log(
                        "skipped applying empty runtime for transient empty profile state"
                    )
                    outcome = {
                        "status": "skipped",
                        "reason": "transient-empty-last-good",
                    }
            elif not profiles.get("current") and explicit_empty_patch:
                set_log_context(stage="apply")
                apply_empty_profile_runtime()
            return outcome
        except Exception as exc:
            append_operation_log("profile configuration apply failed", error=exc)
            save_profiles_state(profiles_before)
            return validation_invalid(exc, fallback_code="PROFILE_APPLY_FAILED")
        finally:
            PROFILE_MUTATION_LOCK.release()

    if cmd == "enhance_profiles":
        if not PROFILE_MUTATION_LOCK.acquire(blocking=False):
            return {"status": "busy"}
        set_log_context(stage="apply")
        try:
            profiles = get_profiles_state()
            if profiles.get("current"):
                apply_current_profile()
            elif profiles_explicitly_empty(profiles):
                apply_empty_profile_runtime()
            else:
                mark_runtime_profile_degraded(
                    "当前配置列表为空，继续保留上一次成功运行态。"
                )
            return validation_valid()
        except ApiError as exc:
            append_operation_log("profile enhancement failed", error=exc)
            return validation_invalid(exc, fallback_code="PROFILE_APPLY_FAILED")
        except Exception as exc:
            append_operation_log("profile enhancement failed", error=exc)
            return validation_invalid(
                ApiError(
                    "PROFILE_APPLY_FAILED",
                    f"应用运行时配置失败: {exc}",
                    status=HTTPStatus.BAD_GATEWAY,
                    layer="runtime",
                    recoverable=False,
                ),
                fallback_code="PROFILE_APPLY_FAILED",
            )
        finally:
            PROFILE_MUTATION_LOCK.release()

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
        profiles = get_profiles_state()
        if profiles.get("current"):
            text, _ = build_runtime_text()
            return text
        if MIHOMO_CONFIG_PATH.exists():
            return MIHOMO_CONFIG_PATH.read_text(encoding="utf-8")
        text, _ = build_runtime_text(base_text=empty_profile_runtime_text())
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
        apply_runtime_for_current_or_empty_state()
        return {"secret": controller_secret()}

    if cmd == "patch_clash_mode":
        overlay = load_overlay()
        overlay["mode"] = args.get("payload") or "rule"
        save_overlay(overlay)
        apply_runtime_for_current_or_empty_state()
        return None

    if cmd == "get_clash_logs":
        try:
            result = run_command(
                [
                    "journalctl",
                    "-u",
                    "mihomo",
                    "-n",
                    "300",
                    "--no-pager",
                    "-o",
                    "cat",
                ]
            )
            return filter_mihomo_journal_lines(result.stdout.splitlines())
        except Exception as exc:
            append_operation_log(f"get_clash_logs failed: {exc}")
            raise ApiError(
                "GET_CLASH_LOGS_FAILED",
                f"读取 Mihomo 日志失败: {exc}",
                status=HTTPStatus.BAD_GATEWAY,
                layer="verge-api",
                recoverable=True,
            ) from exc

    if cmd == "clear_logs":
        atomic_write_text(OPERATIONS_LOG_PATH, "")
        return None

    if cmd == "get_verge_config":
        return get_verge_config_state()

    if cmd == "patch_verge_config":
        current = get_verge_config_state()
        payload_raw = args.get("payload") or {}
        payload = payload_raw if isinstance(payload_raw, dict) else {}
        if "enable_system_proxy" in payload:
            if bool(payload.get("enable_system_proxy")):
                append_operation_log(
                    "ignored patch_verge_config enable_system_proxy=true in lazycat-web runtime"
                )
            payload = copy.deepcopy(payload)
            payload["enable_system_proxy"] = False
        merged = deep_merge(current, payload)
        save_verge_config_state(merged)
        if RUNTIME_RELEVANT_VERGE_KEYS.intersection(payload.keys()):
            apply_runtime_for_current_or_empty_state()
        return get_verge_config_state()

    if cmd == "save_dns_config":
        save_dns_config_state(args.get("dnsConfig") or {})
        return None

    if cmd == "check_dns_config_exists":
        return DNS_CONFIG_PATH.exists()

    if cmd == "get_dns_config_content":
        return render_dns_config_content(load_dns_state())

    if cmd == "validate_dns_config":
        return list(validate_dns_state(load_dns_state()))

    if cmd == "apply_dns_config":
        verge = get_verge_config_state()
        verge["enable_dns_settings"] = bool(args.get("apply"))
        save_verge_config_state(verge)
        apply_runtime_for_current_or_empty_state()
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
        return upgrade_core_release(
            str(get_verge_config_state().get("clash_core") or "verge-mihomo")
        )

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

    if cmd == "get_ip_info":
        return get_ip_info()

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
        raw_name = str(args.get("name") or "")
        name = urllib.parse.quote(raw_name, safe="")
        url = str(args.get("url") or "http://cp.cloudflare.com")
        timeout = int(args.get("timeout") or 10000)
        return controller_delay_result(f"/proxies/{name}/delay", raw_name, url, timeout)

    if cmd == "clash_api_get_provider_proxy_delay":
        provider = str(args.get("provider") or "")
        raw_name = str(args.get("name") or "")
        provider_path = urllib.parse.quote(provider, safe="")
        name_path = urllib.parse.quote(raw_name, safe="")
        url = str(args.get("url") or "http://cp.cloudflare.com")
        timeout = int(args.get("timeout") or 10000)
        return controller_delay_result(
            f"/providers/proxies/{provider_path}/{name_path}/delay",
            raw_name,
            url,
            timeout,
        )

    if cmd == "test_delay":
        target = str(args.get("url") or "http://cp.cloudflare.com")
        result = run_url_probe(target)
        return {
            "target": target,
            "status": "success" if result["code"] == "OK" else result["data"].get("status"),
            "latencyMs": result.get("data", {}).get("latencyMs"),
            "errorCode": None if result["code"] == "OK" else result["code"],
            "errorMessage": None if result["code"] == "OK" else result["message"],
        }

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

    def has_lazycat_session(self) -> bool:
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return False
        try:
            cookies = SimpleCookie()
            cookies.load(cookie_header)
        except Exception:
            return False
        for name in LAZYCAT_AUTH_COOKIE_NAMES:
            morsel = cookies.get(name)
            if morsel and morsel.value.strip():
                return True
        return False

    def authenticate(
        self,
        allow_query_token: bool = False,
        allow_lazycat_session: bool = False,
    ) -> bool:
        expected = verge_api_secret()
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:].strip() == expected:
            return True
        if allow_query_token:
            parsed = urllib.parse.urlparse(self.path)
            token = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
            if token == expected:
                return True
        if allow_lazycat_session and self.has_lazycat_session():
            return True
        return False

    def route_request(self, head_only: bool = False) -> None:
        request_id = uuid.uuid4().hex
        self._request_id = request_id
        LOG_CONTEXT.set({"request_id": request_id})
        parsed = urllib.parse.urlparse(self.path)
        try:
            ensure_state()
        except Exception as exc:
            if parsed.path == "/healthz":
                self.send_json(
                    {
                        "ok": False,
                        "status": "degraded",
                        "time": iso_now(),
                        "controller": {"status": "unknown"},
                        "restore": {
                            "status": "degraded",
                            "phase": "reconcile_failed",
                        },
                        "error": sanitize_log_text(str(exc))[:500],
                    },
                    status=HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            raise
        if parsed.path == "/healthz":
            payload = healthz_payload()
            self.send_json(
                payload,
                status=HTTPStatus.OK
                if payload.get("ok")
                else HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return

        if parsed.path == "/public-config":
            if not self.authenticate(allow_query_token=True, allow_lazycat_session=True):
                self.send_json(
                    error_envelope(
                        "UNAUTHORIZED",
                        "缺少有效的 LazyCat 登录态或 API token。",
                        recoverable=False,
                    ),
                    status=HTTPStatus.UNAUTHORIZED,
                )
                return
            self.send_json(public_config_payload())
            return

        if parsed.path == "/runtime-info":
            if urllib.parse.parse_qs(parsed.query).get("scope", [""])[0] == "contract":
                self.send_json(runtime_contract_probe_payload())
                return
            if not self.authenticate(allow_query_token=True, allow_lazycat_session=True):
                self.send_json(
                    error_envelope(
                        "UNAUTHORIZED",
                        "缺少有效的 LazyCat 登录态或 API token。",
                        recoverable=False,
                    ),
                    status=HTTPStatus.UNAUTHORIZED,
                )
                return
            self.send_json(runtime_info_payload())
            return

        if parsed.path == "/file":
            if not self.authenticate(allow_query_token=True, allow_lazycat_session=True):
                self.send_json(
                    error_envelope(
                        "UNAUTHORIZED",
                        "缺少有效的 LazyCat 登录态或 API token。",
                        recoverable=False,
                    ),
                    status=HTTPStatus.UNAUTHORIZED,
                )
                return
            raw_path = urllib.parse.parse_qs(parsed.query).get("path", [""])[0]
            target = Path(raw_path)
            if not target.exists() or not file_is_allowed(target):
                self.send_json(
                    error_envelope(
                        "NOT_FOUND",
                        "请求的文件不存在或不在允许范围内。",
                        recoverable=False,
                    ),
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self.send_bytes(target.read_bytes(), content_type, head_only=head_only)
            return

        if parsed.path == "/probe" and self.command == "POST":
            if not self.authenticate(allow_lazycat_session=True):
                self.send_json(
                    error_envelope(
                        "UNAUTHORIZED",
                        "缺少有效的 LazyCat 登录态。",
                        recoverable=False,
                        layer="probe",
                    ),
                    status=HTTPStatus.UNAUTHORIZED,
                )
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                kind = str(payload.get("kind") or "").strip().lower()
                target = str(payload.get("target") or "").strip()
                timeout_ms = int(payload.get("timeoutMs") or 12000)
                if kind == "ip_info":
                    result = run_ip_info_probe()
                elif kind == "unlock":
                    result = run_unlock_probe(target or None, timeout_ms)
                elif kind == "url":
                    if not target:
                        raise ApiError(
                            "INVALID_REQUEST",
                            "probe url 缺少 target。",
                            layer="probe",
                        )
                    result = run_url_probe(target, timeout_ms)
                else:
                    raise ApiError(
                        "INVALID_REQUEST",
                        f"不支持的 probe kind: {kind or '<empty>'}",
                        layer="probe",
                    )
                self.send_json(result)
            except Exception as exc:
                append_operation_log(f"probe error: {exc}")
                payload, status = exception_envelope(exc, default_code="PROBE_FAILED")
                self.send_json(payload, status=status)
            return

        if parsed.path == "/invoke" and self.command == "POST":
            if not self.authenticate(allow_lazycat_session=True):
                self.send_json(
                    error_envelope(
                        "UNAUTHORIZED",
                        "缺少有效的 LazyCat 登录态。",
                        recoverable=False,
                    ),
                    status=HTTPStatus.UNAUTHORIZED,
                )
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                command = str(payload.get("cmd") or "")
                LOG_CONTEXT.set({"request_id": request_id, "command": command})
                result = invoke_command(command, payload.get("args") or {})
                self.send_json(result if result is not None else None)
            except Exception as exc:
                append_operation_log(f"invoke error: {exc}", error=exc)
                payload, status = exception_envelope(exc)
                payload["requestId"] = request_id
                self.send_json(payload, status=status)
            return

        self.send_json(
            error_envelope(
                "NOT_FOUND",
                "请求的接口不存在。",
                recoverable=False,
            ),
            status=HTTPStatus.NOT_FOUND,
        )

    def log_message(self, format: str, *args: Any) -> None:
        append_operation_log(format % args)


def runtime_health_watch_loop() -> None:
    while not HEALTH_WATCH_STOP.wait(HEALTH_WATCH_INTERVAL_SECONDS):
        try:
            healthz_payload()
        except Exception as exc:
            append_operation_log("runtime health watch failed", error=exc)


def main() -> int:
    startup_error: Exception | None = None
    try:
        ensure_state()
    except Exception as exc:
        # Keep the health endpoint available when startup reconciliation is
        # blocked by a malformed transaction or an unavailable controller.
        # Every normal API operation still calls ensure_state and therefore
        # remains fail-closed until the operator repairs the runtime.
        startup_error = exc
        append_operation_log("startup reconciliation failed", error=exc)
        record_runtime_alert("restore", "degraded", str(exc))
        flush_alert_outbox()
    append_operation_log(f"starting verge api on {HOST}:{PORT}")
    if startup_error is not None:
        append_operation_log("serving degraded health until startup reconciliation succeeds")
    if HEALTH_WATCH_INTERVAL_SECONDS > 0:
        try:
            healthz_payload()
        except Exception as exc:
            append_operation_log("initial runtime health watch failed", error=exc)
        threading.Thread(
            target=runtime_health_watch_loop,
            name="mihomo-runtime-health-watch",
            daemon=True,
        ).start()
    server = ThreadingHTTPServer((HOST, PORT), VergeApiHandler)
    try:
        server.serve_forever()
    finally:
        HEALTH_WATCH_STOP.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
