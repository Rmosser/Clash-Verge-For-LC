# Host-Native Runbook

这份文档只写当前宿主机运行链路的部署、恢复和验收。

## 适用范围

- `rainierdev.heiyu.space`
- `rainierspace.heiyu.space`

## 当前基线

仓库当前支持的保守基线是：

- `MIHOMO_TUN_ENABLE=0`
- `MIHOMO_DNS_ENABLE=0`
- `127.0.0.1:7890`：Mihomo mixed-port
- `172.18.0.1:9090`：controller
- `172.18.0.1:9091`：Verge API
- `172.18.0.1:17890`：container proxy
- 可选 `172.18.0.1:17896` → `127.0.0.1:7896`：pinned container proxy（见 [CONTAINER_PROXY_GUIDE.md](CONTAINER_PROXY_GUIDE.md#固定节点入口)）

`deploy_microserver.sh` 默认使用该保守基线。生产命令仍显式带环境变量，便于审阅并避免本地 `.env` 覆盖意图。

## 两台机器的差异

### `rainierdev`

- 已安装 root `user-systemd` bootstrap
- 已做真实 reboot 验证
- 冷启动后仍需要人工解锁磁盘

### `rainierspace`

- 已部署 root `user-systemd` bootstrap
- `2026-05-09` 排查到一次重启后自举失败：`172.18.0.1` bridge 在 10 秒内未出现，bootstrap 退出，导致宿主机运行链不能自动恢复
- 当前 bootstrap 已改为等待 bridge 最多 180 秒，并在失败后由 systemd 自动重试
- 还没有做新的真实 reboot 级强验证
- 当前可以视为“已部署、待重启验收”，不要视为“和开发机同级可靠”

## 标准部署

### 1. 重种宿主机基线

```bash
MICROSERVER_HOST=rainierdev.heiyu.space \
MIHOMO_TUN_ENABLE=0 \
MIHOMO_DNS_ENABLE=0 \
bash scripts/deploy_microserver.sh --confirm
```

用途：

- 下发 `/etc/mihomo/config.yaml`
- 下发 `mihomo.service`
- 下发 `mihomo-verge-api.service`
- 下发 `mihomo-container-proxy.socket` 与 `mihomo-container-proxy-pinned.socket`
- 恢复 `9090`、`9091`、`17890`、`17896` 运行链；它会覆盖 `config.yaml`，pinned listener 需通过 Verge API 重新渲染才会回来

### 2. 安装或重装 dashboard

```bash
MICROSERVER_HOST=rainierdev.heiyu.space \
LAZYCAT_BOX=rainierserver \
MIHOMO_DASHBOARD_URL=https://clash.rainierserver.heiyu.space \
bash scripts/deploy_dashboard.sh --confirm
```

## Mihomo core-only 升级

core-only 路径不重写配置、systemd unit、TUN、DNS 或 container proxy，只更新
共享 updater、Verge API 和 Mihomo 二进制。当前固定 stable 版本为 `v1.19.33`。

先升级开发机：

```bash
MICROSERVER_HOST=rainierdev.heiyu.space \
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 \
bash scripts/deploy_microserver.sh --confirm \
  --upgrade-core --only-core --core-version v1.19.33
```

通过开发机验收后，对 `rainierspace` 使用相同的显式版本命令。updater 会在
`/var/lib/mihomo/rollback/` 保存旧二进制、asset SHA256 和状态；下载校验、
`mihomo -t`、systemd active 或 controller `/version` 失败时自动回滚。

手动回滚：

```bash
bash scripts/mihomo-manager rollback-core --confirm
```

升级后至少检查：

```bash
systemctl is-active mihomo.service mihomo-verge-api.service mihomo-container-proxy.socket
curl -fsS -H "Authorization: Bearer <secret>" http://172.18.0.1:9090/version
curl -fsS http://172.18.0.1:9091/healthz
bash scripts/selfcheck.sh
```

## 开机自举

### 开发机

前提：先把开发机种成健康基线。

```bash
MICROSERVER_HOST=rainierdev.heiyu.space \
bash scripts/install_host_native_bootstrap.sh --confirm
```

### 生产机

```bash
MICROSERVER_HOST=rainierspace.heiyu.space \
bash scripts/install_host_native_bootstrap.sh --confirm
```

这条路径当前已部署，但还没做真实 reboot 验证。

自举状态保存在 `/root/.config/lzc-mihomo-bootstrap/`：

- `generations/<generation>/` 是完整、校验过的候选；`current-generation` 是原子
  发布指针；`applied-generation` 是最后一次完整验收的 generation。
- `state/pending.env` 表示文件切换尚未完成。若 bootstrap 在切换中被杀，下一次
  启动会保留 pending 状态并从同一 generation 新建 staging，完成全量校验后再
  启动服务。
- 启动会先尝试重启并验收当前 live 配置；只有 live 配置缺失或校验失败才使用
  generation 恢复。懒猫真实重启会重置 `/etc` 与 `/var/lib`，live 配置必然缺失，
  所以重启后总是走 generation 路径。
- 为了不让重启丢掉 snapshot 之后的改动，Verge API 在每次成功应用配置后、以及每轮
  健康巡检（默认 60 秒）里，把 `config.yaml`、`/var/lib/mihomo/verge`（不含
  `logs/`）和各 select 组当前选中的节点镜像到持久的 `live/`，并记下镜像所基于的
  generation。generation 恢复时，只有镜像完整、manifest 校验通过且基准等于当前
  generation，才会覆盖上去并在 controller 就绪后恢复节点选择；镜像校验失败则按
  generation 原样启动。改动后约 60 秒内才进入镜像，重新安装 bootstrap 会产生新
  generation，旧镜像随之失效、直到下一轮巡检重写。

### 健康与告警

`/healthz` 只有在 Verge API、Mihomo controller `/version` 且没有未决 restore
transaction 时才返回 200；controller 不可达或恢复状态未知时返回 503。API
会在 `/var/lib/mihomo/verge/logs/alerts.jsonl` 保留可重放的告警 outbox，并按
状态转换和 cooldown 去重。需要主动投递时，在 root systemd drop-in 中设置
`MIHOMO_ALERT_WEBHOOK_URL`，并保留 `MIHOMO_HEALTH_WATCH_INTERVAL_SECONDS` 的
轮询间隔；不要把 webhook secret 写进仓库。

## 重启后的验收

### `rainierdev`

先人工解锁磁盘，再运行受身份守卫的只读自检：

```bash
MICROSERVER_HOST=rainierdev.heiyu.space bash scripts/selfcheck.sh
```

健康标准：

- `Linger=yes`
- `lzc-mihomo-bootstrap.service` 为 `active`
- 三个宿主机服务都为 `active`
- 四个监听都出现；启用了 pinned 入口时还应有 `172.18.0.1:17896` 与 `127.0.0.1:7896`

### `rainierspace`

生产机先看宿主机运行链是否还在：

```bash
MICROSERVER_HOST=rainierspace.heiyu.space bash scripts/selfcheck.sh
```

如果失败，优先走“重种宿主机基线 + 重装 dashboard”，不要先做零散修补。

## 排障顺序

### 页面停在 `starting`

先查：

- `mihomo.service`
- `mihomo-verge-api.service`
- `172.18.0.1:9090`
- `172.18.0.1:9091`

### `17890` 不在

先查：

- `systemctl status mihomo-container-proxy.socket`
- `journalctl -u mihomo-container-proxy.socket -b`

### `17896` 不通或出口不对

先查：

- `systemctl status mihomo-container-proxy-pinned.socket`
- `ss -lnt | grep 127.0.0.1:7896`：没有说明 overlay 的 `lzc-pinned-listeners` 未渲染进 `config.yaml`
- `grep -A6 '^listeners:' /etc/mihomo/config.yaml` 里的 `proxy:` 是否还在当前订阅中

### `9090` 不在

先查：

- `systemctl status mihomo.service`
- `journalctl -u mihomo.service -b`

### `9091` 在但 `9090` 不在

结论直接收敛为：前端 sidecar 还活着，真正坏的是 Mihomo controller。

## 快速止血

最保守的止血命令：

```bash
MICROSERVER_HOST=rainierdev.heiyu.space \
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 \
bash scripts/deploy_microserver.sh --confirm
```

如果已经在宿主机上，且要立刻释放 TUN：

```bash
systemctl stop mihomo
```
