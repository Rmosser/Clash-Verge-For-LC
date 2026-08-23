# Clash Verge Rev v2.5.2 WebPort 迁移计划

### 状态与结论

- Status：`rainierdev_candidate_restored_pending_current_head_review`。方案 1 强化版、LPK v2
  打包迁移、exact-head 本地/Woodpecker、`rainierdev` API/UI 前向部署、LPK 验收、配对回滚
  演练与最终候选恢复均已通过；尚待本文件当前态提交后的 exact-head 复验、独立 Review、
  expected-head merge、main push 验证与分支清理。
- 当前只读基线：`main` / `origin/main` 均为
  `ab1331e0cd8120ca41e6c015a285b9c66b23721f`；实施开始前已重新 fetch/prune，worktree
  当时干净且只有一个 worktree。后续 PR/merge 前仍须重新 fetch/prune 并复核 exact head，
  不能把本记录当成未来远端真相。
- 迁移结论：`需要适配后迁移`，不得用官方源码直接覆盖当前 vendor。
- 官方目标固定为 release tag `v2.5.2`、commit
  `28f2efc504059b1dc75c793618b775c8e1b2a5f1`；拒绝 `dev`、`2.5.4` 或其他浮动 ref。
- 建议实施分支：`codex/clash-verge-rev-v2.5.2-webport`。
- 本文件是该迁移任务的按需实施计划，不承担全局 Active Plan 或机器 schema 职责。

### Progress

- 2026-08-23：执行 `git fetch --prune origin`；确认 `origin/main`、本地 `main` 和
  HEAD 均为 `ab1331e0cd8120ca41e6c015a285b9c66b23721f`，工作区干净且只有当前 worktree；
  已从该 exact head 创建 `codex/clash-verge-rev-v2.5.2-webport`。
- 2026-08-23：重新核对官方 release 页面与 `v2.5.2` tag，确认 exact commit 为
  `28f2efc504059b1dc75c793618b775c8e1b2a5f1`；未采用 `dev`、`v2.5.4` 或浮动 ref。
- 2026-08-23：在临时 staging 取得官方 `v2.4.7`（resolved commit
  `520a7ed83fda06b6507c46e51e16f737c58c7ddc`）和 `v2.5.2`（exact commit
  `28f2efc504059b1dc75c793618b775c8e1b2a5f1`），并完成临时 staging、固定 patch
  series 和 overlay-safe vendor 同步；最终 committed vendor 通过 `--verify`，未含
  `src-tauri`、`v1.19.29` 或 node_modules。
- 2026-08-23：完成 v2.5.2 WebPort 工具链：pnpm 11.3.0、Vite 8、TypeScript 6、React
  19.2.7、browser shims、runtime contract、system-proxy lock、profile health/last-good
  和合成 API/UI 测试；frozen install、typecheck、36 个前端 unit tests、49 个 Python
  tests、lint 和 production build 已通过。
- 2026-08-23：完成只允许 `rainierdev.heiyu.space` 的 API/runtime-contract 配对部署与
  opaque backup 回滚脚本；Gate 0 只读回读确认 host-native Mihomo `v1.19.30`、相关服务
  active、controller `172.18.0.1:9090`、Verge API `172.18.0.1:9091` 和 proxy
  `172.18.0.1:17890`，未执行生产或核心变更。
- 2026-08-23：functional candidate 提交为 `9bd79564bfe70214b4d0423f51e0d03e5bcc4f86`；
  release metadata 已绑定该 exact candidate，metadata commit 后必须重新执行全部本地门禁。
- 2026-08-23：PR #13 exact head `4da60740f6aaa0fef9be8ac192439e6174ce382a` 的 Woodpecker
  pipeline 39 成功，GitHub required context 为
  `ci/woodpecker/pr/woodpecker-harness`；同一 head 的 overlay verify、仓库测试、文档检查、
  pnpm 11.3.0 frozen install、typecheck、36 个前端 unit tests、lint、production build 和
  `git diff --check` 全部通过。workflow 中 Node 版本断言的 template literal 解析问题已修为
  字符串拼接后验证通过。
