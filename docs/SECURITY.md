# Security notes

## Controller exposure

- Do not expose Mihomo `external-controller` to LAN/WAN.
- This project is designed to keep the controller reachable only on the microserver host, and access it via the LazyCat app route (`/api -> host.lzcapp:9090`).

## Secret (Bearer token)

- Always set a non-empty `secret:` in `/etc/mihomo/config.yaml`.
- `scripts/deploy_microserver.sh` auto-generates one if empty and saves it locally to `var/private/mihomo.secret`.
- Use `scripts/mihomo-manager secret show` to retrieve the current secret when configuring metacubexd.
- The LazyCat dashboard no longer embeds runtime secrets into `lzcapp-config.js`.
  - Browsers bootstrap runtime config from `/verge-api/public-config` behind the LazyCat login session.
  - `/api/*` still uses the Mihomo Bearer secret, but the secret is resolved on the microserver at runtime instead of being baked into the LPK.

## TUN / transparent proxy risk

- TUN changes can break LazyCat control-plane / tunnel traffic.
- Review `docs/LAZYCAT_NETWORK_REPORT.md` before changing TUN, and keep required bypasses (`6.6.6.6/32`, `2000::6666/128`, `fc03:1136:3800::/40`, plus local/container networks).

## Docker privileged risk

The compose option in `deploy/` uses host networking + `NET_ADMIN` + `/dev/net/tun`, which is effectively a privileged networking setup. Only use it if you understand the risks and trust the image/source.
