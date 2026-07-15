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
- Harness upgrade file: `.github/workflows/codex-review-signal.yml`
- Harness upgrade file: `.github/pull_request_template.md`
- Harness upgrade file: `scripts/check_docs.py`
- Harness upgrade file: `scripts/check_codex_review.py`
- Harness upgrade file: `scripts/check_docs_project.py`
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
- `python3 -I -B scripts/check_loop_checkpoints.py --base HEAD`
- `python3 -m json.tool docs/doc-sync-rules.json`
- `python3 -m json.tool .harness/repo-contract.json`
- `python3 scripts/check_codex_review.py --fixture <fixture>`（通用 gate 仓库）

## Checkpoint 证据

- Context Claim：本次只处理 repo-native Harness 入口、治理文档、模板和检查脚本；平台门禁另行验证。
- Scope Claim：允许清单见 `## Scope`；产品行为和线上状态不属于本次语义变更。
- Change Claim：新增或更新 AGENTS/docs/governance/docs sync/repo contract/PR template/docs CI/current-head Codex Review gate/Harness check 脚本，并归档旧 active plan 以保持 active 基数 0..1。
- Validation Claim：以本计划 `## Verification` 中的本地命令和主 Agent 最终复核结果为准。

## Agent Delegation

- Delegation decision: multi-repo Harness task, delegate batch review/repair to subagents while main Agent owns final acceptance.
- Used subagent: yes
- No-subagent fallback reason: n/a
- Delegated scope: bounded repo batches under `/Users/rinier/Projects`; Harness files only.
- Forbidden scope: product behavior, secrets, deployment/runtime state, platform settings, independent push/merge/heartbeat closure.
- Subagent result: complete - delegated repository review and rollout preparation found no unresolved P0/P1 findings.
- Main agent review: accepted - main Agent verified 27/27 live base bindings, 135 repository checks, 72 platform/tool tests, and repository-specific validation.
- Rework requested: no - rollout conflicts, repo-native path differences, and stale trust-boundary fields were repaired and revalidated.
- Final accepted diff: accepted - repository-layer self-supervised Harness only; live emitter smoke and platform protection remain separate post-merge evidence.

## Codex Review

- Required: for non-trivial PRs before merge
- Requested by: pending
- Requested at: pending
- Completed review head: pending
- Current review target pointer: PR comment / GitHub review object
- Heartbeat required: yes when waiting on review
- Heartbeat interval: project policy
- Heartbeat stop condition: review complete and repair ledger closed
- Review result: pending

## Review Repair Policy

- Start tier: low
- Current tier: low
- Max attempts per tier: 2
- Attempts at current tier: 0
- Total repair attempts: 0
- Escalation path: low -> medium -> high -> xhigh -> human
- Stop condition: review findings closed or human intervention required
- Last repeated finding: none
- Human intervention required: no

## Repair Ledger

| Attempt | Tier | Finding class | Commit | Checks | Result | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | - | none | - | - | no feedback repair yet | wait for review |
| main-1 | high | main-agent acceptance | staged worktree | 27/27 base binding; 135 repo checks; 72 platform/tool tests; repo-specific checks | pass | create signed commit and deliver by PR |

## Post-Merge Cleanup

- Main synced: pending
- Local branch deleted: pending
- Heartbeat closed: pending
