# Harness Delegation Upgrade

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
- Change Claim：新增或更新 AGENTS/docs/governance/docs sync/repo contract/PR template/docs CI/current-head Codex Review gate/Harness check 脚本，并归档旧 active plan 以保持 active 基数 0..1。
- Validation Claim: repo-native docs, real `origin/main` Scope, JSON, YAML, and diff checks passed on 2026-07-15; no additional product command was removed from the prior docs workflow.

## Agent Delegation

- Delegation decision: multi-repo Harness task, delegate batch review/repair to subagents while main Agent owns final acceptance.
- Used subagent: yes
- No-subagent fallback reason: n/a
- Delegated scope: `Rmosser/Clash-Verge-For-LC` only; Harness files listed in `## Scope`.
- Forbidden scope: product behavior, secrets, deployment/runtime state, platform settings, independent push/merge/heartbeat closure.
- Subagent result: complete - three independent batch reviews completed and all local findings were repaired; signed repair-head Codex review remains pending
- Main agent review: accepted on 2026-07-15 after independent diff, trust-boundary, and validation review
- Rework requested: completed - review findings and main-agent canonical normalization are addressed
- Final accepted diff: accepted by the main Agent for signed commit and fresh current-head Codex review

## Codex Review

- Required: for non-trivial PRs before merge
- Requested by: Rmosser via `@codex review`
- Requested at: 2026-07-15T10:02:11Z
- Completed review head: `785f102ea4e5eea747e9af2f8ef75023fa654ae7`
- Current review target pointer: PR #5 / https://github.com/Rmosser/Clash-Verge-For-LC/pull/5#pullrequestreview-4703051561
- Heartbeat required: yes when waiting on review
- Heartbeat interval: project policy
- Heartbeat stop condition: review complete and repair ledger closed
- Review result: findings on the recorded head; repaired worktree awaits a new commit and fresh current-head review.

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

## Post-Merge Cleanup

- Main synced: pending
- Local branch deleted: pending
- Heartbeat closed: pending
