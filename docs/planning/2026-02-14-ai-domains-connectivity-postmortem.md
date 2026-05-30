# 2026-02-14 微服内 AI 域名不可达排障复盘（OpenAI / Claude / Gemini）

状态：历史复盘，不是当前默认网络配置说明。

当前执行规则以 [../CURRENT_RUNTIME.md](../CURRENT_RUNTIME.md) 和 [../LAZYCAT_NETWORK_REPORT.md](../LAZYCAT_NETWORK_REPORT.md) 为准。本文件只保留当时的症状、证据和修复结论。

背景：在懒猫微服（Debian 12）上启用 Mihomo（Clash Meta / MetaCubeX mihomo）+ TUN 接管整机流量后，盒子内访问 ChatGPT/Claude/Gemini 相关域名出现“有的能开、有的完全打不开”的情况。本次排障与修复目标是：在不破坏懒猫控制面/内网穿透的前提下，让 AI 相关域名稳定可用，并形成可回滚的变更机制。

本复盘不包含任何 `secret`、节点账号/密码等敏感信息。

## 结论摘要

1. **直连链路存在“选择性 TLS 握手被掐断”**：`example.com` 直连可握手，但 `1.1.1.1` / `www.google.com` / `cloudflare-dns.com` 等直连在 TLS ClientHello 后被中断（`SSL_ERROR_SYSCALL`）。
2. **DNS 存在污染/异常回答**：对 `api.openai.com` / `chatgpt.com` / `gemini.google.com` 等域名，系统 DNS（含路由器 DNS 与部分公共 DNS）出现明显不可信的回答（返回不合理网段或 `SERVFAIL` / 空答案）。
3. **代理节点可达性不一致**：`PROXY` 选择为 `AUTO` 时可以访问上述站点；手动强制某些具体节点时，访问会再次失败。`AUTO` 的 `url-test` 会动态选择“当前能用”的节点，掩盖了节点差异。
4. **根修复是“让 DNS 走代理的 DoH + respect-rules”**：在 mihomo 内启用 `dns:`（本机 `127.0.0.1:1053`），DoH 使用 Cloudflare，并通过规则强制 DoH 端点走 `PROXY`，同时对 `.heiyu.space/.lazycat.cloud` 做 `nameserver-policy` 保持直连解析，避免破坏懒猫控制面。
5. `oaiusercontent.com` apex 目前 **NOERROR 但无 A/AAAA（NODATA）** 属于 DNS 记录层面事实；可用的主机多在子域名（如 `files.oaiusercontent.com`）。不要试图“硬把 apex 绑到某个子域名 IP”。

## 现场症状与证据

### 1) AI 域名“有的通有的不通”

复测域名集合（示例）：

- OpenAI: `openai.com`, `api.openai.com`, `chatgpt.com`, `oaistatic.com`, `oaiusercontent.com`
- Anthropic/Claude: `anthropic.com`, `claude.ai`
- Google/Gemini: `gemini.google.com`, `ai.google.dev`, `bard.google.com`

现象（修复前）：

- 部分域名 `ping` 不通，但 `https` 能通（这是正常的：很多站点禁 ICMP）
- 更关键的是：`https` 对某些大厂域名完全失败（握手被掐断或超时），且 DNS 回答异常

### 2) 直连链路 TLS 被掐断，但并非全网断

直连探测（关键信号）：

- `curl -Ivs https://example.com`：TLS 握手完整成功
- `curl -Ivs https://1.1.1.1` / `https://www.google.com` / `https://cloudflare-dns.com`：
  - TCP 443 可连接
  - TLS ClientHello 发出后立即 `SSL_ERROR_SYSCALL`

推论：上游网络/出口链路对特定目的地存在干预或不稳定（并非 mihomo 本身问题）。

### 3) DNS 异常：路由器 DNS 与公共 DNS 的表现不一致且不可依赖

- 系统默认上游 DNS 来自路由器（`192.168.1.1` / `fe80::1`）时，`resolvectl query` 对部分域名返回不可信结果。
- 尝试切换为公共直连 DNS（`223.5.5.5` / `119.29.29.29`）时，`busybox nslookup api.openai.com`、`chatgpt.com` 甚至返回 `SERVFAIL`（表明这条链路上公共 DNS 直连不稳定/被干预/策略限制）。

结论：**单靠“把系统 DNS 改成公共直连”无法保证 AI 域名干净解析**。

## 关键修复动作（已在微服落地）

### A. 启用 mihomo 的本机代理端口（用于显式验证与工具使用）

修复点：确保 `mixed-port: 7890` 真正监听在 `127.0.0.1:7890`。

验收命令：

```bash
ss -ltnp | rg ':7890\\b|:9090\\b|:1053\\b' || true
```

### B. PROXY 节点选择策略：保持 `PROXY= AUTO`

现象：

- `PROXY= AUTO` 可访问 `1.1.1.1/google/cloudflare-dns`
- 强制切换某些具体节点会导致同样站点 `SSL_ERROR_SYSCALL` 或超时

结论：在没有更严格的可达性评估规则前，**优先使用 `AUTO(url-test)`**，必要时把测试 URL 扩展为更贴近目标站点的组合（例如同时测 `cloudflare-dns.com/generate_204` 与 `www.google.com/generate_204`）。

### C. 启用 mihomo DNS（本机 1053）+ DoH 走 PROXY + respect-rules（核心）

