# Clash Verge for LazyCat

LazyCat Microservice deployment and dashboard packaging for Mihomo.

This repository adapts the `clash-verge-rev` / `metacubexd` ecosystem to the LazyCat microservice environment so you can:

- run Mihomo on a LazyCat microserver with TUN enabled
- keep LazyCat control-plane and tunnel traffic bypassed
- access a web dashboard through the LazyCat app route instead of exposing the controller to LAN/WAN

## Upstream Credit

This project is not an original proxy dashboard implementation.

It stands on the work of these upstream projects:

- [clash-verge-rev/clash-verge-rev](https://github.com/clash-verge-rev/clash-verge-rev): the upstream Verge frontend source vendored in this repo
- [MetaCubeX/metacubexd](https://github.com/MetaCubeX/metacubexd): the official Mihomo dashboard distributed as static assets
- [MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo): the proxy core this project deploys and manages

If you want the original desktop app or the upstream dashboard itself, use the upstream repositories first. This repository exists to solve LazyCat-specific deployment, ingress, and operational problems around them.

## What This Repo Adds

Compared with upstream projects, this repository mainly adds:

- LazyCat-oriented deployment scripts for the microserver
- a LazyCat Launchpad app that serves the dashboard and proxies `/api` to the host controller
- controller-secret handling that avoids direct LAN/WAN exposure
- TUN safety notes and bypass guidance for the LazyCat control plane
- operational scripts for health checks, upgrades, rollback, and egress auditing

In other words: upstream provides the core UI and engine, this repo provides the LazyCat adaptation layer.

## Safety First

Before using or modifying this setup:

- read `docs/LAZYCAT_NETWORK_REPORT.md` before changing any TUN or transparent-proxy behavior
- do not expose Mihomo `external-controller` to LAN/WAN
- keep real configs and credentials under `var/private/` and out of git

More details: `docs/SECURITY.md`.

## Repository Layout

- `src/mihomo-dashboard-app/`: LazyCat app package for the web dashboard
- `src/mihomo-dashboard-app/vendor/clash-verge-rev/`: vendored upstream Verge frontend source
- `scripts/`: deploy, sync, self-check, and operational scripts
- `infra/`: microserver-side templates and helpers
- `deploy/`: optional Docker Compose deployment
- `configs/`: non-secret config templates
- `docs/`: operations notes, security notes, and network impact reports
- `var/private/`: local private config and secrets, intentionally not committed

## Quick Start

1. Create local env:

```bash
cp .env.example .env
```

2. Put your real Mihomo config at `var/private/mihomo.config.yaml`.

Required for dashboard access:

```yaml
external-controller: 172.18.0.1:9090
```

3. Deploy Mihomo to the microserver:

```bash
scripts/deploy_microserver.sh
```

4. Build and install the LazyCat dashboard app:

```bash
scripts/deploy_dashboard.sh
```

5. Or run both:

```bash
scripts/deploy_all.sh
```

6. Show the controller secret if you need to connect manually:

```bash
scripts/mihomo-manager secret show
```

## Daily Operations

```bash
scripts/mihomo-manager status
scripts/mihomo-manager logs
scripts/mihomo-manager reload
scripts/selfcheck.sh
```

## Local Runtime Contract

This repo is deployment- and ops-oriented. It does not run a long-lived local daemon, but it keeps standard entrypoints:

```bash
bash scripts/run_local.sh
bash scripts/stop_local.sh
bash scripts/doctor.sh
```

## Keeping Up with Upstream

The vendored Verge frontend can be refreshed from upstream with:

```bash
scripts/sync_clash_verge_rev.sh
```

By default it syncs from:

- `https://github.com/clash-verge-rev/clash-verge-rev.git`
- ref `v2.4.7`

The vendored upstream license and upstream README are preserved under:

- `src/mihomo-dashboard-app/vendor/clash-verge-rev/LICENSE`
- `src/mihomo-dashboard-app/vendor/clash-verge-rev/README.upstream.md`

## Why This README Is Explicit About Origin

For an open-source derivative, the most useful README is the one that reduces confusion:

- users can quickly tell whether they need this repo or the upstream project
- maintainers avoid overstating authorship
- contributors can see where LazyCat-specific changes belong
- upstream authors get visible credit instead of being hidden inside a vendor directory

If you fully recreated an existing open-source project, the best move is to say so plainly and then explain your specific delta.

## Contributing

Issues and pull requests are welcome, especially for:

- LazyCat deployment compatibility
- safer TUN defaults and rollback paths
- dashboard packaging and ingress behavior
- documentation, recovery guides, and test coverage

When changing vendored frontend code, document whether the change should stay local or be proposed upstream.

## License and Notice

This repository vendors upstream code from `clash-verge-rev`, which ships with GPL-3.0 licensing in the vendored source tree.

Before publishing this repository broadly, make sure you:

- keep upstream copyright and license notices intact
- add a top-level `LICENSE` file for this repository
- verify your redistribution terms are compatible with the upstream license

If you want, the next step can be to turn this README into a stronger public-facing version with badges, screenshots, a "Who is this for?" section, and a short migration guide from upstream usage to LazyCat usage.
