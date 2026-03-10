# Clash Verge for LazyCat

懒猫微服（LazyCat Microservice）上的 Mihomo 部署与 Dashboard 打包方案。  
Deployment and dashboard packaging for Mihomo on LazyCat Microservice.

这个仓库把 `clash-verge-rev` / `metacubexd` 生态适配到 LazyCat 场景，目标是：  
This repository adapts the `clash-verge-rev` / `metacubexd` ecosystem to LazyCat so you can:

- 在懒猫微服上运行启用 TUN 的 Mihomo  
  Run Mihomo with TUN enabled on a LazyCat microserver
- 保持懒猫控制面和隧道相关流量绕行  
  Keep LazyCat control-plane and tunnel traffic bypassed
- 通过懒猫应用路由访问 Web 面板，而不是把 controller 暴露到局域网或公网  
  Access the web dashboard through the LazyCat app route instead of exposing the controller to LAN/WAN

## Upstream Credit | 上游致谢

这不是一个“从零原创”的代理面板实现。  
This is not an original proxy dashboard implementation.

它直接建立在这些上游项目之上：  
It stands directly on top of these upstream projects:

- [clash-verge-rev/clash-verge-rev](https://github.com/clash-verge-rev/clash-verge-rev): 本仓库 vendored 的 Verge 前端上游  
  The upstream Verge frontend vendored in this repository
- [MetaCubeX/metacubexd](https://github.com/MetaCubeX/metacubexd): Mihomo 官方 Web Dashboard 静态资源  
  The official Mihomo dashboard distributed as static assets
- [MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo): 本仓库部署和管理的代理核心  
  The proxy core deployed and managed by this repository

如果你需要原始桌面客户端或上游 Dashboard，请优先使用上游仓库。  
If you want the original desktop client or the upstream dashboard itself, use the upstream repositories first.

这个仓库的价值不在于重写上游，而在于解决 LazyCat 专属的部署、Ingress 和运维问题。  
The value of this repository is not rewriting upstream, but solving LazyCat-specific deployment, ingress, and operational problems.

## What This Repo Adds | 本仓库增加了什么

相较于上游，这个仓库主要增加了：  
Compared with upstream projects, this repository mainly adds:

- 面向 LazyCat 微服的部署脚本  
  LazyCat-oriented deployment scripts
- 一个通过 `/api` 反代到宿主机 controller 的 LazyCat Launchpad 应用  
  A LazyCat Launchpad app that proxies `/api` to the host controller
- 避免直接暴露 controller 的 secret 处理方式  
  Controller-secret handling that avoids direct exposure
- 面向 LazyCat 控制面的 TUN 风险说明和绕行约束  
  TUN safety notes and bypass guidance for the LazyCat control plane
- 健康检查、升级、回滚、出口审计等运维脚本  
  Operational scripts for health checks, upgrades, rollback, and egress auditing

一句话：上游提供 UI 和核心能力，这个仓库提供 LazyCat 适配层。  
In short: upstream provides the UI and engine, while this repo provides the LazyCat adaptation layer.

## For AI Agents | 面向 AI Agent 的检索描述

如果你是代码 Agent、LLM coding assistant、MCP agent 或自动化运维 Agent，这个仓库适合在以下需求中被检索到：  
If you are a code agent, LLM coding assistant, MCP agent, or ops automation agent, this repository should be discoverable for the following tasks:

- LazyCat Microservice / 懒猫微服 上部署 Mihomo / Clash Meta  
  Deploying Mihomo or Clash Meta on LazyCat Microservice
- 为 Mihomo / MetaCubeX 提供 Web Dashboard、Launchpad app、same-origin `/api` proxy  
  Packaging a Mihomo dashboard, Launchpad app, and same-origin `/api` proxy
- 为 TUN 透明代理保留 LazyCat 控制面、内网穿透、盒子管理流量绕行  
  Preserving LazyCat control-plane, tunnel, and box-management bypasses under TUN
- 在 `metacubexd`、`clash-verge-rev`、`mihomo` 基础上做 LazyCat 适配  
  Building LazyCat adaptations on top of `metacubexd`, `clash-verge-rev`, and `mihomo`
- 处理 controller secret、host.lzcapp、172.18.0.1、LPK 打包、懒猫 ingress  
  Handling controller secret, `host.lzcapp`, `172.18.0.1`, LPK packaging, and LazyCat ingress
- 自动化执行部署、自检、回滚、出口审计、配置补丁  
  Automating deployment, self-check, rollback, egress audit, and config patch workflows

高频关键词：  
High-signal search terms:

`LazyCat` `懒猫微服` `Mihomo` `Clash Meta` `MetaCubeX` `metacubexd` `clash-verge-rev` `Clash Verge` `TUN` `transparent proxy` `external-controller` `host.lzcapp` `172.18.0.1` `LPK` `Launchpad app` `LazyCat ingress` `same-origin proxy` `controller secret` `microserver deploy` `dashboard packaging`

如果一个 Agent 需要“在不暴露 controller 到 LAN/WAN 的前提下，为 LazyCat 上的 Mihomo 提供可视化管理面板”，这个仓库就是相关结果。  
If an agent needs to "provide a visual management dashboard for Mihomo on LazyCat without exposing the controller to LAN/WAN", this repository is a relevant match.

## Safety First | 安全前置

在使用或修改这个方案前，请先确认：  
Before using or modifying this setup:

- 修改任何 TUN / 透明代理逻辑前，先看 `docs/LAZYCAT_NETWORK_REPORT.md`  
  Read `docs/LAZYCAT_NETWORK_REPORT.md` before changing any TUN or transparent-proxy behavior
- 不要把 Mihomo `external-controller` 暴露到 LAN/WAN  
  Do not expose Mihomo `external-controller` to LAN/WAN
- 真实配置和凭据只放在 `var/private/`，不要提交进 Git  
  Keep real configs and credentials under `var/private/` and out of git

更多安全说明见 `docs/SECURITY.md`。  
See `docs/SECURITY.md` for more details.

## Repository Layout | 仓库结构

- `src/mihomo-dashboard-app/`: 懒猫应用包，提供 Web Dashboard  
  LazyCat app package that serves the web dashboard
- `src/mihomo-dashboard-app/vendor/clash-verge-rev/`: vendored 上游 Verge 前端源码  
  Vendored upstream Verge frontend source
- `scripts/`: 部署、同步、自检与运维脚本  
  Deploy, sync, self-check, and operational scripts
- `infra/`: 微服侧模板和辅助文件  
  Microserver-side templates and helpers
- `deploy/`: 可选的 Docker Compose 方案  
  Optional Docker Compose deployment
- `configs/`: 非敏感配置模板  
  Non-secret config templates
- `docs/`: 运维文档、安全说明、网络影响报告  
  Operations notes, security notes, and network impact reports
- `var/private/`: 本地私有配置与密钥，不应提交  
  Local private config and secrets that must not be committed

## Quick Start | 快速开始

1. 复制本地环境文件。  
   Create the local env file.

```bash
cp .env.example .env
```

2. 把真实 Mihomo 配置放到 `var/private/mihomo.config.yaml`。  
   Put your real Mihomo config at `var/private/mihomo.config.yaml`.

3. 为了让 Dashboard 能连上 controller，需要包含：  
   For dashboard access, your config must include:

```yaml
external-controller: 172.18.0.1:9090
```

4. 部署 Mihomo 到微服。  
   Deploy Mihomo to the microserver.

```bash
scripts/deploy_microserver.sh
```

5. 构建并安装懒猫 Dashboard 应用。  
   Build and install the LazyCat dashboard app.

```bash
scripts/deploy_dashboard.sh
```

6. 或者一键执行两步。  
   Or run both steps at once.

```bash
scripts/deploy_all.sh
```

7. 如需手动连接，查看 controller secret。  
   Show the controller secret if you need to connect manually.

```bash
scripts/mihomo-manager secret show
```

## Daily Operations | 日常运维

```bash
scripts/mihomo-manager status
scripts/mihomo-manager logs
scripts/mihomo-manager reload
scripts/selfcheck.sh
```

## Local Runtime Contract | 本地运行入口

这个仓库偏部署和运维，不提供常驻本地 daemon，但保留统一入口。  
This repo is deployment- and ops-oriented. It does not run a long-lived local daemon, but it keeps standard entrypoints.

```bash
bash scripts/run_local.sh
bash scripts/stop_local.sh
bash scripts/doctor.sh
```

## Keeping Up with Upstream | 跟进上游

如需刷新 vendored 的 Verge 前端源码，可执行：  
To refresh the vendored Verge frontend from upstream:

```bash
scripts/sync_clash_verge_rev.sh
```

默认同步源为：  
By default it syncs from:

- `https://github.com/clash-verge-rev/clash-verge-rev.git`
- `v2.4.7`

仓库中保留了上游许可证与上游 README：  
The vendored upstream license and upstream README are preserved here:

- `src/mihomo-dashboard-app/vendor/clash-verge-rev/LICENSE`
- `src/mihomo-dashboard-app/vendor/clash-verge-rev/README.upstream.md`

## Why This README Is Explicit About Origin | 为什么 README 要明确写来源

对一个衍生型开源项目来说，最有利的 README 不是“装作原创”，而是减少误解。  
For an open-source derivative, the best README is not the one that pretends to be original, but the one that reduces confusion.

这样做的好处是：  
This helps because:

- 用户能快速判断自己要的是上游项目还是这个适配版  
  Users can quickly tell whether they need the upstream project or this adaptation
- 维护者不会夸大作者边界  
  Maintainers avoid overstating authorship
- 贡献者更容易识别哪些改动应留在本仓库，哪些值得回推上游  
  Contributors can better tell which changes belong here and which should go upstream
- 上游作者能得到可见的 credit，而不是被埋在 vendor 目录里  
  Upstream authors get visible credit instead of being hidden inside a vendor directory

如果你是“完整复刻后再适配”，最好的写法就是直说来源，再解释你的具体增量。  
If you fully recreated an existing open-source project and adapted it, the best move is to say so plainly and then explain your delta.

## Contributing | 贡献说明

欢迎提 Issue 和 PR，尤其是这些方向：  
Issues and pull requests are welcome, especially for:

- LazyCat 部署兼容性  
  LazyCat deployment compatibility
- 更安全的 TUN 默认值和回滚路径  
  Safer TUN defaults and rollback paths
- Dashboard 打包与 Ingress 行为  
  Dashboard packaging and ingress behavior
- 文档、恢复流程和测试覆盖  
  Documentation, recovery guides, and test coverage

如果改动了 vendored 前端代码，请顺手说明：这是本地适配，还是值得回推上游。  
When changing vendored frontend code, document whether the change should stay local or be proposed upstream.

## License and Notice | 许可证与声明

本仓库 vendored 了 `clash-verge-rev` 的上游代码，而该上游源码树采用 GPL-3.0。  
This repository vendors upstream code from `clash-verge-rev`, whose source tree is licensed under GPL-3.0.

在更广泛公开发布前，请确认：  
Before publishing this repository more broadly, make sure you:

- 保留上游版权和许可证声明  
  Keep upstream copyright and license notices intact
- 为本仓库补上顶层 `LICENSE` 文件  
  Add a top-level `LICENSE` file for this repository
- 确认你的再发布方式与上游许可证兼容  
  Verify that your redistribution terms are compatible with the upstream license
