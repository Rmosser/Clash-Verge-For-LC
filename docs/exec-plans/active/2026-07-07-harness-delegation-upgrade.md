# Harness Delegation Upgrade

- Status: active

- 状态：active
- 更新时间：2026-07-15

## 任务分类

- Task class: critical
- Reasoning budget: high
- Delegation route: main+parallel-subagents
- 判定理由：多仓库 Harness baseline / checker / delegation schema 改造，需要主 Agent 保留治理和最终验收，子 agent 分批执行或复核。

## 已读上下文

- AGENTS.md
- docs/index.md
- docs/governance/checkpoint-ci-gate.md
- docs/exec-plans/template.md
- docs/doc-sync-rules.json

## Goal

- 将本仓库升级到新版 Harness delegation schema，并提供 repo-native docs/checkpoint gate 的本地可验证入口。

## Non-Goals

- 不声明 GitHub branch protection / ruleset 已经启用。
- 不修改产品行为、发布配置、线上状态或密钥。
- 不把预先存在的脏工作树内容声明为本次 Harness 变更的语义成果。

## Scope

<!-- 机器对账约定：反引号包裹的路径是允许清单（目录以 / 结尾，支持 fnmatch 通配且 * 跨目录）；含 forbidden / 禁止 / 不允许 等否定标记的行，其反引号路径是禁止清单并优先生效；## Non-Goals 中的反引号路径同样计入禁止清单。无反引号的文字仅供人读。 -->

- Harness upgrade file: `AGENTS.md`
- Harness upgrade file: `docs/index.md`
- Harness upgrade file: `docs/governance/checkpoint-ci-gate.md`
- Harness upgrade file: `docs/exec-plans/template.md`
- Harness upgrade file: `docs/exec-plans/active/`
- Harness upgrade file: `docs/exec-plans/completed/`
- Harness upgrade file: `docs/doc-sync-rules.json`
- Harness upgrade file: `.harness/repo-contract.json`
- Harness upgrade file: `.github/workflows/docs-ci.yml`
- Harness upgrade file: `.github/workflows/codex-review-gate.yml`
- Harness upgrade file: `.github/workflows/codex-review-heartbeat.yml`
- Harness upgrade file: `.github/pull_request_template.md`
- Harness upgrade file: `scripts/check_docs.py`
- Harness upgrade file: `scripts/check_codex_review.py`
- Harness upgrade file: `scripts/check_loop_checkpoints.py`
- Harness upgrade file: `docs/exec-plans/active/.gitkeep`
- Harness upgrade file: `docs/exec-plans/active/2026-07-07-harness-delegation-upgrade.md`
- Harness upgrade file: `docs/exec-plans/active/20260530-runtime-hardening-recovery.md`
- Harness upgrade file: `docs/exec-plans/completed/.gitkeep`
- Harness upgrade file: `docs/exec-plans/completed/archived-before-harness-upgrade-20260530-runtime-hardening-recovery.md`
- Unprivileged review-event signal: `.github/workflows/codex-review-signal.yml`

## Acceptance

- docs/checkpoint gate 文件存在且入口可发现。
- Active Plan 模板包含 task class、reasoning budget、delegation route 和 Agent Delegation 字段。
- `scripts/check_docs.py --all` 能检查 required paths、entrypoint links、active plan 基数和证据字段。
- `scripts/check_loop_checkpoints.py` 能对 Scope Claim 与 git diff 做上界校验。
- 非平凡 PR 的 review gate 只接受绑定 live PR head 的 Codex 证据，并由受信任默认分支 emitter 写入 commit status。

## 文档影响

- 更新 Harness 治理入口、计划模板、doc sync rules、repo contract、PR template 和 docs CI workflow。

## Verification

- `python3 -I -B scripts/check_docs.py --all`
- `python3 -I -B scripts/check_loop_checkpoints.py --base 0d3610f1353a9a0242a9c54c7fd037f2e8da37d5 --head HEAD`
- `python3 -m json.tool docs/doc-sync-rules.json`
- `python3 -m json.tool .harness/repo-contract.json`
- `python3 -I -B scripts/check_codex_review.py --fixture <fixture>`（通用 gate 仓库）

