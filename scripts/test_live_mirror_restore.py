"""Live runtime mirror: Verge API writes it, the host-native bootstrap restores it after a reboot.

A LazyCat reboot resets /etc and /var/lib; the mirror under /root carries config.yaml, the verge state and
select-group choices across it. These tests run the real writer (mihomo-verge-api.py) and the real bootstrap
functions against each other, so the two sides cannot drift apart on format.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import sys
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
    (data / "logs" / "alerts.jsonl").write_text('{"id": "a1", "delivery": "pending"}\n', encoding="utf-8")
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
        logs = live / "var-lib-mihomo" / "verge" / "logs"
        if (logs / "operations.log").exists() or not (logs / "alerts.jsonl").is_file():
            raise AssertionError("the mirror keeps the alert outbox from logs/ and nothing else")
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


def assert_interrupted_publication() -> None:
    for failure in ("exception", "killed"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_mirror(root)
            old_config = (root / "live/etc-mihomo/config.yaml").read_bytes()
            (root / "config.yaml").write_text("mixed-port: 7892\nsecret: s3cret\n")
            common = dict(BOOTSTRAP_ROOT=root, LIVE_MIRROR_DIR=root / "live",
                          DATA_ROOT=root / "var-lib-mihomo-verge", MIHOMO_CONFIG_PATH=root / "config.yaml",
                          RESTORE_TRANSACTION_PATH=root / "var-lib-mihomo-verge/restore-transaction.json")
            if failure == "exception":
                rename = os.rename

                def fail_publish(source, destination):
                    if Path(source).name.startswith(".live-staging."):
                        raise OSError("injected publish failure")
                    return rename(source, destination)

                with patch.multiple(API, **common), patch.object(API, "controller_request", return_value=SELECTORS), \
                     patch.object(API.os, "rename", side_effect=fail_publish):
                    try:
                        API.sync_live_mirror()
                    except OSError:
                        pass
                    else:
                        raise AssertionError("publication should fail")
            else:
                # Kill the real writer after moving live aside, bypassing its exception cleanup.
                program = f"""
import importlib.util, os
from pathlib import Path
spec = importlib.util.spec_from_file_location('api', {str(ROOT / 'infra/microserver/mihomo-verge-api.py')!r})
api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
for key, value in { {k: str(v) for k, v in common.items()}!r}.items():
    setattr(api, key, Path(value))
api.controller_request = lambda *a, **kw: {SELECTORS!r}
rename = os.rename
def die_after_move(source, destination):
    rename(source, destination)
    if Path(destination).name == '.live-old':
        os._exit(77)
