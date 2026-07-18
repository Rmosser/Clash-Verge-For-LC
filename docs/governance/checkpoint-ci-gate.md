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

非平凡 PR 必须由默认分支上的 `.github/workflows/codex-review-gate.yml` 读取 GitHub 当前事实，并把 `codex-review` commit status 直接写到 live PR head。writer 必须绑定 open PR 的 base repository、`main`、base SHA、head repository 与 head SHA，在 pending 和最终写入前重验完整身份；默认分支更新后逐个 `repository_dispatch` 重算所有 open `main` PR。evaluator 必须以 Python isolated mode 启动，避免仓库同目录模块劫持标准库 import。写权限只位于受信任的 `pull_request_target`、`issue_comment` 和 `repository_dispatch` gate；`repository_dispatch` 只执行默认分支 workflow，heartbeat 用它逐 PR 唤醒 gate。相同 SHA/context 的最新 status 已与本轮最终 state 和 description 一致时，reconcile 必须保持幂等，不得再次写 pending/final，以免长期开启的 PR 耗尽 GitHub 单 SHA/context status 上限。`workflow_dispatch` 可以选择 PR branch，禁止用于 `statuses: write` gate，也不得为 manual smoke 保留例外。不得使用 PR-controlled review-event workflow 转发特权事件。`.github/workflows/codex-review-heartbeat.yml` 仅由默认分支 schedule 运行，自身不得写 status。整个 `.github/workflows/`、repo contract、doc-sync rules 以及 Harness checker 脚本都属于可信控制面；普通 PR 新增、修改、重命名或删除任一 workflow，或修改这些 checker/control 文件，必须 fail closed，防止同一 GitHub Actions App 身份下的同名 status writer 或自改 checker 进入 PR。每个 PR 的 writer 使用同一 concurrency group。

特权 review-trigger 入口及其完整本地 import / 动态 helper 闭包属于 immutable trusted controls，普通 PR 修改其中任一文件必须 fail closed。docs status publisher 的两个最终 live identity guard 都必须在身份漂移时调用受验证的 failure writer；bare nonzero exit 不能替代旧绿色状态的失效写入。

自动产生且直接绑定 live head 的 allowlisted Codex artifact 可以独立成立，不以手工 trigger 为前提。显式 `@codex review` 请求只有作者关联为 `OWNER`、`MEMBER` 或 `COLLABORATOR`，并附带唯一完整 40 位 `Head SHA` 时，才可作为 gate provenance 进入本轮可信排序；标准单行仍可请求 Codex，但不能绑定 reaction 或简化 issue artifact。只有这个可信请求精确绑定 live head，且 allowlisted Codex 的 `+1` reaction 不早于请求时，该 reaction 才可作为 clean evidence；不带完整标准 footer 的简化 clean issue artifact 仍必须晚于可信请求。GitHub reaction 与 trigger 可能只有秒级时间戳，因此精确绑定 trigger 的同秒 `+1` 可以成立；负向 current-head review、inline comment 或 finding 在同秒即视为 blocker，不能被后续 reaction 覆盖。通过条件还包括：结果与 live head 一致，且该 review round 没有 current-head inline finding、P0..P3 finding 或 finding-bearing review。review API artifact 的完整 `commit_id` 是权威 head binding；正文中的 `Reviewed commit` marker 可为 10..40 位十六进制前缀，若存在必须匹配 live head。当前 head 的 `COMMENTED` review 只有在正文是受识别的 Codex Review 汇总、带当前 head marker 的 review 正文或显式 clean 文本，并且没有 current-head inline finding、finding marker 或 stale marker 时才视为 clean；timeout、partial review 或未知状态文本必须 fail closed。issue-comment clean artifact 没有 API `commit_id` 可依赖，因此必须包含匹配 live head 的 10..40 位 marker；Codex 当前标准的短庆祝语是可选内容，标准 `About Codex in GitHub` details footer 仍须精确匹配，不得把任意尾文当作 clean。旧 head 的绿色结果、Active Plan 自报字段、默认分支事件 SHA 都不能代替当前 head 证据。evaluator 在已经绑定 live PR 身份后若遇到 API 或求值异常，publisher 必须尽力把同一 head 上的旧绿色 `codex-review` 改写为 failure；只有 status API 本身不可用时才允许以非零退出并报告无法写入。