目标：绕开系统 DNS 污染/异常回答，同时不破坏懒猫控制面解析。

实现要点：

- `dns.enable: true`
- `dns.listen: 127.0.0.1:1053`
- `dns.respect-rules: true`（让 DNS 查询也按规则走 PROXY/DIRECT）
- `dns.nameserver: https://1.1.1.1/dns-query`, `https://1.0.0.1/dns-query`
- `dns.nameserver-policy`：
  - `+.heiyu.space` / `+.lazycat.cloud` 强制使用直连 DNS（例如 `192.168.1.1`, `fe80::1`），避免控制面/穿透异常
- 配套规则：强制 DoH 端点 IP（`1.1.1.1/1.0.0.1` 及 IPv6）走 `PROXY`，否则仍会触发“直连 TLS 被掐断”。

验收命令（DNS + HTTPS）：

```bash
# 解析走 mihomo dns
busybox nslookup api.openai.com 127.0.0.1:1053
busybox nslookup chatgpt.com 127.0.0.1:1053
busybox nslookup gemini.google.com 127.0.0.1:1053

# 通过 mihomo 代理验证真实可达性
curl -sS -o /dev/null -w "%{http_code}\n" -x http://127.0.0.1:7890 https://api.openai.com/v1/models
```

### D. DNS 变更“断链自动回滚”机制（5 分钟未确认回滚）

风险：改 DNS / 改路由可能导致懒猫控制面不可达，进而远程断线。

落地机制：在微服安装脚本 `lzc-net-safe-apply`，提供：

- `apply-dns <iface> <dns...>`：应用 DNS 并创建 `systemd-run --on-active=300s` 的回滚 timer
- `confirm`：取消回滚（确认远程访问正常）
- `rollback`：立即回滚
- `status`：查看 timer 与当前 DNS

使用示例（5 分钟）：

```bash
export LZC_NET_ROLLBACK_DNS="192.168.1.1 fe80::1"
export LZC_NET_ROLLBACK_AFTER_SECS=300
/usr/local/sbin/lzc-net-safe-apply apply-dns wlp4s0 223.5.5.5 119.29.29.29
# 确认远程访问 OK 后：
/usr/local/sbin/lzc-net-safe-apply confirm
```

说明：该机制保证“你不 confirm 就会回滚”，是防断线的关键护栏。

### E. 让 systemd-resolved 直接使用 mihomo DNS

- `systemd-resolved` 默认仍指向 `127.0.0.53` 的 stub，而 upstream 是路由器/ISP，造成 `api.openai.com` 等返回被污染的地址。
- 强制 `resolved` 用 `127.0.0.1:1053`（mihomo DoH/respect-rules链）解决，就可以让 OpenClaw/TUN 的直连流量获得干净答案而不需手动指定 `-x`.
- 变更方法：在 `systemd` drop-in (`/etc/systemd/resolved.conf.d/`) 写入 `[Resolve] DNS=127.0.0.1`，`FallbackDNS=192.168.1.1 fe80::1`，然后 `systemctl restart systemd-resolved`. 仓库里新增 `scripts/use_mihomo_dns_resolved.sh` 便于远程执行。
- 验收命令：`resolvectl status` 应显示 `DNS Servers: 127.0.0.1`; `curl https://api.openai.com`（无 `-x`）需要在执行 `systemctl restart mihomo` 之后正常返回 (SSL 不再被 `SSL_ERROR_SYSCALL` 断开)。

## 关于 oaiusercontent.com 的特别说明

- `oaiusercontent.com`（apex）目前表现为 `NOERROR` 但无 A/AAAA（DoH 返回 SOA/Authority，无 Answer），因此 **解析为空是正常现象**。
- 可用主机通常在子域名，例如：
  - `files.oaiusercontent.com`：可解析、可通过代理访问（返回 404 也意味着连通没问题）
- 不建议硬编码 apex 到某个 Cloudflare IP（这会造成语义错误，并可能随时失效）。

## 最终验收清单（本次通过）

1. 懒猫应用入口可访问：`https://clash.<boxname>.heiyu.space` TLS 正常
2. `PROXY=AUTO` 时，通过 `127.0.0.1:7890` 访问：
   - `https://1.1.1.1` / `https://www.google.com` / `https://cloudflare-dns.com` 握手成功（200/301）
3. DoH 解析链路正常（通过代理）：Cloudflare/Google DoH 可返回 JSON（至少对常见域名有 Answer）
4. OpenAI API 验收：
   - `https://api.openai.com/v1/models` 返回 401（未带 token 的正确行为）
5. Gemini/Google 验收：
   - `https://gemini.google.com` 通过代理返回 200

## TODO（建议沉淀到仓库，避免“线上改了但仓库没记录”）

1. 把本次实测可用的 `dns:` 块 + DoH 规则，沉淀到仓库模板：
   - `infra/mihomo/config.base.yaml`
   - `scripts/patch_remote_mihomo_config.py`（确保部署脚本会自动注入）
2. 把 `lzc-net-safe-apply` 也沉淀到仓库（例如 `infra/microserver/`），并写入 `docs/LAZYCAT_NETWORK_REPORT.md` 的“安全变更流程”。
3. 扩展 `AUTO(url-test)` 的测试 URL 与候选节点策略，让“自动选路”更贴近 AI 目标站点真实可用性。
