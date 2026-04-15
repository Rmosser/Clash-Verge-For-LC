# 安全边界

## 必守规则

- 不要把 Mihomo `external-controller` 暴露到 LAN/WAN
- `external-controller` 保持在 `172.18.0.1:9090`
- 浏览器入口只走懒猫应用路由，不走裸端口
- `secret` 不允许为空
- 真实配置、订阅 token 和 secret 不进 Git；只放 `var/private/` 或目标机的私有路径

## 当前访问模型

- 用户访问：`https://clash.<box>.heiyu.space`
- 浏览器运行时配置：`/verge-api/public-config`
- 宿主机控制接口：
  - `172.18.0.1:9090`：controller
  - `172.18.0.1:9091`：Verge API
  - `172.18.0.1:17890`：container proxy

## 高风险变更

以下变更都默认视为高风险：

- 打开或重写 `tun`
- 打开或重写 `dns`
- 修改 `route-exclude-address`
- 覆盖 `.heiyu.space` / `.lazycat.cloud` 的解析策略
- 把 compose 方案直接拿去替代当前 host-native 运行链

动手前先读 [LAZYCAT_NETWORK_REPORT.md](LAZYCAT_NETWORK_REPORT.md)。

## 额外说明

`deploy/` 下的 compose 目录需要 `host network`、`NET_ADMIN` 和 `/dev/net/tun`，属于高权限网络方案。它不是当前仓库默认部署路径。
