# 当前运行 Contract

这份文档定义仓库当前默认要表达的运行真相。其他文档如果和本页冲突，以本页为准。

## 适用范围

- 懒猫应用：`cloud.lazycat.app.clash-verge-for-lc`
- 宿主机运行时：`mihomo`、`mihomo-verge-api`、`mihomo-container-proxy`、可选的 `mihomo-container-proxy-pinned`
- 目标机器：`rainierdev.heiyu.space`、`rainierspace.heiyu.space`

## 固定术语

- `dashboard`：浏览器里的 Clash Verge Web 前端
- `controller`：Mihomo controller，监听 `172.18.0.1:9090`
- `Verge API`：懒猫 Web 版运行时后端，监听 `172.18.0.1:9091`
- `container proxy`：容器显式代理入口，监听 `172.18.0.1:17890`，跟随 `PROXY` 等规则选路
- `pinned container proxy`：可选的固定节点容器入口，监听 `172.18.0.1:17896`，转发到 Verge API overlay `lzc-pinned-listeners` 生成的 `127.0.0.1:7896` listener，始终只走指定节点

## 上游版本

- Dashboard 基于 Clash Verge Rev `v2.5.8`，WebPort `2.5.8-webport.0`，LPK `0.4.0`。
- Web adapter 将 controller 与活动 YAML 转换为上游 ProxyView v1，保留 provider 来源与同名节点顺序；配置 degraded 时保留最后成功快照。
- 运行状态来自宿主机 controller，系统代理、sidecar 和桌面服务安装保持禁用。
- Mihomo core 默认固定为稳定版 `v1.19.33`（2026-10-21 发布）。
- 核心升级仍通过共享 updater 校验 release digest、架构、版本与现有配置，并保留自动回滚。
- 仓库版本与目标机已安装版本分别核实；LPK 不包含宿主机核心。

## 当前推荐基线

仓库当前支持的保守基线是：

- `MIHOMO_TUN_ENABLE=0`
- `MIHOMO_DNS_ENABLE=0`
- `127.0.0.1:7890` 作为宿主机 mixed-port
- `172.18.0.1:9090` 作为 controller
- `172.18.0.1:9091` 作为 Verge API
- `172.18.0.1:17890` 作为容器显式代理入口
- 可选：`172.18.0.1:17896` 作为固定节点容器入口（`127.0.0.1:7896` listener 由 overlay 生成）

端口设置保存时同步 GUI 配置与运行覆盖层；可选端口的启用状态参与生成 Mihomo 配置，应用失败时恢复两份设置。

## 运行时恢复与健康契约

- `install_host_native_bootstrap.sh` 将宿主机文件（含 API 必需的 `mihomo_core_updater.py`）发布为不可变 generation；
  `current-generation`、`applied-generation` 和 `state/pending.env` 记录启动
  reconcile 边界。启动时优先校验并重启现有 live 配置，只有 live 配置缺失或
  校验失败才回退到完整 generation，避免把 snapshot 之后的配置静默覆盖。
- generation 应用先写 pending transaction、停止相关服务、完成独立 staging
  校验，再切换文件并验证 Mihomo controller 与 Verge API；进程在中途被杀时，
  下一次启动会依据 pending generation 重做完整应用，不把混代文件当作成功。
- 配置了 pinned listener 时，健康巡检每 5 分钟经 controller 的 delay 接口探测一次各 listener 的节点
  （`MIHOMO_PINNED_PROBE_URL`，默认 `https://www.gstatic.com/generate_204`）；连续 2 次失败记
  `pinned.<name>` 告警，恢复后记 ok。告警发件箱 `logs/alerts.jsonl` 与 `logs/alert-state.json`
  随 live 镜像持久化，重启后不重发已投递告警、不丢待发告警。
- 懒猫重启会重置 `/etc` 与 `/var/lib`。Verge API 把可变运行状态（`config.yaml`、
  不含 `logs/` 的 verge 目录、select 组的当前选择）镜像到
  `/root/.config/lzc-mihomo-bootstrap/live/`，每次成功应用配置后与每轮健康巡检时
  刷新，并记录基准 generation；bootstrap 应用同一 generation 时把通过校验的镜像
  覆盖上去，并在 controller 就绪后恢复节点选择。基准不一致或校验失败时只用
  generation，因此回滚到旧 generation 不会被镜像覆盖。
  镜像发布先持久化 staging，再切换目录；若切换中断，bootstrap 会对 `.live-old/`
  执行相同的 manifest 与 generation 校验并恢复上一份完整镜像。节点选择恢复请求
  失败时保留 pending transaction、返回失败并由启动服务重试；pending 存在期间
  API 不刷新镜像，避免默认选择覆盖待恢复的选择。
