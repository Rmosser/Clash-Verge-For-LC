# scripts/

Operational scripts.

- `deploy_microserver.sh`
  - Pushes `/etc/mihomo/config.yaml` + systemd unit to the microserver and restarts `mihomo`.
  - Reads `.env` if present.
  - Core upgrade flags:
    - `--upgrade-core`: force core upgrade even when `/usr/local/bin/mihomo` already exists.
    - `--core-version <tag>`: pin core version.
    - `--latest-stable`: force GitHub stable latest tag.
    - `--only-core`: upgrade core only (skip config/unit/mmdb deploy).
    - `--no-rollback`: disable automatic rollback.
  - Automatic rollback:
    - On upgrade failure, restores backup core and attempts service restart.
    - Writes metadata to `/var/lib/mihomo/rollback/latest.env`.

- `deploy_dashboard.sh`
  - Builds the LazyCat dashboard LPK and installs it via `lzc-cli`.
  - `--clean-reset` removes legacy dashboard pkgm residues, purges the current app's LazyCat deploy mapping, and resets `/var/lib/mihomo/verge/` before reinstall.
  - Verifies that the expected public route is reachable after install, and warns if `LAZYCAT_APP_DOMAIN` drifts from the public ingress domain.
  - Verifies the real runtime chain after install: `/verge-api/healthz`, `/verge-api/public-config`, controller `/version`/`/configs`/`/proxies`, and websocket handshakes for `/traffic` + `/memory`.
  - Does not embed controller or verge-api secrets into `dist/lzcapp-config.js`; the browser bootstraps them at runtime behind LazyCat login.

- `deploy_all.sh`
  - Runs both deploy steps.

- `update_metacubexd.sh`
  - Downloads and unpacks `metacubexd` static assets into `src/mihomo-dashboard-app/dist`.
  - Sets `defaultBackendURL` to `/api` (proxied by LazyCat ingress to the host controller).

- `patch_remote_mihomo_config.py`
  - Safe patcher for `/etc/mihomo/config.yaml` (avoids printing credentials).

- `mihomo-manager`
  - CLI wrapper (via SSH) for operations:
    - `status` / `logs` / `config-test` / `reload` / `restart-core` / `update-geo` / `version` / `secret show`
    - `upgrade-core [version]`: one-click core upgrade (default stable latest)
    - `rollback-core [latest|/var/lib/mihomo/rollback/mihomo.<ts>.bak]`: manual rollback
  - Prefers the remote controller secret and only falls back to local secret files when needed.

- `selfcheck.sh`
  - Runs a quick remote health check (status, config test, `/version`, `/verge-api/public-config`, bypass probes).

- `audit_proxy_egress.sh`
  - Audits each Socks5 proxy's IPv4/IPv6 egress via Mihomo controller API (/proxies/*/delay).
  - Controller secret never leaves the microserver.

- `patch_auto_group.py`
  - Dependency-free patcher to restrict `proxy-groups.AUTO.proxies` to a specific list.
  - Intended for `var/private/mihomo.config.yaml` (ignored, contains credentials).

- `egress_fix.sh`
  - End-to-end helper:
    - runs `audit_proxy_egress.sh`
    - if any V6-capable proxies exist, pins AUTO group to them
    - deploys via `deploy_microserver.sh`
    - runs 30x curl acceptance checks via the local mixed-port

- `block_aaaa_resolved.sh` / `unblock_aaaa_resolved.sh`
  - Optional workaround: configure `systemd-resolved` to refuse AAAA record types.
  - Used when your proxy nodes are V4-only egress and IPv6 destinations cause stalls/EOF under TUN.
  - Note: on some LazyCat base OS builds, `systemd-resolved.service` may not exist.

- `prefer_ipv4_gai.sh` / `unprefer_ipv4_gai.sh`
  - Workaround: tune `/etc/gai.conf` so apps prefer IPv4 destinations (without breaking IPv6 access to IPv6 proxy servers).
  - This is the recommended fallback when `systemd-resolved` is not manageable as a unit.

- `ensure_ipv6_reject_rule.py`
  - Optional workaround: inject `IP-CIDR6,::/0,REJECT,no-resolve` before `GEOIP,CN`/`MATCH` to fail-fast on IPv6 destinations.
  - Useful when your proxies are V4-only egress but clients still attempt IPv6 (prevents long hangs).
