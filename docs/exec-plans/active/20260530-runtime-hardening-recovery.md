# Runtime Hardening Recovery

## 任务分类

- non-trivial
- 判定理由：本次变更承接旧 runtime-dirty 分支中的宿主机恢复、container proxy 监听、unlock probe 并发和本地 scratch ignore 变更，影响运行时可靠性。

## 已读上下文

- AGENTS.md
- docs/index.md
- docs/governance/checkpoint-ci-gate.md
- docs/exec-plans/template.md
- docs/HOST_NATIVE_RUNBOOK.md
- infra/microserver/mihomo-container-proxy.socket
- infra/microserver/mihomo-verge-api.py
- infra/microserver/test_mihomo_verge_api.py
- scripts/install_host_native_bootstrap.sh
- scripts/test.sh

## Goal

- 从旧 mixed/backup 分支中抽出仍未进入 main 的 runtime hardening 变更，形成干净 PR。
- 合并后让旧 mixed/backup/preserve 分支不再承载独有 runtime work。

## Non-Goals

- 不重新引入旧 Harness baseline 文件或旧 Active Plan。
- 不回滚 PR #2 的 current-runtime 文档修复。
- 不修改 GitHub workflow、branch protection 或 required checks。

## Scope

- 允许修改：`.gitignore`、`docs/HOST_NATIVE_RUNBOOK.md`、`infra/microserver/mihomo-container-proxy.socket`、`infra/microserver/mihomo-verge-api.py`、`infra/microserver/test_mihomo_verge_api.py`、`scripts/install_host_native_bootstrap.sh`、Active Plan 状态。
- 禁止修改：dashboard 源码、packaging docs、GitHub 平台设置、旧 mixed branch 历史。

## Acceptance

- Active Plan 唯一：`docs/exec-plans/active/` 只包含本计划。
- Runtime hardening diff 不包含旧 Harness baseline drift。
- Existing local checks pass.
- Codex Review feedback is requested and repaired before merge.

## 文档影响

- 更新 host-native runbook 中 rainierspace reboot/bootstrap 风险说明。
- 归档已合并 docs-density Active Plan，新增本计划。

## Verification

- `python3 -m json.tool docs/doc-sync-rules.json`
- `python3 -m json.tool .harness/repo-contract.json`
- `git diff --check origin/main...HEAD`
- `bash scripts/test.sh`
- `find docs/exec-plans/active -type f | sort`
- `git diff --name-only origin/main...HEAD`

## Checkpoint 证据

- Context Claim：基于 `origin/main` after PR #2，旧 branches 只作为 source commits，当前 contract 来自 main。
- Scope Claim：只承接 runtime hardening 和 `.codex-tmp/` ignore，不承接旧治理文件漂移。
- Change Claim：container proxy 增加 bridge listeners/freebind；unlock probe 并发并传递 timeout；bootstrap bridge wait 可配置并由 systemd 重试；runbook 记录风险；`.gitignore` 忽略本地 scratch。
- Validation Claim：运行 JSON、diff whitespace、shell/python syntax 检查，并核对 active plan 唯一性和 diff 范围。

## Agent Delegation

- Used subagent: no
- Delegated scope: none
- Forbidden scope: old mixed branch history, GitHub platform settings, dashboard source
- Subagent result: n/a
- Main agent review: `accepted clean extraction after cherry-pick conflict resolution on 2026-05-30`
- Rework requested: `no`
- Final accepted diff: `pending final checks and Codex Review`

## Codex Review

- Required: true
- PR: `pending`
- Requested by: `pending after branch push`
- Requested at: `pending`
- Review target: `latest PR head; exact current SHA is recorded in the @codex review PR comment`
- Heartbeat required: true while waiting for review
- Heartbeat interval: `manual current-session polling`
- Heartbeat stop condition: review returned, PR merged, or branch cleanup blocks are reported
- Review result: `pending`

## Review Repair Policy

- Start tier: low
- Current tier: low
- Max attempts per tier: 2
- Attempts at current tier: 0
- Total repair attempts: 0
- Escalation path: low -> medium -> high -> xhigh -> human
- Stop condition: review findings resolved or main agent escalates
- Last repeated finding: none
- Human intervention required: false

## Repair Ledger

| Attempt | Tier | Finding class | Commit | Checks | Result | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | - | none | - | - | no feedback repair yet | wait for review |

## Post-Merge Cleanup

- Main synced: `pending`
- Local branch deleted: `pending`
- Heartbeat closed: `pending`
