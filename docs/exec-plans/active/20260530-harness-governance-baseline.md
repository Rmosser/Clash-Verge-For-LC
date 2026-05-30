# Harness Governance Baseline PR1

- 状态：active
- 更新时间：2026-05-30

## 任务分类

- non-trivial
- 判定理由：本次变更建立仓库入口层、Active Plan 模板、doc-sync 规则和 Harness contract，会影响后续 Agent 交付方式。

## 已读上下文

- AGENTS.md
- README.md
- docs/README.md
- docs/USER_GUIDE.md
- docs/SECURITY.md
- docs/LAZYCAT_NETWORK_REPORT.md
- scripts/test.sh
- scripts/lint.sh
- harness-engineering-coach/SKILL.md
- harness-engineering-coach/references/agents-entrypoint-principles.md
- harness-engineering-coach/references/agent-native-execution-policy.md
- harness-engineering-coach/references/diagnostic-checklist.md
- harness-engineering-coach/references/merge-gate-prerequisites.md

## Goal

- 在 clean worktree / branch `codex/harness-governance-baseline-clean` 上建立 PR1 治理基线。
- 让后续 Agent 能从仓库入口发现真相源、Active Plan、doc-sync 规则和 checkpoint gate。

## Non-Goals

- 不新增或修改 scripts。
- 不新增或修改 `.github/workflows`、PR template、branch protection 或 GitHub 设置。
- 不修改代码、infra、runtime 文件、lockfile 或部署包。
- 不把旧混合分支、运行态变更或 docs-density 变更塞入本 PR。

## Scope

- 允许修改：AGENTS.md、README.md、docs/README.md、docs/index.md、docs/governance/checkpoint-ci-gate.md、docs/exec-plans/template.md、docs/exec-plans/active/20260530-harness-governance-baseline.md、docs/exec-plans/completed/.gitkeep、docs/doc-sync-rules.json、.harness/repo-contract.json。
- 禁止修改：scripts/、.github/、src/、infra/、deploy/、configs/、docs/CURRENT_RUNTIME.md、HOST_NATIVE_RUNBOOK、PACKAGING、lockfile、运行态旧变更。

## Acceptance

- 入口层不授权绕过 PR、review、checks 或 branch protection。
- 当前 Active Plan 明确 subagent 状态，并记录主 Agent 对 clean worktree diff 的验收结论。
- repo contract 与 doc-sync 规则为后续 verifier / CI 提供稳定读取入口。
- 最终 diff 不包含 infra、scripts、src、运行态旧变更或 lockfile。

## 文档影响

- 新增 Harness governance 入口与索引。
- 将 docs 索引和 README 指向新的治理入口。

## Verification

- `python3 -m json.tool docs/doc-sync-rules.json`
- `python3 -m json.tool .harness/repo-contract.json`
- `bash scripts/test.sh`
- `git diff --check origin/main...HEAD`
- `git diff --name-only origin/main...HEAD`
- 归档残留关键词扫描：通过

## Checkpoint 证据

- Context Claim：目标 worktree 为 `/Users/rinier/Projects/lazyCat/.harness-worktrees/Clash-Verge-For-LC-harness`；当前分支为 `codex/harness-governance-baseline-clean`；原始 repo 路径不得触碰。
- Scope Claim：本 PR 只做 PR1 入口层和治理基线，禁止 scripts / workflows / code / infra / runtime 文件。
- Change Claim：变更限于入口、索引、checkpoint gate、exec plan 模板与当前计划、doc-sync 规则、repo contract 和必要 README 链接。
- Validation Claim：运行 JSON 检查、现有 `scripts/test.sh`，并用 git diff 文件列表确认范围。

## Agent Delegation

- Used subagent: yes
- Delegated scope: 在目标 clean worktree 内完成 Harness Engineering PR1 治理基线文件改造、本地检查和本地 commit。
- Forbidden scope: 不触碰原始 repo；不修改 scripts、.github/workflows、PR template、branch protection、GitHub 设置、代码、infra、runtime 文件、lockfile；不 push、不 PR、不 merge。
- Subagent result: `completed by subagent pending main review`
- Main agent review: `accepted by main agent on 2026-05-30 after diff scope inspection`
- Rework requested: `no`
- Final accepted diff: `accepted; PR1 governance-only diff, no scripts/workflows/code/infra/runtime files`

## Codex Review

- Required: true for the eventual non-trivial PR
- Requested by: `pending until PR is opened`
- Requested at: `pending until PR is opened`
- Review target: `pending until pushed; exact current head is recorded in PR comment / GitHub review object`
- Heartbeat required: true when PR is opened and waiting for review
- Heartbeat interval: `pending`
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
