# Clash-Verge-For-LC Woodpecker Development Harness Candidate

## 任务分类

- non-trivial / critical
- 判定理由：修复真实前端 lint 债务，新增 PR/push CI control-plane workflow，
  并为后续 GitHub required context 准备真实门禁证据。

## 已读上下文与核心信念

- 完整读取 `AGENTS.md`、根目录及各子目录 `README*`、`docs/CURRENT_RUNTIME.md`、
  `docs/LAZYCAT_NETWORK_REPORT.md` 与 `docs/SECURITY.md`。
- `AGENTS.md` 指向的 `skills/lazycat-dev/SKILL.md` 在 exact baseline 中不存在；
  本候选按仓库权威运行文档以及 `manage-repo-harness`、`proxy-config-writer` 技能执行。
- 默认分支基线：`0d3610f1353a9a0242a9c54c7fd037f2e8da37d5`，full-history clone。
- 核心信念：保守基线保持 `TUN=0`、`DNS=0`；controller 只监听微服 bridge，
  不暴露 LAN/WAN；真实订阅、token、secret 与节点凭据不进入 Git 或 CI。

## Goal

- 最小诚实修复阻止既有 `pnpm lint` 的 2 个 error 与 106 个 Prettier warning。
- 提供最小、repo-native、无 secret 的 Woodpecker PR/push workflow 候选。
- 使用仓库现有 shell 检查和前端 frozen install、typecheck、unit、lint、build 作为真实开发证据。

## Non-Goals

- 不复用旧 PR #5/#6；它们只作为历史参考。
- Woodpecker `/repos/22` 已由主 Agent 激活；本实现分支不再修改 activation 设置，且不修改 GitHub required context、branch protection 或 ruleset。
- 不修改或部署 host-native 运行时，不启用 TUN/DNS，不构建或安装 LPK。
- 不访问真实订阅、token、secret、节点配置、宿主机 controller 或目标机。

## Scope

- 修复 `src/mihomo-dashboard-app/browser/` 中现有 lint 问题：移除一个未使用 import，
  消除一次无效初始赋值，应用项目既有 Prettier 规则，并忽略 lint 生成的 `.eslintcache`。
- 新增 `.woodpecker/woodpecker-harness.yaml`。
- 建立当前唯一 Active Plan，同步 checkpoint、contract、docs index 与 doc-sync 清单；
  将已经合并到 main 的旧 runtime hardening Plan 归档。

## Acceptance

- workflow 仅响应面向 `main` 的 pull_request 与 push。
- plugin-git 与 Node 22 镜像固定到 digest，`pull: false`，完整 clone 并抓取 target branch。
- PR 检查 `origin/$CI_COMMIT_TARGET_BRANCH...HEAD` 的已提交 diff；push 检查当前提交。
- 以 exact `corepack pnpm@10.29.2` 运行 `scripts/test.sh` 之外的 frozen install、typecheck、test:unit、lint 与 build；测试环境固定 `TZ=Asia/Shanghai`，保持既有显式 `+08:00` 日志解析用例的语义；Vite build 使用 3072 MiB Node heap，在实际外层 4 GiB memory + 2 GiB swap cgroup 内为 Node 及构建辅助进程保留明确余量。
- 不声明 secret、privileged、volume、Docker socket、publish 或 deploy。
- 本地 worktree 与 clean `git archive` 验证均通过，不修改运行配置。

## 文档影响

- 当前为 `activated_canary_pending`：`repo_harness_ready=false`、
  `platform_gate_ready=false`、`actions_replacement_ready=false`。
- live activation 已完成；success/failure/repair canary 与 current-head Review 仍由主 Agent执行。

## Verification

