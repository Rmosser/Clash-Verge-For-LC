# PRD

状态：历史设计文档，不是当前 source of truth。

当前执行请改看：

- [CURRENT_RUNTIME.md](CURRENT_RUNTIME.md)
- [HOST_NATIVE_RUNBOOK.md](HOST_NATIVE_RUNBOOK.md)
- [USER_GUIDE.md](USER_GUIDE.md)

## 这份文档还保留什么

只保留仍然稳定的产品级约束：

- 运行核心是 `mihomo`
- Web 面板来自 `clash-verge-rev` / `metacubexd` 的 Web 适配
- controller 不直接暴露到 LAN/WAN
- 懒猫应用入口优先走同域路由，而不是裸端口
- 宿主机运行时、Web 面板、容器显式代理是三条不同职责的链路

## 已失效的设计假设

以下口径不要再当成当前真相：

- “部署后由用户在浏览器里手填 controller secret”
- “compose 是当前默认部署路径”
- “脚本默认值就等于当前推荐基线”
- “同一份 PRD 同时承担设计、实施、验收和当前运行 contract”

## 当前实现收敛

当前仓库已经把文档分成四类：

- 当前 contract：`CURRENT_RUNTIME.md`
- 面向最终用户：`USER_GUIDE.md`
- 面向运维：`HOST_NATIVE_RUNBOOK.md`
- 历史事故与复盘：`planning/`
