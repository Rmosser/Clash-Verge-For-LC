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
  当前 PR head 的 Codex Review 请求、结果和 finding -> scripts/check_codex_review.py

人工执行（主 Agent）
  Context Claim 对真相源的语义对账
  Change Claim 叙述与 git diff 的逐项对账
  Validation Claim 覆盖充分性判断
  subagent result 的独立复核
```

机器检查只证明 diff 没有越出 Scope 上界，不证明 Change Claim 叙述完整或准确。报告门禁能力时，不得把 Scope 上界检查写成 Change Claim 对账。

## Current-Head Codex Review

非平凡 PR 必须由默认分支上的 `.github/workflows/codex-review-gate.yml` 读取 GitHub 当前事实，并把 `codex-review` commit status 直接写到 live PR head。writer 必须绑定 open PR 的 base repository、`main`、base SHA、head repository 与 head SHA，在 pending 和最终写入前重验完整身份；默认分支更新后逐个 `repository_dispatch` 重算所有 open `main` PR。evaluator 必须以 Python isolated mode 启动，避免仓库同目录模块劫持标准库 import。写权限只位于受信任的 `pull_request_target`、`issue_comment` 和 `repository_dispatch` gate；`repository_dispatch` 只执行默认分支 workflow，heartbeat 用它逐 PR 唤醒 gate。`workflow_dispatch` 可以选择 PR branch，禁止用于 `statuses: write` gate，也不得为 manual smoke 保留例外。不得使用 PR-controlled review-event workflow 转发特权事件。`.github/workflows/codex-review-heartbeat.yml` 仅由默认分支 schedule 运行，自身不得写 status。整个 `.github/workflows/`、repo contract、doc-sync rules 以及 Harness checker 脚本都属于可信控制面；普通 PR 新增、修改、重命名或删除任一 workflow，或修改这些 checker/control 文件，必须 fail closed，防止同一 GitHub Actions App 身份下的同名 status writer 或自改 checker 进入 PR。每个 PR 的 writer 使用同一 concurrency group。

标准单行 `@codex review` 是合法请求，不要求 trigger comment 自带 SHA。通过条件同时包括：请求后的 allowlisted Codex 结果、结果与 live head 一致、且该 review round 没有 current-head inline finding、P0..P3 finding 或 finding-bearing review。review API artifact 的完整 `commit_id` 是权威 head binding；正文中的 `Reviewed commit` marker 可为 10..40 位十六进制前缀，若存在必须匹配 live head。当前 head 的 `COMMENTED` review 只有在正文是受识别的 Codex Review 汇总、带当前 head marker 的 review 正文或显式 clean 文本，并且没有 current-head inline finding、finding marker 或 stale marker 时才视为 clean；timeout、partial review 或未知状态文本必须 fail closed。issue-comment clean artifact 没有 API `commit_id` 可依赖，因此必须包含匹配 live head 的 10..40 位 marker。旧 head 的绿色结果、Active Plan 自报字段、默认分支事件 SHA 都不能代替当前 head 证据。

本模板显式采用 `supervision_model=repository_self_supervised`。GitHub Actions App `15368` 是仓库内所有 Actions workflow 的共享身份，因此 `status_source_isolation=shared_actions_app_not_isolated` 且 `source_isolated=false`。该身份被接受为同仓库自监督的 required-check 来源，但不得宣称独立 App、外部 custody 或 source-isolated review。

部署采用两阶段：先合并 workflow/evaluator，让它在默认分支受保护控制面中运行；再在该仓库的测试 PR 上用 PR 事件、标准 review comment 或默认分支 `repository_dispatch` 执行 live current-head emitter smoke。smoke 必须逐仓库证明 `codex-review` 写到准确 PR head、creator App id 为 `15368`、新 head 不继承旧绿结果、API/证据失败保持 pending 或 failure、普通 PR 修改任一 workflow/contract/doc-sync/checker 会 fail closed，并确认没有 Actions job/check 或其他 status writer 使用同一 `codex-review` context，避免 context collision。只有该仓库通过后，才可把 `context=codex-review` + `app_id=15368` 加入该仓库的 required checks；未通过时保持 advisory。该 required gate 仍是仓库自监督，不得报告为独立监督。Actions job 名不得与 commit-status context 同名。

`loop/checkpoints` 也必须由默认分支/PR base 上的可信 workflow 和 verifier 读取 PR checkout 数据，不能执行 PR-controlled checker。状态写入必须与 PR 数据 checkout/验证分离：pending 和 result publisher job 可写 `statuses` 但不得 checkout，validation job 只读且不得写 status；两个 checkout 都必须关闭 credential persistence。为兼容 GitHub 对 `pull_request_target` fork HEAD checkout 的保护，target checkout 只能在 validation job 明确设置 `allow-unsafe-pr-checkout: true`，并且该 job 只能把 target 当数据交给可信 checker，禁止执行 target 中的代码、脚本、action 或产品验证；产品验证必须放在独立的只读 `pull_request` workflow。Scope verifier 必须显式使用真实 PR base/head；`--base HEAD --head HEAD` 只允许未提交或 unborn 的本地工作树检查，不能成为 committed PR 的 Validation Claim。

Scope 对账约定：`## Scope` 段中反引号包裹的路径是机器可读的允许清单；含 forbidden / excluded / do not / 禁止 / 不允许 / 不得 等否定标记的行，其反引号路径是机器可读的禁止清单，优先于允许清单和 harness 记账路径。机器只识别 verifier 顶部 `FORBIDDEN_LINE_RE` 列出的标记词——声明禁区的正规方式是把路径写进 `## Non-Goals`（或 `## 非目标`）：该段所有反引号路径无论措辞如何都计入禁止清单。无反引号的自由文本仅供人读。同一计划出现多个 `## Scope` 标题直接判失败。
