# 当前运行 Contract

这份文档定义仓库当前默认要表达的运行真相。其他文档如果和本页冲突，以本页为准。

## 适用范围

- 懒猫应用：`cloud.lazycat.app.clash-verge-for-lc`
- 宿主机运行时：`mihomo`、`mihomo-verge-api`、`mihomo-container-proxy`
- 目标机器：`rainierdev.heiyu.space`、`rainierspace.heiyu.space`

## 固定术语

- `dashboard`：浏览器里的 Clash Verge Web 前端
- `controller`：Mihomo controller，监听 `172.18.0.1:9090`
- `Verge API`：懒猫 Web 版运行时后端，监听 `172.18.0.1:9091`
- `container proxy`：容器显式代理入口，监听 `172.18.0.1:17890`

## 当前推荐基线

截至 `2026-04-15`，当前已验证基线是：

- `MIHOMO_TUN_ENABLE=0`
- `MIHOMO_DNS_ENABLE=0`
- `127.0.0.1:7890` 作为宿主机 mixed-port
- `172.18.0.1:9090` 作为 controller
- `172.18.0.1:9091` 作为 Verge API
- `172.18.0.1:17890` 作为容器显式代理入口

注意：

- `scripts/deploy_microserver.sh` 的脚本默认值仍是 `TUN=1`、`DNS=1`
- 但当前仓库推荐和已验证基线不是脚本默认值
- 要落当前基线，显式执行：

```bash
MICROSERVER_HOST=<box>.heiyu.space \
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 bash scripts/deploy_microserver.sh
```

## 浏览器访问 contract

- 用户入口始终是 `https://clash.<box>.heiyu.space`
- 浏览器通过 `/verge-api/public-config` 获取运行时配置
- 当前默认路径不需要手填 controller URL 或 controller secret
- `172.18.0.1:9090` 不对 LAN/WAN 暴露

## 容器出网 contract

- 不要假设 TUN 会自动代理 Docker 容器
- 容器统一走 `172.18.0.1:17890`
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
MICROSERVER_HOST=<box>.heiyu.space \
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 bash scripts/deploy_microserver.sh
```

如果已经拿到宿主机但需要立刻释放 TUN：

```bash
systemctl stop mihomo
```
