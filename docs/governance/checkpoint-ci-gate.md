# Checkpoint CI Gate

Clash-Verge-For-LC 采用简化的 repo-native Agent CI/CD 治理：Agent 可以写候选，
CI 提供真实测试证据，GitHub 平台门禁负责阻止不合格合并。

Checkpoint CI Gate 只裁决 merge eligibility、evidence completeness 与 claim/fact
consistency；它不控制本地写权限、PR 分支 push 权限或第三方 connector 权限。

## 四个 Claim

- Context Claim：本次任务适用哪些真相源与核心信念。
- Scope Claim：允许和禁止哪些变更。
- Change Claim：实际 diff 包含哪些文件和行为。
- Validation Claim：哪些测试与平台事实足以证明候选。

## 核心信念

- 当前已验证保守基线是 `MIHOMO_TUN_ENABLE=0`、`MIHOMO_DNS_ENABLE=0`。
- Mihomo controller 保持 `172.18.0.1:9090`，只在微服 bridge 可达，不暴露 LAN/WAN。
- 浏览器通过 LazyCat 登录后的应用路由和 `/verge-api/public-config` 获取运行时配置。
- 真实订阅、token、secret、节点凭据与目标机配置不得进入 Git、文档或 CI 日志。
- 普通开发 CI 不触发 host、TUN、DNS、systemd、LPK、publish 或 deploy。

## 当前候选

候选基于默认分支 `0d3610f1353a9a0242a9c54c7fd037f2e8da37d5`，从 full-history
clone 建立。workflow 固定 plugin-git 与 Node 22 镜像 digest、设置 `pull: false`，
抓取 target branch；PR 检查 `origin/$CI_COMMIT_TARGET_BRANCH...HEAD` 的已提交 diff，
push 检查当前提交。

仓库基线的 `pnpm lint` 有 2 个 error 与 106 个 Prettier warning。候选只移除一个
未使用 import、消除一个无效初始赋值，并按仓库现有 Prettier 规则格式化被报告文件；
不改变 TUN、DNS、controller、订阅或运行配置。

workflow 运行 `scripts/test.sh`，并以 exact `corepack pnpm@10.29.2` 运行 frozen install、typecheck、test:unit、lint 与 build。测试步骤固定 `TZ=Asia/Shanghai`，与包含明确 `+08:00`
时间戳的既有 parser 单元测试语义一致；不修改产品 parser 或测试期望来迎合 Agent 的 UTC 默认值。Vite production build 使用 `NODE_OPTIONS=--max-old-space-size=3072`。只读内核证据确认原任务上限 4 GiB memory + 2 GiB swap 无法同时容纳完整 Vite build；标准 Docker backend 任务上限现为 6 GiB memory + 8 GiB memory+swap，并发仍为 1。该调整不跳过 build，也不增加 workflow 权限。
它不声明 secret、privileged、volume、Docker socket、发布或部署步骤。负向 canary
只允许临时 committed trailing whitespace，验证失败后删除并用同一完整检查集证明修复。

## 当前状态

- `woodpecker_runtime_ready`：由控制面仓库另行报告，本仓库文件不作证明。
- `repo_harness_ready=false`：候选已在 Woodpecker `/repos/22` 激活；前五次实际执行依次暴露 pnpm 版本、UTC 时区、Vite 默认堆上限与 4 GiB 任务资源不足，标准 Agent 资源修复已完成，尚未完成真实 success/failure/repair canary、独立 current-head Review 和合并后验证。
- `platform_gate_ready=false`：live context 尚未完成正负 canary，且未安装 required context。
- `actions_replacement_ready=false`：本候选不修改或停用 GitHub Actions。
