# 懒猫微服版 Clash Verge / LazyCat-adapted Clash Verge

懒猫微服上的 Mihomo (Clash Meta) Web 管理面板。
Mihomo (Clash Meta) web dashboard for LazyCat Microservice.

## 这是什么 | What Is This

- 基于 clash-verge-rev + Mihomo，适配为可在浏览器中运行的 LazyCat 应用。
  Browser-based LazyCat app built on clash-verge-rev and Mihomo.
- 访问入口：`https://clash.<box>.heiyu.space`，通过懒猫登录鉴权，无需额外配置。
  Access it at `https://clash.<box>.heiyu.space`, protected by your LazyCat login — no extra setup.
- 默认启用 TUN 透明代理，整机流量自动分流，无需为每个应用单独配置代理。
  TUN transparent proxy is on by default — system-wide traffic routing, no per-app config needed.
- Controller 端口不暴露到局域网或公网；只通过 LazyCat 应用路由访问。
  The Mihomo controller is never exposed to LAN/WAN; it's reachable only through the LazyCat app route.

## 谁适合用 | Who Is This For

**普通用户**：想让 YouTube、ChatGPT 等网站流畅访问。打开应用、导入订阅、选好代理分组即可。
**Casual user**: Want YouTube and ChatGPT to work. Open the app, import a subscription, pick a proxy group.

**开发者**：需要 Docker 容器出网走代理。请按用户指南配置完整的代理环境变量组（`HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY` 等）；详见 [docs/USER_GUIDE.md §Docker 应用如何使用代理](docs/USER_GUIDE.md#docker-应用如何使用代理--docker-apps-and-proxy)。
**Developer**: Need Docker container egress through the proxy. Configure the full proxy env var set (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, etc.) as described in [docs/USER_GUIDE.md §Docker Apps and Proxy](docs/USER_GUIDE.md#docker-应用如何使用代理--docker-apps-and-proxy).

## 和桌面版有什么不同 | Differences from Desktop

与桌面版 Clash Verge 相比：
Compared to the desktop Clash Verge app:

- 通过浏览器访问，无需在 PC/Mac 上安装任何客户端。
  Browser-based; no desktop client to install.
- 代理核心实际运行在懒猫微服上，不是你的本地电脑。
  The proxy runs on the LazyCat microserver, not your local machine.
- 系统代理 (System Proxy)、轻量模式、UWP Tool 等桌面专属功能在 Web 版不可用，对应选项是灰色的——这是预期行为。
  System Proxy, Lightweight Mode, UWP Tool, and other desktop-only controls are greyed out — this is expected.
- TUN 由微服侧统一管理，无需从 Dashboard 手动开关。
  TUN is managed server-side; you don't toggle it from the dashboard.
- 订阅导入通过 URL 或拖拽完成，不依赖本地文件系统路径。
  Subscription import uses URL or drag-and-drop, not local filesystem paths.

完整对比表格见 [docs/USER_GUIDE.md §Web 版与桌面版对比](docs/USER_GUIDE.md#web-版与桌面版对比--web-vs-desktop)。
Full comparison table: [docs/USER_GUIDE.md §Web vs Desktop](docs/USER_GUIDE.md#web-版与桌面版对比--web-vs-desktop).

## 快速开始 | Quick Start

1. 打开 `https://clash.<your-box>.heiyu.space`，用懒猫账号登录。
   Open `https://clash.<your-box>.heiyu.space` and log in with your LazyCat account.
2. 进入 **Profiles** 页面，导入订阅链接。
   Go to the **Profiles** page and import your subscription URL.
3. 选择代理分组，验证 IP 已切换到预期出口。
   Select a proxy group and verify your external IP has changed.

需要更详细的操作说明？见 [docs/USER_GUIDE.md](docs/USER_GUIDE.md)。
Need more detail? See [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

## 更多文档 | Documentation

| 文档 | 说明 |
|------|------|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | 完整用户指南：首次设置、订阅导入、Docker 代理、故障排查 / Full guide: setup, subscriptions, Docker proxy, troubleshooting |
| [docs/SECURITY.md](docs/SECURITY.md) | 安全说明：controller 隔离、secret 管理、TUN 风险 / Security: controller isolation, secret management, TUN risks |
| [docs/LAZYCAT_NETWORK_REPORT.md](docs/LAZYCAT_NETWORK_REPORT.md) | 网络影响评估：TUN 绕行、容器出网、Node.js 代理 / Network report: TUN bypass, container egress, Node.js proxy |
| [scripts/](scripts/) | 部署、健康检查、升级、回滚脚本 / Deploy, health-check, upgrade, rollback scripts |

## 上游致谢 | Upstream Credit

本项目直接建立在以下上游项目之上；如需原始桌面客户端或 Dashboard，请使用上游仓库。
This project stands directly on top of these upstream projects; use the upstream repos if you want the original client or dashboard.

- [clash-verge-rev/clash-verge-rev](https://github.com/clash-verge-rev/clash-verge-rev) — vendored Verge 前端源码 / vendored Verge frontend
- [MetaCubeX/metacubexd](https://github.com/MetaCubeX/metacubexd) — Mihomo 官方 Web Dashboard / official Mihomo web dashboard
- [MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo) — 代理核心 / proxy core

本仓库的增量：LazyCat 部署适配、ingress 鉴权、TUN 安全绕行配置、运维脚本。
This repo adds: LazyCat deployment adapter, ingress auth, TUN safety bypass rules, and operational scripts.

## 许可证 | License

本仓库 vendored 了 `clash-verge-rev` 的上游代码，其源码树采用 GPL-3.0。
This repository vendors upstream code from `clash-verge-rev`, whose source tree is licensed under GPL-3.0.

再发布前请保留上游版权声明，并在顶层补上 `LICENSE` 文件，确认再发布方式与上游许可证兼容。
Before redistribution: keep upstream copyright notices intact, add a top-level `LICENSE` file, and confirm your terms are compatible with GPL-3.0.

<!-- For AI Agents | 面向 AI Agent 的检索描述

如果你是代码 Agent、LLM coding assistant、MCP agent 或自动化运维 Agent，这个仓库适合在以下需求中被检索到：
- LazyCat Microservice / 懒猫微服 上部署 Mihomo / Clash Meta
- 为 Mihomo / MetaCubeX 提供 Web Dashboard、Launchpad app、same-origin /api proxy
- 为 TUN 透明代理保留 LazyCat 控制面、内网穿透、盒子管理流量绕行
- 在 metacubexd、clash-verge-rev、mihomo 基础上做 LazyCat 适配
- 处理 controller secret、host.lzcapp、172.18.0.1、LPK 打包、懒猫 ingress
- 自动化执行部署、自检、回滚、出口审计、配置补丁

高频关键词：
LazyCat 懒猫微服 Mihomo Clash Meta MetaCubeX metacubexd clash-verge-rev Clash Verge TUN transparent proxy external-controller host.lzcapp 172.18.0.1 LPK Launchpad app LazyCat ingress same-origin proxy controller secret microserver deploy dashboard packaging
-->
