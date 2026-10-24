"""Live runtime mirror: Verge API writes it, the host-native bootstrap restores it after a reboot.

A LazyCat reboot resets /etc and /var/lib; the mirror under /root carries config.yaml, the verge state and
select-group choices across it. These tests run the real writer (mihomo-verge-api.py) and the real bootstrap
functions against each other, so the two sides cannot drift apart on format.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts" / "install_host_native_bootstrap.sh"
GENERATION = "gen.20261024T000000Z.1"
SPEC = importlib.util.spec_from_file_location("verge_api", ROOT / "infra" / "microserver" / "mihomo-verge-api.py")
API = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(API)

SELECTORS = {"proxies": {
    "PROXY": {"type": "Selector", "now": "EB", "all": ["CN2", "EB"]},
    "GLOBAL": {"type": "Selector", "now": "PROXY", "all": ["DIRECT", "PROXY"]},
    "EB": {"type": "Vless"},
}}


def bootstrap_functions() -> str:
    script = BOOTSTRAP.read_text(encoding="utf-8").split("<<'SCRIPT'\n", 1)[1].split("\nSCRIPT\n", 1)[0]
    return script[script.index("read_value() {"):script.index("write_pending() {")]


def run_bootstrap(root: Path, body: str, env: dict | None = None) -> subprocess.CompletedProcess:
    shim = "" if shutil.which("sha256sum") else 'sha256sum() { shasum -a 256 "$@"; }\n'
    program = (f"set -euo pipefail\n{shim}bootstrap_root={str(root)!r}\nlive_root=\"$bootstrap_root/live\"\n"
               f"{bootstrap_functions()}\n{body}\n")
    return subprocess.run(["bash", "-c", program], capture_output=True, text=True, env=env)


def write_mirror(root: Path, controller=SELECTORS) -> tuple[bool, bool]:
    data = root / "var-lib-mihomo-verge"
    (data / "logs").mkdir(parents=True)
    (data / "profiles").mkdir()
    (data / "verge.json").write_text('{"verge_mixed_port": 7890}', encoding="utf-8")
    (data / "profiles" / "p1.yaml").write_text("proxies: []\n", encoding="utf-8")
    (data / "logs" / "operations.log").write_text("noise\n", encoding="utf-8")
    config = root / "config.yaml"
    config.write_text("mixed-port: 7890\nsecret: s3cret\n", encoding="utf-8")
    (root / "current-generation").write_text(GENERATION + "\n", encoding="utf-8")
    with patch.object(API, "BOOTSTRAP_ROOT", root), patch.object(API, "LIVE_MIRROR_DIR", root / "live"), \
         patch.object(API, "DATA_ROOT", data), patch.object(API, "MIHOMO_CONFIG_PATH", config), \
         patch.object(API, "RESTORE_TRANSACTION_PATH", data / "restore-transaction.json"), \
         patch.object(API, "controller_request", return_value=controller):
        first = API.sync_live_mirror()
        second = API.sync_live_mirror()
    return first, second


def assert_writer() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first, second = write_mirror(root)
        live = root / "live"
        if not (first and not second):
            raise AssertionError("the mirror must be written once and skipped while nothing changed")
        if (live / "var-lib-mihomo" / "verge" / "logs").exists():
            raise AssertionError("logs must stay out of the mirror")
        if json.loads((live / "selections.json").read_text()) != {"GLOBAL": "PROXY", "PROXY": "EB"}:
            raise AssertionError("select-group choices must be mirrored")
        if f"BASE_GENERATION={GENERATION}" not in (live / "metadata.env").read_text():
            raise AssertionError("the mirror must name the generation it was taken on")
        if run_bootstrap(root, f"live_mirror_usable {GENERATION}").returncode != 0:
            raise AssertionError("the bootstrap must accept the mirror the API wrote")
        if run_bootstrap(root, "live_mirror_usable gen.20261023T000000Z.9").returncode == 0:
            raise AssertionError("a mirror taken on another generation must not be laid over it")
        (live / "var-lib-mihomo" / "verge" / "verge.json").write_text("tampered", encoding="utf-8")
        if run_bootstrap(root, f"live_mirror_usable {GENERATION}").returncode == 0:
            raise AssertionError("a mirror whose files no longer match its manifest must be rejected")


def assert_writer_skips_mid_restore_and_keeps_choices_without_controller() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_mirror(root)
        config = root / "config.yaml"
        config.write_text("mixed-port: 7891\nsecret: s3cret\n", encoding="utf-8")
        common = dict(BOOTSTRAP_ROOT=root, LIVE_MIRROR_DIR=root / "live", DATA_ROOT=root / "var-lib-mihomo-verge",
                      MIHOMO_CONFIG_PATH=config,
                      RESTORE_TRANSACTION_PATH=root / "var-lib-mihomo-verge" / "restore-transaction.json")
        (root / "state").mkdir()
        (root / "state" / "pending.env").write_text("PHASE=applying\n", encoding="utf-8")
        with patch.multiple(API, **common), patch.object(API, "controller_request", return_value=SELECTORS):
            if API.sync_live_mirror():
                raise AssertionError("no mirror while a bootstrap transaction is pending")
        (root / "state" / "pending.env").unlink()
        with patch.multiple(API, **common), patch.object(API, "controller_request", side_effect=OSError("down")):
            if not API.sync_live_mirror():
                raise AssertionError("a config change must refresh the mirror")
        if json.loads((root / "live" / "selections.json").read_text()) != {"GLOBAL": "PROXY", "PROXY": "EB"}:
            raise AssertionError("an unavailable controller must not erase the last known choices")
        if "mixed-port: 7891" not in (root / "live" / "etc-mihomo" / "config.yaml").read_text():
            raise AssertionError("the refreshed mirror must carry the new config")


class FakeController(BaseHTTPRequestHandler):
    puts: list = []
    auth: list = []

    def do_GET(self):
        FakeController.auth.append(self.headers.get("Authorization"))
        body = json.dumps({"proxies": {
            "PROXY": {"type": "Selector", "now": "CN2", "all": ["CN2", "EB"]},
            "GLOBAL": {"type": "Selector", "now": "DIRECT", "all": ["DIRECT", "PROXY"]},
            "AUTO": {"type": "URLTest", "now": "CN2", "all": ["CN2"]},
        }}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", "0"))
        FakeController.puts.append((self.path, json.loads(self.rfile.read(length))))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


def assert_selection_restore() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeController)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "live").mkdir()
            (root / "live" / "selections.json").write_text(json.dumps(
                {"PROXY": "EB", "GLOBAL": "PROXY", "AUTO": "CN2", "Gone": "X", "🇺🇸 grp": "EB"}), encoding="utf-8")
            (root / "config.yaml").write_text("mixed-port: 7890\nsecret: 's3cret'\n", encoding="utf-8")
            env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                   "CONTROLLER_URL": f"http://127.0.0.1:{server.server_port}", "MIHOMO_CONFIG": str(root / "config.yaml")}
            result = run_bootstrap(root, "restore_selections", env)
    finally:
        server.shutdown()
    if result.returncode != 0 or "restored=2 skipped=3" not in result.stdout:
        raise AssertionError(f"restore_selections: {result.returncode} {result.stdout} {result.stderr}")
    if sorted(FakeController.puts) != [("/proxies/GLOBAL", {"name": "PROXY"}), ("/proxies/PROXY", {"name": "EB"})]:
        raise AssertionError(f"only changed select groups with a valid choice may be set: {FakeController.puts}")
    if FakeController.auth != ["Bearer s3cret"]:
        raise AssertionError("the controller secret must be read from config.yaml without quotes")


def main() -> None:
    assert_writer()
    assert_writer_skips_mid_restore_and_keeps_choices_without_controller()
    assert_selection_restore()
    print("live mirror restore contract: ok")


if __name__ == "__main__":
    main()
