# Security notes

## Controller exposure

- Do not expose Mihomo `external-controller` to LAN/WAN.
- This project is designed to keep the controller reachable only on the microserver host, and access it via the LazyCat app route (`/api -> host.lzcapp:9090`).

## Secret (Bearer token)

- Always set a non-empty `secret:` in `/etc/mihomo/config.yaml`.
- `scripts/deploy_microserver.sh` auto-generates one if empty and saves it locally to `var/private/mihomo.secret`.
- Use `scripts/mihomo-manager secret show` to retrieve the current secret when configuring metacubexd.
  - `scripts/deploy_dashboard.sh` can optionally embed the secret into the dashboard package (behind LazyCat login) to make first-time setup zero-config.

## TUN / transparent proxy risk

- TUN changes can break LazyCat control-plane / tunnel traffic.
- Review `docs/LAZYCAT_NETWORK_REPORT.md` before changing TUN, and keep required bypasses (`6.6.6.6/32`, `2000::6666/128`, `fc03:1136:3800::/40`, plus local/container networks).

## Docker privileged risk

The compose option in `deploy/` uses host networking + `NET_ADMIN` + `/dev/net/tun`, which is effectively a privileged networking setup. Only use it if you understand the risks and trust the image/source.
