# lzc-clash_mihome

LazyCat Microservice (懒猫微服) + Mihomo (Clash Meta) setup:

- Split-tunnel rules: CN DIRECT, others PROXY (with MATCH fallback)
- TUN (transparent proxy) enabled on the microserver
- A LazyCat Launchpad app provides a small Web dashboard to switch proxy groups/nodes

## Layout

- `src/mihomo-dashboard-app/`  LazyCat app (LPK) that serves a dashboard and proxies `/api` to Mihomo controller
- `scripts/`                  Scripts for patching/validating remote configs safely
- `configs/`                  Rules/config templates (non-secret)
- `docs/`                     Ops notes + network impact report
- `var/private/`              Local/private configs (DO NOT COMMIT)

## Quick commands

Build dashboard LPK:

```bash
cd src/mihomo-dashboard-app
lzc-cli project build -f lzc-build.yml -o mihomo-dashboard.lpk
```

Install/upgrade dashboard app:

```bash
cd src/mihomo-dashboard-app
lzc-cli app install mihomo-dashboard.lpk
```
