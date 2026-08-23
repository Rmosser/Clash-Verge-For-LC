# Development Change Evidence

本仓库使用 repo-native CI 提供候选变更的可执行反馈。仓库规则只描述稳定边界；commit、pipeline、Review 和平台门禁状态必须实时读取，不写成长期“当前状态”。

## 候选证据

非平凡变更在合并前应能回答：

- 适用了哪些产品和安全约束；
- 实际 diff 改变了什么；
- 哪些 test、lint、typecheck、build 或 smoke 覆盖了变化；
- 哪些结果来自本地、CI、平台或运行态，哪些尚未验证。

不要求为每个任务创建固定格式的 Claim、Active Plan、Repair Ledger 或归档记录。复杂任务可以使用 `docs/plans/` 中的可选模板。

## CI 边界

- Woodpecker 对面向 `main` 的 pull request 和 `main` push 运行仓库检查。
- PR workflow 不读取真实订阅、token、secret、节点配置或目标机状态。
- CI 不使用 privileged、volume 或 Docker socket，也不发布、部署或修改 host runtime。
- 真实产品检查不可被语法检查替代；完整命令以 `docs/quality.md` 和 workflow 为准。

## 平台与运行态

本地测试、CI、GitHub merge eligibility 和远端运行态是不同证据层。仓库文件不能证明 required checks、branch protection、管理员 bypass、当前 Review 或部署健康；报告这些状态时必须绑定实时读取的 commit 和平台结果。
