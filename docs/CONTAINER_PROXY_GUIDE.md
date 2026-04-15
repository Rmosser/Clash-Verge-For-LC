# 容器代理指南

这份文档只写容器和开发者该怎么走代理。

## 什么时候看这份文档

出现以下任一情况时，直接按本文配置：

- Docker 容器需要访问外网
- 浏览器能访问，但容器里的程序不行
- Node.js 程序设置了 `HTTP_PROXY` 仍然直连失败

## 核心规则

- 不要假设 TUN 会自动覆盖容器网络
- 容器统一走 `172.18.0.1:17890`
- `NO_PROXY` 里保留懒猫平台域名和代理入口本身

## 代理入口

```text
http://172.18.0.1:17890
```

这条链路实际转发到宿主机 `127.0.0.1:7890`。

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
