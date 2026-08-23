# Project Agents

## lzc-clash_mihome - Agent 操作手册

目标：在懒猫微服上运行 Mihomo (Clash Meta)，实现：

- 国内直连 / 国外代理（兜底 MATCH,PROXY）
- 启用 TUN 透明代理，但必须绕行懒猫内网穿透/控制面相关流量
- 提供可视化 Web 控制台（作为懒猫应用）用于手动切换节点/分组

## 关键约束

- 不要破坏懒猫内网穿透/控制面：任何透明代理/TUN 变更前先看 `docs/LAZYCAT_NETWORK_REPORT.md`。
- 不要把 Mihomo 控制端口暴露到局域网：当前对外只通过懒猫登录后的应用路由访问。
- 非平凡变更从当前 baseline / worktree HEAD 开 focused branch；保留已有工作树改动，不把旧分支或旧 PR 当成当前真相。
- 不要把本文件理解为绕过 review、checks、branch protection 或运行态验收的授权；仓库检查、平台门禁和远端状态分别核实。
- 不提交订阅、controller secret、私有配置、LPK 或运行态数据。

## Woodpecker 开发与证据边界

- 非平凡任务在 `docs/exec-plans/active/` 保持且仅保持一个当前 Active Plan。
- 当前运行真相保持 `MIHOMO_TUN_ENABLE=0`、`MIHOMO_DNS_ENABLE=0`；普通开发 CI 不修改
  host、TUN、DNS、systemd、LPK 或 deploy 状态。
- Mihomo controller 只允许监听 `172.18.0.1:9090` 微服 bridge，不向 LAN/WAN 暴露。
- CI 不读取真实订阅、token、secret、节点配置或目标机状态；PR workflow 不获得 secret，
  不使用 privileged、volume、Docker socket，也不发布或部署。
- 真实产品检查不可被语法检查替代；Woodpecker 候选运行 frozen install、typecheck、
  unit、lint 与 build。
- `repo_harness_ready` 与 `platform_gate_ready` 分开报告；仓库文件不能证明 GitHub 平台门禁。

## Context Map

- 文档索引：[docs/index.md](docs/index.md)，治理契约：[.harness/repo-contract.json](.harness/repo-contract.json)
- 质量命令与 CI：[docs/quality.md](docs/quality.md)
- 脚本用途：[scripts/README.md](scripts/README.md)
- 网络变更约束：[docs/LAZYCAT_NETWORK_REPORT.md](docs/LAZYCAT_NETWORK_REPORT.md)
- 安全边界：[docs/SECURITY.md](docs/SECURITY.md)
- Active Plan 模板：[docs/exec-plans/template.md](docs/exec-plans/template.md)
- 当前 Active Plan：[docs/exec-plans/active/](docs/exec-plans/active/)
- 文档同步规则：[docs/doc-sync-rules.json](docs/doc-sync-rules.json)

只读取当前任务所需的领域文档；历史事故和复盘默认不作为当前运行 contract。

## Standard Quality

本地仓库级质量入口是 `bash scripts/test.sh`，覆盖 shell/Python 检查和微服 API 单元测试；dashboard 的 install、unit、typecheck、lint、build、文档检查和远端 smoke 命令见 [docs/quality.md](docs/quality.md)。

## 常用命令

```bash
# Local Runtime Contract v1 (stub; this repo has no long-running local daemon)
bash scripts/run_local.sh
bash scripts/stop_local.sh

# Local Runtime Contract v2 (stub)
bash scripts/doctor.sh

# 连接微服（示例）
ssh -i ~/.ssh/id_ed25519 root@rainierserver.heiyu.space

# 查看 mihomo 状态
systemctl status mihomo
journalctl -u mihomo -n 100 --no-pager

# 构建/部署 dashboard LPK
cd src/mihomo-dashboard-app
lzc-cli project build -f lzc-build.yml -o mihomo-dashboard.lpk
lzc-cli app install mihomo-dashboard.lpk
```
