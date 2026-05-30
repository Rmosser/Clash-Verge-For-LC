# deploy/

这是一个可选的 Docker Compose 方案，用来在微服宿主机上运行 `mihomo` 容器。

它不是当前仓库默认和已验证的整套部署路径。当前默认路径是 host-native，见 [../docs/CURRENT_RUNTIME.md](../docs/CURRENT_RUNTIME.md) 和 [../docs/HOST_NATIVE_RUNBOOK.md](../docs/HOST_NATIVE_RUNBOOK.md)。

## 适用场景

只在以下场景使用：

- 你明确要用 Docker 管理 `mihomo` core
- 你接受 `host network`、`NET_ADMIN`、`/dev/net/tun` 带来的高权限网络风险
- 你知道这套 compose 目录只覆盖 `mihomo` core，不自动提供当前 dashboard 依赖的完整 host-native 运行链

## 不适用场景

以下需求不要优先选这里：

- 想得到当前仓库推荐的默认部署方案
- 想直接复用当前 dashboard 的完整 `/verge-api/public-config` 引导链
- 想把文档中的“当前已验证基线”原样部署到 `rainierdev` 或 `rainierspace`

## 快速开始

```bash
cd deploy
cp .env.example .env
./init.sh
docker compose up -d
```

默认情况下：

- `MIHOMO_TUN_ENABLE=1`
- `external-controller` 必须保持 `172.18.0.1:9090`
- `secret` 会在为空时生成到 `deploy/secret.txt`

## TUN 开关

关闭 TUN：

```bash
MIHOMO_TUN_ENABLE=0 ./init.sh
```

## 当前限制

- 这份 compose 目录只管 `mihomo`
- 它不自动安装 `mihomo-verge-api`
- 它不自动提供当前仓库默认的浏览器运行时引导路径

如果你要当前仓库的默认整套链路，回到仓库根目录执行：

```bash
MICROSERVER_HOST=<box>.heiyu.space \
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 bash scripts/deploy_microserver.sh
MICROSERVER_HOST=<box>.heiyu.space \
bash scripts/deploy_dashboard.sh
```