- 2026-08-23：Gate 0 在 `rainierdev` 再次确认 Mihomo `v1.19.30`、Mihomo
  `ActiveEnterTimestampMonotonic=129115776897`、Verge API health `200` 和相关 listener。
  首次 Gate A API/runtime-contract 配对部署时，远端 health probe 在 API 重启后连接被拒绝；
  专用脚本已自动恢复原 API、unit、runtime-contract 配对版本。回滚后 API health 为 `200`，
  Mihomo 版本和启动时间未变；按 Stop Condition 停止前向迁移，未部署 UI 或执行 LPK 安装。
- 2026-08-23：本 session 只读重验 `rainierdev`：Mihomo 完整版本仍为 `v1.19.30`，
  `ActiveEnterTimestampMonotonic=129115776897`，Verge API `NRestarts=0`，固定 listener
  `127.0.0.1:7890`、`172.18.0.1:9090/9091/17890` 均在，API health 为 `200`。
  API unit 是 `Type=simple`，而 Python 在 bind 前执行状态准备；结合上次“systemd 已 active、
  立即 curl connection refused、随后旧版本恢复健康”且没有 restart storm 的证据，最强解释是
  listener readiness window，而不是 Mihomo、bind 地址或持续 API crash。
- 2026-08-23：按方案 1 强化版把 API 配对部署改为最多 30 秒的 monotonic deadline：先验证
  `ActiveState` / `NRestarts`，再等待精确 `172.18.0.1:9091` listener，最后只做一次无 body
  health probe；candidate、显式回滚和自动恢复都拒绝 restart storm，并在成功/失败路径复核
  Mihomo binary 与启动时间。opaque backup 只接受脚本生成的 `backup.<8 alnum>`，远程参数采用
  有限字符集。故障注入覆盖 delayed readiness、timeout、service failure、health 后不稳定、
  rollback/restore restart storm、Mihomo drift、回滚失败和路径穿越。
- 2026-08-23：exact head `547cf03bd15a46969b525911f3d6788a9732911a` 的本地完整门禁与
  候选 LPK build/lint 通过；Woodpecker pipeline 41 在 readiness 用例已经输出 `deploy_ok`
  后因最小 CI 镜像没有测试断言所用的 `rg` 而失败。该失败不在 clone、产品代码或部署逻辑，
  仅把测试断言改用镜像已有的 `grep -E`；新 head 必须重新通过全部本地门禁和 required context。
- 2026-08-23：当前 `lzc-cli 2.0.9` 要求 LPK v2 package metadata；新增相邻
  `package.yml` 与 `en`/`zh` locale，把四条 routes/services 留在原 manifest，并把 icon 缩为
  `512x512` / `180768` bytes。`project lint` 无 warning，运行契约 hash
  `6daa4597d3e7751a6f86625b6335b2415c5d9ce09c1cff1d8c5e3b7dd6680f94` 与当前 HEAD、
  `origin/main` 相同；候选 LPK build/lint 通过，内层只含 295 个静态 Web 条目。
- 2026-08-23：拒绝安装旧 `output/release/0.2.0` 未知产物，因为它无法证明 source identity
  且不通过当前 LPK lint。改从 exact repo commit
  `e4a3db6644a5623143eadc1db5c41a34f4ed3838` 隔离重建 v2.4.7 baseline，产物为
  `output/rollback-baseline/e4a3db6-lpkv2/clash-verge-for-lc-0.2.0.lpk`，SHA-256
  `b758f1c4cb593343526f9c5d6a8565d9b2156a900deeb1241dade661f8eddeff`；project/lpk lint、
  frozen install 和 build 全通过，包内只有静态 Web 文件，不含 Mihomo、配置、订阅、密钥、
  数据库或运行态数据。
