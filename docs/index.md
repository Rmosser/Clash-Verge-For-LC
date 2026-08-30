# 文档索引

本仓库是懒猫微服上的 Mihomo / Clash Verge 管理服务。这里按问题路由到当前有效文档；历史材料不替代运行 contract。

## 按任务加载

| 任务 | 必读上下文 | 最小验证与同步 |
| --- | --- | --- |
| Dashboard 功能或 UI | `quality.md`、相邻代码/测试；需要运行态能力时再读 `CURRENT_RUNTIME.md` | 定向 unit/typecheck/lint/build；用户行为变化同步用户文档或 smoke 清单 |
| Verge API、宿主机脚本 | `CURRENT_RUNTIME.md`、`../scripts/README.md`、`quality.md` | `bash scripts/test.sh`；接口或默认值变化同步 Current/Runbook |
| TUN、DNS、透明代理、容器出网 | `LAZYCAT_NETWORK_REPORT.md`、`SECURITY.md`、`HOST_NATIVE_RUNBOOK.md` | 先证明回退路径，再做远端 readback；本地或 CI 不能替代运行态验收 |
| LPK 构建或发布 | `PACKAGING.md`、`quality.md` | 包检查与安装/入口 smoke 分层报告 |
| 上游同步 | `../scripts/README.md`、overlay manifest/patch series、迁移计划 | 重放 overlay，并运行 dashboard 全部门禁 |
| 文档、Harness、交付规则 | 本页、`governance/development-change-evidence.md`、`doc-sync-rules.json` | `python3 -I -B scripts/check_docs.py --all` 与 Fresh Reader 复读 |

表中没有命中的任务，从相邻代码和测试开始，只在遇到跨域 contract 时继续展开。`planning/`、`exec-plans/completed/` 和已完成计划默认不加载。

## Agent 与质量

- [../AGENTS.md](../AGENTS.md)：最小入口和安全边界。
- [quality.md](quality.md)：本地与 CI 的 test、lint、typecheck、build、文档检查和 smoke 命令。
- [../scripts/README.md](../scripts/README.md)：部署、诊断和质量脚本的用途。
- [doc-sync-rules.json](doc-sync-rules.json)：稳定入口、必需路径和本地链接检查清单。

## 产品与运行

- [../README.md](../README.md)：项目定位、快速开始和用户入口。
- [USER_GUIDE.md](USER_GUIDE.md)：用户指南、订阅导入、Docker 代理和常见问题。
- [CONTAINER_PROXY_GUIDE.md](CONTAINER_PROXY_GUIDE.md)：开发容器使用宿主机代理的配置与诊断。
- [CURRENT_RUNTIME.md](CURRENT_RUNTIME.md)：当前运行 contract。
- [LAZYCAT_NETWORK_REPORT.md](LAZYCAT_NETWORK_REPORT.md)：TUN、控制面绕行、容器出网和网络风险。
- [SECURITY.md](SECURITY.md)：controller 隔离、secret 管理和安全边界。
- [HOST_NATIVE_RUNBOOK.md](HOST_NATIVE_RUNBOOK.md)：宿主机部署、恢复和重启验收。
- [PACKAGING.md](PACKAGING.md)：LPK 构建与发布边界。
- [CLASH_VERGE_WEB_SMOKE_CHECKLIST.md](CLASH_VERGE_WEB_SMOKE_CHECKLIST.md)：Web 回归清单。

## 交付与计划

- [development-change-evidence.md](governance/development-change-evidence.md)：候选变更、CI 与平台证据边界。
- [../.woodpecker/woodpecker-harness.yaml](../.woodpecker/woodpecker-harness.yaml)：无 secret 的 PR/push 开发检查。
- [plans/template.md](plans/template.md)：复杂或长周期任务可选的轻量计划模板。
- [plans/clash-verge-rev-v2.5.2-webport.md](plans/clash-verge-rev-v2.5.2-webport.md)：尚未开始的 Clash Verge Rev v2.5.2 WebPort 迁移方案。

计划是按需上下文，不是全局机器 schema。仓库文件可以说明检查要求，但 GitHub required checks、branch protection、Review 和运行态部署状态必须从对应平台实时读取。

## 历史与背景

- [PRD.md](PRD.md)：历史设计文档，不是当前手册。
- [planning/](planning/)：事故分析和复盘。
- [exec-plans/completed/](exec-plans/completed/)：已完成或被取代的旧计划，仅供追溯。
