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
  - Fetches the latest `metacubexd` release assets by default (can be pinned via env).

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

- `selfcheck.sh`
  - Runs a quick remote health check (status, config test, /version, bypass probes).
