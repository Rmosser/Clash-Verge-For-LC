# scripts/

Operational scripts.

- `deploy_microserver.sh`
  - Pushes `/etc/mihomo/config.yaml` + systemd unit to the microserver and restarts `mihomo`.
  - Reads `.env` if present.

- `deploy_dashboard.sh`
  - Builds the LazyCat dashboard LPK and installs it via `lzc-cli`.

- `deploy_all.sh`
  - Runs both deploy steps.

- `patch_remote_mihomo_config.py`
  - Safe patcher for `/etc/mihomo/config.yaml` (avoids printing credentials).
