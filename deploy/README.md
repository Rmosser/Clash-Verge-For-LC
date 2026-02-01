# deploy/

Docker compose deployment option for **mihomo** on the microserver.

Notes:

- The dashboard is shipped as a **LazyCat app** (`src/mihomo-dashboard-app/`), not via compose.
- This compose setup is intended for the **microserver host** (Debian) and uses `network_mode: host`
  so TUN + policy routing can affect the host network stack.
- Before enabling or changing TUN, review `docs/LAZYCAT_NETWORK_REPORT.md` (avoid breaking LazyCat control-plane/tunnel).

## Quick start

From the microserver (or any machine that controls the microserver Docker daemon):

```bash
cd deploy
cp .env.example .env   # optional
./init.sh              # generates config.yaml + secret.txt if needed
docker compose up -d
```

Then:

- Install the LazyCat dashboard app via `scripts/deploy_dashboard.sh`.
- Open the dashboard and set the controller secret from `deploy/secret.txt`.

## TUN toggle

- Default is enabled (`MIHOMO_TUN_ENABLE=1`).
- To disable TUN during init:

```bash
MIHOMO_TUN_ENABLE=0 ./init.sh
```
