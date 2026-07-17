# Plan Title

- Status: active

## Task Classification / 任务分类

- Task class: trivial / standard / critical
- Reasoning budget: low / medium / high
- Delegation route: single-agent / main+subagent / main+work-thread / main+parallel-subagents / no-subagent-fallback
- 判定理由：

## 已读上下文

-

## Goal

-

## Non-Goals

-

## Scope

<!-- 机器对账约定：反引号包裹的路径是允许清单（目录以 / 结尾，支持 fnmatch 通配且 * 跨目录）；含 forbidden / 禁止 / 不允许 等否定标记的行，其反引号路径是禁止清单并优先生效；## Non-Goals 中的反引号路径同样计入禁止清单。无反引号的文字仅供人读。 -->

-

## Acceptance

-

## Documentation Impact / 文档影响

-

## Verification

- `python3 -I -B scripts/check_docs.py --all`
- `python3 -I -B scripts/check_loop_checkpoints.py`

<!-- checkpoint verifier 默认从 GITHUB_BASE_REF、HARNESS_DIFF_BASE_REF 或 origin 的默认分支解析真实 base。已提交 PR 不得用 --base HEAD 做 Scope 证据。 -->

## Checkpoint 证据 / Checkpoint Evidence

- Context Claim：
- Scope Claim：
<!-- Change Claim 只列当前 diff 实际新增、修改、删除的路径和行为。 -->
- Change Claim：
- Validation Claim：

## Agent Delegation

- Delegation decision:
- Used subagent:
- No-subagent fallback reason:
<!-- Delegated scope 只写本仓库内的相对路径/职责，不写机器绝对路径或父工作区。 -->
- Delegated scope:
- Forbidden scope:
- Subagent result:
- Main agent review: `pending`
- Rework requested: `pending`
- Final accepted diff: `pending`

## Codex Review

- Required:
- Requested by:
- Requested at:
<!-- 已完成 review 时写完整 40 位 SHA；尚未完成时写 pending。 -->
- Completed review head:
- Current review target pointer: PR comment / GitHub review object
- Heartbeat required:
- Heartbeat interval:
- Heartbeat stop condition:
- Review result:

## Review Repair Policy

- Start tier:
- Current tier:
- Max attempts per tier: 2
- Attempts at current tier:
- Total repair attempts:
- Escalation path:
- Stop condition:
- Last repeated finding:
- Human intervention required:

## Repair Ledger

| Attempt | Tier | Finding class | Commit | Checks | Result | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | - | none | - | - | no feedback repair yet | wait for review |

## Post-Merge Cleanup

- Main synced:
- Active Plan archived:
- Transition invariant: if this plan lands under `active/`, no unrelated PR may merge and rollout completion, required-check activation, or local deletion must wait until the immediate archive cleanup PR empties the active slot.
- Local branch deleted:
- Heartbeat closed:
