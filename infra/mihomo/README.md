# infra/mihomo

Microserver-side (Debian) deployment artifacts for Mihomo (Clash Meta).

## Files

- `mihomo.service`
  - Snapshot of the systemd unit currently running on the microserver.
  - Grants `CAP_NET_ADMIN`/`CAP_NET_RAW` so Mihomo can manage TUN + policy routing.

- `config.base.yaml`
  - Safe template (no credentials) documenting the key settings we rely on:
    - `external-controller: 172.18.0.1:9090` so LazyCat ingress can reach it via `host.lzcapp`
    - `tun:` enabled with `route-exclude-address` bypasses for LazyCat

## Runtime requirements (microserver)

- Mihomo binary installed at `/usr/local/bin/mihomo`
- `Country.mmdb` present at `/var/lib/mihomo/Country.mmdb` (required if rules use `GEOIP,CN`)

## Deployment

Use the repo scripts:

- `scripts/deploy_microserver.sh`  (push config + unit, restart)
- `scripts/deploy_dashboard.sh`    (build + install the LazyCat dashboard app)
- `scripts/deploy_all.sh`          (both)
