# Checkpoint CI Gate

本文件定义本仓库的 Agent CI/CD 证据门禁。它不控制 Agent 是否能写工作区，也不替代 GitHub branch protection；它定义非平凡 PR 在进入 merge 前必须留下哪些可检查证据。

```text
Agent 在授权上下文内写代码。
CI 检查证据。
Branch protection 卡住合并。
```

## 执行权限边界

- 不治理：Agent 对 worktree 的本地写入权限。
- 不治理：PR 分支 push 权限。
- 不治理：云端 connector、账号或 secret 权限。
- 治理：merge eligibility、evidence completeness、claim / fact consistency、PR review loop、post-merge cleanup。

## 四个 Claim

```text
Context Claim     -> 哪些真相源和规则适用于本次任务？
Scope Claim       -> 哪些修改被允许、被禁止、属于非目标？
Change Claim      -> Agent 声称改了哪些文件 / 变更类型？
Validation Claim  -> 应该用哪些验证证明本次变更正确？
```

## 四类对账

```text
Context Claim     vs diff class / doc rules
Scope Claim       vs policy / Active Plan / forbidden paths
Change Claim      vs git diff
Validation Claim  vs validation registry / CI result
```

执行口诀：Context 对真相源，Scope 对边界，Change 对 diff，Validation 对证据。

## PR1 基线状态

- repo_harness_ready：partial。本 PR 铺设入口、Active Plan、doc-sync 规则和 repo contract；后续 PR 才接入 verifier / CI。
- platform_gate_ready：false。required checks、branch protection 和 bypass 状态尚未在 GitHub 平台侧验证。
- planned_required_check：`loop/checkpoints`，仅为后续平台门禁目标；本 PR 不新增 workflow 或 required check。

## 非平凡 PR 最低证据

- 当前 Active Plan 路径。
- Context / Scope / Change / Validation 四个 claim。
- 实际 diff 与 Change Claim 对账结果。
- 本仓库能运行的检查命令及结果。
- Codex Review、heartbeat、repair ledger 和 post-merge cleanup 状态。