## Checkpoint 证据

- Context Claim：本次只处理 repo-native Harness 入口、治理文档、模板和检查脚本；平台门禁另行验证。
- Scope Claim：允许清单见 `## Scope`；产品行为和线上状态不属于本次语义变更。
- Change Claim: actual `git diff origin/main` plus current worktree paths include `.github/pull_request_template.md`, `.github/workflows/codex-review-gate.yml`, `.github/workflows/codex-review-heartbeat.yml`, `.github/workflows/docs-ci.yml`, `.harness/repo-contract.json`, `AGENTS.md`, `docs/doc-sync-rules.json`, `docs/exec-plans/active/.gitkeep`, `docs/exec-plans/active/2026-07-07-harness-delegation-upgrade.md`, `docs/exec-plans/completed/.gitkeep`, `docs/exec-plans/completed/archived-before-harness-upgrade-20260530-runtime-hardening-recovery.md`, `docs/exec-plans/template.md`, `docs/governance/checkpoint-ci-gate.md`, `docs/index.md`, `scripts/check_codex_review.py`, `scripts/check_docs.py`, `scripts/check_loop_checkpoints.py`; the current repair binds the complete repository-specific docs workflow by a trusted SHA-256, validates the synthetic base/head merge tree, and enforces trusted lower bounds for required paths, checks, entrypoint links, exclusion globs, diff classes, and target invariants; Markdown and governance traversal rejects symlinks while including root README, delegated scopes cannot escape through absolute or parent-relative paths, failed default-branch validation still reconciles every open PR, standard Codex footers are accepted without accepting arbitrary tails, and unchanged status evidence causes zero writes after a second live identity check; governance text is reached through descriptor-rooted no-follow parent traversal, opened non-blocking, bounded to 1 MiB, and decoded only after regular-file verification; automatic current-head Codex artifacts, trusted head-bound triggers, exact control-file pins, closed diff classes, conservative docs classification, fail-closed shell fanout, and mandatory two-stage Active Plan archival are enforced.
- Validation Claim: the complete current-round validation contract bound to canonical tree SHA-256 `777848d564c8e2445fcf5ad2fb5784c49c841e44bfe6518a71cbf69cf1259124` passed repository validators 29/29, canonical skill tests 224/224, rollout orchestration tests 436/436, and normalizer dry-run checks 29/29; the commit gate separately verifies the fixed SSH identity's signed attestation over the exact final report and dirty-tree digests before staging; the repository-specific dirty-tree digest is bound only by the signed external validation report and delivery manifest, avoiding Active Plan self-reference.

## Agent Delegation

- Delegation decision: multi-repo Harness task, delegate batch review/repair to subagents while main Agent owns final acceptance.
- Used subagent: yes
- No-subagent fallback reason: n/a
- Delegated scope: `Rmosser/Clash-Verge-For-LC` only; Harness files listed in `## Scope`.
- Forbidden scope: product behavior, secrets, deployment/runtime state, platform settings, independent push/merge/heartbeat closure.
- Subagent result: complete - independent review-evaluator, trusted-policy, evidence-provenance, workflow-status, product-check, archive-preflight, and publisher-idempotency reviews were reconciled; fresh signed-head Codex review remains pending
- Main agent review: accepted after independent diff, trust-boundary, and validation review
- Rework requested: completed - automatic current-head review evidence, trusted full-head triggers and same-second blockers, old-green invalidation, exact control pins, closed policy classes, conservative docs classification, symlink-safe preview and Scope reads, signed dirty-tree validation evidence without Active Plan self-reference, idempotent checkpoint status, synthetic merge-tree validation, recoverable product-check reruns, completed two-stage archive transition, repository-specific repairs, all-batch temporary-index preflight, signer preflight, and crash-safe publisher/cleanup findings are addressed
- Final accepted diff: accepted by the main Agent for signed commit and fresh current-head Codex review

## Codex Review

