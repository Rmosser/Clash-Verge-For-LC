# Development Change Evidence

本仓库使用 repo-native CI 提供候选变更的可执行反馈。仓库规则只描述稳定边界；commit、pipeline、Review 和平台门禁状态必须实时读取，不写成长期“当前状态”。

## 候选证据

非平凡变更在合并前应能回答：

- 适用了哪些产品和安全约束；
- 实际 diff 改变了什么；
- 哪些 test、lint、typecheck、build 或 smoke 覆盖了变化；
- 哪些结果来自本地、CI、平台或运行态，哪些尚未验证。

不要求为每个任务创建固定格式的 Claim、Active Plan、Repair Ledger 或归档记录。复杂任务可以使用 `docs/plans/` 中的可选模板。

## 文档、代码与意图

- 用户当前接受的要求是本次意图输入，不把分支中间方案写成最终目标。
- 代码、测试、配置、UI 和导出物共同定义候选实际行为；Current 文档解释受支持的行为、边界和操作方式。
- 行为或默认值变化时，在同一候选中更新能裁决它的测试与受影响的 Current 文档。只改文档不能证明行为已经改变，只改代码也不能让使用者知道 contract 已变。
- 目标机、GitHub 门禁和 Review 是外部状态，必须实时读取；不得把一次观察固化成长期“当前状态”。
- 历史材料只解释当时发生过什么。若与当前代码或 Current 文档冲突，先修正 canonical state，不从历史推导现行操作。

## Review 收敛与发布

每轮 Review 绑定同一个候选快照：干净工作树使用 commit SHA；有未提交内容时明确写成 `HEAD + working tree`。检查只证明它实际覆盖的快照，远程 Review 不覆盖未 push 的本地改动。

继续修改前要有一个具体、可信、与本次 diff 相关且足以阻断交付的问题。目标满足、关键行为已验证、项目要求的检查通过且没有可信 blocker 时停止制造新 diff。

交付前按 base 到候选的净变化复读 canonical 内容：当前接口和不变量留在代码、测试和 Current 文档；本次调查、修复轮次与验证过程留在 commit、PR 或任务记录。发布整理若改变仓库内容，重新绑定候选并重跑受影响检查。

## CI 边界

- Woodpecker 对面向 `main` 的 pull request 和 `main` push 运行仓库检查。
- PR workflow 不读取真实订阅、token、secret、节点配置或目标机状态。
- CI 不使用 privileged、volume 或 Docker socket，也不发布、部署或修改 host runtime。
- 真实产品检查不可被语法检查替代；完整命令以 `docs/quality.md` 和 workflow 为准。

## 平台与运行态

本地测试、CI、GitHub merge eligibility 和远端运行态是不同证据层。仓库文件不能证明 required checks、branch protection、管理员 bypass、当前 Review 或部署健康；报告这些状态时必须绑定实时读取的 commit 和平台结果。