- 2026-08-23：exact head `d07187b8bfb3087af1a65723c9808b89352748a0` 重新通过全部本地
  门禁：docs、overlay verify、39 个 API 与 10 个 core updater Python tests、readiness
  故障注入、frozen install、typecheck、36 个前端 unit tests、lint、production build、
  shellcheck、静态边界扫描与候选 LPK build/lint/content audit。Woodpecker pipeline 42
  同一 exact head 的 required context `ci/woodpecker/pr/woodpecker-harness` 为 success。
- 2026-08-23：只在 `rainierdev` 完成 Gate A API-first 配对部署与 UI release deploy；部署后的
  API、unit、runtime contract 文件身份匹配候选，project `0.3.0`、app/fetchproxy health、
  静态入口、fetch health、Verge API health、四条既有 route 与 runtime contract 均通过。
  LazyCat 外部入口的四条路径均按预期由登录层保护；未连接生产环境。
- 2026-08-23：完成 Gate B exact candidate LPK 验收，候选 SHA-256 为
  `bf403c270d36e5b1bcbc669119e18416ab452545c9fe75c21382dfde187dc229`，大小
  `21797888` bytes，LPK v2 lint 通过；包内 295 个条目均为静态 Web 内容，不含 Mihomo、
  配置、订阅、密钥、数据库、native binary 或运行态数据。安装后 project `0.3.0` 与两个
  容器均 healthy。
- 2026-08-23：严格按版本对完成回滚演练：先用 opaque backup 恢复旧 API/unit/runtime
  contract 并确认 API health 与旧 contract 行为，再安装已证明身份的 baseline LPK
  `b758f1c4cb593343526f9c5d6a8565d9b2156a900deeb1241dade661f8eddeff`；project
  `0.2.0`、app/fetchproxy 与 API/fetch health 均通过。随后再次 API-first 部署候选配对版本，
  再安装 exact candidate LPK，最终恢复 project `0.3.0` 与候选 runtime contract。
- 2026-08-23：回滚与最终恢复前后，host-native Mihomo 始终为 `v1.19.30`，
  `ActiveEnterTimestampMonotonic=129115776897`、`NRestarts=0`，固定 listener、DNS listener
  计数与 TUN interface 计数均未漂移；没有重启/升级核心，没有修改 TUN、DNS、路由、Compose
  或 bootstrap。浏览器会话不可用，因此不声明 selector/视觉 UI smoke；UI 证据限定为 CLI、
  project/container status、静态入口、route、health 与 runtime contract 检查。

### Goal

- 将 vendored Clash Verge Rev 前端从 `v2.4.7` 迁移到官方稳定版 `v2.5.2`。
- 保留并重合并 LazyCat WebPort bootstrap、browser shims、runtime contract、profile
  last-good、日志、探针、系统代理锁和桌面能力降级等定制。
- 对齐官方 v2.5.2 Web 工具链，并在本地、Woodpecker、`rainierdev` 快循环和阶段性
  LPK 安装四层完成验收。
- 保持 host-native Mihomo `v1.19.30` 为唯一核心权威，不允许前端或上游 desktop
  代码降级、覆盖或重新接管核心。

### Non-Goals 与硬边界

- 不迁移上游内置 Mihomo `v1.19.29`、`src-tauri`、Rust service lifecycle、sidecar、
  desktop updater、tray、系统服务、UWP、全局热键或 OS-specific 网络实现。
- 不修改 `mihomo_core_updater.py`、`scripts/mihomo-manager` 或完整
  `scripts/deploy_microserver.sh` 的核心版本、升级、回滚和默认运行链路。
- 不修改 Mihomo 配置、TUN、DNS 开关、路由策略、LazyCat 网络绕行、Docker Compose
  或 host-native bootstrap enablement。
- 不读取、输出、保存或提交真实订阅、节点、token、controller secret、私有配置、LPK
  或运行态数据；测试只使用合成 fixture。
- 不连接或部署 `rainierspace`、`rainierserver` 或任何生产入口；本任务只允许
  `rainierdev` 开发机验证。
- 现有备份只作为回滚保障，不扩大授权范围。

### 固定版本与运行契约

- Dashboard app version：`2.5.2-webport.0`。
- LazyCat package version：`0.3.0`。
- `apiSchemaVersion` / `uiSchemaVersion`：`2026.08-lzc-v2`。
- `packageFingerprint`：
  `cloud.lazycat.app.clash-verge-for-lc/2.5.2-webport.0`。
- `buildId` / `gitCommit`：在 release metadata commit 中记录其前一笔已完整验证的
  functional candidate；metadata commit 后必须重新执行全套检查。
- `infra/microserver/mihomo-verge-api.service` 只更新前端 app version metadata；
  `MIHOMO_CORE_VERSION=v1.19.30`、bind、ExecStart、Restart 和 Install 语义保持不变。
- LazyCat 路由保持：
  - `/api/=http://host.lzcapp:9090`
  - `/verge-api/=http://host.lzcapp:9091`
  - `/fetch/=http://fetchproxy:3001`
  - `/=file:///lzcapp/pkg/content/`
- `systemProxy` 始终强制 `disabled`；浏览器不得获得宿主机系统代理、服务或核心控制权。

### Vendor 同步与 overlay 设计

1. 在 `src/mihomo-dashboard-app/vendor-overlays/clash-verge-rev/` 建立固定 upstream
   manifest、`series` 和有序 patch；manifest 至少记录 repository、ref、commit、
   sourcePath 和 overlay version。
2. 先从 pristine `v2.4.7` 提取当前 LazyCat 差异，按以下语义拆分 patch：
   - runtime bootstrap / runtime-contract；
   - browser Tauri shims；
   - profile import / health / last-good；
   - logs / runtime probes / delay / IP info；
   - system proxy disabled / desktop-only guards；
   - WebPort routing / health / degraded affordances；
   - API command compatibility 和必要 UI 定制。
3. `scripts/sync_clash_verge_rev.sh` 默认 `--verify`，只在临时 staging 中完成：
   - 校验 ref 是稳定 semver tag；
   - detached checkout exact commit；
   - 只导入官方 Web `src`、LICENSE、README；
   - 拒绝 `src-tauri`、Cargo、sidecar、core updater；
   - 应用 overlay 并运行必要检查；
   - 比较 staging 与 committed vendor。
4. 只有显式 `--apply` 且所有 patch/check 通过，才原子替换 vendor；任何 clone、commit
   校验、patch、typecheck、unit 或 build 失败都不得触碰现有 vendor。
5. vendor 记录 `UPSTREAM_VERSION=2.5.2`、完整 `UPSTREAM_COMMIT` 和
   `OVERLAY_VERSION`；不直接编辑 vendor 来“试试看”。

### Web 工具链迁移

- `packageManager` 固定为 `pnpm@11.3.0`；Node 运行门槛固定为 `>=22.22.0`。
- 对齐官方 Web 依赖：Vite 8、TypeScript 6、React/React DOM 19.2.7、MUI 9、
  React Router 8、TanStack React Virtual、SWR 2.4.x，以及 v2.5.2 使用的
  `qrcode.react`、`meta-json-schema` 等依赖。
- Vitest 升到与 Vite 8 兼容的 4.x；保留 WebPort 的 `test:unit` 和现有质量入口。
- `@vitejs/plugin-react-swc` 改为官方 `@vitejs/plugin-react`；legacy、SVGR、ESLint
  和 TypeScript types 按 v2.5.2 Web 构建栈更新。
- 删除新版源码不再引用的 `@mui/lab`、`@tanstack/react-table`、`react-virtuoso`、
  `axios` 和 SWC plugin；删除前先以 import scan 证明无引用。
- 新增 dashboard 目录级 `pnpm-workspace.yaml`，采用 pnpm 11 `allowBuilds`；初始
  allowlist 与上游 Web 构建一致，只按实际安装日志增加项目确实需要的包。
