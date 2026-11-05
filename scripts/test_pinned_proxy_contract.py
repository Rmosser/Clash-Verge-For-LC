"""Pinned container proxy contract: units, Verge API ports and bootstrap generations agree.

The pinned entry (app bridges :17896 -> 127.0.0.1:7896) is optional: generations captured before it
existed carry no PINNED_PROXY_ENABLED flag and must stay valid rollback targets.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra" / "microserver"
BOOTSTRAP = ROOT / "scripts" / "install_host_native_bootstrap.sh"
DEPLOY = ROOT / "scripts" / "deploy_microserver.sh"
REQUIRED = (
    "usr-local-bin/mihomo", "etc-mihomo/config.yaml", "etc-mihomo/verge-api.secret", "systemd/mihomo.service",
    "systemd/mihomo-verge-api.service", "usr-local-lib-lzc-mihomo/mihomo-verge-api.py",
    "usr-local-lib-lzc-mihomo/mihomo_core_updater.py", "usr-local-lib-lzc-mihomo/runtime-contract.json",
)


def unit_values(path: Path, key: str) -> list[str]:
    return [line.split("=", 1)[1].strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith(f"{key}=")]


def assert_units() -> None:
    shared = unit_values(INFRA / "mihomo-container-proxy.socket", "ListenStream")
    pinned = unit_values(INFRA / "mihomo-container-proxy-pinned.socket", "ListenStream")
    bridges = [s.rsplit(":", 1)[0] for s in shared]
    if pinned != [f"{b}:17896" for b in bridges]:
        raise AssertionError(f"pinned socket must listen on every shared bridge at :17896, got {pinned}")
    if unit_values(INFRA / "mihomo-container-proxy-pinned.socket", "FreeBind") != ["true"]:
        raise AssertionError("pinned socket must use FreeBind like the shared socket")
    service = INFRA / "mihomo-container-proxy-pinned.service"
    if unit_values(service, "ExecStart") != ["/lib/systemd/systemd-socket-proxyd 127.0.0.1:7896"]:
        raise AssertionError("pinned service must forward to the pinned listener 127.0.0.1:7896")
    if unit_values(service, "User") != ["nobody"]:
        raise AssertionError("pinned service must run unprivileged")


def assert_api_port() -> None:
    spec = importlib.util.spec_from_file_location("verge_api", INFRA / "mihomo-verge-api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    listeners = module.normalize_pinned_listeners(
        [{"name": "pinned-eb", "port": 7896, "proxy": "node"}],
        module.pinned_listener_reserved_ports({}, {"verge_mixed_port": 7890}),
    )
    if listeners[0]["listen"] != "127.0.0.1" or listeners[0]["port"] != 7896:
        raise AssertionError("the documented pinned listener must be accepted on loopback :7896")


def assert_deploy_lists() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    for needle in ('"$pinned_proxy_socket" "$pinned_proxy_service"',
                   "mihomo-container-proxy.socket mihomo-container-proxy-pinned.socket",
                   "mihomo-container-proxy.socket|mihomo-container-proxy-pinned.socket|",
                   '"$path" == "$pinned_proxy_socket"'):
        if needle not in text:
            raise AssertionError(f"deploy_microserver.sh snapshot/rollback lists miss the pinned units: {needle}")


def bootstrap_functions() -> str:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    script = text.split("<<'SCRIPT'\n", 1)[1].split("\nSCRIPT\n", 1)[0]
    start, end = script.index("read_value() {"), script.index("write_pending() {")
    return script[start:end]


def validate(generation_files: dict[str, str]) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        generation = "gen.20261024T000000Z.1"
        source = root / "generations" / generation
        for rel, content in generation_files.items():
            path = source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        files = sorted(p for p in source.rglob("*") if p.is_file())
        (source / "manifest.sha256").write_text(
            "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  ./{p.relative_to(source)}\n" for p in files),
            encoding="utf-8")
        (source / "COMPLETE").write_text("", encoding="utf-8")
        shim = "" if shutil.which("sha256sum") else 'sha256sum() { shasum -a 256 "$@"; }\n'
        program = (f"set -euo pipefail\n{shim}generations_root={str(root / 'generations')!r}\n"
                   f"{bootstrap_functions()}\nvalidate_generation {generation}\n")
        return subprocess.run(["bash", "-c", program], capture_output=True).returncode == 0


def assert_generations() -> None:
    base = {rel: rel for rel in REQUIRED}
    legacy = {**base, "metadata.env": "GENERATION=x\nCONTAINER_PROXY_ENABLED=0\nRESOLVED_SYNC_ENABLED=0\n"}
    if not validate(legacy):
        raise AssertionError("a generation without PINNED_PROXY_ENABLED must stay a valid rollback target")
    pinned_meta = "GENERATION=x\nCONTAINER_PROXY_ENABLED=0\nPINNED_PROXY_ENABLED=1\nRESOLVED_SYNC_ENABLED=0\n"
    if validate({**base, "metadata.env": pinned_meta}):
        raise AssertionError("PINNED_PROXY_ENABLED=1 without the unit files must be rejected")
    units = {"systemd/mihomo-container-proxy-pinned.socket": "s", "systemd/mihomo-container-proxy-pinned.service": "s"}
    if not validate({**base, **units, "metadata.env": pinned_meta}):
        raise AssertionError("PINNED_PROXY_ENABLED=1 with both unit files must validate")
    if validate({**base, "metadata.env": pinned_meta.replace("PINNED_PROXY_ENABLED=1", "PINNED_PROXY_ENABLED=2")}):
        raise AssertionError("PINNED_PROXY_ENABLED must be 0 or 1")


def main() -> None:
    assert_units()
    assert_api_port()
    assert_deploy_lists()
    assert_generations()
    print("pinned container proxy contract: ok")


if __name__ == "__main__":
    main()
