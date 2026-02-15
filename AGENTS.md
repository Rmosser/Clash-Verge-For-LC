# Project Agents

## lzc-clash_mihome - Agent 操作手册

目标：在懒猫微服上运行 Mihomo (Clash Meta)，实现：

- 国内直连 / 国外代理（兜底 MATCH,PROXY）
- 启用 TUN 透明代理，但必须绕行懒猫内网穿透/控制面相关流量
- 提供可视化 Web 控制台（作为懒猫应用）用于手动切换节点/分组

## Skills

- **lazycat-dev**: 懒猫微服应用开发/部署流程、lzc-cli、manifest/build 配置等。 (file: skills/lazycat-dev/SKILL.md)

## 关键约束

- 不要破坏懒猫内网穿透/控制面：任何透明代理/TUN 变更前先看 `docs/LAZYCAT_NETWORK_REPORT.md`。
- 不要把 Mihomo 控制端口暴露到局域网：当前对外只通过懒猫登录后的应用路由访问。

## 常用命令

```bash
# Local Runtime Contract v1 (stub; this repo has no long-running local daemon)
bash scripts/run_local.sh
bash scripts/stop_local.sh

# Local Runtime Contract v2 (stub)
bash scripts/doctor.sh

# 连接微服（示例）
ssh -i ~/.ssh/id_ed25519 root@rainierserver.heiyu.space

# 查看 mihomo 状态
systemctl status mihomo
journalctl -u mihomo -n 100 --no-pager

# 构建/部署 dashboard LPK
cd src/mihomo-dashboard-app
lzc-cli project build -f lzc-build.yml -o mihomo-dashboard.lpk
lzc-cli app install mihomo-dashboard.lpk
```
