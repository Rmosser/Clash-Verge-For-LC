# 懒猫微服网络改动影响评估报告（2026-01-31）

目标：把“国内直连 / 国外代理（YouTube/ChatGPT 走代理）”这套规则在懒猫微服上生效，同时尽量 **不影响懒猫微服/客户端的内网穿透与控制面通信**。

本报告用于你后续随时对照：我们改了哪些网络相关配置、可能影响哪些系统功能、以及启用“全局透明代理/TUN”前需要做哪些绕行（bypass）。

---

## 1. 参考资料（官方）

以下内容来自懒猫微服官方开发者文档/官网页面（建议你后续以这些为准做复核）：

- 开发者文档：网络机制与 VPN  
  `https://developer.lazycat.cloud/network.html`
- 开发者文档：自己架设网络穿透  
  `https://developer.lazycat.cloud/tunnel.html`
- 官网宣传页（含“超稳定内网穿透”等描述）  
  `https://lazycat.cloud/m`

---

## 2. 官方文档中与“不要破坏内网穿透”最相关的要点（摘录/转述）

### 2.1 连接机制（直连优先，失败再中继）

开发者文档描述：设备/客户端会尽量走 **直连**（例如 IPv6、或更好的 NAT 环境），如果直连效果不好再走 **中继**；同时强调传输通道的安全性（加密/认证）。这意味着：

- 任何“全局代理/透明代理/VPN/TUN”一旦把 **控制面/穿透探测** 的流量也改走代理，可能导致直连探测失败、连接变慢甚至不可用。

### 2.2 官方给出的“减少 VPN/代理对懒猫微服连接影响”的建议（强相关）

开发者文档给出的核心思路是：**懒猫内网穿透/控制面相关流量应尽量直连，不要被代理劫持/改路由**。文档明确提到了（转述）：

- `.heiyu.space`、`.lazycat.cloud` 相关域名应拿到“真实 IP”（不要被 fake-ip/劫持 DNS 影响）。
- 有一些“探测/连通性检查”会访问特定地址（例如 `6.6.6.6`、`2000::6666`），这些在 TUN/代理场景里应被排除（bypass）。
- `fc03:1136:3800::/40`（懒猫内网相关 IPv6 段）应走直连（bypass），避免被代理接管。

这些点对我们要做的“全局透明代理/TUN（场景 2）”非常关键：**必须做 bypass**，否则风险很高。

---

## 3. 现状快照（本次改动针对的机器）

- 机器：`lzcbox-d76cc5f0`
- 系统：Debian 12（bookworm）
- 关键网络形态（来自现场观察）：
  - 局域网网卡：`wlp4s0`（示例：`192.168.1.10/24`）
  - 懒猫内网/穿透相关：存在 `heiyu-0` 接口（IPv6 `fc03:.../40`）
  - 容器/应用桥接：存在多个 bridge（例如 `172.18.0.0/16`、`172.28.x.x/26` 等）

结论：这不是“单纯一台裸 Debian”，其网络栈里包含懒猫系统组件与容器网络；**透明代理如果不做绕行，极易误伤**（例如把容器互联/控制面流量也代理掉）。

---

## 4. 我们已经做了哪些网络相关改动（已落地）

### 4.1 安装并运行 mihomo（Clash Meta 内核）

用途：作为本机代理核心（后续可用于透明代理/TUN，但目前还没启用全局劫持）。

- 二进制：`/usr/local/bin/mihomo`
- systemd 服务：`/etc/systemd/system/mihomo.service`（已 enable）
- 运行用户：`mihomo`（system user）
- 数据目录：`/var/lib/mihomo/`
  - `Country.mmdb`（为 `GEOIP,CN` 规则提供 GeoIP 数据）
  - `cache.db`（运行缓存）
- 配置文件：`/etc/mihomo/config.yaml`

### 4.2 规则与节点

