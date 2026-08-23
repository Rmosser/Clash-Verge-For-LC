# Project Agents

本仓库在懒猫微服上运行 host-native Mihomo，并提供 LazyCat Web 控制台。Agent 从本文件进入，按任务只加载必要文档。

## 安全边界

- 修改 TUN、DNS、透明代理或容器出网前，先读 `docs/LAZYCAT_NETWORK_REPORT.md`。
- 当前保守运行基线保持 `MIHOMO_TUN_ENABLE=0`、`MIHOMO_DNS_ENABLE=0`。
- Mihomo controller 只监听 `172.18.0.1:9090` 微服 bridge，不向 LAN/WAN 暴露。
- 不提交订阅、controller secret、私有配置、LPK 或运行态数据。
- 普通开发 CI 不修改 host、TUN、DNS、systemd、LPK 或部署状态，也不获得 secret、privileged、volume 或 Docker socket。

## Context Map

- 文档索引：[docs/index.md](docs/index.md)
- 质量命令与 CI：[docs/quality.md](docs/quality.md)
- 脚本用途：[scripts/README.md](scripts/README.md)
- 当前运行契约：[docs/CURRENT_RUNTIME.md](docs/CURRENT_RUNTIME.md)
- 网络约束：[docs/LAZYCAT_NETWORK_REPORT.md](docs/LAZYCAT_NETWORK_REPORT.md)
- 安全边界：[docs/SECURITY.md](docs/SECURITY.md)
- 可选实施计划：[docs/plans/](docs/plans/)

历史计划、事故和复盘仅供追溯，不作为当前运行 contract。复杂或长周期任务可以使用可选计划；普通任务不要求创建、归档或维护全局 Active Plan。

## Standard Quality

仓库级快速入口是 `bash scripts/test.sh`。Dashboard 的 frozen install、unit、typecheck、lint、build，以及文档检查和远端 smoke 命令见 [docs/quality.md](docs/quality.md)。
