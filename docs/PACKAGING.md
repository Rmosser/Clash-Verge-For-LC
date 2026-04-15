# 打包与分发

这份文档只定义 LPK 打包，不定义宿主机部署。

## 只出包

```bash
bash scripts/build_dashboard_release.sh
```

产物目录：

```text
output/release/<version>/
```

目录内容：

- `clash-verge-for-lc-<version>.lpk`
- `clash-verge-for-lc-<version>.lpk.sha256`
- `INSTALL.md`
- `build-info.txt`

## LPK 包含什么

- Web dashboard 静态资源
- 懒猫 ingress 路由配置
- 同源订阅抓取代理 `fetchproxy`

## LPK 不包含什么

- `mihomo`
- `mihomo-verge-api`
- `mihomo-container-proxy`
- TUN、DNS、route bypass 等宿主机运行时配置

结论：`LPK` 只能完成“应用安装”，不能替代宿主机运行时部署。

## 宿主机运行时怎么部署

需要宿主机运行时：

```bash
MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0 bash scripts/deploy_microserver.sh
```

需要把 dashboard 直接装到当前 `lzc-cli` 选中的盒子：

```bash
bash scripts/deploy_dashboard.sh
```
