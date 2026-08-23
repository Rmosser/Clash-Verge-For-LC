# 文档索引

本仓库是懒猫微服上的 Mihomo / Clash Verge 管理服务。这里按问题路由到当前有效文档；历史复盘不替代运行 contract。

## Agent 与质量

- [../AGENTS.md](../AGENTS.md)：最小入口规则和安全边界。
- [quality.md](quality.md)：本地/CI 的 test、lint、typecheck、build、文档检查和 smoke 命令。
- [../scripts/README.md](../scripts/README.md)：部署、诊断和质量脚本的用途。
- [doc-sync-rules.json](doc-sync-rules.json)：文档入口完整性检查所需的轻量清单。

## 产品与运行

- [../README.md](../README.md)：项目定位、快速开始和用户入口。
- [USER_GUIDE.md](USER_GUIDE.md)：用户指南、订阅导入、Docker 代理和常见问题。
- [CURRENT_RUNTIME.md](CURRENT_RUNTIME.md)：当前运行 contract。
- [LAZYCAT_NETWORK_REPORT.md](LAZYCAT_NETWORK_REPORT.md)：TUN、控制面绕行、容器出网和网络风险。
- [SECURITY.md](SECURITY.md)：controller 隔离、secret 管理和安全边界。
- [HOST_NATIVE_RUNBOOK.md](HOST_NATIVE_RUNBOOK.md)：宿主机部署、恢复和重启验收。
- [PACKAGING.md](PACKAGING.md)：LPK 构建与发布边界。
- [CLASH_VERGE_WEB_SMOKE_CHECKLIST.md](CLASH_VERGE_WEB_SMOKE_CHECKLIST.md)：Web 回归清单。

## 治理与交付

- [AGENTS.md](../AGENTS.md)：Agent 入口层和最小工作规则。
- [docs/governance/checkpoint-ci-gate.md](governance/checkpoint-ci-gate.md)：Agent CI/CD 证据门禁。
- [docs/exec-plans/template.md](exec-plans/template.md)：非平凡任务 Active Plan 模板。
- [docs/exec-plans/active/](exec-plans/active/)：当前唯一 Active Plan 所在目录。
- [docs/exec-plans/completed/](exec-plans/completed/)：已完成或被取代计划归档目录。
- [docs/doc-sync-rules.json](doc-sync-rules.json)：文档同步和入口链接规则。
- [.harness/repo-contract.json](../.harness/repo-contract.json)：仓库治理契约，供后续 verifier / CI 读取。
- [当前 Active Plan](exec-plans/active/20260808-woodpecker-development-harness.md)：
  Clash-Verge-For-LC 的 Woodpecker 开发 CI 候选与验证证据。
- [Woodpecker workflow](../.woodpecker/woodpecker-harness.yaml)：无 secret 的 PR/push 开发检查。

## 边界

仓库文件负责暴露真相、计划、证据和检查要求。GitHub required checks、branch protection 和管理员 bypass 状态必须在平台侧单独验证，不能仅由仓库文档声明为已生效。

当前状态为 `merged_push_validated_required_gate_proven`：Woodpecker `/repos/22` 已激活；pnpm、
时区与任务内存问题已按真实测试和完整 build 修复，同一 live context 的 success、故意失败
与 repair success 已完成；`552859f` Review 找到的 extensionless Bash 覆盖缺口已修复，
`6c3ce2f` 在 pipeline 17 后独立 Review `CLEAN / 0`，PR #7 已 expected-head merge；main
`02ce1f3` pipeline 18 push success，strict required context 经 PR #8 pipeline 19 failure +
live `BLOCKED` 证明生效。
`repo_harness_ready=true`、`platform_machine_gate_ready=true`、`platform_gate_ready=false`、
`actions_replacement_ready=false`。

## 历史与背景

- [PRD.md](PRD.md)：历史设计文档，不是当前手册。
- [planning/](planning/)：事故分析和复盘。
- [exec-plans/completed/](exec-plans/completed/)：旧任务记录，仅供追溯。

平台侧的 required checks、branch protection、review 和运行态部署状态必须分别核实；本仓库文档不会自报这些外部状态。
