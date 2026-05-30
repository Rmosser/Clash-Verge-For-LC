# 懒猫网络变更约束

这份文档只定义一件事：什么时候可以改 `TUN` / `DNS`，以及改完必须验证什么。

## 当前策略

- 当前默认和已验证基线是 `TUN=0`、`DNS=0`
- 重新启用 `TUN` 或 `DNS` 不是日常配置动作，而是高风险网络改动
- 任何高风险改动都要先能回退到 [CURRENT_RUNTIME.md](CURRENT_RUNTIME.md) 里的保守基线

## 为什么高风险

懒猫控制面、origin 建链、应用 realize、容器 bridge 网络和普通宿主机代理不是同一条链。`TUN` / `DNS` 一旦改错，影响的不只是 Clash 自己，还可能直接把：

- `lzc-cli box list`
- `origin.lazycat.cloud`
- 懒猫应用 realize
- dashboard 到 controller 的访问链

一起打坏。

## 不可删的绕行对象

### 域名

- `.heiyu.space`
- `.lazycat.cloud`

### 地址

- `6.6.6.6/32`
- `2000::6666/128`
- `fc03:1136:3800::/40`

### 本地与容器网络

- `127.0.0.0/8`
- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`
- `169.254.0.0/16`
- `100.64.0.0/10`
- `::1/128`
- `fc00::/7`
- `fe80::/10`
- `ff00::/8`
- 当前盒子上的容器 bridge CIDR

### 已观测到的 NAT/STUN 探测地址

当前代码和运行时里已经纳入的地址：

- `45.63.83.38/32`
- `45.32.130.255/32`
- `95.179.192.146/32`
- `139.84.241.187/32`
- `141.11.139.150/32`
- `110.42.109.179/32`
- `183.136.206.164/32`
- `114.66.59.177/32`
- `110.42.42.48/32`
- `139.180.182.231/32`
- `45.32.239.193/32`
- `107.172.76.12/32`

## 改动前要求

满足以下条件后再动：

1. 你已经能 SSH 到目标机器
2. 你知道如何执行保守基线回退：

```bash
MICROSERVER_HOST=<box>.heiyu.space \
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 bash scripts/deploy_microserver.sh
```

3. 你知道 `lzc-net-safe-apply` 的 DNS 自动回滚流程

## 改动后必须做的验证

### 基础服务

- `systemctl is-active mihomo.service`
- `curl -fsS -H "Authorization: Bearer <secret>" http://172.18.0.1:9090/version`
- `curl -fsS http://172.18.0.1:9091/public-config`

### 路由与绕行

- `ip route get 6.6.6.6`
- `ip -6 route get 2000::6666`
- `ip -6 route get fc03:1136:3800::1`

### DNS

如果启用了 `DNS=1`，至少验证：

- `dig TXT _dnsaddr.origin.lazycat.cloud @127.0.0.1 -p 1053`
- `dig TXT _dnsaddr.origin.lazycat.cloud @127.0.0.53`
- `dig AAAA www.baidu.com @127.0.0.1 -p 1053`

### 平台链路

- `lzc-cli box list` 仍是 `READY`
- `https://clash.<box>.heiyu.space` 可访问
- 普通应用仍可 realize
- 手机端诊断不再报 `origin` / 注册服务异常

## DNS 安全应用流程

改 DNS 时，优先走自动回滚工具：

```bash
export LZC_NET_ROLLBACK_DNS="192.168.1.1 fe80::1"
lzc-net-safe-apply apply-dns <iface> 223.5.5.5 119.29.29.29
```

外部验证通过后再确认：

```bash
lzc-net-safe-apply confirm
```

## 历史复盘入口

需要历史案例和证据时再看：

- [planning/2026-02-14-ai-domains-connectivity-postmortem.md](planning/2026-02-14-ai-domains-connectivity-postmortem.md)
- [planning/2026-03-12-clash-post-deploy-network-incident.md](planning/2026-03-12-clash-post-deploy-network-incident.md)