- Required: for non-trivial PRs before merge
- Requested by: Rmosser via `@codex review`
- Requested at: 2026-07-15T10:02:11Z
- Completed review head: `b5daa5292329b0490d21faeebac906d34ca6fff8`
- Current review target pointer: PR #5 / https://github.com/Rmosser/Clash-Verge-For-LC/pull/5#discussion_r3608402874
- Heartbeat required: yes when waiting on review
- Heartbeat interval: project policy
- Heartbeat stop condition: review complete and repair ledger closed
- Review result: P1 publisher identity-drift finding on the recorded head; repaired worktree awaits a new commit and fresh current-head review.

## Review Repair Policy

- Start tier: low
- Current tier: medium
- Max attempts per tier: 2
- Attempts at current tier: 1
- Total repair attempts: 1
- Escalation path: low -> medium -> high -> xhigh -> human
- Stop condition: review findings closed or human intervention required
- Last repeated finding: none
- Human intervention required: no

## Repair Ledger

| Attempt | Tier | Finding class | Commit | Checks | Result | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| main-1 | high | main-agent acceptance | staged worktree | 27/27 base binding; 135 repo checks; 72 platform/tool tests; repo-specific checks | pass | create signed commit and deliver by PR |
| review-1 | low | P1/P2: CI-portable legacy links and committed PR base | `785f102ea4e5eea747e9af2f8ef75023fa654ae7` | external Codex review | two findings | Worker C repair |
| worker-c-1 | medium | review repair and self-supervision consistency | uncommitted worktree | docs-all; checkpoint-diff against `0d3610f1353a9a0242a9c54c7fd037f2e8da37d5`; JSON; diff-check; evaluator 4-case smoke; `scripts/test.sh` | local checks pass; main acceptance and fresh review pending | main review, signed repair commit, fresh current-head review |
| main-2 | high | main-agent canonical normalization and P1-P3 independent review repair | working tree | docs/Scope/JSON/YAML/diff + preserved product checks | passed | sign commit and request fresh current-head review |
| review-2 | high | independent canonical and platform findings: incomplete COMMENTED result, false dry-run, status/check collision, suite binding, review-policy preservation, owner payload, explicit protection authorization, journal mode, inventory owner, live base, and publish concurrency | 5891d55a40a1d30d52bdda9d7d7017c2404c3b34 | canonical skill review plus repository review batch | repair applied | main-agent validation |
| main-3 | high | canonical fail-closed review and platform proof repair | working tree | docs/Scope/JSON/YAML/Python/diff + preserved product checks + 71 skill tests + 70 platform/normalizer tests + 11 delivery-state tests + 30-repo zero-diff preview | passed | sign commit and request fresh current-head review |
| review-10 | high | P1: publisher identity drift could preserve stale-base `loop/checkpoints` success | `b5daa5292329b0490d21faeebac906d34ca6fff8` | docs-all; two guard mutation regressions; worktree scope; JSON/YAML parse; `scripts/test.sh` | pass: both publisher guards now fail the bound head closed | create signed repair commit and request fresh current-head review |
| review-9 | high | independent findings: same-second blockers, trusted trigger provenance, symlink-safe preview and Scope reads, fixed worktree identity, signed dirty-tree evidence, temporary-index and signer preflight, idempotent checkpoint status, recoverable product reruns, and completed archive state | 368e6b24beb31a94aa1a1a9892a444c76041ad63 | main-agent integration plus bounded subagent review batch | repair applied | main-agent validation |
| main-10 | high | stable signed evidence and closure recovery | working tree | signed current-round evidence contract + 224 skill tests + 436 rollout orchestration tests + 29 repository validators | passed | sign commit and request fresh current-head review |

## Post-Merge Cleanup

- Main synced: pending
- Active Plan archived: pending - mandatory immediate cleanup PR; rollout completion, platform activation, and local deletion remain blocked until the active slot is empty
- Transition invariant: fail closed - no unrelated product PR may merge between the baseline merge and archive cleanup
- Local branch deleted: pending
- Heartbeat closed: pending