被 dismiss 的 finding-bearing review 只要仍绑定 live head 且属于当前可信 trigger 轮次，就继续作为 blocker；dismissed clean review 和 obsolete-head review 不得污染当前轮次。

本模板显式采用 `supervision_model=repository_self_supervised`。GitHub Actions App `15368` 是仓库内所有 Actions workflow 的共享身份，因此 `status_source_isolation=shared_actions_app_not_isolated` 且 `source_isolated=false`。该身份被接受为同仓库自监督的 required-check 来源，但不得宣称独立 App、外部 custody 或 source-isolated review。

部署采用两阶段：先合并 workflow/evaluator，让它在默认分支受保护控制面中运行；再在该仓库的测试 PR 上用 PR 事件、标准 review comment 或默认分支 `repository_dispatch` 执行 live current-head emitter smoke。smoke 必须逐仓库证明 `codex-review` 写到准确 PR head、creator App id 为 `15368`、新 head 不继承旧绿结果、API/证据失败保持 pending 或 failure、普通 PR 修改任一 workflow/contract/doc-sync/checker 会 fail closed，并确认没有 Actions job/check 或其他 status writer 使用同一 `codex-review` context，避免 context collision。只有该仓库通过后，才可把 `context=codex-review` + `app_id=15368` 加入该仓库的 required checks；未通过时保持 advisory。该 required gate 仍是仓库自监督，不得报告为独立监督。Actions job 名不得与 commit-status context 同名。

`loop/checkpoints` 也必须由默认分支/PR base 上的可信 workflow 和 verifier 读取 PR checkout 数据，不能执行 PR-controlled checker。状态写入必须与 PR 数据 checkout/验证分离：pending 和 result publisher job 可写 `statuses` 但不得 checkout，validation job 只读且不得写 status。pending 未成功时 validation 必须跳过，publisher 同时消费 pending/validation 结果并 fail closed；pending/final 写入前后重验 live PR 身份，同一 head/base/context 的已知 pending 或最终 state/description 必须零重复写入。三个 checkout 都使用支持 fork 安全 opt-in 的 `actions/checkout@v7`；两个 validation checkout 必须关闭 credential persistence，且只有不执行代码的 fork target data checkout 可以并必须设置一次 `allow-unsafe-pr-checkout: true`，可信 base 与默认分支 checkout 禁止该 opt-in。target 只能在 data-only validation job 作为数据交给可信 checker，禁止执行 target 中的 checker、action 或产品验证；产品验证必须放在独立的只读 `pull_request` workflow。任何其他会 checkout 并执行 PR-controlled 代码的 `pull_request` workflow 也必须显式声明只读顶层权限，执行该代码的 job 不得拥有 `statuses: write`；共享 GitHub Actions App 身份下不能依赖仓库默认 token 权限。验证对象必须是由 live base SHA 与 live head SHA 物化出的 merge tree，而不是过时 raw head；base 更新后的 fanout 即使默认分支自检失败也必须运行，使旧绿状态被重新裁决。可信 checker 必须对整个 docs workflow 做 canonical hash，并以 trusted manifest 下界约束 required paths、additional checks、entrypoint links、link exclusions 和 diff classes；读取治理文档、独立读取 Active Plan 或遍历 Markdown 前必须拒绝 symlink，根目录 README 也属于可信链接检查范围。Scope verifier 仍须显式使用真实 PR base/head；`--base HEAD --head HEAD` 只允许未提交或 unborn 的本地工作树检查，不能成为 committed PR 的 Validation Claim。