- `git diff --check origin/main...HEAD`
- `git ls-files -z -- '*.sh' | xargs -0 -r -n 1 bash -n`
- `python3 -m json.tool .harness/repo-contract.json`
- `python3 -m json.tool docs/doc-sync-rules.json`
- `bash scripts/test.sh`
- `corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app install --frozen-lockfile`
- `corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app typecheck`
- `corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app test:unit`
- `corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app lint`
- `corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app build`
- 对 `git archive` 展开的 clean tree 重复上述治理和产品验证

## Checkpoint 证据

- Context Claim：exact main、运行真相、安全边界、现有 package scripts 与 lockfile 已复读；
  旧 PR #5/#6 不作为本候选或证据复用。
- Scope Claim：只允许 lint 修复、workflow 与治理同步；禁止 activation、merge、ruleset、
  host mutation、TUN/DNS、LPK、deploy、真实凭据与真实订阅。
- Change Claim：前端语义只移除无用 import/赋值并格式化，`.gitignore` 忽略 lint cache；
  新增单步 Node 22 workflow 与最小治理证据。
- Validation Claim：committed diff、shell/JSON、frozen install、typecheck、unit、lint、build，
  本地与 clean archive 都必须通过。

## Canary Plan

- Initial success：pending。
- Intentional failure：pending；只允许 committed trailing-whitespace fixture，不修改产品测试或运行配置。
- Repair success：pending；删除 fixture 后重复完整真实检查。
- Live context discovery：pending。

## Agent Delegation

- Used subagent: yes
- Delegated scope: clean full-history clone、lint 修复、候选 workflow、治理同步、
  本地/archive 验证、签名提交、push 与 ready PR
- Forbidden scope: activation、merge、ruleset/required context、host/runtime、TUN/DNS、LPK/deploy、真实凭据
- Subagent result: pending main-agent diff review
- Main agent review: `pending`

## Codex Review

- Required: yes, at exact live PR head after canary evidence sync
- review_target_head_sha: `pending`
- Review result: `pending`
- Review supervision model: `trusted_agent_interpreted`

## Repair Ledger

| Attempt | Finding | Evidence | Result | Next action |
| --- | --- | --- | --- | --- |
| 0 | baseline lint debt | 2 errors + 106 warnings | repaired locally | run full worktree and clean archive verification |
| 1 | live activation | `/repos/22`; PR enabled; deploy/trusted capabilities disabled | complete | trigger the first real PR pipeline |
| 2 | initial pipeline failed before tests | pipeline 1 invoked Corepack's default pnpm 11.20.0 while the project requires 10.29.2 | repaired workflow to invoke exact `corepack pnpm@10.29.2`; not counted as intentional canary | rerun the complete real check set |
| 3 | second pipeline reached real unit tests, then failed on Agent timezone drift | pipeline 2 installed 597 dependencies and passed typecheck, but the Agent UTC default rendered two explicit `+08:00` log timestamps eight hours earlier | fixed the test step to `TZ=Asia/Shanghai` without changing product parser or test expectations; not counted as intentional canary | rerun the complete real check set |
| 4 | third pipeline passed unit and lint, then exhausted Node's default heap during real Vite build | pipeline 3 proved 27+7 unit tests and zero-warning lint, then exited 134 at about 2 GiB heap during `vite build`; host showed 15 GiB RAM and Docker inspect showed no inner Agent limit, while the enclosing cgroup was not yet observed | initially set `NODE_OPTIONS=--max-old-space-size=4096`; pipeline 4 then exposed the outer limit; no build or validation step removed; not counted as intentional canary | bound the heap to the actual enclosing cgroup |
| 5 | fourth pipeline passed unit and lint, then hit the enclosing cgroup rather than host capacity | pipeline 4 with a 4096 MiB Node heap exited 137; kernel evidence bound its container to 4 GiB memory + 2 GiB swap and recorded the Node OOM kill near 4 GiB RSS | reduced the Node old-space ceiling to 3072 MiB to leave cgroup headroom; full build remains required; not counted as intentional canary | rerun the complete real check set |

## Post-Merge Cleanup

- Main synced: pending
- Local branch deleted: pending
