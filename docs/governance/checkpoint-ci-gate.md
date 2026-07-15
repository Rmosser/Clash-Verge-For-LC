# Checkpoint CI Gate

```text
Agent 在授权上下文内写代码。
CI 检查证据。
Branch protection 卡住合并。
```

必须裁决：

```text
证据完整性
claim / fact 一致性
validation 证据
merge eligibility
```

必须另行验收：

```text
worktree 写入权限
PR branch push 权限
cloud connector 权限
```

## 四个 Claim

```text
Context Claim     -> 适用真相源、规则、diff class。
Scope Claim       -> 允许范围、禁止范围、非目标。
Change Claim      -> Agent 声称的文件、变更类型、文档影响。
Validation Claim  -> 验证命令、结果、证据。
```

## 四类对账

```text
Context Claim     vs diff class / doc rules
Scope Claim       vs policy / Active Plan / forbidden paths
Change Claim      vs git diff
Validation Claim  vs validation registry / CI result
```

执行规则：Context 对真相源，Scope 对边界，Change 对 diff，Validation 对证据。

## 对账的机器化边界

```text
机器执行（required check）
  docs 结构、断链、active plan 基数与证据章节 -> scripts/check_docs.py
  Scope Claim vs git diff（diff 必须落在 Scope 允许清单内） -> scripts/check_loop_checkpoints.py

人工执行（主 Agent）
  Context Claim 对真相源的语义对账
  Change Claim 叙述与 git diff 的逐项对账
  Validation Claim 覆盖充分性判断
  subagent result 的独立复核
```

机器检查只证明 diff 没有越出 Scope 上界，不证明 Change Claim 叙述完整或准确。报告门禁能力时，不得把 Scope 上界检查写成 Change Claim 对账。

## Current-Head Codex Review

非平凡 PR 必须由默认分支上的 `.github/workflows/codex-review-gate.yml` 读取 GitHub 当前事实，并把 `codex-review` commit status 直接写到 live PR head。evaluator 必须以 Python isolated mode 启动，避免仓库同目录模块劫持标准库 import。写权限只位于受信任的 `pull_request_target`、`issue_comment` 和 `workflow_dispatch` gate；不得使用 PR-controlled review-event workflow 转发特权事件。`.github/workflows/codex-review-heartbeat.yml` 只在默认分支 schedule 上逐 PR dispatch 可信 gate，自身不得写 status。整个 `.github/workflows/`、repo contract、doc-sync rules 以及 Harness checker 脚本都属于可信控制面；普通 PR 新增、修改、重命名或删除任一 workflow，或修改这些 checker/control 文件，必须 fail closed，防止同一 GitHub Actions App 身份下的同名 status writer 或自改 checker 进入 PR。issue-comment clean artifact 必须绑定完整 40 位 commit，正文必须严格匹配 clean 语法。

通过条件同时包括：当前 head 的显式 `@codex review` 请求、请求后的 allowlisted Codex 结果、结果中的 reviewed commit 与 live head 一致、且该 review round 没有 current-head inline finding 或 finding-bearing review。旧 head 的绿色结果、`COMMENTED` 状态本身、Active Plan 自报字段、默认分支事件 SHA 都不能代替当前 head 证据。

部署采用两阶段：先合并 workflow/evaluator，并通过 manual dispatch / proof manifest 证明 advisory `codex-review` 能写到指定 PR head。GitHub Actions App `15368` 是仓库内所有 Actions workflow 的共享身份，target URL 也由 writer 自报，二者不能建立特定 workflow 与 status 的因果关系；因此在独立 GitHub App / 外部 OIDC relay 或平台 required-workflow 身份就绪前，不得把它加入 required checks。Actions job 名不得与 commit-status context 同名。

Scope 对账约定：`## Scope` 段中反引号包裹的路径是机器可读的允许清单；含 forbidden / excluded / do not / 禁止 / 不允许 / 不得 等否定标记的行，其反引号路径是机器可读的禁止清单，优先于允许清单和 harness 记账路径。机器只识别 verifier 顶部 `FORBIDDEN_LINE_RE` 列出的标记词——声明禁区的正规方式是把路径写进 `## Non-Goals`（或 `## 非目标`）：该段所有反引号路径无论措辞如何都计入禁止清单。无反引号的自由文本仅供人读。同一计划出现多个 `## Scope` 标题直接判失败。
