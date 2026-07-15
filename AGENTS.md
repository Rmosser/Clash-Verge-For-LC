# Project Agents

## lzc-clash_mihome - Agent 操作手册

目标：在懒猫微服上运行 Mihomo (Clash Meta)，实现：

- 国内直连 / 国外代理（兜底 MATCH,PROXY）
- 启用 TUN 透明代理，但必须绕行懒猫内网穿透/控制面相关流量
- 提供可视化 Web 控制台（作为懒猫应用）用于手动切换节点/分组

## Skills

- **lazycat-dev**: 懒猫微服应用开发/部署流程、lzc-cli、manifest/build 配置等。 (file: skills/lazycat-dev/SKILL.md)

## 关键约束

- 不要破坏懒猫内网穿透/控制面：任何透明代理/TUN 变更前先看 `docs/LAZYCAT_NETWORK_REPORT.md`。
- 不要把 Mihomo 控制端口暴露到局域网：当前对外只通过懒猫登录后的应用路由访问。
- 非平凡变更必须从当前提供的 baseline / worktree HEAD 开新分支，并维护当前唯一 Active Plan；旧分支和旧 PR 只能作为参考，除非用户明确要求继续它们。
- 不要把本文件理解为绕过 PR、review、checks 或 branch protection 的授权；合并资格由证据门禁和平台门禁共同决定。
- 主 Agent 负责编排、范围定义和验收；subagent 只在授权范围内执行，不自行扩大 PR 阶段，不独立提交、push、merge 或关闭 heartbeat。

## 真相入口

- 文档索引：`docs/index.md`
- Harness checkpoint gate：`docs/governance/checkpoint-ci-gate.md`
- Active Plan 模板：`docs/exec-plans/template.md`
- 当前 Active Plan：`docs/exec-plans/active/`
- 文档同步规则：`docs/doc-sync-rules.json`
- 仓库治理契约：`.harness/repo-contract.json`

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

## Harness Engineering

本仓库采用 repo-native Agent CI/CD 治理模型；平台门禁和仓库证据分层报告，不互相冒充。

入口：

- [docs/index.md](docs/index.md)
- [docs/governance/checkpoint-ci-gate.md](docs/governance/checkpoint-ci-gate.md)
- [docs/exec-plans/template.md](docs/exec-plans/template.md)
- [docs/doc-sync-rules.json](docs/doc-sync-rules.json)
- [.harness/repo-contract.json](.harness/repo-contract.json)

任务分级：

- Task class `trivial` / Reasoning budget `low`：小、局部、可逆、低风险；不触及代码行为、CI、配置、发布、安全、文档索引或平台门禁；默认单 Agent。
- Task class `standard` / Reasoning budget `medium`：非平凡但范围清楚；默认主 Agent + subagent / work thread。
- Task class `critical` / Reasoning budget `high`：跨 PR 阶段、CI/verifier、平台门禁、review repair、merge cleanup、发布、安全或多仓库工作；主 Agent 保持编排和验收位，执行/验证拆给 subagent / work thread。

Agent-native 协作：

- Delegation route 必须写入 Active Plan；非平凡任务默认 `main+subagent` 或 `main+work-thread`。
- 只有用户明确禁止、工具不可用或任务不可合理拆分时才走 no-subagent fallback，并在 Active Plan 记录原因。
- 主 Agent 维护 Active Plan、定义 delegated scope / forbidden scope、复核 diff、语义和关键检查；subagent result 不是最终验收。
- subagent 只在授权范围内执行，不独立扩大 PR 阶段，不独立提交、push、merge 或关闭 heartbeat。
- 新任务默认从当前 provided baseline / worktree HEAD 开始；旧分支或旧 PR 只能作为参考，除非用户明确要求继续。
