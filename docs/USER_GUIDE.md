# 用户指南 | User Guide

懒猫微服版 Clash Verge（Clash for LC）完整操作参考。
Complete usage reference for Clash for LC (LazyCat-adapted Clash Verge).

---

## 产品定位 | What Is Clash for LC

Clash for LC 是一个运行在**懒猫微服**上的 Web 应用，让你通过浏览器管理 Mihomo (Clash Meta) 代理——不需要在 PC/Mac 上安装任何桌面客户端。
Clash for LC is a web app that runs on your **LazyCat microserver**, letting you manage Mihomo (Clash Meta) from any browser — no desktop client needed.

它不是从零实现的代理核心或面板，而是把以下上游项目适配到 LazyCat 场景：
It does not reimplement the proxy engine or dashboard; it adapts the following upstream projects to LazyCat:

- [clash-verge-rev/clash-verge-rev](https://github.com/clash-verge-rev/clash-verge-rev) — Verge 前端 UI
- [MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo) — 代理核心（运行在微服宿主机）
- [MetaCubeX/metacubexd](https://github.com/MetaCubeX/metacubexd) — Mihomo 官方 Web Dashboard

本仓库的增量是：LazyCat 部署适配、ingress 鉴权、TUN 安全绕行配置。
This repo's contribution: LazyCat deployment adapter, ingress auth, and TUN safety bypass configuration.

---

## 开始之前 | Before You Start

开始前请确认以下几项：
Before starting, confirm:

- [ ] 懒猫微服在线且网络正常。 / LazyCat microserver is online and reachable.
- [ ] 你有一个代理订阅链接（来自机场或其他服务商）。 / You have a proxy subscription URL (from your provider).
- [ ] 使用现代浏览器（Chrome / Firefox / Safari 最新版）。 / You're using a modern browser (latest Chrome, Firefox, or Safari).
- [ ] 已在懒猫微服上安装 Clash for LC 应用（LPK）。 / The Clash for LC app (LPK) is installed on your microserver.

无需命令行操作，无需在本地运行任何脚本。
No CLI access or local scripts required for day-to-day use.

---

## 首次设置 | First-Time Setup

### 第一步：打开面板 | Open the Dashboard

在浏览器中访问：
Open in your browser:

```
https://clash.<your-box-name>.heiyu.space
```

用懒猫账号登录。登录后，面板会自动连接到微服上的 Mihomo 控制器，无需手动填写 API 地址或密钥。
Log in with your LazyCat account. The dashboard connects to the Mihomo controller automatically — no API URL or secret needed.

### 第二步：导入订阅 | Import Your Subscription

1. 点击左侧导航的 **Proxies（代理）**。
   Click **Proxies** in the left nav.
2. 点击右上角 **+** 或"添加订阅"，粘贴你的订阅 URL。
   Click **+** or "Add subscription", paste your subscription URL.
3. 点击"更新"拉取节点列表。
   Click "Update" to fetch the node list.

> **SubHub 用户注意**：请使用 SubHub 的直出 YAML 订阅链接，例如 `/sub/device/<token>/clash.yaml?profile=lazycat`。不要把需要懒猫登录的 SubHub 页面地址粘贴到订阅框——那会导致 401 或 HTML 响应而非 YAML。如果微服从 `*.heiyu.space` 拉取大订阅超时，先在浏览器下载 YAML 文件，再通过拖拽导入。
> **SubHub users**: Use the direct YAML export URL (e.g., `/sub/device/<token>/clash.yaml?profile=lazycat`), not the SubHub web page URL. If fetching times out over `*.heiyu.space`, download the YAML in your browser first, then drag-and-drop it into the dashboard.

### 第三步：选择代理分组 | Select a Proxy Group

1. 在 **Proxies** 页面找到你的代理分组（通常是"全局"或"自动选择"）。
   Find your proxy group on the **Proxies** page (typically "Global" or "Auto Select").
2. 选择一个节点或让自动测速选择最优节点。
   Pick a node, or let auto-latency testing select the best one.
3. 打开 [https://ip.sb](https://ip.sb) 或类似工具，确认出口 IP 已切换。
   Open [https://ip.sb](https://ip.sb) and confirm your IP has changed.

---

## 日常使用 | Daily Usage

### 切换节点 | Switching Nodes

在 **Proxies** 页面直接点击节点卡片，或使用右上角的延迟测速按钮重新测速后让自动分组切换。
Click any node card on the **Proxies** page, or use the latency test button to re-rank and auto-switch.

### 更新订阅 | Updating Subscriptions

在 **Proxies** 页面的订阅卡片上点击"更新"图标，或开启自动更新（建议每 24 小时）。
Click the refresh icon on your subscription card, or enable auto-update (recommended: every 24 hours).

### 查看日志 | Viewing Logs

进入 **Logs** 页面，可以查看实时连接日志和规则匹配结果，帮助排查哪些流量走了哪条规则。
Go to the **Logs** page to see real-time connection logs and rule-match results.

### 查看当前连接 | Viewing Connections

**Connections** 页面显示当前活跃连接，可以手动关闭异常连接。
The **Connections** page shows active connections; you can close any stuck connection manually.

---

## Web 版与桌面版对比 | Web vs Desktop

| 特性 | Clash for LC（Web 版） | 桌面版 Clash Verge |
|------|----------------------|-------------------|
| 运行环境 | 懒猫微服宿主机 | 本地 PC/Mac |
| 访问方式 | 浏览器，`https://clash.<box>.heiyu.space` | 本机 GUI 应用 |
| 安装要求 | 无需本地安装，LPK 安装在微服 | 需要在每台电脑上安装 |
| 系统代理 (System Proxy) | **不可用**（灰色，桌面专属） | 可用 |
| TUN 透明代理 | 由微服侧管理，默认开启，Dashboard 显示状态 | 可在 GUI 手动开关 |
| 轻量模式 (Lightweight Mode) | **不可用** | 可用 |
| UWP Tool | **不可用** | 可用（Windows 版） |
| 文件导入 | URL 订阅或拖拽上传 | 本地文件路径 |
| Controller 访问 | 通过 LazyCat 应用路由（不暴露端口） | 直接监听本机端口 |
| 安全模型 | 依赖懒猫登录鉴权，controller secret 由微服管理 | 依赖本地 secret，端口可被本机程序访问 |

**灰色选项说明 / Why options are greyed out**：桌面专属功能（System Proxy、轻量模式、UWP Tool）需要操作桌面系统服务，而 Clash for LC 运行在浏览器沙箱中，无法调用这些能力。这不是 bug，是设计边界。TUN 代理在微服侧已由部署配置管理，不需要从 Dashboard 手动控制。

---

## Docker 应用如何使用代理 | Docker Apps and Proxy

> **🔧 技术细节 | Technical Detail** — 普通用户可以跳过本节。
> **🔧 Technical Detail** — Casual users can skip this section.

### 为什么 TUN 不会自动代理容器 | Why TUN Doesn't Auto-Proxy Containers

Mihomo 的 TUN 透明代理接管的是宿主机路由表，而 Docker 容器通过独立的 bridge 网络出网。TUN 的 `route-exclude-address` 会排除容器网段（`172.18.0.0/16` 等），以防止服务发现流量被误代理。因此，容器出网需要显式配置代理，而不是依赖 TUN。

TUN transparent proxy intercepts the host routing table, but Docker containers use separate bridge networks. Container subnets are in the TUN bypass list to prevent service-discovery traffic from being misrouted. Container egress therefore needs explicit proxy config, not TUN.

### 代理入口 | Proxy Endpoint

微服宿主机上运行着一个 `systemd-socket-proxyd` 转发服务，把以下地址暴露给容器网络：

The microserver runs a `systemd-socket-proxyd` relay that exposes:

```
http://172.18.0.1:17890
```

这个地址把流量转发到宿主机上的 `127.0.0.1:7890`（Mihomo mixed-port），容器可以访问，LAN/WAN 不可访问。

This relays to `127.0.0.1:7890` (Mihomo mixed-port) on the host — accessible to containers, not to LAN/WAN.

### 环境变量（复制即用）| Env Vars (Copy-Paste Ready)

在需要出网的容器中设置以下 6 个环境变量：
Set all 6 in any container that needs outbound access:

```bash
HTTP_PROXY=http://172.18.0.1:17890
HTTPS_PROXY=http://172.18.0.1:17890
http_proxy=http://172.18.0.1:17890
https_proxy=http://172.18.0.1:17890
NO_PROXY=localhost,127.0.0.1,::1,.heiyu.space,.lazycat.cloud,172.18.0.1
no_proxy=localhost,127.0.0.1,::1,.heiyu.space,.lazycat.cloud,172.18.0.1
```

### NO_PROXY 说明 | NO_PROXY Entries Explained

| 条目 | 原因 |
|------|------|
| `localhost`, `127.0.0.1`, `::1` | 本机回环，不需要代理 / Loopback — no proxy needed |
| `.heiyu.space` | 懒猫平台域名，应直连 / LazyCat platform domains — must be direct |
| `.lazycat.cloud` | 懒猫控制面域名，应直连 / LazyCat control-plane — must be direct |
| `172.18.0.1` | 代理入口本身，避免代理套代理 / The proxy relay itself — avoid loop |

> 使用域名/主机名白名单而非 CIDR，是因为部分运行时（如 Node.js）对 CIDR 格式的 NO_PROXY 支持不完整。
> Domain/hostname entries are used instead of CIDR because some runtimes (e.g., Node.js) have incomplete CIDR support in NO_PROXY.

### Docker Compose 示例 | Docker Compose Example

```yaml
services:
  my-app:
    image: my-app:latest
    environment:
      - HTTP_PROXY=http://172.18.0.1:17890
      - HTTPS_PROXY=http://172.18.0.1:17890
      - http_proxy=http://172.18.0.1:17890
      - https_proxy=http://172.18.0.1:17890
      - NO_PROXY=localhost,127.0.0.1,::1,.heiyu.space,.lazycat.cloud,172.18.0.1
      - no_proxy=localhost,127.0.0.1,::1,.heiyu.space,.lazycat.cloud,172.18.0.1
```

### Node.js fetch 注意事项 | Node.js fetch Caveat

Node.js 内置 `fetch`（基于 undici）默认不一定遵守 `HTTP(S)_PROXY` 环境变量。如果你的容器运行 Node.js 应用且出现直连失败，需要在启动时注入一个 undici bootstrap。

Node.js built-in `fetch` (undici) may not honor `HTTP(S)_PROXY` by default. If your Node.js container shows direct-connect failures, you need a bootstrap that injects `undici.EnvHttpProxyAgent` at startup.

详见 [docs/LAZYCAT_NETWORK_REPORT.md §8.4](LAZYCAT_NETWORK_REPORT.md#84-容器出网标准做法显式代理) 中的最小 bootstrap 示例。
See [docs/LAZYCAT_NETWORK_REPORT.md §8.4](LAZYCAT_NETWORK_REPORT.md#84-容器出网标准做法显式代理) for the minimal bootstrap pattern.

---

## 常见问题排查 | Troubleshooting

### Dashboard 里系统代理、TUN 开关是灰色的 | Desktop options are greyed out

**原因**：这些是桌面专属功能，Web 版不支持，这是预期行为。
**处理**：不需要处理。TUN 已由微服侧配置管理，日常无需在 Dashboard 操作。

**Cause**: These are desktop-only features; the web version intentionally does not support them.
**Action**: Nothing to do. TUN is managed server-side and is already active.

---

### TUN 开启了，但容器访问被封锁的站点仍然失败 | TUN on but container can't reach blocked sites

**原因**：TUN 不自动代理 Docker 容器流量（容器网段被 bypass）。
**处理**：按本指南"Docker 应用如何使用代理"一节，给容器设置 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量。

**Cause**: TUN bypass list excludes container subnets by design.
**Action**: Add the 6 proxy env vars to your container as shown in the Docker section above.

---

### 浏览器访问正常，但 Docker 应用出网失败 | Browser works but Docker app fails

**原因**：浏览器流量经过宿主机网络栈，TUN 可以拦截；Docker 容器通过 bridge 出网，TUN 不覆盖。
**处理**：给 compose 服务加上代理环境变量（见上方 Docker Compose 示例）。

**Cause**: Browser traffic goes through the host network stack (TUN covers it); Docker containers go through bridge networks (TUN doesn't).
**Action**: Add proxy env vars to your compose service.

---

### Node.js 应用设置了 HTTPS_PROXY 但仍然直连失败 | Node.js ignores proxy env vars

**原因**：Node.js 内置 `fetch` 不自动读取代理环境变量。
**处理**：在启动脚本中用 `NODE_OPTIONS=--require ./proxy-bootstrap.cjs` 注入 undici `EnvHttpProxyAgent`。详见 [LAZYCAT_NETWORK_REPORT.md §8.4](LAZYCAT_NETWORK_REPORT.md#84-容器出网标准做法显式代理)。

**Cause**: Node.js built-in `fetch` does not automatically read proxy env vars.
**Action**: Inject undici `EnvHttpProxyAgent` via `NODE_OPTIONS=--require ./proxy-bootstrap.cjs`. See §8.4 of the network report.

---

### 想直接访问 9090 端口 | Tempted to expose port 9090

**请不要这样做。**Controller 端口（`172.18.0.1:9090`）仅在微服内部 bridge 上监听，通过 LazyCat 应用路由访问，已经通过懒猫登录鉴权保护。把它暴露到 LAN/WAN 会绕过鉴权，让任何人都能控制你的代理。

**Don't do this.** The controller (`172.18.0.1:9090`) is only accessible inside the microserver via the LazyCat app route, which is protected by your LazyCat login. Exposing it to LAN/WAN bypasses authentication and lets anyone control your proxy.

使用 `https://clash.<box>.heiyu.space` 访问面板即可。
Use `https://clash.<box>.heiyu.space` — that's the intended access point.

---

### 修改 TUN 配置后懒猫连接变慢或断开 | LazyCat breaks after TUN changes

**原因**：TUN 的绕行地址被改动，导致懒猫控制面流量被代理接管。
**处理**：立刻执行 `systemctl stop mihomo`（停止代理，释放 TUN）；不要删除 bypass 规则，应恢复到上次已知正常的配置，然后重启。

修改 TUN 配置前，请务必先阅读 [docs/LAZYCAT_NETWORK_REPORT.md §6–7](LAZYCAT_NETWORK_REPORT.md)，了解哪些地址必须始终保持 bypass。

**Cause**: TUN bypass addresses were changed, causing LazyCat control-plane traffic to be intercepted.
**Action**: Run `systemctl stop mihomo` immediately to release TUN. Do not remove bypass rules — restore to the last known-good config and restart.

Before changing TUN config, read [docs/LAZYCAT_NETWORK_REPORT.md §6–7](LAZYCAT_NETWORK_REPORT.md) to understand which addresses must always be bypassed.

---

## 安全须知 | Safety Notes

- **Controller 不对外**：`172.18.0.1:9090` 仅在微服内网可达，访问面板请使用 LazyCat URL。
  **Controller is private**: `172.18.0.1:9090` is only reachable inside the microserver. Use the LazyCat URL to access the dashboard.

- **Secret 自动生成**：部署脚本会自动生成 Mihomo secret 并保存到 `var/private/mihomo.secret`，不会嵌入到 LPK 包中。浏览器通过懒猫登录 session 引导运行时配置，无需手动处理 secret。
  **Secret is auto-generated**: The deploy script generates and stores the Mihomo secret in `var/private/mihomo.secret` — it is never baked into the LPK. Browsers bootstrap config via the LazyCat login session.

- **TUN bypass 列表是关键安全配置**：`6.6.6.6/32`、`2000::6666/128`、`fc03:1136:3800::/40` 等地址必须始终在 bypass 列表中，否则可能导致懒猫控制面断连。不要随意删改这些条目。
  **TUN bypass list is critical**: `6.6.6.6/32`, `2000::6666/128`, and `fc03:1136:3800::/40` must always be in the bypass list. Removing them risks breaking the LazyCat control plane.

- **敏感配置放 `var/private/`**：真实配置和订阅 token 只存放在 `var/private/`，不要提交到 Git。
  **Keep secrets in `var/private/`**: Real configs and subscription tokens belong in `var/private/`, never in git.

更多安全细节见 [docs/SECURITY.md](SECURITY.md)。
For more security details, see [docs/SECURITY.md](SECURITY.md).
