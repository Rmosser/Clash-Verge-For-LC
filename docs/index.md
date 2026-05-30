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

## 边界

仓库文件负责暴露真相、计划、证据和检查要求。GitHub required checks、branch protection 和管理员 bypass 状态必须在平台侧单独验证，不能仅由仓库文档声明为已生效。
