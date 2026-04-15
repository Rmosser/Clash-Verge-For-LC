# networkdiagnostic-app

兼容版 `cloud.lazycat.networkdiagnostic`。目标不是重做前端，而是替换仓库可控的后端实现。

## 当前边界

- 保留官方前端构建产物
- 用仓库自己的后端实现 `/api/list-api` 和各个 `By*` 诊断接口
- 包名保持兼容，方便在盒子上替换官方应用

## 适用场景

- 官方包只有编译后的后端二进制，仓库内无法直接 patch
- 需要调整 `ByOrigin`、resolver 行为或其他诊断语义
- 需要保留现有前端 UI，但把后端逻辑收回到仓库里维护

## 目录约定

- `upstream-dist/`：官方前端快照
- `server.mjs`：仓库维护的诊断 API 实现

## 构建

```bash
cd src/networkdiagnostic-app
lzc-cli project build -f lzc-build.yml -o networkdiagnostic-compat.lpk
```

## 安装

```bash
lzc-cli app install src/networkdiagnostic-app/networkdiagnostic-compat.lpk
```
