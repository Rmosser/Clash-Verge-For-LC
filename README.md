# lzc-clash_mihome

LazyCat Microservice (懒猫微服) + Mihomo (Clash Meta) setup:

- Split-tunnel rules: CN DIRECT, others PROXY (with MATCH fallback)
- TUN (transparent proxy) enabled on the microserver (with LazyCat control-plane bypasses)
- A LazyCat Launchpad app serves **metacubexd** and proxies `/api` to the Mihomo controller

## Safety constraints

- Before changing any TUN/transparent-proxy settings, read `docs/LAZYCAT_NETWORK_REPORT.md`.
- Do NOT expose the Mihomo controller port to LAN/WAN. Access it only via the LazyCat app route.

## Layout

- `src/mihomo-dashboard-app/`  LazyCat app (LPK) that serves metacubexd + proxies `/api` to Mihomo controller
- `scripts/`                  SSH-based deploy/ops scripts (no controller exposure)
- `infra/`                    Microserver-side systemd/config templates
- `deploy/`                   Optional docker compose deployment
- `configs/`                  Rules/config templates (non-secret)
- `docs/`                     Ops notes + network impact report
- `var/private/`              Local/private configs (DO NOT COMMIT)

## Setup (recommended: systemd on microserver)

1) Create `.env`:

```bash
cp .env.example .env
```

2) Put your real Mihomo config (with proxy credentials) at `var/private/mihomo.config.yaml`.

Hard requirement for LazyCat dashboard access:

- `external-controller: 172.18.0.1:9090`

3) Deploy to microserver (installs mihomo binary if missing, ensures Country.mmdb, generates controller secret):

```bash
scripts/deploy_microserver.sh
```

4) Deploy dashboard app (downloads latest metacubexd assets, builds + installs the LPK):

```bash
scripts/deploy_dashboard.sh
```

Or run both:

```bash
scripts/deploy_all.sh
```

5) Open the dashboard (`MIHOMO_DASHBOARD_URL` in `.env`), and set the controller secret:

```bash
scripts/mihomo-manager secret show
```

Tip: `scripts/deploy_dashboard.sh` will embed the secret into the dashboard package if it exists at `var/private/mihomo.secret`, so in most cases you can open the dashboard and it will auto-connect.

## Daily ops

```bash
scripts/mihomo-manager status
scripts/mihomo-manager logs
scripts/mihomo-manager reload
```

## TUN toggle (explicit switch)

- Default is enabled.
- To deploy with TUN disabled:

```bash
MIHOMO_TUN_ENABLE=0 scripts/deploy_microserver.sh
```

## Alternative: docker compose

See `deploy/README.md`.