- 上游出口：来自你提供的 `Mac.yaml`（21 个 SOCKS5 入口；包含账号/密码等敏感信息）
- 分流/广告规则：来自 `sr_cnip_ad_懒猫.conf` 的 `[Rule]` 段
  - 将 `FINAL,PROXY` 转为 mihomo/Clash 的 `MATCH,PROXY`
  - 保留 `GEOIP,CN,DIRECT`（需 `Country.mmdb`）

### 4.3 监听方式（仍保持“仅本机开放端口”，但已启用 TUN 透明代理）

- 代理端口：`127.0.0.1:7890`（mixed-port）
- 控制端口：`172.18.0.1:9090`（仅在微服内部 bridge 上监听，供懒猫 ingress/应用访问）

端口仍然只监听在本机（不会把代理端口暴露到局域网），但现在已经开启 **TUN 透明代理**：

- **整机流量会被接管并进入 mihomo 规则分流**（国内直连/国外代理）
- 通过 `tun.route-exclude-address` 绕行懒猫内网/探测相关地址，避免影响内网穿透

### 4.4 apt 走代理（已启用）

为方便在机器上拉包/更新，我们设置了：

- `/etc/apt/apt.conf.d/90mihomo-proxy`
  - `Acquire::http::Proxy "http://127.0.0.1:7890";`
  - `Acquire::https::Proxy "http://127.0.0.1:7890";`

### 4.5 已启用 TUN（全局透明代理）

已在 `/etc/mihomo/config.yaml` 启用 `tun:`，并在 systemd unit 给 `mihomo` 进程授予了 TUN 所需权限：

- tun 栈：`stack: system`
- 自动路由：`auto-route: true`（auto redir: false）
- 关键绕行（bypass）：
  - `fc03:1136:3800::/40`（懒猫内网相关 IPv6 段）
  - `6.6.6.6/32`、`2000::6666/128`（懒猫探测地址）

启用后可以通过 `ip route get 6.6.6.6` / `ip -6 route get 2000::6666` 验证它们走“正常出口”（不是 tun 的 `198.18.0.0/30`）。

### 4.6 已安装可视化控制台（懒猫应用）

为方便手动切换节点/分组，我们在懒猫微服上安装了一个 Web 控制台应用（LPK）：

- 应用包：`cloud.lazycat.app.mihomo-dashboard`
- 子域名：`mihomo`
- 访问入口：`https://mihomo.<boxname>.heiyu.space`（示例：`https://mihomo.rainierserver.heiyu.space`）
- 设计目标：不把 mihomo 控制端口暴露到局域网；通过懒猫登录鉴权后访问（路由 `/api` 反代到 `host.lzcapp:9090`）

---

## 5. 当前这套“国内直连 / 国外代理”规则是否已生效？

已生效；并且在启用 TUN 后，**整机流量会自动进入 mihomo**（无需每个应用单独设置代理）。

典型规则核心逻辑（你理解的那套）等价于：

- 强制代理（可选，通常是 YouTube/ChatGPT 等域名）
- `GEOIP,CN,DIRECT`
- `MATCH,PROXY`

在微服上我们已启用对应规则，并补齐了 `Country.mmdb`，避免 `GEOIP` 报错。

---

## 6. 为什么你担心“全局透明代理/TUN”会影响内网穿透：风险点清单

如果我们把场景升级为 **全局透明代理/TUN**（你选的“2”），风险主要来自：

1. **控制面/穿透探测被代理劫持**：官方明确提示 `.heiyu.space`、`.lazycat.cloud`、`fc03:1136:3800::/40`、探测 IP（如 `6.6.6.6`、`2000::6666`）应绕行；否则可能导致连接慢/失败。
2. **容器/应用内部网络被代理劫持**：`172.18.0.0/16`、`172.28.x.x` 等属于容器桥接/服务发现网络，透明代理若不排除，可能导致应用互访异常。
3. **UDP/直连特性被破坏**：穿透/NAT traversal 常依赖 UDP、直连路径质量；代理会改变路径与 MTU/拥塞控制，可能引发不可预测的问题。

