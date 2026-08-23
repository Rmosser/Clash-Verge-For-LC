# Clash-Verge-For-LC Woodpecker Development Harness and Quality Entrypoints

## 任务分类

- non-trivial / critical
- 判定理由：保留已验证的 Woodpecker PR/push 门禁，并把文档完整性、仓库级测试入口
  和当前 Active Plan 一并纳入可执行的质量反馈。

## 已读上下文与核心信念

- 完整读取 `AGENTS.md`、根目录及各子目录 `README*`、`docs/CURRENT_RUNTIME.md`、
  `docs/LAZYCAT_NETWORK_REPORT.md` 与 `docs/SECURITY.md`。
- `AGENTS.md` 指向的 `skills/lazycat-dev/SKILL.md` 在 exact baseline 中不存在；
  本候选按仓库权威运行文档以及 `manage-repo-harness`、`proxy-config-writer` 技能执行。
- 默认分支基线：`0d3610f1353a9a0242a9c54c7fd037f2e8da37d5`，full-history clone。
- 核心信念：保守基线保持 `TUN=0`、`DNS=0`；controller 只监听微服 bridge，
  不暴露 LAN/WAN；真实订阅、token、secret 与节点凭据不进入 Git 或 CI。

## 当前任务扩展：质量入口迁移（2026-08-23）

本节是当前唯一 Active Plan 对本次 follow-up 的权威记录；上文保留已完成的
Woodpecker harness 建设和平台证据，避免把历史 canary 当作本次变更的验收依据。

- Baseline：`origin/main` 的 `a2d30df`，保留现有 `.harness`、治理门禁和
  `.woodpecker/woodpecker-harness.yaml`。
- Goal：增加 `docs/quality.md`、`scripts/check_docs.py` 和文档入口清单，令
  required paths、Markdown 本地链接和入口链接在 CI 中可执行检查；同时让
  `scripts/test.sh` 可从任意当前目录运行，并让本地 shell 语法检查覆盖仓库内 `.sh` 文件。
- Scope：只修改文档/治理入口、`scripts/test.sh`、`scripts/lint.sh` 和现有 Woodpecker
  harness 的检查顺序；不修改产品运行时、TUN/DNS、LPK、部署、secret 或 GitHub Actions。
- Acceptance：文档检查在 clean checkout 通过；仓库级测试从根目录和非根目录均通过；
  Woodpecker 继续执行 frozen install、dashboard unit、typecheck、lint 和 build。
- Verification：`python3 -I -B scripts/check_docs.py --all`、`bash scripts/test.sh`、
  `(cd docs && bash ../scripts/test.sh)`、全套 dashboard pnpm 检查和 exact-head PR check。

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
- Follow-up 增加 `docs/quality.md`、`scripts/check_docs.py`、入口清单和仓库级质量脚本，
  并把文档检查接入现有 Woodpecker workflow。

## Acceptance

- workflow 仅响应面向 `main` 的 pull_request 与 push。
- plugin-git 与 Node 22 镜像固定到 digest，`pull: false`，完整 clone 并抓取 target branch。
- PR 检查 `origin/$CI_COMMIT_TARGET_BRANCH...HEAD` 的已提交 diff；push 检查当前提交。
- 以 exact `corepack pnpm@10.29.2` 运行 `scripts/test.sh` 之外的 frozen install、typecheck、test:unit、lint 与 build；测试环境固定 `TZ=Asia/Shanghai`，保持既有显式 `+08:00` 日志解析用例的语义；Vite build 使用 3072 MiB Node heap。标准 Docker backend 的单任务资源已从 4 GiB memory / 6 GiB memory+swap 调至 6 GiB / 8 GiB，并发仍为 1。
- 不声明 secret、privileged、volume、Docker socket、publish 或 deploy。
- 本地 worktree 与 clean `git archive` 验证均通过，不修改运行配置。
- `check_docs.py` 覆盖 required paths、Markdown 本地链接和声明的入口链接；
  `scripts/test.sh` 从非根目录调用不会依赖调用者的当前工作目录。

## 文档影响

