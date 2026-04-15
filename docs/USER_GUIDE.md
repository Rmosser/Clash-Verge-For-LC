# 用户指南

这份文档只写最终用户在浏览器里的操作，不写宿主机部署、Docker、Node.js 或 systemd。

## 适用对象

适用于已经装好 `Clash Verge For LC` 懒猫应用、只需要导入订阅和切换节点的用户。

如果你要改宿主机运行时或让 Docker 容器走代理，改看：

- [CURRENT_RUNTIME.md](CURRENT_RUNTIME.md)
- [CONTAINER_PROXY_GUIDE.md](CONTAINER_PROXY_GUIDE.md)
- [HOST_NATIVE_RUNBOOK.md](HOST_NATIVE_RUNBOOK.md)

## 首次使用

1. 打开 `https://clash.<box>.heiyu.space`
2. 用懒猫账号登录
3. 进入 `Profiles`
4. 粘贴订阅 URL，或把 YAML 文件拖进页面
5. 更新订阅
6. 进入 `Proxies`
7. 选择一个节点或自动分组
8. 打开 `https://ip.sb` 确认出口已变化

### SubHub 用户

- 使用直出 YAML 链接
- 不要把需要懒猫登录的页面地址直接粘进订阅框
- 如果大订阅拉取超时，先在浏览器下载 YAML，再拖拽导入

## 日常使用

### 切换节点

- 在 `Proxies` 页直接切换
- 需要重新测速时，先跑延迟测试再选节点

### 更新订阅

- 在 `Profiles` 页点击更新
- 自动更新可以开，但不是首次使用的前置条件

### 看状态

- `Logs`：看规则命中和实时连接日志
- `Connections`：看当前活跃连接并手动断开异常连接

## 你会看到的 Web 版限制

- `System Proxy` 是灰色的：Web 版不能接管你的电脑系统代理
- `TUN` 开关是灰色的：TUN 由宿主机运行时决定，不在浏览器里切
- `Lightweight Mode`、`UWP Tool`、托盘相关功能不可用：这些属于桌面版能力

这些都不是 bug。

## 不要做的事

- 不要试图直接访问或暴露 `9090`
- 不要把“桌面版可点”的功能默认当成“Web 版也该能点”
- 不要把需要登录的网页地址当成订阅地址

## 常见问题

### 页面能开，但节点切换或状态不正常

先做两件事：

1. 刷新页面
2. 回到 `Profiles` 重新更新当前订阅

如果仍然异常，让运维排查 [HOST_NATIVE_RUNBOOK.md](HOST_NATIVE_RUNBOOK.md)。

### 浏览器能用，但 Docker 应用仍然出不了网

这不是用户侧问题。容器出网默认不靠浏览器设置，改看 [CONTAINER_PROXY_GUIDE.md](CONTAINER_PROXY_GUIDE.md)。