结论：**全局透明代理/TUN 不是“打开就完事”**，必须先按官方建议 + 现场网络拓扑做严格 bypass。

---

## 7. 全局透明代理/TUN 的建议落地策略（建议先评审再动手）

为了尽量不破坏懒猫系统，我建议“透明代理”分两步：

### 第一步（低风险）：只代理“你明确指定的服务”（历史方案）

- 继续维持当前模式：应用/命令显式使用 `127.0.0.1:7890`（或仅对特定 systemd 服务注入代理环境变量）。
- 好处：对懒猫穿透/控制面影响最小；故障可控、回滚简单。

### 第二步（高风险）：全局透明代理/TUN（已实施；需要严格 bypass）

如果你确实要“整机都自动分流”，在启用前至少要保证：

- **绕行域名/网段（强烈建议）**
  - `.heiyu.space`、`.lazycat.cloud`
  - `fc03:1136:3800::/40`
  - `6.6.6.6/32`、`2000::6666/128`
  - RFC1918/本地网段：`10/8`、`172.16/12`、`192.168/16`、`127/8`、`169.254/16`、`fc00::/7`、`fe80::/10` 等
  - 容器桥接网段（建议运行时自动识别并绕行）：例如 `172.18.0.0/16`、`172.28.0.0/16`（或更精细到每个 bridge 的 CIDR）

- **实现方式选择**
  - Linux 上常见是 `iptables`(nf_tables) + `redir-port`，或 mihomo 的 `tun`/`tproxy` 能力。
  - 无论哪种，都应保证“先 bypass 再接管”，并提供一键回滚。

本次已按官方文档提示 + 现场网络拓扑落地 bypass（至少包含 `fc03:1136:3800::/40`、`6.6.6.6/32`、`2000::6666/128`、RFC1918/本地网段等），并在启用后验证 `hext` 控制面连接仍保持建立状态。

---

## 8. 验证/回归测试清单（每次改动后都跑一遍）

### 8.1 mihomo 自检

- 配置校验：`mihomo -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml`
- 服务状态：`systemctl status mihomo`
- 代理出网：`curl -x http://127.0.0.1:7890 https://api.ipify.org`

### 8.2 懒猫穿透/控制面健康度（重点）

建议结合官方文档里的思路检查：

- DNS 是否被劫持：`.heiyu.space`、`.lazycat.cloud` 是否能解析到真实地址
- 探测地址是否能直连：`6.6.6.6`、`2000::6666`
- `fc03:1136:3800::/40` 是否走直连（不要被代理接管）

（注：具体命令可按你的系统工具选择，例如 `dig`/`nslookup`/`traceroute`/`ip route get` 等。）

---

### 8.3 DNS 变更安全流程（5 分钟未确认自动回滚）

背景：DNS/TUN/透明代理相关改动一旦误伤 `.heiyu.space/.lazycat.cloud` 或控制面探测流量，可能导致你在外部无法访问微服。为降低“改完就断链”的风险，我们提供一个安全工具：`lzc-net-safe-apply`。

工具安装位置（微服侧）：

- `/usr/local/sbin/lzc-net-safe-apply`

仓库沉淀（用于部署脚本自动安装）：

- `infra/microserver/lzc-net-safe-apply`
- `scripts/deploy_microserver.sh`（默认会安装，不默认执行）

标准流程（以网卡 `wlp4s0` 为例）：

1) 预设回滚 DNS（建议指向路由器 + link-local，确保控制面域名可直连解析）：

```bash
export LZC_NET_ROLLBACK_DNS="192.168.1.1 fe80::1"
```

2) 应用 DNS 变更（立刻生效，同时自动安排 5 分钟后回滚）：

```bash
lzc-net-safe-apply apply-dns wlp4s0 223.5.5.5 119.29.29.29
```

3) 立刻从外部验证懒猫入口仍可访问（至少满足其一即可）：