- 不复制上游 `type: module`，保持 `public/lzcapp-fetch-proxy.js` 的 CommonJS 运行契约。
- 锁文件必须由裁剪后的 WebPort package 使用 pnpm 11.3.0 重建，不得复制包含
  Tauri/desktop Git dependency 的官方 lockfile。
- 不把 `@tauri-apps/*`、Tauri CLI、`tauri-plugin-mihomo-api` 或 desktop release
  tooling 放入 package/lock；源码中的同名 import 继续由 Vite alias 与 TS paths 接管。
- Vite 8 配置采用官方 Safari 14 browser floor，同时保留 vendored root、`base: "./"`、
  publicDir、`lzcapp-config.js` 注入、LazyCat aliases、outDir、terser 和现有 polyfills。
- TS config 加入 `vite/client`、`vite-plugin-svgr/client`，覆盖 `import.meta.glob`、
  raw/worker imports 和 SVG `?react` 类型。
- Woodpecker 必须在 install 前验证 Node `>=22.22.0` 和 pnpm 精确 `11.3.0`；若现有
  pinned Node image 不满足，先更新到满足门槛的固定 digest。heap 先保持 3072 MiB，
  只有确认为 V8 OOM 时才升至 4096 MiB，并同步 workflow 与质量文档。

### 上游前端功能迁移

- 迁移代理组筛选、排序、批量延迟、快速定位、sticky group、独立滚动状态、provider
  节点延迟、隐藏组过滤和当前节点同步。
- 迁移连接页表格/虚拟列表和内存泄漏修复、首页 mode/version/traffic 状态修复、日志滚动、
  规则刷新、URI parser、订阅拖拽性能与 shared query/WebSocket visibility 管理。
- 迁移 TrustTunnel、OpenVPN、Tailscale、GostRelay 等节点类型展示和 URLTest 选择修复。
- 将现有 profile-health、last-good proxies、probe error taxonomy、日志历史/实时合并、
  system-proxy lock 和 runtime contract 阻断行为重合并到新版数据流。
- 官方 desktop service lifecycle 与 Rust Mihomo transport 明确跳过；仅迁移浏览器可用的
  query、WebSocket 和 API 通信改进。
- `fake-ip-range6` 只解析并无损 round-trip：字段不存在时 UI 保持空白且保存时省略，
  不注入默认值、不启用 DNS/IPv6/TUN；真正新增编辑/运行行为延期。

### Browser shim 与 API 接口决策

- Profile 命令统一使用：

  ```ts
  type ValidationOutcome =
    | { status: "valid" | "busy" }
    | { status: "invalid"; kind: string; message: string }
    | { status: "skipped"; reason: string };
  ```

- `patch_profiles_config`、`enhance_profiles`、`save_profile_file` 的 Python 实现返回上述
  outcome：成功为 `valid`，并发锁为 `busy`，验证失败为 `invalid` 且恢复旧文件/profile/
  runtime，transient-empty last-good 为 `skipped`。
- shim 继续接受旧后端的 `null`、`true` 和 `[boolean,message]`；
  `validate_dns_config` 保留旧数组返回，由 command boundary 归一化，避免破坏旧 UI。
- 新增 `get_clash_mode(): string | null`：先读有效 overlay mode，再退回 controller
  `/configs`；无法读取时返回 `null`。
- 新增 `get_runtime_proxy_group_order(): string[]`：按运行配置 `proxy-groups` 顺序返回；
  无有效运行配置时返回空数组。
- 新增 `clash_api_get_provider_proxy_delay`，由 Python 将 provider/proxy 分别 URL encode
  后请求 controller provider healthcheck；浏览器不得持有 controller 地址或 secret。
- 延迟结果兼容官方 `{delay}`，同时保留 `target/status/latencyMs/errorCode/errorMessage`；
  UI 必须区分 success、timeout、network_error 和 target_unreachable。
- `Traffic` 扩展 `upTotal/downTotal`；以 host-native Mihomo `/traffic` 返回的累计值为
  权威，缺字段时补 `0`，不得把瞬时速率在浏览器内累加或持久化。
