# scripts/

这份文档只回答三个问题：什么时候用哪个脚本、它会改什么、哪些是当前默认路径。

## 当前默认路径

| 脚本 | 什么时候用 | 会改什么 |
| --- | --- | --- |
| `deploy_microserver.sh` | 部署或重种宿主机运行时 | 下发 `mihomo`、config、systemd units、Verge API、container proxy、可选 DNS 同步 |
| `deploy_dashboard.sh` | 安装或重装懒猫 dashboard 应用 | 构建并安装 LPK，校验 `/api`、`/verge-api` 和 websocket 链路 |
| `build_dashboard_release.sh` | 只出可分发 LPK | 在 `output/release/<version>/` 生成版本化安装包 |
| `install_host_native_bootstrap.sh` | 给 `rainierdev` / `rainierspace` 安装开机自举 | 采样当前 live host-native 部署并安装 root user-systemd bootstrap |

## 诊断与恢复

| 脚本 | 什么时候用 | 输出或效果 |
| --- | --- | --- |
| `selfcheck.sh` | 想快速看宿主机链路是否健康 | 检查服务状态、controller、`/verge-api/public-config`、绕行探针 |
| `mihomo-manager` | 需要远程 status/logs/reload/restart/rollback | 通过 SSH 包装常用运维动作 |
| `patch_remote_mihomo_config.py` | 想补丁化远端 `config.yaml` | 保持 secret、TUN、DNS、rules patch 的一致写法 |

## 可选或专项脚本

| 脚本 | 用途 |
| --- | --- |
| `update_metacubexd.sh` | 更新 vendored `metacubexd` 静态资源并补当前 Web 版 patch |
| `audit_proxy_egress.sh` | 审计每个代理节点的 IPv4/IPv6 出口 |
| `egress_fix.sh` | 自动挑选可用节点并做一轮显式代理验收 |
| `patch_auto_group.py` | 限定 `AUTO` 组使用的节点集合 |
| `block_aaaa_resolved.sh` / `unblock_aaaa_resolved.sh` | 专项 IPv6 绕行 workaround |
| `prefer_ipv4_gai.sh` / `unprefer_ipv4_gai.sh` | 调整地址族优先级的 workaround |
| `ensure_ipv6_reject_rule.py` | 注入 IPv6 fail-fast 规则 |
| `install_dev_host_native_bootstrap.sh` | 给 `rainierdev` 提供快捷入口，实质仍调用 `install_host_native_bootstrap.sh` |

## 当前最重要的执行约束

- 当前已验证基线不是脚本默认值；要显式传 `MIHOMO_TUN_ENABLE=0 MIHOMO_DNS_ENABLE=0`
- 改网络前先看 [../docs/LAZYCAT_NETWORK_REPORT.md](../docs/LAZYCAT_NETWORK_REPORT.md)
- 重启恢复和机器差异看 [../docs/HOST_NATIVE_RUNBOOK.md](../docs/HOST_NATIVE_RUNBOOK.md)