- `mihomo-resolved-sync.service` 每次 `apply` 都重新探测当前 IPv4 default-route
  interface；持久化 interface 只用于没有 default route 时的安全 revert，不能驱动
  新的 DNS assignment。
- `/healthz` 同时探测 Mihomo `/version` controller、restore transaction 和告警
  delivery channel；controller 或恢复事务异常、告警日志损坏、已配置告警的发送未确认时返回 HTTP 503。
  外部通知是可选能力：未配置时不阻止应用健康检查，Web 控制台明确显示未启用。Verge API 可按
  `/root/.config/lzc-mihomo-alerts/telegram.json`（Telegram bot，经宿主机 `127.0.0.1:7890` 发出，
  优先）或 `MIHOMO_ALERT_WEBHOOK_URL` 配置主动告警，所有状态转换和 delivery receipt 先
  fsync 到 `/var/lib/mihomo/verge/logs/alerts.jsonl`。启动及每次 append/flush 都会
  逐行恢复 JSONL；损坏行会被隔离并记录到同目录的
  `alerts.jsonl.corrupt.jsonl`，不会阻断后续有效告警，也不会与新 append 粘连。
  HTTP delivery 使用原告警 `id` 作为 `Idempotency-Key`，默认最多尝试 5 次、按
  60 秒起始退避且最多 3600 秒；未配置、待发送、持续失败、耗尽或 journal 损坏时，
  `/healthz` 和 `/runtime-info` 的 `alerting` 都是 `degraded`/`ready: false`。
  后台 watcher 由 `MIHOMO_HEALTH_WATCH_INTERVAL_SECONDS` 控制（默认 systemd 配置为
  60 秒）。

`scripts/deploy_microserver.sh` 的 host-native 默认值与该基线一致。为便于审阅和目标机区分，运维命令仍建议显式写出：

```bash
MICROSERVER_HOST=rainierdev.heiyu.space \
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 \
bash scripts/deploy_microserver.sh --confirm
```

## 浏览器访问 contract

- 用户入口始终是 `https://clash.<box>.heiyu.space`
- 浏览器通过 `/verge-api/public-config` 获取运行时配置
- 当前默认路径不需要手填 controller URL 或 controller secret
- `172.18.0.1:9090` 不对 LAN/WAN 暴露

## 容器出网 contract

- 不要假设 TUN 会自动代理 Docker 容器
- 容器默认走 `172.18.0.1:17890`，跟随用户在 dashboard 里选的 `PROXY`
- 需要固定出口的应用改走 `172.18.0.1:17896`；它只经过 overlay 指定的节点，节点缺失时连接失败，不回落到 `PROXY`
- `lzc-pinned-listeners` 保存在 Verge API overlay，随每次 profile 渲染写入 `listeners:`；bootstrap generation 用 `PINNED_PROXY_ENABLED` 记录 socket 是否启用，缺省视为 0
- pinned listeners 追加到 profile 原有列表，保留原入站选项与注释；同名或端口范围冲突会拒绝应用。
  支持 block/flow 列表和 mapping；列表别名、merge key 或 name/port 的别名应先展开为字面值。
  overlay 应用失败会恢复此前的 overlay；清空 pinned 列表不会删除 profile 自有 listeners。
- 具体环境变量和 Node.js 说明见 [CONTAINER_PROXY_GUIDE.md](CONTAINER_PROXY_GUIDE.md)

## 变更规则

- 任何重新启用 `TUN` 或 `DNS` 的改动都属于高风险网络改动
- 动手前先读 [LAZYCAT_NETWORK_REPORT.md](LAZYCAT_NETWORK_REPORT.md)
- 改完后必须验证：
  - `origin.lazycat.cloud` 相关 DNS 正常
  - dashboard 可访问
  - `lzc-cli box list` 保持 `READY`
  - 普通应用仍可 realize

## 快速止血

如果改动后出现控制面退化、应用拉不起来、dashboard 卡启动页，优先回到保守基线：

```bash
MICROSERVER_HOST=rainierdev.heiyu.space \
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 \
bash scripts/deploy_microserver.sh --confirm
```

如果已经拿到宿主机但需要立刻释放 TUN：

```bash
systemctl stop mihomo
```
