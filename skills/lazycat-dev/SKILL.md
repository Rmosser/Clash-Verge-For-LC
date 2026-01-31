---
name: lazycat-dev
description: |
  懒猫微服（LazyCat Microservice）应用开发技能。用于在懒猫微服设备上创建、开发、调试和部署应用。

  触发场景：
  - 用户提到"懒猫微服"、"懒猫"、"LazyCat"、"LCMD"
  - 用户想要开发部署到懒猫微服的应用
  - 用户询问 lzc-cli 命令用法
  - 用户需要配置 lzc-build.yml 或 lzc-manifest.yml
  - 用户想在懒猫微服上部署前端、后端、数据库服务
  - 用户提到"懒猫算力舱"、"AI算力舱"、"算力舱"
  - 用户想要开发 AI 应用、调用本地大模型
  - 用户询问 GPU 加速、Ollama、大模型部署相关问题
---

# 懒猫微服开发

## 环境要求

- Node.js 18+
- lzc-cli：`npm install -g @lazycatcloud/lzc-cli`
- macOS 需要 rsync 3.2.0+：`brew install rsync`
- 懒猫微服客户端已安装并连接设备

检查环境：
```bash
node --version && lzc-cli --version && lzc-cli box list
```

## 核心工作流

### 1. 创建项目
```bash
lzc-cli project create <项目名>
```
选择模板（Vue3/React/Python/Go 等），自动生成项目结构。

### 2. 本地开发

**方式 A：本地开发服务器（推荐）**

修改 `lzc-build.yml` 的路由指向本地 IP：
```yaml
devshell:
  routes:
    - /=http://<本地IP>:3000
```

然后：
```bash
lzc-cli project devshell -f  # 重新部署（进入后输入 exit 退出）
npm install && npm run dev   # 本地启动开发服务器
```

**方式 B：容器内开发**
```bash
lzc-cli project devshell     # 进入开发容器
npm install && npm run dev   # 在容器内运行
```

### 3. 构建部署
```bash
lzc-cli project build        # 构建，生成 .lpk 文件
lzc-cli app install          # 部署到懒猫微服
```

## 项目结构

```
project/
├── lzc-build.yml      # 构建配置
├── lzc-manifest.yml   # 应用元信息
├── lzc-icon.png       # 应用图标（PNG，≥512×512）
├── src/               # 源代码
└── dist/              # 构建输出（contentdir）
```

## 快速配置示例

### 纯前端应用
```yaml
# lzc-build.yml
buildscript: npm run build
contentdir: ./dist

# lzc-manifest.yml
application:
  routes:
    - /=file:///lzcapp/pkg/content/dist
```

### 前后端应用
```yaml
# lzc-manifest.yml
application:
  routes:
    - /=http://frontend:3000
    - /api=http://backend:8080

services:
  frontend:
    image: registry.lazycat.cloud/node:18-alpine
  backend:
    image: registry.lazycat.cloud/python:3.11-alpine
```

### 带数据库应用
```yaml
# lzc-manifest.yml
services:
  mysql:
    image: registry.lazycat.cloud/mysql
    binds:
      - /lzcapp/var/mysql:/var/lib/mysql
    environment:
      - MYSQL_ROOT_PASSWORD=password
      - MYSQL_DATABASE=mydb
```
连接地址：`mysql.<package>.lzcapp:3306`

## 关键规则

1. **数据持久化**：只有 `/lzcapp/var` 目录数据会持久保存，其他目录重启后清空
2. **服务发现**：服务间通信使用 `http://<service名>:<端口>`
3. **GPU 加速**：在 `lzc-manifest.yml` 添加 `gpu_accel: true`
4. **多实例**：添加 `multi_instance: true` 支持多用户独立实例

## 懒猫AI算力舱

### 硬件规格
- **GPU**：NVIDIA Jetson Orin 64GB（275 TOPS 算力）
- **显存**：64GB LPDDR5（可运行 70B-671B 大模型）
- **CPU**：12核 Arm Cortex-A78AE @ 2.2GHz
- **网口**：2.5GbE + 10GbE 双网口

### 使用方式
1. **独立使用**：接显示器键鼠，作为 Ubuntu AI 电脑
2. **配合微服**：通过内网穿透远程调用 AI 算力

### 应用启用 GPU
```yaml
# lzc-manifest.yml
application:
  gpu_accel: true
```

### 调用本地大模型（Ollama）

算力舱可运行 Ollama 服务，应用通过 HTTP API 调用：

```python
# Python 示例：调用 Ollama API
import requests

response = requests.post(
    "http://ollama:11434/api/generate",
    json={
        "model": "qwen2.5:72b",
        "prompt": "你好",
        "stream": False
    }
)
result = response.json()["response"]
```

```yaml
# lzc-manifest.yml 配置 Ollama 服务
services:
  ollama:
    image: dustynv/ollama:r36.2.0
    binds:
      - /lzcapp/var/ollama:/ollama
    environment:
      - OLLAMA_MODELS=/ollama
```

### 推荐模型
| 模型 | 显存需求 | 适用场景 |
|------|---------|---------|
| qwen2.5:7b | ~8GB | 轻量对话 |
| qwen2.5:32b | ~20GB | 通用任务 |
| qwen2.5:72b | ~45GB | 复杂推理 |
| deepseek-r1:70b | ~45GB | 深度思考 |

## 常用命令速查

| 命令 | 作用 |
|------|------|
| `lzc-cli project create <name>` | 创建项目 |
| `lzc-cli project devshell` | 进入开发容器 |
| `lzc-cli project devshell -f` | 强制重建容器 |
| `lzc-cli project build` | 构建 .lpk |
| `lzc-cli app install` | 部署应用 |
| `lzc-cli app uninstall <id>` | 卸载应用 |
| `lzc-cli app log <id>` | 查看日志 |
| `lzc-cli box list` | 查看设备 |

## 详细参考

配置项详解、数据库配置、环境变量等完整参考：见 [references/api_reference.md](references/api_reference.md)

官方文档：https://developer.lazycat.cloud/
