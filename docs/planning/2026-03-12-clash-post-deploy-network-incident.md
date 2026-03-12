# 2026-03-12 Clash 部署后微服网络失联事故研判

## 背景

在对懒猫微服上的 Mihomo / Clash Verge Web 做深度适配并重新部署后，出现了以下连锁现象：

- `ssh root@rainierserver.heiyu.space` 超时
- `lzc-cli box list` 从 `READY` 退化为 `CONNECTING`
- `lzc-cli app install/status` 最终报开发者工具连接 `ETIMEDOUT`
- `https://clash.rainierserver.heiyu.space` 无法访问
- 浏览器里已打开的 Clash Verge 页面仍可看到缓存 UI，但 `/verge-api/invoke` 等接口请求失败
- 设备重启后，Mac 侧依然观测到：
  - `lzc-cli box list` 仍为 `CONNECTING`
  - `ssh` 仍超时
  - `https://clash.rainierserver.heiyu.space` 仍超时
- 用户随后已在微服侧移除 Clash，但 Mac 侧再次复测仍然观测到：
  - `lzc-cli box list` 仍为 `CONNECTING`
  - `ssh` 仍超时
  - `https://clash.rainierserver.heiyu.space` 仍超时
- 用户补充的新线索：
  - 当前微服“无法拉起任何应用”
- 但手机客户端仍能进入“微服网络检测”，并拿到：
  - “Cannot connect to origin server”
  - “访问微服注册服务异常”
  - NAT / IPv6 影响直连的提示

本文件用于沉淀：

1. 当前最可能的根因猜测
2. 支持这些猜测的证据
3. 在“不重置微服”的前提下还可以尝试的恢复路径

## 先排除什么

这次新增的 Web 端适配改动本身，不像是导致“整机网络栈 / 控制面掉线”的主因。

原因：

- 本轮前端改动主要集中在：
  - `src/mihomo-dashboard-app/public/lzcapp-fetch-proxy.js`
  - `src/mihomo-dashboard-app/vendor/clash-verge-rev/src/services/runtime-probe.ts`
  - `src/mihomo-dashboard-app/vendor/clash-verge-rev/src/components/setting/*`
- 这些改动只会影响：
  - Web UI 错误展示
  - Web 版能力降级
  - `/fetch/probe` 的 JSON envelope 兼容性
- 它们不会直接改宿主机默认路由、TUN 路由表、systemd 网络单元或懒猫控制面路径

更可疑的是宿主机级 Mihomo/TUN 部署链路。

## 最可能的根因猜测

### 猜测 1：`TUN + auto-route + strict-route` 抢走了懒猫控制面 / 穿透流量

这是当前最优先的怀疑对象。

关键证据：