- 当前为 `merged_push_validated_required_gate_proven`：`repo_harness_ready=true`、
  `platform_machine_gate_ready=true`、`platform_gate_ready=false`、`actions_replacement_ready=false`。
- live activation、success/failure/repair canary、current-head Review、合并后 push 与 required gate proof 均已完成；GitHub 仍不能机器判定自然语言 Review，因此 aggregate `platform_gate_ready` 不抬高。

## Verification

- `git diff --check origin/main...HEAD`
- `git ls-files -z -- '*.sh' | xargs -0 -r -n 1 bash -n`
- `python3 -m json.tool .harness/repo-contract.json`
- `python3 -m json.tool docs/doc-sync-rules.json`
- `python3 -I -B scripts/check_docs.py --all`
- `bash scripts/test.sh`
- `(cd docs && bash ../scripts/test.sh)`
- `corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app install --frozen-lockfile`
- `corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app typecheck`
- `corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app test:unit`
- `corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app lint`
- `corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app build`
- 对 `git archive` 展开的 clean tree 重复上述治理和产品验证
- Agent memory override backup：`/srv/woodpecker-rainierdev/backups/standard-compose-20260808T090904Z/standard-compose.override.before-agent-memory-20260808T161639Z.yaml`，SHA-256 `39ad4d3cc9be92060e7f59cd69ddb8fd6c5cc62835612d687a7b6b1a2ee3049a`
- Root-only rollback：同目录 `rollback-agent-memory-20260808T161639Z.sh`；运行 override SHA-256 `284d8eef677194d881e2d8fb7b446d5ff0002bbee05f2d662c0b35340e1a5381`
- Agent recreate 后 healthy；Server/Cloudflared 保持运行，公网 root 200、`/healthz` 204

## Checkpoint 证据

- Context Claim：exact main、运行真相、安全边界、现有 package scripts 与 lockfile 已复读；
  旧 PR #5/#6 不作为本候选或证据复用。
- Scope Claim：只允许 lint 修复、workflow 与治理同步；禁止 activation、merge、ruleset、
  host mutation、TUN/DNS、LPK、deploy、真实凭据与真实订阅。
- Change Claim：前端语义只移除无用 import/赋值并格式化，`.gitignore` 忽略 lint cache；
  新增单步 Node 22 workflow 与最小治理证据。
- Follow-up Change Claim：新增文档质量映射和 checker，扩展仓库 `.sh` 语法扫描，
  并令测试入口先切换到 repository root。
- Validation Claim：committed diff、shell/JSON、frozen install、typecheck、unit、lint、build，
  本地与 clean archive 都必须通过。

## Canary Plan

- Initial success：`d7f2a8a531ab9730628f352f1cb5178ba7002288`，pipeline 7 success。
- Intentional failure：`eff0b2123930661d42e5449540f9c13613734906`，pipeline 9 failure；唯一临时变更为 committed trailing whitespace，不修改产品测试或运行配置。
- Repair success：`62a52fdcc11178452d01b5cfd47562c260e43655`，pipeline 11 success；fixture 已完全删除。
- Live context discovery：三次均为 `ci/woodpecker/pr/woodpecker-harness`；GitHub commit status 与 Woodpecker URL 一致。
- Merge + push：PR #7 以 expected head `6c3ce2f0386bf8fe4878012e68d1ace4d85d2785` squash merge 为 main `02ce1f391502fa9ca2531ca58240e8b46b0ef089`；pipeline 18 push success。
- Required gate：main strict required context 为 `ci/woodpecker/pr/woodpecker-harness`、`app_id=null`；一次性 PR #8 head `e5448e54a50b047422d119c8e65bcc42bb8f6f54` 在 pipeline 19 failure 时 live `BLOCKED`，随后关闭未合并并删除远端分支。

## Agent Delegation

- Used subagent: yes
- Delegated scope: clean full-history clone、lint 修复、候选 workflow、治理同步、
  本地/archive 验证、签名提交、push 与 ready PR
