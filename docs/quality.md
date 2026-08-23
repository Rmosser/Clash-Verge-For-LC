# Quality

本仓库同时包含宿主机/微服脚本、Python API 服务和 dashboard 前端。质量入口分成不需要远端状态的本地检查，以及必须连接运行环境的 smoke。

## 依赖准备

```bash
corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app install --frozen-lockfile
```

CI 使用锁文件安装依赖。仓库没有把 `pytest` 当作必需依赖；Python 服务测试使用标准库 `unittest`。
如果本机没有 Corepack，用
`npm exec --yes --package=pnpm@10.29.2 -- pnpm <args>` 运行下列同版本命令；
不要省略 `--frozen-lockfile` 或改用浮动 pnpm。

## 本地命令

先运行仓库级入口：

```bash
bash scripts/test.sh
```

它执行：

- `bash scripts/lint.sh`：仓库内 `.sh` 文件的 shell 语法和 Python 编译检查；
- `python3 -m unittest -v infra/microserver/test_mihomo_verge_api.py`：微服 API 单元测试；
- dashboard 的安装、单元测试、typecheck、lint 和 build 在下方单独运行；这样脚本在依赖尚未安装的 clean checkout 中仍能直接给出仓库级反馈。

其余质量门：

```bash
python3 -I -B scripts/check_docs.py --all
corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app install --frozen-lockfile
corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app typecheck
corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app test:unit
corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app lint
corepack pnpm@10.29.2 --dir src/mihomo-dashboard-app build
```

`build` 已经包含一次 TypeScript 检查；单独运行 `typecheck` 是为了让 CI 和本地失败信息更快定位。

## Smoke 与运行态回读

- `bash scripts/doctor.sh`：确认本地 runtime contract；本仓库没有长期运行的本地 daemon，因此只输出 stub 说明。
- `bash scripts/selfcheck.sh`：连接配置的微服主机，检查服务、controller、Verge API、DNS/TCP/HTTPS 和 TUN 绕行；需要 SSH 和远端 secret，不在 CI 中自动执行。
- [CLASH_VERGE_WEB_SMOKE_CHECKLIST.md](CLASH_VERGE_WEB_SMOKE_CHECKLIST.md)：需要浏览器/懒猫登录态的 Web 回归。
- 修改 TUN、DNS 或容器出网前，先读 [LAZYCAT_NETWORK_REPORT.md](LAZYCAT_NETWORK_REPORT.md)。

本地测试、CI 结果和远端运行态是三层证据：前两者通过不代表已经部署或运行态健康。

## CI

`.woodpecker/woodpecker-harness.yaml` 在面向 `main` 的 pull request 和 `main` push 上运行：

1. 文档入口检查、shell/Python 检查和 Python 单元测试；
2. 安装 dashboard 锁定依赖；
3. dashboard 单元测试、typecheck、ESLint 和生产构建。

CI 镜像、插件 digest、内存约束和无 secret 边界以 workflow 为准；GitHub required check 和运行态 smoke 仍须分别实时核实。

质量命令失败时，先报告第一个失败命令的完整错误、文件位置和是否属于依赖/环境问题；不要把远端 smoke 未执行写成通过。
