# scripts/

Operational scripts.

- `deploy_microserver.sh`
  - Pushes `/etc/mihomo/config.yaml` + systemd unit to the microserver and restarts `mihomo`.
  - Reads `.env` if present.

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
  - Minimal CLI wrapper (via SSH) for common operations:
    - status/logs/config-test/reload/restart-core/update-geo/secret show

- `selfcheck.sh`
  - Runs a quick remote health check (status, config test, /version, bypass probes).
