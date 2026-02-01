# 懒猫微服 Clash 运行与管理（mihomo + metacubexd）PRD

> 目标：让一个“代码型 AI”（或开发者）按本文档实现一个**可一键部署、可网页管理、可开机自启**的 Clash（Clash-compatible）运行环境，运行在懒猫微服（Debian 系）Linux 服务器上。

---
## 1. 背景与问题

### 1.1 背景

* 用户希望在**懒猫微服**上运行 Clash 核心，实现本机/局域网的代理与规则分流能力，并且通过网页面板进行管理。
* 选型固定为：

  * 内核：MetaCubeX/mihomo（Clash-compatible，规则隧道内核）
  * 前端：MetaCubeX/metacubexd（官方 Dashboard）

mihomo 的官方文档提供了 systemd 服务化示例、配置项说明与 RESTful API。([虚空终端][1])
metacubexd 官方仓库提供了功能列表与多种部署方式（预构建静态资源、Docker、Compose）。([GitHub][2])

### 1.2 懒猫微服环境特性（约束）

* 懒猫微服操作系统基于 Debian（官方描述）。([懒猫云][3])
* 懒猫微服提供 Dockerd 开发模式（独立 Docker 守护进程）并对特权容器给出安全风险提示。([懒猫微服][4])
* 若用户使用 KVM 模式对外暴露端口，存在少量不支持的端口区间（需避开）。([懒猫微服][5])

### 1.3 需要解决的核心问题

1. **部署复杂**：mihomo 二进制、配置目录、systemd 服务、面板静态文件、端口与鉴权等需要手工串起来。
2. **管理门槛**：希望在浏览器里能看到流量、切换节点、看日志、更新订阅（provider）等。
3. **安全风险**：外网暴露面板/API 易被扫描，需要最小暴露面（建议不直接暴露 controller 端口）。
4. **平台适配**：懒猫微服既可走“传统 SSH/systemd”，也可走 “Dockerd + Compose”。

---

## 2. 产品目标与成功标准

### 2.1 产品目标（MVP）

1. 在懒猫微服上**稳定运行 mihomo**，支持开机自启、崩溃自启。([虚空终端][1])
2. 提供 **metacubexd Web 面板**，可在浏览器中完成常用管理（流量、节点、连接、规则、日志等）。([GitHub][2])
3. 默认提供**安全基线**：

   * controller API 不直接暴露到公网（默认仅本机/内网可达）
   * API 启用 secret（Bearer Token）([虚空终端][6])
4. 提供两种部署路径（至少实现一种，推荐两种都交付）：

   * **方案 A：Dockerd + docker compose（适配懒猫微服 Dockge/pg-docker）**([懒猫微服][4])
   * **方案 B：systemd（传统 Linux 方式）**([虚空终端][1])

### 2.2 成功标准（验收口径）

* 部署完成后：

  * `mihomo` 进程持续运行（或容器健康运行）
  * 浏览器可打开面板并成功连接到内核（能看到代理组/节点列表）
  * 能切换代理组、执行延迟测试、查看实时日志、查看连接列表（由 metacubexd 支持）([GitHub][2])
* 重启服务器后服务自动恢复（systemd WantedBy 或容器 restart always）。([虚空终端][1])

---

## 3. 范围定义

### 3.1 MVP 范围（必须做）

1. **一键部署**（脚本或 compose 一条命令落地）
2. **配置落地**：创建标准目录结构、生成/导入 config.yaml
3. **服务化运行**：systemd 或 docker restart 策略
4. **面板可用**：metacubexd 静态文件部署或容器部署
5. **安全基线**：secret、最小暴露端口

### 3.2 增强范围（可选）

* HTTPS/TLS（自签或反代证书）
* 多用户/多实例（不同配置目录、不同端口）
* 自动更新（mihomo / metacubexd / GEO 数据）：

  * mihomo API 提供升级与更新 UI/GEO 的接口能力（如 /upgrade、/upgrade/ui、/upgrade/geo）。([虚空终端][7])
* 订阅管理增强（配置模板自动生成 proxy-providers / rule-providers）
* 与懒猫微服的“应用形态”（lzcapp）集成（若用户计划上架/图形化安装）

### 3.3 非目标（明确不做）

* 不开发新的代理协议/加密算法
* 不提供机场订阅或节点内容
* 不处理任何“绕过/规避监管”的场景描述（仅提供通用网络代理与分流能力部署）

---

## 4. 用户画像与典型场景

### 4.1 用户画像

* **个人开发者/极客**：能 SSH，能看日志，想要稳定运行与网页管理。
* **家庭网络管理员**：希望给内网设备提供统一代理出口/分流策略。