- `https://mihomo.<boxname>.heiyu.space` 可打开
- 或能确认控制面域名解析与 443 连接正常

4) 5 分钟内确认（取消自动回滚）：

```bash
lzc-net-safe-apply confirm
```

如果忘记确认或验证失败：系统会在 5 分钟后自动回滚到 `LZC_NET_ROLLBACK_DNS`（或变更前捕获到的 DNS 配置）。

---

### 8.4 容器出网标准做法（显式代理）

背景：有些目标站（例如 `api.openai.com`、`api.telegram.org`）在“直连”场景会出现 TLS 握手被中断（`SSL_ERROR_SYSCALL` / `ECONNRESET`），但通过宿主机 `mihomo` 的显式代理可用。为让懒猫应用/Docker 容器稳定出网，推荐统一走“容器侧显式代理入口”，而不是依赖透明代理是否覆盖到容器网络。

微服侧（宿主机）做法：

- 保持 `mihomo` 仍只监听本机：`127.0.0.1:7890`
- 新增一个仅容器网桥可达的代理入口：`172.18.0.1:17890`（不会暴露到 LAN/WAN）
- 通过 `systemd-socket-proxyd` 转发：`172.18.0.1:17890 -> 127.0.0.1:7890`

仓库沉淀对应的 unit 模板（部署脚本会自动安装并启用）：

- `infra/microserver/mihomo-container-proxy.socket`
- `infra/microserver/mihomo-container-proxy.service`

容器侧通用环境变量（建议全部容器统一）：

```bash
HTTP_PROXY=http://172.18.0.1:17890
HTTPS_PROXY=http://172.18.0.1:17890
http_proxy=http://172.18.0.1:17890
https_proxy=http://172.18.0.1:17890

# 仅使用域名/主机名/IP 白名单绕开内网流量，避免依赖 CIDR 支持。
NO_PROXY=localhost,127.0.0.1,::1,.heiyu.space,.lazycat.cloud,172.18.0.1
no_proxy=localhost,127.0.0.1,::1,.heiyu.space,.lazycat.cloud,172.18.0.1
```

Node.js（`fetch`）额外注意：

- Node 内置 `fetch` 默认不一定遵守 `HTTP(S)_PROXY`。
- 推荐用 `NODE_OPTIONS=--require ...` 在启动前注入一个 bootstrap，把全局 `fetch` 切换到 `undici.fetch` 并启用 `EnvHttpProxyAgent`（自动读取 `HTTP(S)_PROXY` + `NO_PROXY`）。

最小 bootstrap 范式（示例：`proxy-bootstrap.cjs`）：

```js
(() => {
  const env = process.env;
  const hasProxy = !!(env.HTTP_PROXY || env.HTTPS_PROXY || env.http_proxy || env.https_proxy);
  if (!hasProxy) return;

  // 如果 undici 不在 CWD 可 resolve（例如作为全局模块/依赖被安装在别处），用 createRequire 锚定入口文件。
  const { createRequire } = require("module");
  const req = createRequire(env.APP_ENTRY || process.argv[1] || __filename);

  let undici;
  try {
    undici = req("undici");
  } catch {
    return;
  }

  const proxy = env.HTTPS_PROXY || env.HTTP_PROXY || env.https_proxy || env.http_proxy;
  const agent =
    typeof undici.EnvHttpProxyAgent === "function"
      ? new undici.EnvHttpProxyAgent()
      : new undici.ProxyAgent(proxy);

  undici.setGlobalDispatcher(agent);
  globalThis.fetch = undici.fetch;
})();
```

---

## 9. 回滚方案（出现异常时先保系统）

如果发现内网穿透/控制面异常，建议先快速回滚到“无全局代理”的安全状态：

1) 停止代理服务（临时）：`systemctl stop mihomo`  
2) 禁用开机自启（可选）：`systemctl disable mihomo`  
3) 取消 apt 代理（如影响更新）：删除 `/etc/apt/apt.conf.d/90mihomo-proxy`