Scope 对账约定：`## Scope` 段中反引号包裹的路径是机器可读的允许清单；含 forbidden / excluded / do not / 禁止 / 不允许 / 不得 等否定标记的行，其反引号路径是机器可读的禁止清单，优先于允许清单和 harness 记账路径。机器只识别 verifier 顶部 `FORBIDDEN_LINE_RE` 列出的标记词——声明禁区的正规方式是把路径写进 `## Non-Goals`（或 `## 非目标`）：该段所有反引号路径无论措辞如何都计入禁止清单。无反引号的自由文本仅供人读。同一计划出现多个 `## Scope` 标题直接判失败。

## Active Plan Archive Transition

当非平凡 baseline PR 必须依赖 `active/` 中的计划证明 Scope 时，归档采用强制两阶段：先合并已经完成 current-head review 的 baseline，再立即用独立 cleanup PR 把该计划移入 `completed/`。计划模板必须含唯一 `Status: active`；cleanup 归档时原子改为 `Status: completed`、`Active Plan archived: completed` 与 `Transition invariant: satisfied/closed`。过渡窗口不是 rollout 完成态；现存 Active Plan 的 Scope gate 必须让无关产品 PR fail closed，并且 required-check 激活、本地分支/worktree 删除和完成声明都必须等待 cleanup PR 合并且 `active/` 槽清空。

归档目标还必须精确写入 `Main synced: completed`、`Local branch deleted: deferred-to-rollout-closure` 与 `Heartbeat closed: deferred-to-rollout-closure`。这两个 deferred 值不是完成声明；rollout closure 必须在 cleanup PR 合并后另行证明分支/worktree 已删除且 heartbeat 已关闭。`docs/exec-plans/active/.gitkeep` 是零字节、非可执行的普通文件哨兵，必须在 baseline 中建立并在 cleanup 中保持不变，使空闲态的 fresh checkout 仍保留 `active/`；archive-only Scope 例外不得把该哨兵当作可变路径。archive-only Scope 例外只允许 Active Plan 的六个 lifecycle 字段按该契约变化、把唯一 active 文件原子移入 `completed/`，并把唯一索引链接从 active 路径切换到 completed 路径。

新增 completed plan 必须来自 trusted/base 中唯一同名 Active Plan，目标 active 文件同时被移除，并且只能发生 canonical lifecycle 字段、原子 active-to-completed 移动和唯一索引链接切换；目标文件自身的 completed 声明不能替代 provenance。

## Batch Validation Evidence

多仓 rollout 的 validation 报告必须绑定固定 inventory、canonical tree、每个仓库的 current HEAD、changed paths、完整 dirty-tree 内容摘要和实际测试计数，再由固定 SSH signing identity 签署报告原文。提交器必须在 staging 前验证签名、报告 freshness、全部 30 个仓库身份与内容摘要；publisher 继续使用同一固定公钥和 principal 验证 author/committer 与签名，不得从可变 global config 或提交本身选择信任身份。Active Plan 只记录稳定验证契约，不嵌入具体 attestation commit、生成时间或报告摘要，以免被签内容自引用而无法收敛。

normalizer 和 Active Plan recorder 必须先完成整批预检，再通过同目录临时文件、文件与目录 `fsync`、原子替换写入，并用 `0600` crash journal 在异常时回滚、在下次运行前恢复；并发内容漂移时不得覆盖用户改动。提交和归档的 dry-run / 整批 preflight 使用临时 `GIT_INDEX_FILE`；所有仓库预检、签名身份检查和独立 signer probe 完成前，不得修改任何目标仓库的真实 index 或创建提交。签名提交失败且 HEAD 未前进时恢复原始 index；HEAD 已前进时保留可验证、可恢复的提交并 fail closed。archive journal 的 worktree phase 只恢复 active/completed/index 三路径且内容精确匹配 phase-1 哈希的中断状态，任何额外或陌生内容都不得被覆盖。