- Forbidden scope: activation、merge、ruleset/required context、host/runtime、TUN/DNS、LPK/deploy、真实凭据
- Subagent result: candidate preparation complete; main Agent repaired live pnpm/timezone/resource findings and completed canary
- Main agent review: `exact_head_clean_review_and_machine_gate_proof_complete`

## Codex Review

- Required: yes, at exact live PR head after canary evidence sync
- reviewed_head_sha: `6c3ce2f0386bf8fe4878012e68d1ace4d85d2785`
- Review result: `CLEAN / 0`; pipeline 17 passed the same live context and the incremental Review verified the four-file fact sync while workflow/product/core-belief bytes remained unchanged
- Merge authority: expected-head squash merge; main and merge SHA reread exact before the push proof
- Review supervision model: `trusted_agent_interpreted`

## 当前任务 Review 与修复

- PR：`#10`
- 初始 reviewed head：`71451d949269778b347521b0a09b1759c4d428b1`
- 初始结果：1 个 P1 与 2 个 P2；问题集中在 Active Plan 事实同步、非根目录测试入口
  和 shell 语法覆盖范围。
- Repair policy：一次集中修复后重新运行完整本地与 exact-head CI 验证；不重复请求 review。

## Repair Ledger

| Attempt | Finding | Evidence | Result | Next action |
| --- | --- | --- | --- | --- |
| 0 | baseline lint debt | 2 errors + 106 warnings | repaired locally | run full worktree and clean archive verification |
| 1 | live activation | `/repos/22`; PR enabled; deploy/trusted capabilities disabled | complete | trigger the first real PR pipeline |
| 2 | initial pipeline failed before tests | pipeline 1 invoked Corepack's default pnpm 11.20.0 while the project requires 10.29.2 | repaired workflow to invoke exact `corepack pnpm@10.29.2`; not counted as intentional canary | rerun the complete real check set |
| 3 | second pipeline reached real unit tests, then failed on Agent timezone drift | pipeline 2 installed 597 dependencies and passed typecheck, but the Agent UTC default rendered two explicit `+08:00` log timestamps eight hours earlier | fixed the test step to `TZ=Asia/Shanghai` without changing product parser or test expectations; not counted as intentional canary | rerun the complete real check set |
| 4 | third pipeline passed unit and lint, then exhausted Node's default heap during real Vite build | pipeline 3 proved 27+7 unit tests and zero-warning lint, then exited 134 at about 2 GiB heap during `vite build`; host showed 15 GiB RAM and Docker inspect showed no inner Agent limit, while the enclosing cgroup was not yet observed | initially set `NODE_OPTIONS=--max-old-space-size=4096`; pipeline 4 then exposed the outer limit; no build or validation step removed; not counted as intentional canary | bound the heap to the actual enclosing cgroup |
| 5 | fourth pipeline passed unit and lint, then hit the enclosing cgroup rather than host capacity | pipeline 4 with a 4096 MiB Node heap exited 137; kernel evidence bound its container to 4 GiB memory + 2 GiB swap and recorded the Node OOM kill near 4 GiB RSS | reduced the Node old-space ceiling to 3072 MiB to leave cgroup headroom; full build remains required; not counted as intentional canary | rerun the complete real check set |
| 6 | fifth actual run still exceeded the explicit 4 GiB task budget | pipeline 6 passed committed diff, shell/JSON, install, typecheck, 27+7 unit tests and zero-warning lint, then received an OOM kill in the full Vite build | backed up the standard override; raised only Docker backend task memory to 6 GiB and memory+swap to 8 GiB; concurrency remains 1; Agent healthy and public service unchanged; not counted as intentional canary | rerun the complete real check set |
| 7 | complete canary after standard resource repair | pipeline 7 success at `d7f2a8a`; pipeline 9 intentional committed-whitespace failure at `eff0b21`; pipeline 11 repair success at `62a52fd`; all use the same live context | success/failure/repair evidence complete; fixture absent | sync evidence, rerun current head, request independent Review |
| 8 | exact-head Review found two extensionless Bash host tools outside the syntax gate | Review of `552859fac00dc7670ffebdac240c11387327541d` was `NON_CLEAN / 1`; both files are tracked, executable, and use a Bash shebang | added explicit `bash -n` coverage without executing the host tools; aligned contract evidence | rerun the complete current-head pipeline and request a fresh exact-head Review |
| 9 | repaired exact head passed full validation and fresh Review | pipeline 15 success at `2541549b637cd03f1c429b5fae6828acea635b94`; independent Review `CLEAN / 0` with live head unchanged | record the exact Review without changing workflow or product bytes | run the fact-sync head through the same context and obtain incremental Review, then install the live required context |
| 10 | Review fact sync and expected-head merge | pipeline 17 success and incremental `CLEAN / 0` at `6c3ce2f0386bf8fe4878012e68d1ace4d85d2785` | installed strict required context after live reread; squash merged exact head to `02ce1f391502fa9ca2531ca58240e8b46b0ef089` | verify main push and a failing PR is blocked |
| 11 | platform machine gate proof | pipeline 18 main push success; PR #8 pipeline 19 same-context failure and live `BLOCKED` | closed PR #8 unmerged and deleted its remote branch; required context remained strict and all other protection fields unchanged | record final facts; keep `platform_gate_ready=false` because Review is not machine-enforced |
| 12 | current quality-entrypoint Review | PR #10 exact head `71451d9` found one P1 and two P2 findings | concentrated repair updates the sole Active Plan, makes the test entrypoint cwd-independent, and expands `.sh` syntax coverage | run full repair verification and merge only after the exact head is green |