- shim 对外接受官方大写 `LogLevel`，拼接 controller `/logs?level=` 时转换为小写，
  前端 `ILogItem.type` 保持既有规范。
- WebSocket `addListener()` 返回 unsubscribe；`close()` 清理 listener/实例，
  `cleanupAll()` 关闭全部连接；visibility/reconnect 不得遗留旧 listener 或清空 last-good。
- window/event shims 增加 `startResizeDragging`、`onFocusChanged`、generic `listen` 和
  `WINDOW_CLOSE_REQUESTED`：DOM 可表达的 focus 事件映射到浏览器，desktop-only 事件为
  明确 no-op/disabled，不模拟原生窗口 authority。
- `getVersion()` 始终读取 controller `/version`；`upgradeCore()` 始终经现有
  `/verge-api/invoke upgrade_core` 和 stable `v1.19.30` updater，不接受前端传入版本。

### Verge API 与订阅导入适配

- `infra/microserver/mihomo-verge-api.py` 增加上述只读命令、结构化 profile outcome、
  provider delay 和事务回退测试。
- `fetch_remote_profile()` 增加：
  - 按 `Content-Encoding: gzip` 或 gzip magic 解压，并在解压后再次执行 max-size 门禁；
  - 正确处理 `user:@host` 空密码 Basic Auth，发起请求前从 URL 移除 userinfo；
  - TLS handshake/protocol 失败映射为稳定 `PROFILE_FETCH_TLS_ERROR`；
  - 不关闭证书校验，不允许 TLS 1.0/1.1 降级；
  - redirect 到不同 origin 时不转发 Authorization；
  - 日志和错误 envelope 遮蔽 userinfo、token、query secret。
- 保持 HTML/login page、无有效 proxies/providers/groups/rules、timeout、HTTP、network
  拒绝行为，以及失败后 last-good runtime 不被清空。
- 新增单用途 `scripts/deploy_verge_api.sh`，而不是修改完整核心部署链：
  - 必须显式目标 `rainierdev.heiyu.space`，拒绝其他 host；
  - 不 source `.env`，不读取配置、订阅、controller/verge secret 或 MMDB；
  - 只备份/上传 `mihomo-verge-api.py`、API unit metadata 和 `runtime-contract.json`；
  - 只执行 `daemon-reload` 与 `restart mihomo-verge-api`，不 enable/disable 服务；
  - 只验证无敏感输出的 `/healthz`、`/runtime-info` 选定字段；
  - 失败时自动恢复三个文件并只重启 Verge API；输出可用于配对回滚的 opaque backup id。

### 自动化测试与本地验收

必须新增覆盖：

- overlay 可重放、拒绝 dev/错误 ref/commit、失败不覆盖 vendor；CI 使用本地 fixture，
  不依赖 GitHub 网络。
- ValidationOutcome 新旧返回归一化、busy、invalid 事务回退、transient-empty last-good。
- provider/proxy URL encode，以及 delay success、timeout、network、controller 4xx/5xx。
- Traffic totals 缺失/完整、LogLevel 映射、WebSocket 多订阅/可见性/重连/cleanup。
- gzip、Basic Auth 空密码、TLS 错误、跨 origin redirect 不泄漏 Authorization、错误脱敏。
- `fake-ip-range6` 缺失不写入、已有值无损 round-trip。
- runtime contract 成对匹配、systemProxy disabled、静态 icon/SVG/raw/worker 资源可构建。
- `upgrade_core` shim/backend 只在 mock 中验证，禁止 rainierdev smoke 真实执行升级。

本地与 CI 固定命令：