- 部署脚本默认会开启 TUN：
  - [scripts/deploy_microserver.sh](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/scripts/deploy_microserver.sh#L149)
- 基础 TUN 配置是：
  - `stack: system`
  - `auto-route: true`
  - `strict-route: true`
  - 位置见 [infra/mihomo/config.base.yaml](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/infra/mihomo/config.base.yaml#L55)
- 部署脚本会在远端直接重启 `mihomo`：
  - [scripts/deploy_microserver.sh](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/scripts/deploy_microserver.sh#L507)

为什么它危险：

- 懒猫控制面/内网穿透不只依赖域名解析正确，还依赖真实出站路径不能被代理接管
- 官方与仓库文档都强调 `.heiyu.space`、`.lazycat.cloud`、探测地址、`fc03:1136:3800::/40` 必须绕行
- 但懒猫实际可能还会访问：
  - 动态公网 relay IP
  - UDP/QUIC 探测与保活流量
  - 控制面未在文档里完全列出的地址

一旦这些流量掉进 `MATCH,PROXY` 或被 TUN 接管失败，盒子会立刻从控制面掉线。

### 猜测 2：DNS 覆盖策略过于激进，导致控制面域名解析链路失稳

关键证据：

- 部署脚本默认会把 DNS 块重写为仓库里的“known-good DNS”：
  - [scripts/deploy_microserver.sh](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/scripts/deploy_microserver.sh#L155)
  - [scripts/patch_remote_mihomo_config.py](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/scripts/patch_remote_mihomo_config.py#L31)
- 这个 DNS 块写死了：
  - `192.168.1.1`
  - `fe80::1`
  - `1.1.1.1 / 1.0.0.1 DoH`

风险点：

- `192.168.1.1` 与 `fe80::1` 假设了当前局域网/路由器拓扑没有变化
- 如果现场网关、IPv6 邻居或懒猫控制面依赖的 bootstrap DNS 与这个假设不一致，`mihomo` 重启后控制面域名可能无法走到正确地址

### 猜测 3：`heiyu.space / lazycat.cloud` 的 DIRECT 规则在真实私有配置中不一定存在

这是一个很容易被忽略的点。

关键证据：

- 仓库模板明确把这两条规则写成“应存在”：
  - [infra/mihomo/config.base.yaml](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/infra/mihomo/config.base.yaml#L96)
- 但 `patch_remote_mihomo_config.py` 并不会强制补这两条 DIRECT 规则
- 它只是把这两条规则当作“插入锚点”来放置强制 PROXY / DoH 规则：
  - [scripts/patch_remote_mihomo_config.py](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/scripts/patch_remote_mihomo_config.py#L105)
  - [scripts/patch_remote_mihomo_config.py](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/scripts/patch_remote_mihomo_config.py#L373)

这意味着：

- 如果真实的 `var/private/mihomo.config.yaml` 没有这两条 DIRECT 规则
- 那么即使 `nameserver-policy` 让域名解析到了“正确 IP”
- 真实连接仍然可能被后续规则链送去 `PROXY`

最新核查结论：

- 已本地核查 `var/private/mihomo.config.yaml`
- 这两条规则实际存在：
  - `DOMAIN-SUFFIX,heiyu.space,DIRECT`
  - `DOMAIN-SUFFIX,lazycat.cloud,DIRECT`
- 因此这个猜测目前降级为“已证伪的次要怀疑项”，不是优先根因

### 猜测 4：`system` 栈 TUN 与懒猫宿主机的特殊网络拓扑冲突

关键证据：

- 仓库已有网络评估报告，明确指出宿主机上同时存在：
  - 局域网接口
  - 懒猫内网接口
  - 多个容器 bridge
  - 位置见 [docs/LAZYCAT_NETWORK_REPORT.md](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/docs/LAZYCAT_NETWORK_REPORT.md)
- 当前绕行主要是“按目标地址排除”

风险点：

- 如果懒猫保活/探测依赖“接口级直连”或特定 UDP 行为
- 那么仅靠 `route-exclude-address` 可能还不够
- `auto-route + strict-route` 在某些内核/发行版上也可能比预期更激进

## 事故证据摘要

### 宿主机级部署链路确实会动网络核心

- `deploy_microserver.sh` 会：
  - 补丁化 `/etc/mihomo/config.yaml`
  - 写入 systemd unit
  - 校验配置
  - 直接 `systemctl restart mihomo`
  - 见 [scripts/deploy_microserver.sh](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/scripts/deploy_microserver.sh#L504)

### 控制面探活在部署脚本里本来就被视为关键健康信号

- 部署脚本重启后会探：
  - `http://172.18.0.1:9090/version`
  - `http://172.18.0.1:9091/healthz`
  - 见 [scripts/deploy_microserver.sh](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/scripts/deploy_microserver.sh#L520)
- 这说明我们自己的部署逻辑也承认：
  - 控制器可达
  - Verge API 可达
  是部署成功的基本条件

### 现场现象符合“控制面掉线”，不像“整机断电”

- 浏览器缓存页面还在
- `lzc-cli box list` 是 `CONNECTING`，不是设备消失
- 直连网口能起链路，但对端没吐出任何可用网络服务
- 手机客户端仍能进入设备诊断页，说明：
  - 设备并非完全从懒猫云侧消失
  - 更像是“云侧还能识别设备，但 origin / 注册服务 / 开发者工具实时链路异常”
- 移除 Clash 后控制面仍未恢复，说明：
  - 受影响的很可能不只是 Web 应用包
  - 更像是宿主机级网络状态、控制面注册状态，或残留的宿主机 Mihomo/TUN 配置仍在生效
- “任何应用都拉不起来”进一步说明：
  - 影响范围已经超出 `cloud.lazycat.app.clash-verge-for-lc`
  - 更像是宿主机级网络/运行时环境被污染
  - 单纯卸载 Clash 应用包并不能恢复宿主机控制面

## 在不重置微服的前提下，还能做什么

以下动作按“前提最少、风险最低、收益最高”的顺序排。

### 1. 等待最薄的一层连接恢复，然后立刻做“去 TUN 化止血”

只要恢复以下任一入口，就优先执行：

- `ssh` 恢复
- `lzc-cli box list` 回到 `READY`
- `clash.<box>.heiyu.space` 可以重新访问

第一时间建议做的不是继续调功能，而是先止血：

```bash
MIHOMO_TUN_ENABLE=0 bash scripts/deploy_microserver.sh
```

必要时连 DNS 一起降级：

```bash
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 bash scripts/deploy_microserver.sh
```

这样做的目标是：

- 保留 dashboard / Verge API
- 先移除最可能打断控制面的透明代理能力
- 把系统退回“显式代理优先”的安全状态

### 2. 若 SSH 恢复但控制链路不稳，优先在宿主机上直接验证三件事

对应脚本已经在仓库里准备好了：

- `bash scripts/selfcheck.sh`
- `bash scripts/mihomo-manager status`
- `bash scripts/mihomo-manager version`

重点看：

- `mihomo` 是否还 active
- `/version` 是否能从宿主机本地控制器打通
- `ip route get 6.6.6.6`
- `ip -6 route get 2000::6666`
- `ip -6 route get fc03:1136:3800::1`

### 3. 若仅能恢复到 SSH，但想最快回退核心

仓库里已有手工回滚入口：

- [scripts/mihomo-manager](/Users/rinier/Projects/lazyCat/Clash-Verge-For-LC/scripts/mihomo-manager)

可用命令：

```bash
bash scripts/mihomo-manager rollback-core
```

注意：

- 这只能回退 Mihomo 二进制版本
- 不能解决“当前配置本身就把控制面打偏”的问题
- 所以优先级低于“先禁用 TUN 重新下发配置”

### 4. 保持直连网口，等待设备侧协议栈恢复

当前 Mac 侧已经确认：

- 扩展坞网卡 `en7` 已起链路
- 速率 `1000baseT`
- Mac 自己拿到了 `169.254.208.111`

但目前没有看到：

- DHCP
- ARP 邻居
- IPv6 邻居
- SSH / HTTP / HTTPS / 9090 监听

这意味着：

- 物理链路没问题
- 但微服当前没有在这块口上吐出协议栈

在不重置的前提下，能继续做的只有：

- 保持这根线不拔
- 持续观察是否开始出现：
  - 对端 ARP
  - 新的非 `169.254.*` 地址
  - `22/80/443/9090` 变为可达

### 5. 核查真实私有配置，确认关键 DIRECT 规则是否缺失

这一步已经完成。

- 打开 `var/private/mihomo.config.yaml`

核查结果：

- `DOMAIN-SUFFIX,heiyu.space,DIRECT`
- `DOMAIN-SUFFIX,lazycat.cloud,DIRECT`
- `GEOIP,CN,DIRECT`
- `MATCH,PROXY`
- `fc03:1136:3800::/40`
- `6.6.6.6/32`
- `2000::6666/128`

结论：

- 规则层面“明显漏掉关键 DIRECT / bypass 项”这一条，目前没有直接证据支持
- 当前怀疑重点仍应回到：
  - TUN 的系统级接管方式
  - DNS 启动链路
  - 懒猫控制面可能使用的额外动态地址或 UDP/QUIC 路径

### 6. 如果设备有本地 UI/控制台，但不算“重置”

这仍属于“不重置前可做的动作”：

- 查看本地系统界面是否还在线
- 查看是否能只重启：
  - 网络服务
  - 开发者工具
  - 懒猫控制面守护进程

只要不是整机恢复出厂或全量重置，这类局部服务恢复依然值得优先尝试。

## 当前不建议做的事

### 1. 继续发布 dashboard 或继续改前端

原因：

- 当前问题明显不在 Web UI 本身
- 继续发布只会增加变量

### 2. 在没有宿主机连接的前提下盲猜更多网段并做大范围扫描

原因：

- 现在直连网口只有物理链路，没有任何协议层反馈
- 大范围扫描收益低，噪音高

### 3. 只做二进制回滚，不动配置

原因：

- 如果根因是配置层的 TUN / DNS / 规则链
- 单纯回滚 Mihomo 二进制并不能真正止血

## 备份恢复后优先排查的线索

如果你稍后拿到设备备份或导出的系统文件，优先找下面这些内容：

### 1. Mihomo 宿主机配置与状态

- `/etc/mihomo/config.yaml`
- `/etc/mihomo/verge-api.secret`
- `/var/lib/mihomo/`
- `/var/lib/mihomo/rollback/latest.env`
- `/var/lib/mihomo/rollback/upgrade-*.log`

重点看：

- `tun.enable`
- `auto-route`
- `strict-route`
- `route-exclude-address`
- `dns` 块是否被覆盖
- 最后一次升级/回滚日志停在什么阶段

### 2. systemd 单元

- `/etc/systemd/system/mihomo.service`
- `/etc/systemd/system/mihomo-verge-api.service`
- `/etc/systemd/system/mihomo-container-proxy.socket`
- `/etc/systemd/system/mihomo-container-proxy.service`

重点看：

- 是否已 enable
- 最近一次启动失败时的 `ExecStart`、权限、环境变量

### 3. 网络侧残留

- `ip route`
- `ip rule`
- `ip -6 route`
- `nft list ruleset`
- `iptables-save`
- `resolvectl status` 或 `/etc/resolv.conf`

重点看：

- 是否有残留 TUN 路由
- 是否有策略路由把默认出站带偏
- 是否有 nftables / iptables 重定向残留
- DNS 是否仍被改到不兼容的上游

### 4. 懒猫运行时/应用侧日志

- 开发者工具或微服系统日志
- “注册服务异常”对应的后台日志
- 应用无法拉起时的平台日志

重点看：

- 是不是所有应用都卡在：
  - 网络注册
  - 拉镜像/拉资源
  - 健康检查
  - origin 建链

### 5. 结论优先级

如果备份里能证明以下任一项，根因就会更明确：

- `mihomo` 仍在开机自启且 `tun.enable: true`
- 默认路由/策略路由被切到 TUN
- 开发者工具/注册服务的请求被送入 `MATCH,PROXY`
- 所有应用都卡在同一种网络错误上

## 本次备份盘实查结果

本轮已经直接对备份盘做了只读取证。

- 介质不是 macOS 可直接挂载的 APFS / exFAT，而是 `btrfs`
- 只读索引保存在：
  - `output/backup-disk/btrfs-target-index.txt`
  - `output/backup-disk/more-index.txt`
  - `output/backup-disk/log-scan.txt`
- 过程中的原始配置/日志转储含有凭据和账户信息，已移到本机临时目录 `/tmp/backup-disk-sensitive`，不应提交进仓库

### 1. 备份确认这台机器长期存在宿主机级 `mihomo-host-native`

备份里能直接看到：

- `lzcos/var.20260312T0924/custom/mihomo-host-native/`
- 其中包含：
  - `bin/mihomo`
  - `etc-mihomo/config.yaml`
  - `systemd/mihomo.service`
  - `systemd/mihomo-container-proxy.socket`
  - `var-lib-mihomo/verge/*`

结论：

- 宿主机级 Mihomo 不是这次 3 月 12 日才第一次出现
- 这套 `host-native` 方案至少从更早时间就已经存在，并带着 systemd 常驻与容器代理入口 `172.18.0.1:17890`

### 2. `bootstrap.log` 证明 3 月 12 日当天发生了多次宿主机级重启/重套用

备份中的 `bootstrap.log` 记录了多次：

- `2026-03-12T08:35:52+08:00`
- `2026-03-12T08:45:38+08:00`
- `2026-03-12T08:53:25+08:00`
- `2026-03-12T08:57:27+08:00`
- `2026-03-12T09:16:09+08:00`
- `2026-03-12T09:17:09+08:00`
- `2026-03-12T09:20:03+08:00`
- `2026-03-12T09:20:56+08:00`

并且每次都显示：

- `bootstrap start`
- `bootstrap done: mihomo=active socket=active`

结论：

- 当天不是“服务根本没起来”，而是 `mihomo.service` 和 `mihomo-container-proxy.socket` 多次被重新套用后仍然显示 active
- 因此问题更像“服务在，但宿主机网络语义已经偏了”，不是单纯 `systemd` 启动失败

### 3. 备份快照里的“当前运行态”已经是 empty runtime，但 `TUN + DNS` 仍然开启

备份中的当前宿主机配置文件显示：

- `profiles.json` 为：
  - `current: ""`
  - `items: []`
- `config.yaml` 为：
  - `tun.enable: true`
  - `dns.enable: true`
  - `proxy-groups: [DIRECT]`
  - `rules: DOMAIN-SUFFIX,heiyu.space,DIRECT`
  - `rules: DOMAIN-SUFFIX,lazycat.cloud,DIRECT`
  - `rules: MATCH,DIRECT`

同时 `operations.log` 记录到：

- `2026-03-12T00:28:27Z applied empty runtime profile`
- `2026-03-12T00:28:27Z reconciled stale mihomo runtime with empty profile state`
- `2026-03-12T00:28:27Z starting verge api on 172.18.0.1:9091`

结论：

- 备份时间点，系统已经不再持有有效 profile 列表
- 但 `TUN` 和 DNS 接管并没有一起关闭
- 这把根因进一步收敛到：
  - 不是“代理节点分流把流量送错了”这么简单
  - 更像是“即使在 empty runtime / MATCH,DIRECT 下，宿主机 TUN / DNS / 解析链路本身也可能影响微服控制面”

### 4. 系统日志直接出现了 `origin.lazycat.cloud` 解析超时

从备份中的 `system.journal` 可直接提取到：

- `2026-03-12T09:12:53+0800` `cloud.lazycat.networkdiagnostic` 被恢复并进入 ready
- 紧接着 `2026-03-12T09:13:02+0800` 和 `2026-03-12T09:13:04+0800` 出现：
  - `_dnsaddr.origin.lazycat.cloud`
  - `_dnsaddr.origin.lazycat.cloud.lan`
  - 查询超时
  - 错误形态是 `read udp 127.0.0.1:* -> 127.0.0.53:53: i/o timeout`

结论：

- 手机端“Cannot connect to origin server / 访问微服注册服务异常”不是假阳性
- 至少在备份时刻，懒猫侧和 `origin.lazycat.cloud` 相关的 DNS 链路确实已经超时
- 而且超时不是“远端节点代理失败”，而是本机/宿主机 resolver 链路已经卡住

### 5. `hext.log` 还原了穿透/直连层面的退化

同一天的 `hext.log` 里出现了：

- 多条 `context deadline exceeded`
- 多条 `wait connection canceled`
- 多条 `ipv6-tcp Listen failed not support`
- 多条 `ipv6-kcp Listen failed not support`

时间集中在：

- `2026-03-12 08:33`
- `2026-03-12 08:37`

结论：

- 控制面/穿透层并不是“完全静默失联”，而是出现了明显的建链退化
- 这与手机客户端里看到的 NAT / IPv6 / origin 异常是相互印证的

### 6. `clash-verge-for-lc` 容器日志说明 Web 端确实撞到了宿主机控制接口不可达

备份中的容器日志显示：

- `cloudlazycatappclash-verge-for-lc-app-1`
- 反复出现：
  - `dial tcp 172.18.0.1:9090: connect: connection refused`
  - `dial tcp 172.18.0.1:9091: connect: connection refused`
- `cloudlazycatappclash-verge-for-lc-fetchproxy-1` 则基本只是正常监听 `:3001`

结论：

- Web 应用层看到的 `9090 / 9091` 不可达，确实来自宿主机接口不可用，而不是纯前端假错
- `fetchproxy` 并不是主要故障点

### 7. 当前最可信的收敛判断

综合备份证据，现在最像的是：

- 宿主机 `mihomo-host-native` 的 `TUN + DNS` 接管在 empty runtime 下依旧生效
- 微服控制面 / origin / 注册链路在宿主机 resolver 或网络栈层面超时
- 这会让手机客户端还能“看到设备并拉起诊断”，但开发者工具、origin 建链、应用 realize 全部一起变差

换句话说：

- 现在最值得怀疑的不是“代理节点规则没绕行到位”
- 而是“宿主机级 TUN / DNS 接管本身与懒猫控制面兼容性不足”
- 这也解释了为什么卸载 Web 应用后，设备仍没有立刻恢复正常

## 建议的下一步顺序

1. 先把微服恢复到“无宿主机 `mihomo-host-native` 干扰”的基线状态，再确认：
   - `lzc-cli box list` 回到 `READY`
   - 手机端不再报 `origin / 注册服务异常`
   - 普通应用可以再次 realize
2. 保持直连网口连接，继续观察是否恢复最薄的一层入口
3. 一旦 `ssh` 或 `lzc-cli` 恢复，第一时间执行最保守的止血部署：

```bash
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 bash scripts/deploy_microserver.sh
```

4. 待基线稳定后，再逐步恢复显式代理能力，确认：
   - `172.18.0.1:17890` 显式代理可用
   - `172.18.0.1:9090 / 9091` 仅在容器内可达
   - `origin.lazycat.cloud` 和应用 realize 不受影响

5. 最后才重新设计 TUN 上线方案，并要求：
   - 默认关闭
   - 只有显式参数才允许启用
   - 启用前自动保存回退配置
   - 启用后强制验证 `origin`、注册服务、普通应用 realize、手机客户端诊断全部正常

如果后续要单独验证“只关 TUN、保留 DNS”的差异，再执行：

```bash
MIHOMO_TUN_ENABLE=0 bash scripts/deploy_microserver.sh
```

## 重置后复盘与最终修复记录

重置微服后，本次采用了“每一步先备份，再做最小改动”的方式重新联调，并最终把 `networkdiagnostic` 调到了全绿。

### 验证路径

按阶段完成了以下验证：

1. 先恢复开发者工具链路，确认 `lzc-cli`、`developer.tools`、SSH 和普通应用都正常。
2. 只安装 Clash Verge Web 面板，不部署宿主机 Mihomo，确认 Web 应用本身不会破坏平台。
3. 只部署宿主机 `mihomo + mihomo-verge-api`，并保持 `TUN=0`、`DNS=0`，确认显式代理和控制器链路都安全。
4. 单独开启 `DNS=1`，确认 `special TXT DNS` 不再超时。
5. 再单独开启 `TUN=1`，确认平台、开发者工具、普通应用和 Clash Web 仍稳定。
6. 最后针对 `networkdiagnostic` 剩余红项做专项实验。

### 剩余红项的根因拆解

#### 1. IPv6 红项

`ByIPv6Connectivity` 实际探测的是 `www.baidu.com` 的 IPv6 可达性。

实验中确认：

- 盒子本身有 IPv6 路由，并非完全没有 IPv6。
- 但默认 DNS 链路下，`www.baidu.com` 一度拿不到 AAAA 记录。
- 一旦补上 `+.baidu.com -> [192.168.1.1, fe80::1]` 的 `nameserver-policy`，`ByIPv6Connectivity` 就转绿。

结论：

- 这条红项不是纯“运营商没有 IPv6”。
- 更准确地说，是诊断程序挑选的探测域名，在当前 DNS 链路下拿不到 IPv6 结果。

#### 2. NAT 红项

`ByNATType` 的真实探测目标会轮换，而且在 `TUN on` 时会先被卷入 `Meta`。

现场明确观测到的探测地址包括：

- `45.63.83.38:3478`
- `45.32.130.255:3479`
- `95.179.192.146:4001`
- `139.84.241.187:4001`
- `141.11.139.150:4002`
- `110.42.109.179:4002`
- `183.136.206.164:3478/4001`
- `114.66.59.177:4001`
- `110.42.42.48:3479`
- `139.180.182.231:4001`
- `45.32.239.193:4001`
- `107.172.76.12:4001`

实验中确认：

- `TUN off` 时，`ByNATType` 会转绿。
- `TUN on` 时，如果这些探测 IP 没有完全绕过 `Meta/TUN`，`ByNATType` 会间歇性转红。
- 只有把当前观测到的一整组 NAT/STUN 探测 IP 纳入 `route-exclude-address`，这条诊断才稳定转绿。

结论：

- 这条红项不能直接下结论为“运营商就是 NAT4 / 对称 NAT”。
- 更准确地说，是当前诊断流量在 `TUN` 下被污染，导致 NAT 探测失真。

### 本次最终生效的修复

本次最终验证有效、并已准备固化回仓库的修复共有三类：

1. DNS 策略收窄后，额外补上 `+.baidu.com`，保证 `ByIPv6Connectivity` 的探测域名能获得 AAAA。
2. 默认剔除 `IP-CIDR6,::/0,REJECT,no-resolve`，避免把泛公网 IPv6 直接打死。
3. 将当前已观测到的 NAT/STUN 探测 IP 池并入 `route-exclude-address`，确保 `ByNATType` 的外连真正绕过 `Meta/TUN`。

### 风险与后续

当前方案已经把故障消除，但 NAT/STUN 探测地址存在轮换可能。

因此后续若再次出现 `ByNATType` 单项转红，优先排查：

1. `journalctl -u mihomo` 中新的 `3478/3479/4001/4002` 外连 IP
2. 这些新 IP 是否已被纳入 `route-exclude-address`
3. 是否有新的 LazyCat NAT 探测池需要加入默认绕行集合
