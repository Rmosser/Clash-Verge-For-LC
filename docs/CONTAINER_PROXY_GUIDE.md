# 容器代理指南

这份文档只写容器和开发者该怎么走代理。

## 什么时候看这份文档

出现以下任一情况时，直接按本文配置：

- Docker 容器需要访问外网
- 浏览器能访问，但容器里的程序不行
- Node.js 程序设置了 `HTTP_PROXY` 仍然直连失败

## 核心规则

- 不要假设 TUN 会自动覆盖容器网络
- 容器默认走 `172.18.0.1:17890`；需要固定出口的应用走 `172.18.0.1:17896`（见下文「固定节点入口」）
- `NO_PROXY` 里保留懒猫平台域名和代理入口本身

## 代理入口

```text
http://172.18.0.1:17890
```

这条链路实际转发到宿主机 `127.0.0.1:7890`。

## 固定节点入口

```text
http://172.18.0.1:17896
```

端口与 listener 的 `7896` 同尾数；`17891`–`17894` 在 rainierdev 上已被 CI webhook、npm/镜像缓存等服务占用，不要改用它们。

用户在 dashboard 里切换 `PROXY` 不影响这个入口：它转发到宿主机 `127.0.0.1:7896`，那是一个绑定了单个节点的 Mihomo listener。适合需要稳定出口、又不该跟着用户切节点的应用（例如长时间调用模型 API 的生产任务）。

链路由三层组成：

| 层 | 内容 | 持久化 |
| --- | --- | --- |
| Verge API overlay | `lzc-pinned-listeners: [{name, port, proxy}]` | `/var/lib/mihomo/verge/system-overlay.json`，切换或更新订阅时由 `build_runtime_text` 写入 `listeners:` |
| Mihomo listener | `127.0.0.1:7896`，`type: mixed`，`proxy: <节点名>` | 渲染进 `/etc/mihomo/config.yaml` |
| socket 转发 | `mihomo-container-proxy-pinned.socket/.service`：各 app bridge `:17896` → `127.0.0.1:7896` | systemd unit，由 bootstrap generation 恢复 |

### 设置或改指向的节点

在宿主机上调用 Verge API（节点名必须是当前运行配置里存在的节点或策略组，否则返回 `PINNED_LISTENER_UNKNOWN_PROXY`，不会保存）：

```bash
curl -fsS -X POST http://172.18.0.1:9091/invoke \
  -H "Authorization: Bearer $(cat /etc/mihomo/verge-api.secret)" \
  -H 'Content-Type: application/json' \
  -d '{"cmd":"patch_clash_config","args":{"payload":{"lzc-pinned-listeners":[{"name":"pinned-eb","port":7896,"proxy":"<节点名>"}]}}}'
```

端口不能和 mixed / socks / http / redir / tproxy 端口，以及 1053、7891、9090、9091 冲突。传空列表 `[]` 会删除这一项并重新渲染。

### 安装 socket、纳入开机自举

```bash
MICROSERVER_HOST=rainierdev.heiyu.space bash scripts/deploy_pinned_proxy.sh --confirm
MICROSERVER_HOST=rainierdev.heiyu.space bash scripts/install_host_native_bootstrap.sh --confirm
```

`deploy_pinned_proxy.sh --remove --confirm` 卸载 socket。改完 overlay 或 socket 后都要重新运行 bootstrap 安装，让 generation 记下新的 `config.yaml` 和 `PINNED_PROXY_ENABLED`。

### 验收

```bash
ss -lnt | grep -E '172\.18\.0\.1:1789(0|6)|127\.0\.0\.1:7896'
curl -s -x http://172.18.0.1:17890 https://ipinfo.io/ip   # PROXY 当前选择的出口
curl -s -x http://172.18.0.1:17896 https://ipinfo.io/ip   # 固定节点的出口
```

### 故障时的表现

- 节点从订阅里改名或消失：17896 上的连接直接失败（Mihomo 找不到 proxy），不会悄悄改走 `PROXY`；Verge API 的操作日志会记下这次渲染缺少节点。按上文把 overlay 指向新节点名即可。
- `deploy_microserver.sh` 会用本地私有配置覆盖 `config.yaml`，之后要通过 Verge API 重新渲染（`enhance_profiles` 或切换一次 profile）把 listener 带回来。

## 必配环境变量

```bash
HTTP_PROXY=http://172.18.0.1:17890
HTTPS_PROXY=http://172.18.0.1:17890
http_proxy=http://172.18.0.1:17890
https_proxy=http://172.18.0.1:17890
NO_PROXY=localhost,127.0.0.1,::1,.heiyu.space,.lazycat.cloud,172.18.0.1
no_proxy=localhost,127.0.0.1,::1,.heiyu.space,.lazycat.cloud,172.18.0.1
```

## Docker Compose 示例

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

## Node.js

Node.js 内置 `fetch` 不保证读取 `HTTP(S)_PROXY`。如果容器里的 Node.js 仍然直连失败，在启动时注入 `undici` 的代理 agent。

最小 bootstrap：

```js
(() => {
  const env = process.env;
  const hasProxy = !!(env.HTTP_PROXY || env.HTTPS_PROXY || env.http_proxy || env.https_proxy);
  if (!hasProxy) return;

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

启动方式：

```bash
NODE_OPTIONS=--require ./proxy-bootstrap.cjs node app.js
```