如果后续真的启用了 iptables/TUN（未来步骤），则必须同时回滚相应 iptables 规则/路由策略（这一块建议我们到时做成脚本化“一键启用/一键回滚”）。

---

## 10. 本地文件提醒（含敏感信息）

你本机目录中存在含敏感信息的文件（节点账号/密码等）：

- `Mac.yaml`（节点入口原始数据）
- `mihomo.config.yaml`（本次生成并部署到微服的配置副本）

建议按“密码文件”级别对待，不要随意分享/上传。

---

## 11. 2026-02-25 迁移实施记录（Docker -> Linux 原生 + 防自动删）

本节为本次“从 Docker 迁移到 Linux 原生部署”的实操落地记录。

### 11.1 实施结果（最终状态）

- `mihomo` 以 `systemd` 原生运行，且开机自动拉起：
  - `systemctl is-enabled mihomo = enabled`
  - `systemctl is-active mihomo = active`
- 代理入口与控制入口恢复并稳定：
  - `127.0.0.1:7890`（mixed-port）
  - `172.18.0.1:9090`（controller）
  - `172.18.0.1:17890`（container proxy socket）
- TUN 绕行验证通过（关键地址保持直连）：
  - `6.6.6.6/32`
  - `2000::6666/128`
  - `fc03:1136:3800::/40`

### 11.2 关键发现（为什么之前“重启后自动删”）

在该机型当前启动链路下，直接写入 `/etc/systemd/system`、`/usr/local/bin`、`/etc/mihomo`、`/var/lib/mihomo` 的 host 改动，重启后可能丢失。  
因此单纯 `systemctl enable` 不足以保证跨重启保留，必须加“启动期自举恢复”机制。

### 11.3 最终防自动删方案

采用“持久根 + 启动钩子自举”：

- 持久根（放在稳定分区）：`/lzcsys/var/custom/mihomo-host-native`
  - `bin/mihomo`
  - `etc-mihomo/`
  - `var-lib-mihomo/`
  - `systemd/`（`mihomo.service`、container-proxy、backup timer 等）
  - `bootstrap-apply.sh`
- 启动钩子：
  - `/lzcsys/var/custom/hooks/lzc-os-starting/50-mihomo-host-native-bootstrap.sh`
  - 兜底保留：`/lzcsys/var/custom/hooks/data-disk-ready/50-mihomo-host-native-bootstrap.sh`

`bootstrap-apply.sh` 在每次启动时执行：

1. 恢复二进制与脚本到 `/usr/local/bin`、`/usr/local/sbin`
2. 将持久目录 bind 到运行路径：
   - `/etc/mihomo -> /lzcsys/var/custom/mihomo-host-native/etc-mihomo`
   - `/var/lib/mihomo -> /lzcsys/var/custom/mihomo-host-native/var-lib-mihomo`
3. 重新下发 systemd units/tmpfiles
4. `daemon-reload + enable --now` 拉起 `mihomo`、`mihomo-container-proxy.socket`、`mihomo-backup.timer`

### 11.4 备份策略（保留 14 份）

- 定时任务：`mihomo-backup.timer`（每日 `03:30`）
- 执行脚本：`/usr/local/sbin/mihomo-backup.sh`
- 备份目标：
  - 优先：`/lzcsys/data/document/rainier/mihomo-backup`
  - 若数据盘目录不可用，回退：`/lzcsys/var/custom/mihomo-backup`

### 11.5 快照与回滚锚点

- 迁移快照目录：`/var/lib/mihomo/migration-snapshots/`
- 最新落地快照（本次）：`20260225-182008-postreboot`
- 快照包含：配置、units、tmpfiles、`var-lib-mihomo.tgz`、基线验收输出

### 11.6 补充说明

- 本次深度清理已执行：
  - `docker image prune -a -f`
  - `docker volume prune -f`
  - `docker network prune -f`
  - `docker builder prune -a -f`
- 清理后系统核心容器（`lzc-*`、`hext`）保持运行。
