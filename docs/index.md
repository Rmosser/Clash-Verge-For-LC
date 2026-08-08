# 文档索引

本仓库是懒猫微服上的 Mihomo / Clash Verge 管理服务。当前文档入口只负责指向权威真相面，不替代具体运行、部署或治理文档。

## 产品与运行

- [README.md](../README.md)：项目定位、快速开始和用户入口。
- [docs/USER_GUIDE.md](USER_GUIDE.md)：用户指南、订阅导入、Docker 代理和常见问题。
- [docs/LAZYCAT_NETWORK_REPORT.md](LAZYCAT_NETWORK_REPORT.md)：TUN、控制面绕行、容器出网和网络风险。
- [docs/SECURITY.md](SECURITY.md)：controller 隔离、secret 管理和安全边界。

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

当前候选状态为 `canary_validated_review_clean_sync_pending`：Woodpecker `/repos/22` 已激活；pnpm、
时区与任务内存问题已按真实测试和完整 build 修复，同一 live context 的 success、故意失败
与 repair success 已完成；`552859f` Review 找到的 extensionless Bash 覆盖缺口已修复，
`2541549` 的 pipeline 15 与独立 Review 已 `CLEAN / 0`。Review 事实同步 head 的 pipeline/增量
Review、合并后 push 和 required gate proof 仍待完成。
`repo_harness_ready=false`、`platform_gate_ready=false`、
`actions_replacement_ready=false`。