```bash
git diff --check origin/main...HEAD
python3 -I -B scripts/check_docs.py --all
bash scripts/test.sh

node -e 'const [a,b]=process.versions.node.split(".").map(Number); if (a<22||(a===22&&b<22)) process.exit(1)'
npm exec --yes --package=pnpm@11.3.0 -- pnpm --version
npm exec --yes --package=pnpm@11.3.0 -- pnpm --dir src/mihomo-dashboard-app install --frozen-lockfile
TZ=Asia/Shanghai npm exec --yes --package=pnpm@11.3.0 -- pnpm --dir src/mihomo-dashboard-app typecheck
TZ=Asia/Shanghai npm exec --yes --package=pnpm@11.3.0 -- pnpm --dir src/mihomo-dashboard-app test:unit
TZ=Asia/Shanghai npm exec --yes --package=pnpm@11.3.0 -- pnpm --dir src/mihomo-dashboard-app lint
NODE_OPTIONS=--max-old-space-size=3072 TZ=Asia/Shanghai \
  npm exec --yes --package=pnpm@11.3.0 -- pnpm --dir src/mihomo-dashboard-app build

bash scripts/sync_clash_verge_rev.sh --verify
! rg -n '@tauri-apps/|tauri-plugin-mihomo-api|v1\.19\.29' \
  src/mihomo-dashboard-app/package.json \
  src/mihomo-dashboard-app/pnpm-lock.yaml
```

- 本机缺少 Corepack 时使用上述 `npm exec`；Woodpecker 镜像若已验证 Corepack 可用，
  使用 exact `corepack pnpm@11.3.0`，并先断言输出为 `11.3.0`。
- frozen install 失败时修复 package/lock，不能删除 `--frozen-lockfile`；Tauri alias/type 错误
  通过 shim、Vite alias 和 TS paths 修复，不能安装真实 Tauri package。
- 只有实际 V8 heap OOM 才把 workflow heap 提升到 4096 MiB；不减少测试或 build 门禁。

### rainierdev 双阶段验证

#### Gate 0：目标与基线

```bash
lzc-cli --version
lzc-cli box list
lzc-cli box switch rainierdev
lzc-cli box default
ssh root@rainierdev.heiyu.space '
  /usr/local/bin/mihomo -v | head -n 1
  systemctl is-active mihomo.service mihomo-verge-api.service mihomo-container-proxy.socket
  systemctl show mihomo.service -p ActiveEnterTimestampMonotonic --value
  ss -lntp | grep -E "(:7890|:9090|:9091|:17890)" || true
'
```

- 记录 Mihomo service 启动时间、binary version 和监听，不读取配置或 secret。
- 必须看到 `rainierdev` READY、Mihomo `v1.19.30`、controller `172.18.0.1:9090`、
  Verge API `172.18.0.1:9091`、container proxy `172.18.0.1:17890`。
- 不运行当前会读取远端配置/secret 的 `scripts/selfcheck.sh`。

#### Gate A：开发快循环

1. exact candidate HEAD 的本地完整检查和 Woodpecker 已通过后，先用专用脚本部署
   API/runtime-contract 配对版本；API 失败时由脚本自动回滚，不能继续部署 UI。
2. 构建 dashboard 后执行：

   ```bash
   cd src/mihomo-dashboard-app
   lzc-cli project deploy --release
   lzc-cli project info
   lzc-cli docker -- ps
   ```

3. 从 `project info` 取得入口并断言属于 `rainierdev`；验证入口、容器 health、四条路由、
   runtime contract 和静态资源。默认不读取 raw project/app logs；失败证据若可能包含节点、
   URL 或 token，先停止并用无内容的 health/status 证据分层。

#### Gate B：阶段性 LPK 强制验收

```bash
cd src/mihomo-dashboard-app
lzc-cli project lint -f lzc-build.yml
LPK_OUT="$(mktemp -d)"
bash ../../scripts/build_dashboard_release.sh "$LPK_OUT"
LPK_FILE="$(find "$LPK_OUT" -name '*.lpk' -type f | head -n 1)"
lzc-cli lpk lint "$LPK_FILE"
lzc-cli lpk install "$LPK_FILE" --apk n
lzc-cli app status cloud.lazycat.app.clash-verge-for-lc
lzc-cli docker -- ps
```

- `build_dashboard_release.sh` 应改用 exact pnpm 11.3.0，并通过
  `lzc-cli project release -f lzc-build.yml -o <path>` 生成 LPK；产物只放临时目录，
  不提交、不上传生产。