### 4.2 典型用户故事（User Stories）

1. 作为用户，我想“一键安装”，不用手动拼 systemd、UI、配置。
2. 作为用户，我想在浏览器打开面板，看到实时流量与连接，并切换节点。([GitHub][2])
3. 作为用户，我希望重启懒猫微服后服务自动起来。([虚空终端][1])
4. 作为用户，我希望 controller API 不直接暴露公网，至少要有 secret。([虚空终端][6])

---

## 5. 功能需求（FR）

### FR-1 部署与初始化

**输入**

* 运行环境：懒猫微服 Debian 系 Linux（可用 root/SSH 或 Dockerd 模式）。([懒猫云][3])
* 用户提供：一个 mihomo 配置（config.yaml）或订阅（由用户自行转换/生成）。

**输出**

* mihomo 可运行并加载配置目录（`-d /etc/mihomo` 或容器映射配置目录）。([虚空终端][1])
* metacubexd 可访问。

**要求**

* 自动识别架构（x86_64/arm64/armv7 等），下载匹配的发布包（若走二进制安装）。

  * mihomo 官方 FAQ 说明 release 文件名包含 OS、架构、GOAMD64 v1/2/3 等信息。([虚空终端][8])

### FR-2 核心服务运行（mihomo）

* 必须支持：

  * HTTP/SOCKS/mixed 入站端口（至少 mixed-port）
  * allow-lan 与 bind-address（可选开启 LAN 共享）([虚空终端][6])
  * authentication（可选，给代理端口加用户名密码）([虚空终端][6])
  * external-controller（API 地址与端口）([虚空终端][6])
  * secret（API 鉴权 token）([虚空终端][6])

> 注意：external-controller 可以绑定 `127.0.0.1`，也可改成 `0.0.0.0` 监听所有地址。([虚空终端][6])
> PRD 推荐默认绑定 127.0.0.1，再通过反代/同机部署面板访问，减少暴露面。

### FR-3 Web 面板（metacubexd）

* 面板必须提供（由 metacubexd 本身能力覆盖）：

  * 实时流量与统计
  * 代理组管理与延迟测试
  * 连接跟踪与管理
  * 规则查看
  * 实时日志流
  * 移动端自适应 & 多语言([GitHub][2])

* 部署方式（二选一或都支持）：

  1. **预构建静态资源**：克隆 gh-pages 分支到某目录，并通过 `external-ui` 指向该目录（或自行用 Web 服务器托管）。([GitHub][2])
  2. **Docker**：直接运行 `ghcr.io/metacubex/metacubexd`，可设置默认后端 URL。([GitHub][2])

mihomo 官方文档将 metacubexd 列为可用 Web dashboard 之一。([虚空终端][9])

### FR-4 API 交互与基础运维接口（可由脚本/CLI 实现）

为了让“AI 开发”更可控，建议交付一个 `mihomo-manager`（脚本或轻量 CLI），封装常用动作：

* `status`：查看运行状态（systemd status 或 docker ps）
* `logs`：查看/跟随日志（journalctl 或 docker logs）
* `reload`：热重载配置（mihomo API：`PUT /configs?force=true`）([虚空终端][7])
* `restart-core`：内核重启（mihomo API：`POST /restart`）([虚空终端][7])
* `update-geo`：更新 GEO（mihomo API：`POST /upgrade/geo` 或 `/configs/geo`，按实现选择）([虚空终端][7])
* `update-ui`（可选）：更新面板（mihomo API：`POST /upgrade/ui`，前提设置了 external-ui）([虚空终端][7])

API 鉴权方式：`Authorization: Bearer ${secret}`。([虚空终端][7])

### FR-5 端口与网络暴露策略

必须明确端口与用途（默认值可调整）：

* `mixed-port`：对内网设备提供代理（例如 7890）
* `external-controller`：API（建议 127.0.0.1:9090，仅本机）
* `dashboard`：面板端口（如 80/8080/9999）

**对外访问建议**

* 若需要外网访问面板，必须支持：

  * 绑定到域名/反向代理（推荐）
  * 或使用懒猫微服的端口映射/穿透能力（注意避开 KVM 不支持端口列表）([懒猫微服][5])

---

## 6. 非功能需求（NFR）

### NFR-1 稳定性

* 崩溃自动重启

  * systemd：`Restart=always`（官方示例）([虚空终端][1])
  * docker：`restart: always`（metacubexd 示例）([GitHub][2])

### NFR-2 安全

* 默认不将 mihomo 的 controller API 直接暴露公网
* API 必须启用 secret（不允许默认空）
* 若通过 Docker 运行并启用 tun/透明代理，需要 `NET_ADMIN`/特权能力时，必须在文档中显著提示风险（懒猫微服 Dockerd 文档已强调特权容器风险）。([懒猫微服][4])

