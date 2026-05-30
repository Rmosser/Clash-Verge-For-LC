# Docs Density Review PR2

## 任务分类

- non-trivial
- 判定理由：本次变更重构当前运行 contract、用户/运维/发布文档，并新增宿主机 bootstrap/release 脚本；影响后续操作入口和交付判断。

## 已读上下文

- AGENTS.md
- README.md
- docs/index.md
- docs/README.md
- docs/CURRENT_RUNTIME.md
- docs/HOST_NATIVE_RUNBOOK.md
- docs/USER_GUIDE.md
- docs/governance/checkpoint-ci-gate.md
- docs/doc-sync-rules.json
- .harness/repo-contract.json
- scripts/test.sh
- scripts/lint.sh

## Goal

- 合并 PR #2 的 current-runtime 文档重构和脚本包装变更。
- 保留 PR #3 已落地的 Harness governance 入口，并让本 PR 有当前唯一 Active Plan。

## Non-Goals

- 不修改业务代码、dashboard 源码或 Mihomo 核心行为。
- 不新增 GitHub workflow、branch protection 或 required check。
- 不把后续运行态 hardening 分支的 infra/microserver 代码变更并入本 PR。

## Scope

- 允许修改：README、docs 当前运行/用户/运维/安全/发布/复盘文档、deploy/infra/scripts 文档、bootstrap/release shell 脚本、Active Plan 归档状态。
- 禁止修改：infra/microserver 运行时代码、测试代码、dashboard 源码、lockfile、GitHub 平台设置。

## Acceptance

- README 和 docs 索引同时保留 current-runtime 文档入口与 Harness governance 入口。
- `docs/exec-plans/active/` 中只有本计划；已合并 PR #3 计划移入 completed。
- PR diff 不包含 runtime hardening 分支的 `infra/microserver/**` 代码变更。
- 本仓库现有检查通过。

## 文档影响

- 新增 `docs/CURRENT_RUNTIME.md` 作为当前运行 contract。
- 拆分用户、容器代理、host-native 运维、发布和 smoke checklist 文档。
- 将历史 PRD / incident docs 明确降级为背景资料。

## Verification

- `python3 -m json.tool docs/doc-sync-rules.json`
- `python3 -m json.tool .harness/repo-contract.json`
- `git diff --check origin/main...HEAD`
- `bash scripts/test.sh`
- `find docs/exec-plans/active -type f | sort`
- `git diff --name-only origin/main...HEAD`

## Checkpoint 证据

- Context Claim：本 PR 基于 merged PR #3 后的 `origin/main`，适用 `AGENTS.md`、`docs/index.md`、checkpoint gate、doc-sync rules 和 repo contract。
- Scope Claim：只交付文档密度重构、bootstrap/release 脚本包装和 Active Plan 状态修复；不交付 runtime hardening 代码。
- Change Claim：README/docs/deploy/infra/scripts 文档更新，新增 current-runtime/runbook/packaging docs，新增 bootstrap/release shell scripts，归档 PR #3 Active Plan 并新增本 Active Plan。
- Validation Claim：运行 JSON 检查、diff whitespace 检查、现有 shell/python syntax 检查，并核对 active plan 唯一性与 diff 文件列表。

## Agent Delegation

- Used subagent: no
- Delegated scope: none
- Forbidden scope: runtime hardening code, GitHub platform settings, workflow/required-check changes
- Subagent result: n/a
- Main agent review: `accepted scope after merge conflict resolution on 2026-05-30`
- Rework requested: `no`
- Final accepted diff: `pending final checks after Codex Review repair`

## Codex Review

- Required: true
- PR: https://github.com/Rmosser/Clash-Verge-For-LC/pull/2
- Requested by: PR comment `@codex review`
- Requested at: `2026-05-30`
- Review target: `latest PR head; exact current SHA is recorded in the @codex review PR comment`
- Heartbeat required: true while waiting for review
- Heartbeat interval: `manual current-session polling`
- Heartbeat stop condition: review returned, PR merged, or branch cleanup blocks are reported
- Review result: `COMMENTED with two P2 findings on scripts/build_dashboard_release.sh and scripts/install_host_native_bootstrap.sh`

## Review Repair Policy

- Start tier: low
- Current tier: low
- Max attempts per tier: 2
- Attempts at current tier: 1
- Total repair attempts: 1
- Escalation path: low -> medium -> high -> xhigh -> human
- Stop condition: review findings resolved or main agent escalates
- Last repeated finding: none
- Human intervention required: false

## Repair Ledger

| Attempt | Tier | Finding class | Commit | Checks | Result | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | - | none | - | - | review returned two P2 findings | repair |
| 1 | low | script path/retry robustness | pending commit | pending | made output root absolute; extended bridge wait and added systemd restart policy | rerun checks and request review |

## Post-Merge Cleanup

- Main synced: `pending`
- Local branch deleted: `pending`
- Heartbeat closed: `pending`