- 校验 LPK、SHA-256、`INSTALL.md`、`build-info.txt`，并确认包内无 Mihomo binary、
  私有配置、订阅或运行态数据。
- `Installed/not yet realized` 是平台已知显示问题，不能单独判失败；结合容器 health 和
  入口可达性判断。
- 浏览器 smoke 只检查稳定 selector、状态类别和聚合计数，不记录节点名或订阅内容；真实
  import 不提交，真实 `upgrade_core` 不点击。代理筛选/排序/import transport 以合成测试为主。
- 最终再次检查 `/usr/local/bin/mihomo -v=v1.19.30`、Mihomo service 启动时间未变、
  监听地址未变、未新增 DNS listener/TUN interface。

### Stop Conditions

- 官方 ref 不是 exact `v2.5.2` commit，或同步路径包含 dev/2.5.4。
- package、lock、vendor、LPK 或 updater path 出现 Mihomo `v1.19.29`、Tauri core updater
  或新核心下载链路。
- `getVersion()` 不再来自 controller `/version`，或 `upgrade_core` 绕过 host-native updater。
- runtime contract、app version、fingerprint、API/UI schema 不能成对匹配。
- controller/API/WebPort 路由、监听或 LazyCat healthcheck 被上游覆盖。
- Mihomo service 被重启、binary 版本改变，或 TUN/DNS/路由/Compose/bootstrap 出现差异。
- 本地 frozen install、typecheck、unit、lint、build、文档、Woodpecker required context、
  independent Review 或 rainierdev LPK smoke 任一失败。
- 任何测试、日志、截图或 Git diff 暴露订阅、节点、token、secret、私有配置或运行态数据。

### Rollback

- 实施前验证现有 v2.4.7 baseline LPK、SHA-256 和 build metadata 可用；API 专用部署脚本
  在 rainierdev 保存 Python、unit metadata、runtime-contract 三文件配对备份。
- 回滚作为一个版本对执行：先用 opaque backup id 恢复 Verge API 三文件并只重启 API，
  再安装 v2.4.7 baseline LPK；短暂 contract blocked 页面可接受，混装后的继续操作不可接受。
- 回滚后验证 API health、入口、容器、`/usr/local/bin/mihomo -v=v1.19.30` 和 Mihomo
  service 启动时间未变。
- 不使用 `deploy_dashboard.sh --clean-reset`、完整 `deploy_microserver.sh` 或
  `mihomo-manager rollback-core` 作为前端回滚手段。
- 若发现 host-native runtime 被意外修改，立即停止前端回滚流程并将宿主机恢复作为独立、
  重新授权的任务处理；不得自动触碰生产机。

### Commit、PR 与完成标准

建议提交拆分：

1. `chore(vendor): make Clash Verge sync overlay-safe`
2. `feat(verge-api): add v2.5.2 WebPort compatibility`
3. `feat(frontend): rebase WebPort on Clash Verge Rev v2.5.2`
4. `chore(release): bump WebPort runtime and LPK contract`
5. `docs(plan): record v2.5.2 validation and rollback`

- 一个 focused branch、一个 PR；每笔功能提交保持其适用的仓库检查通过，最终 metadata
  commit 后重新运行全部门禁。
- PR exact HEAD 必须通过 `ci/woodpecker/pr/woodpecker-harness`、独立 current-head
  Codex Review `CLEAN / 0` 和 rainierdev LPK smoke；修复后所有证据重新绑定新 HEAD。
- 合并使用 expected-head squash merge；合并后确认 main push、同步本地 main，再删除本地/
  远端迁移分支。
- 完成标准：官方 v2.5.2 Web 前端、LazyCat overlay、WebPort API/runtime contract、
  pnpm 11/Vite 8 构建、rainierdev LPK 和 PR 门禁全部通过；host-native Mihomo 始终为
  `v1.19.30`，生产、TUN、DNS、路由、Compose 和 bootstrap 未被触碰。