### NFR-3 可维护性

* 配置与数据目录清晰可备份
* 关键参数通过 `.env` 或单一配置文件集中管理
* 所有生成文件可重复生成（幂等），二次执行不破坏现有配置（除非显式 `--force`）

### NFR-4 兼容性

* 至少支持：

  * x86_64（懒猫微服常见为 x86 平台）
  * arm64（若用户在其他设备复用）
* 二进制下载需按架构选择正确 release 包（参见官方 FAQ 命名规则）。([虚空终端][8])

---

## 7. 系统方案设计

## 7.1 总体架构

**推荐架构（安全优先，面板同机）：**

1. mihomo：

   * 监听 mixed-port（给客户端用）
   * external-controller 仅监听 127.0.0.1
2. metacubexd：

   * 以静态站点形式运行（Nginx/Caddy/容器内自带 Web Server）
   * 通过同机访问 127.0.0.1:9090 或反代路径访问 controller API

**备选架构（简单但风险更高）：**

* external-controller 直接监听 0.0.0.0，并在内网访问（官方面板 Quick Start 示例如此）。([GitHub][2])

---

## 7.2 关键配置项（mihomo config.yaml）

PRD 要求安装器/模板至少覆盖以下配置点（字段含义见官方文档）：

* `allow-lan`、`bind-address`、`lan-allowed-ips`、`authentication`（可选）([虚空终端][6])
* `external-controller`、`external-controller-cors`、`secret`([虚空终端][6])
* `external-ui` / `external-ui-name` / `external-ui-url`（若采用 mihomo 承载 UI 或提供 UI 更新）([虚空终端][6])

> 备注：官方文档提示当 external-ui 路径不在工作目录时，可能需要配置 `SAFE_PATHS` 环境变量。([虚空终端][6])

---

## 7.3 服务化运行（systemd 方案）

* 参考 mihomo 官方 systemd 示例（ExecStart 使用 `mihomo -d /etc/mihomo`，并声明多项 capabilities）。([虚空终端][1])

PRD 要求 installer 在 systemd 模式下自动生成：

* `/usr/local/bin/mihomo`（或发行版包路径）
* `/etc/mihomo/config.yaml`
* `/etc/systemd/system/mihomo.service`
* 执行 `systemctl daemon-reload && systemctl enable --now mihomo`

---

## 7.4 容器化运行（Dockerd + Compose 方案）

面向懒猫微服更友好（Dockge/pg-docker），并可做到：

* 不改动系统级文件
* 配置文件、日志、规则数据通过 volumes 持久化
* 一键 `docker compose up -d`

参考 metacubexd 官方 README 中的 compose 示例：metacubexd 使用 `ghcr.io/metacubex/metacubexd`，mihomo 可选 `docker.io/metacubex/mihomo:Alpha` 且需要高权限能力。([GitHub][2])

同时必须遵循懒猫微服 Dockerd 文档对 `privileged`/`cap_add` 风险提示，PRD 要求文档显著告知用户不要随意暴露高风险端口到外网。([懒猫微服][4])

---

## 8. 交互与使用流程（用户旅程）

### 8.1 初次部署（MVP）

1. 用户选择部署模式：

   * Dockerd（推荐）
   * systemd（传统）
2. 用户提供/放置 `config.yaml`（或使用模板后再编辑）
3. 启动服务
4. 浏览器打开面板地址
5. 在面板输入/选择后端（controller URL）与 secret，连接成功
6. 完成节点切换与分流验证

### 8.2 日常操作

* 查看流量与连接
* 切换代理组 / 节点
* 查看实时日志
* 更新 providers（由配置里的 interval 或 UI 触发）

---

## 9. 数据与目录规范（建议标准）

### 9.1 systemd 模式目录

* `/etc/mihomo/`

  * `config.yaml`
  * `ui/`（可选：metacubexd 静态文件）
  * `rules/`、`providers/`（可选）
* 日志：`journalctl -u mihomo`（官方示例）([虚空终端][1])

### 9.2 Docker 模式目录（compose 同级）

* `./config.yaml`
* `./data/`（providers、缓存、GEO 等）
* `./ui/`（如果不用 metacubexd 容器而是静态托管）

---

## 10. 风险与对策

1. **外网暴露风险**

   * 风险：暴露 controller API/面板会被扫描
   * 对策：默认 controller 仅监听 127.0.0.1，或至少启用 secret；外网访问必须加额外鉴权/反代/白名单

