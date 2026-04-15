# infra/mihomo

宿主机部署 `mihomo` 时使用的模板和 unit 快照。

## 这里放什么

- `mihomo.service`：当前 host-native 部署使用的 systemd unit 模板
- `config.base.yaml`：安全模板；不含真实节点和凭据

## 这份目录解决什么问题

- 给 `scripts/deploy_microserver.sh` 提供稳定的模板输入
- 固定 controller 监听地址、TUN 基础字段和默认绕行集合
- 避免把真实私有配置写进仓库

## 不要在这里做什么

- 不要把真实订阅、secret 或节点凭据写进这个目录
- 不要把这份模板误当成目标机当前真实配置；目标机真相看 [../../docs/CURRENT_RUNTIME.md](../../docs/CURRENT_RUNTIME.md) 和 [../../docs/HOST_NATIVE_RUNBOOK.md](../../docs/HOST_NATIVE_RUNBOOK.md)