## Post-Merge Cleanup

- Main synced: `02ce1f391502fa9ca2531ca58240e8b46b0ef089`; push pipeline 18 success
- Local branch deleted: pending

## 当前任务扩展：Mihomo core v1.19.30

- Baseline：当前 focused branch 从 main HEAD 创建；只读回读确认 `rainierdev` 为 Mihomo `v1.19.23`、`rainierspace` 为 `v1.19.24`，两台机器均为 x86_64，mihomo、Verge API、container proxy 均 active。
- Goal：将 host-native Mihomo 固定升级到 `v1.19.30`，统一部署脚本、manager 和 Verge API 的升级/回滚实现。
- Scope：只改 core updater、宿主机升级脚本、host-side API、测试与运行手册；不改前端、LPK、订阅、配置、TUN/DNS、路由或 compose。
- Change：新增共享 `infra/microserver/mihomo_core_updater.py`，使用 GitHub release asset digest、架构/版本检查、`flock`、配置测试、原子替换、健康探活、备份和自动回滚；core-only 路径不下发配置或网络 unit。
- Verification：最终通过 `bash scripts/test.sh`、`python3 -I -B scripts/check_docs.py --all`、dashboard frozen install、typecheck、unit（27+7）、lint 和 build；updater 测试覆盖 release digest、checksum/version/config 失败、下载瞬断重试、并发锁、原子切换、健康失败自动回滚和重复目标版本 receipt 保留。
- Rollout：`rainierdev` 已从 `v1.19.23` 升到 `v1.19.30`，30/30 分钟探针通过，并完成回滚到 `v1.19.23` 后恢复；`rainierspace` 已从 `v1.19.24` 升到 `v1.19.30`。两台最终均通过配置测试、systemd、controller、Verge API、监听、盒子 READY、dashboard 入口和普通应用容器验收。
- Release receipt：两台远端 `/var/lib/mihomo/rollback/latest.env` 均记录旧/新版本、asset、URL、SHA256、备份路径、时间和状态；固定 asset 为 `mihomo-linux-amd64-compatible-v1.19.30.gz`，SHA256 为 `db214c7a2517e63c150d123178d16d102e03a241ccdae4e5e07ffbe9cf56c6f9`。不记录 secret、订阅或私有配置。
- 异常收据：生产机首次下载连接关闭时核心未切换；第二次在 API 慢启动超过原 5 秒窗口时自动回滚成功，随后增加 3 次下载重试和 30 秒 API 健康等待后发布成功。`selfcheck.sh` 同步改为远端本地读取 secret、只回显状态，并通过；TCP 直连探针为 WARN，其他 DNS/HTTPS/controller 门禁通过，未记录 secret 或 public-config 内容。