2. **Docker 特权容器风险**

   * 风险：tun/透明代理需要 NET_ADMIN/privileged，可能影响系统与数据安全
   * 对策：默认 MVP 不开启 tun；如需 tun，文档提示与最小权限配置（遵循懒猫 Dockerd 风险提示）。([懒猫微服][4])

3. **架构/内核版本兼容**

   * 风险：下载错二进制或 Linux 内核过旧
   * 对策：下载阶段按官方命名规则匹配；必要时提示选择带 `go123/go120` tag 的兼容包（官方 FAQ 提到 Linux kernel 与 Go 版本支持差异）。([虚空终端][8])

4. **端口映射限制（KVM）**

   * 风险：部分端口不支持转发导致外网访问失败
   * 对策：默认选择常见端口（80/8080/10000+），避开文档列出的不支持端口。([懒猫微服][5])

---

## 11. 验收标准（Acceptance Criteria）

### AC-1 功能验收

* 可启动 mihomo，且能加载指定配置目录（`-d` 参数目录存在且包含 config.yaml）。([虚空终端][1])
* metacubexd 面板可访问，且连接 mihomo controller 成功，页面展示：

  * Proxies / Proxy Groups / Connections / Rules / Logs 等模块正常工作([GitHub][2])
* 能通过 API 完成至少一次配置 reload（`PUT /configs?force=true`）并返回成功。([虚空终端][7])

### AC-2 安全验收

* 默认安装完成后：

  * controller API 不对公网暴露（仅 127.0.0.1 或内网）
  * secret 非空，且面板连接必须输入/携带 secret([虚空终端][6])

### AC-3 运维验收

* 重启系统后服务自动拉起（systemd enable 或 docker restart always）。([虚空终端][1])

---

## 12. 交付物清单（给“AI 开发”用）

### 12.1 必交付

1. `README.md`

   * 懒猫微服两种部署方式说明（Dockerd / systemd）
   * 端口说明与安全建议
2. `deploy/`

   * `docker-compose.yml`（Dockerd 模式）
   * `.env.example`
3. `systemd/`（若实现 systemd 模式）

   * `install.sh`（下载 mihomo + 放置 config + 安装 service）
   * `mihomo.service.tpl`
4. `config/`

   * `config.yaml.template`（含 external-controller、secret、allow-lan、基础 DNS/规则占位）
5. `scripts/`

   * `mihomo-manager`（status/logs/reload/restart 等封装，调用 systemd/docker + mihomo API）([虚空终端][7])

### 12.2 可选交付

* `nginx/` 或 `caddy/` 反代示例（面板同域访问 + controller 仅本机）
* `docs/SECURITY.md`（外网暴露注意事项，特别是 Docker 特权容器风险）([懒猫微服][4])

---

## 13. 参考资料（实现时必须遵循）

* mihomo systemd 服务化示例与能力声明（官方文档）。([虚空终端][1])
* mihomo General configuration（external-controller、secret、external-ui 等）。([虚空终端][6])
* mihomo API 文档（/configs、/restart、/upgrade/ui 等）。([虚空终端][7])
* mihomo release 文件选择规则（架构/GO 版本/GOAMD64 v1/2/3）。([虚空终端][8])
* metacubexd 官方 README（功能、预构建静态资源、Docker/Compose 示例）。([GitHub][2])
* 懒猫微服：系统基于 Debian（官方页面）。([懒猫云][3])
* 懒猫微服 Dockerd 模式与特权容器风险提示（官方开发者手册）。([懒猫微服][4])

---

如果用户希望我把这个 PRD **进一步收敛成“最小可实现版本（只做 Dockerd + Compose）”**，我可以在不改变用户选型（mihomo + metacubexd）的前提下，把“功能范围/交付物/验收标准”压到更适合一轮 AI 生成代码的粒度（每个文件写到字段级、每个命令写到可直接复制运行）。

[1]: https://wiki.metacubex.one/en/startup/service/ "Create a running service - mihomo docs"
[2]: https://github.com/MetaCubeX/metacubexd "GitHub - MetaCubeX/metacubexd: Mihomo Dashboard, The Official One, XD"
[3]: https://lazycat.cloud/ "懒猫微服"
[4]: https://developer.lazycat.cloud/dockerd-support.html "Dockerd 开发模式 | 懒猫微服开发者手册"
[5]: https://developer.lazycat.cloud/kvm.html "KVM 模式 | 懒猫微服开发者手册"
[6]: https://wiki.metacubex.one/en/config/general/ "General configuration - mihomo docs"
[7]: https://wiki.metacubex.one/en/api/ "APIs - mihomo docs"
[8]: https://wiki.metacubex.one/en/startup/faq/ "common problem - mihomo docs"
[9]: https://wiki.metacubex.one/en/startup/web/ "Web dashboard - mihomo docs"
