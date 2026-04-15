# Host-Native Runbook

这份文档只写当前宿主机运行链路的部署、恢复和验收。

## 适用范围

- `rainierdev.heiyu.space`
- `rainierspace.heiyu.space`

## 当前基线

截至 `2026-04-15`，当前推荐和已验证基线是：

- `MIHOMO_TUN_ENABLE=0`
- `MIHOMO_DNS_ENABLE=0`
- `127.0.0.1:7890`：Mihomo mixed-port
- `172.18.0.1:9090`：controller
- `172.18.0.1:9091`：Verge API
- `172.18.0.1:17890`：container proxy

注意：`deploy_microserver.sh` 的脚本默认值仍是 `TUN=1`、`DNS=1`。要落当前基线，必须显式带环境变量。

## 两台机器的差异

### `rainierdev`

- 已安装 root `user-systemd` bootstrap
- 已做真实 reboot 验证
- 冷启动后仍需要人工解锁磁盘

### `rainierspace`

- 已部署 root `user-systemd` bootstrap
- 还没有真实 reboot 级强验证
- 当前可以视为“已部署、待重启验收”，不要视为“和开发机同级可靠”

## 标准部署

### 1. 重种宿主机基线

```bash
MICROSERVER_HOST=<box>.heiyu.space \
MIHOMO_TUN_ENABLE=0 \
MIHOMO_DNS_ENABLE=0 \
bash scripts/deploy_microserver.sh
```

用途：

- 下发 `/etc/mihomo/config.yaml`
- 下发 `mihomo.service`
- 下发 `mihomo-verge-api.service`
- 下发 `mihomo-container-proxy.socket`
- 恢复 `9090`、`9091`、`17890` 运行链

### 2. 安装或重装 dashboard

```bash
MICROSERVER_HOST=<box>.heiyu.space \
LAZYCAT_BOX=<boxname> \
MIHOMO_DASHBOARD_URL=https://clash.<boxname>.heiyu.space \
bash scripts/deploy_dashboard.sh
```

## 开机自举

### 开发机

前提：先把开发机种成健康基线。

```bash
MICROSERVER_HOST=rainierdev.heiyu.space \
bash scripts/install_host_native_bootstrap.sh
```

### 生产机

```bash
MICROSERVER_HOST=rainierspace.heiyu.space \
bash scripts/install_host_native_bootstrap.sh
```

这条路径当前已部署，但还没做真实 reboot 验证。

## 重启后的验收

### `rainierdev`

先人工解锁磁盘，再验：

```bash
ssh root@rainierdev.heiyu.space '
  loginctl show-user root -p Linger -p State
  systemctl --user is-active lzc-mihomo-bootstrap.service
  systemctl is-active mihomo.service mihomo-verge-api.service mihomo-container-proxy.socket
  ss -lntp | grep -E "(:7890|:9090|:9091|:17890)" || true
'
```

健康标准：

- `Linger=yes`
- `lzc-mihomo-bootstrap.service` 为 `active`
- 三个宿主机服务都为 `active`
- 四个监听都出现

### `rainierspace`

生产机先看宿主机运行链是否还在：

```bash
ssh root@rainierspace.heiyu.space '
  systemctl is-active mihomo.service mihomo-verge-api.service mihomo-container-proxy.socket
  ss -lntp | grep -E "(:7890|:9090|:9091|:17890)" || true
'
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

### `9090` 不在

先查：

- `systemctl status mihomo.service`
- `journalctl -u mihomo.service -b`

### `9091` 在但 `9090` 不在

结论直接收敛为：前端 sidecar 还活着，真正坏的是 Mihomo controller。

## 快速止血

最保守的止血命令：

```bash
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 bash scripts/deploy_microserver.sh
```

如果已经在宿主机上，且要立刻释放 TUN：

```bash
systemctl stop mihomo
```