api.os.rename = die_after_move
api.sync_live_mirror()
"""
                result = subprocess.run([sys.executable, "-B", "-c", program], capture_output=True, text=True)
                if result.returncode != 77:
                    raise AssertionError(result.stderr)
            result = run_bootstrap(root, f'live_mirror_usable {GENERATION}\ncat "$live_root/etc-mihomo/config.yaml"')
            if result.returncode or result.stdout.encode() != old_config:
                raise AssertionError(f"{failure}: last committed mirror must remain recoverable: {result}")
            if failure == "killed":
                # Recovery must still reject tampered or different-generation fallback copies.
                if run_bootstrap(root, "live_mirror_usable gen.20261023T000000Z.9").returncode == 0:
                    raise AssertionError("fallback must match the generation")
                metadata = root / ".live-old/metadata.env"
                original = metadata.read_bytes()
                metadata.write_bytes(original + b"tampered\n")
                if run_bootstrap(root, f"live_mirror_usable {GENERATION}").returncode == 0:
                    raise AssertionError("fallback must pass manifest validation")
                metadata.write_bytes(original)
            with patch.multiple(API, **common), patch.object(API, "controller_request", return_value=SELECTORS):
                if not API.sync_live_mirror():
                    raise AssertionError("the next writer must recover and publish the changed config")
            result = run_bootstrap(root, f'live_mirror_usable {GENERATION}\ncat "$live_root/etc-mihomo/config.yaml"')
            if result.returncode or "7892" not in result.stdout:
                raise AssertionError("new mirror must be usable after retry")


class FakeController(BaseHTTPRequestHandler):
    puts: list = []
    auth: list = []
    fail_method = ""

    def do_GET(self):
        if self.fail_method == "GET":
            self.send_error(503)
            return
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
        if self.fail_method == "PUT":
            self.send_error(503)
            return
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


def assert_selection_failure_retains_transaction() -> None:
    # Execute the real apply_generation commit boundary, replacing only its host status/log helpers.
    script = BOOTSTRAP.read_text().split("<<'SCRIPT'\n", 1)[1].split("\nSCRIPT\n", 1)[0]
    tail = script.split('  if [[ "$live_used" == 1 ]]; then\n', 1)[1].split('\n}\n', 1)[0]
    commit = 'finish_apply() {\n  if [[ "$live_used" == 1 ]]; then\n' + tail + '\n}\nfinish_apply\n'
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeController)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for method in ("GET", "PUT"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_mirror(root)
                (root / "state").mkdir()
                pending = root / "state/pending.env"
                pending.write_text("PHASE=applying\n")
                env = {**os.environ, "CONTROLLER_URL": f"http://127.0.0.1:{server.server_port}",
                       "MIHOMO_CONFIG": str(root / "config.yaml")}
                body = (f'live_used=1\ngeneration={GENERATION}\nreason=test\n'
                        'applied_generation_file="$bootstrap_root/applied-generation"\n'
                        'log() { printf "%s\\n" "$1"; }\n'
                        'systemctl() { echo active; }\n'
                        'clear_pending() { rm "$bootstrap_root/state/pending.env"; }\n' + commit)
                FakeController.fail_method = method
                result = run_bootstrap(root, body, env)
                if result.returncode == 0 or not pending.exists() or (root / "applied-generation").exists():
                    raise AssertionError(f"{method} failure must block the commit: {result}")
                before = (root / "live/selections.json").read_bytes()
                with patch.multiple(API, BOOTSTRAP_ROOT=root, LIVE_MIRROR_DIR=root / "live",
                                    MIHOMO_CONFIG_PATH=root / "config.yaml"), \
                     patch.object(API, "controller_request") as controller:
                    if API.sync_live_mirror() or controller.called:
                        raise AssertionError("pending selection restore must block the mirror writer")
                if before != (root / "live/selections.json").read_bytes():
                    raise AssertionError("failed restoration must not overwrite the saved choices")
                FakeController.fail_method = ""
                result = run_bootstrap(root, body, env)
                if result.returncode or pending.exists() or not (root / "applied-generation").exists():
                    raise AssertionError(f"successful retry must commit: {result}")
    finally:
        FakeController.fail_method = ""
        server.shutdown()
        server.server_close()


def assert_logs_merge() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        generation_logs, live_logs = root / "gen-logs", root / "verge" / "logs"
        generation_logs.mkdir()
        live_logs.mkdir(parents=True)
        (generation_logs / "operations.log").write_text("from generation\n", encoding="utf-8")
        (generation_logs / "alerts.jsonl").write_text("old outbox\n", encoding="utf-8")
        (live_logs / "alerts.jsonl").write_text("mirrored outbox\n", encoding="utf-8")
        result = run_bootstrap(root, f"merge_generation_logs {str(generation_logs)!r} {str(live_logs)!r}")
        if result.returncode != 0:
            raise AssertionError(f"merge_generation_logs failed: {result.stderr}")
        if any(p.is_dir() for p in live_logs.iterdir()):
            raise AssertionError("generation logs must not be nested into an existing logs/ directory")
        if (live_logs / "alerts.jsonl").read_text() != "mirrored outbox\n":
            raise AssertionError("the mirrored alert outbox must win over the generation's")
        operations = live_logs / "operations.log"
        if not operations.is_file() or operations.read_text() != "from generation\n":
            raise AssertionError("the generation's other logs must be brought back")
        if run_bootstrap(root, f"merge_generation_logs {str(root / 'none')!r} {str(live_logs)!r}").returncode != 0:
            raise AssertionError("a generation without logs/ must be fine")


def main() -> None:
    assert_writer()
    assert_logs_merge()
    assert_writer_skips_mid_restore_and_keeps_choices_without_controller()
    assert_selection_restore()
    assert_interrupted_publication()
    assert_selection_failure_retains_transaction()
    print("live mirror restore contract: ok")


if __name__ == "__main__":
    main()
