# Clash Verge For LC

懒猫微服上的 Clash Verge Web 面板，以及与之配套的 Mihomo 宿主机运行链路。

## 当前项目边界

- Web 面板以懒猫应用形式发布，入口是 `https://clash.<box>.heiyu.space`
- 宿主机运行时默认采用 host-native 路径，不以 `deploy/` 下的 compose 目录作为当前默认方案
- 容器出网默认走显式代理入口 `172.18.0.1:17890`，不要假设 TUN 会自动覆盖容器网络

## 当前有效 contract

当前 source of truth 在 [docs/CURRENT_RUNTIME.md](docs/CURRENT_RUNTIME.md)。

先记三条：

- 当前已验证基线是保守模式：`MIHOMO_TUN_ENABLE=0`、`MIHOMO_DNS_ENABLE=0`
- 浏览器通过 `/verge-api/public-config` 获取运行时配置；当前默认路径不需要手填 controller secret
- `172.18.0.1:9090` 只允许留在微服 bridge 上，不对 LAN/WAN 暴露

## 文档入口

| 文档 | 目标读者 | 用途 |
| --- | --- | --- |
| [docs/index.md](docs/index.md) | Agent/评审者 | 文档索引与 Harness governance 入口 |
| [docs/CURRENT_RUNTIME.md](docs/CURRENT_RUNTIME.md) | 所有人 | 当前运行 contract；先读这份 |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | 最终用户 | 登录、导入订阅、切节点、看状态 |
| [docs/CONTAINER_PROXY_GUIDE.md](docs/CONTAINER_PROXY_GUIDE.md) | 开发者 | Docker/容器显式代理与 Node.js 注意事项 |
| [docs/HOST_NATIVE_RUNBOOK.md](docs/HOST_NATIVE_RUNBOOK.md) | 运维/实施者 | 宿主机部署、恢复、重启验收 |
| [docs/LAZYCAT_NETWORK_REPORT.md](docs/LAZYCAT_NETWORK_REPORT.md) | 改网络的人 | TUN/DNS 变更约束与验证清单 |
| [docs/SECURITY.md](docs/SECURITY.md) | 运维/评审者 | 安全边界与禁止项 |
| [docs/PACKAGING.md](docs/PACKAGING.md) | 发布者 | 只出 LPK 安装包，不落宿主机运行时 |
| [docs/CLASH_VERGE_WEB_SMOKE_CHECKLIST.md](docs/CLASH_VERGE_WEB_SMOKE_CHECKLIST.md) | 测试/回归者 | Web 端回归检查清单 |
| [docs/PRD.md](docs/PRD.md) | 设计回溯者 | 历史设计文档，不是当前手册 |

## 历史文档

`docs/planning/` 下的文件保留事故研判和复盘，不作为当前操作手册。当前执行以 [docs/CURRENT_RUNTIME.md](docs/CURRENT_RUNTIME.md) 和 [docs/HOST_NATIVE_RUNBOOK.md](docs/HOST_NATIVE_RUNBOOK.md) 为准。

## 上游

- [clash-verge-rev/clash-verge-rev](https://github.com/clash-verge-rev/clash-verge-rev)
- [MetaCubeX/metacubexd](https://github.com/MetaCubeX/metacubexd)
- [MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo)

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
