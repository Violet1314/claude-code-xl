
---

# Claude Code CLI v2.8.33 打包指南

## 1. 环境准备

确保你在项目根目录下，且虚拟环境已激活。

```powershell
# 进入项目目录
cd E:\12-claude-code-xl\Claude-Code-CLI-main

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 确保安装了最新版的 PyInstaller
pip install pyinstaller --upgrade

# 确保所有依赖已安装（含 tiktoken）
pip install -e .
```

## 2. 执行打包命令

v2.8.33 引入了 tiktoken（C 扩展）、autosave、/doctor 等新功能，需要确保收集所有相关资源。

```powershell
pyinstaller --noconfirm --onefile --console `
    --name "ClaudeCode" `
    --paths "src" `
    --add-data "data/config;data/config" `
    --collect-all "rich" `
    --collect-all "prompt_toolkit" `
    --collect-all "httpx" `
    --collect-all "tiktoken" `
    --hidden-import "threading" `
    --hidden-import "pathlib" `
    --hidden-import "json" `
    --hidden-import "ast" `
    --hidden-import "re" `
    --hidden-import "dataclasses" `
    --clean `
    src/claude_code/__main__.py
```

### 参数说明

| 参数 | 说明 |
| --- | --- |
| `--onefile` | 打包成单个 exe 文件 |
| `--console` | 保留控制台窗口（CLI 必需） |
| `--paths "src"` | 添加 src 到模块搜索路径 |
| `--add-data "data/config;data/config"` | 嵌入配置文件目录 |
| `--collect-all "rich"` | **关键**：收集 Rich 库所有主题和样式资源 |
| `--collect-all "prompt_toolkit"` | **关键**：收集交互式输入组件 |
| `--collect-all "httpx"` | 收集 HTTP 客户端依赖 |
| `--collect-all "tiktoken"` | **v2.8.33 新增**：收集 tiktoken C 扩展（.pyd）和编码数据 |

## 3. tiktoken 打包特别说明

### 核心问题

tiktoken 是一个 C 扩展库（`.pyd` 文件），首次使用时需要加载 BPE tokenizer 数据。这些数据通常从网络下载缓存到本地。

### 解决方案

**方案 A：运行时联网下载（推荐，最简单）**

打包后的 exe 首次使用 tiktoken 时会自动从 GitHub 下载 BPE 数据缓存到用户目录。需要用户有网络连接。

如果用户无法联网，tiktoken 初始化会失败，但**程序不会崩溃** — 已内置优雅降级，自动回退到基于字符的快速估算。

**方案 B：预缓存 tokenizer 数据（离线环境推荐）**

在打包前，先运行一次程序让 tiktoken 缓存数据：

```powershell
# 在虚拟环境中预缓存
python -c "import tiktoken; tiktoken.get_encoding('o200k_base'); print('OK')"
```

缓存位置通常在：`%LOCALAPPDATA%\tiktoken_cache\`

将缓存文件随 exe 一起分发，或设置环境变量：

```powershell
# 设置缓存目录（可选，放在启动脚本中）
$env:TIKTOKEN_CACHE_DIR = ".\tiktoken_cache"
.\ClaudeCode.exe
```

### 降级行为

| 场景 | 行为 |
| --- | --- |
| tiktoken 正常加载 | 精确 token 计算（误差 <5%） |
| tiktoken 加载失败（无网络/无缓存） | 自动回退到字符估算（误差 ~30%，不影响功能） |
| tiktoken 未安装 | 同上，完全兼容 |

## 4. 打包后目录结构

```
dist/
├── ClaudeCode.exe               # 主程序
└── data/
    └── config/
        ├── api-config.json      # API 配置（模型、密钥）
        └── system-prompts.json  # 系统提示词

运行时自动创建：
├── data/history/                # 会话历史
├── data/sessions/               # 自动保存（autosave.json）
├── data/stats/                  # 统计数据
└── workplace/                   # 隔离工作区
```

## 5. 运行测试

```powershell
.\ClaudeCode.exe
```

### 常见启动问题

1.  **报错 `ModuleNotFoundError: No module named 'xxx'`**
    *   原因：某些隐式依赖未被 PyInstaller 捕获。
    *   解决：在打包命令中添加 `--hidden-import "xxx"`。

2.  **UI 样式混乱或颜色丢失**
    *   原因：Rich 的主题文件未正确打包。
    *   解决：确保使用了 `--collect-all "rich"`。

3.  **配置文件加载失败**
    *   原因：`data/config` 目录缺失或文件未复制。
    *   解决：检查 `dist/data/config/` 下是否有两个 json 文件。

4.  **tiktoken 相关报错（ModuleNotFoundError: tiktoken）**
    *   原因：tiktoken 的 .pyd 扩展未被 PyInstaller 收集。
    *   解决：确保使用了 `--collect-all "tiktoken"`。
    *   注意：即使 tiktoken 完全不可用，程序也能正常运行（自动降级）。

5.  **PowerShell 执行策略限制**
    *   如果运行 `.ps1` 脚本报错，先执行：
        ```powershell
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
        ```

## 6. v2.8.33 新增功能打包注意

| 功能 | 打包影响 | 处理方式 |
| --- | --- | --- |
| tiktoken 精确 Token 估算 | 新增 C 扩展依赖 | `--collect-all "tiktoken"` |
| 会话崩溃自动恢复 | 新增 `data/sessions/` 目录 | 运行时自动创建 |
| /doctor 诊断命令 | 无额外依赖 | 无需处理 |
| /last-output 命令 | 无额外依赖 | 无需处理 |
| ProjectContext query 检索 | 无额外依赖 | 无需处理 |
| Unix→PS 转换建议 | 无额外依赖 | 无需处理 |
| 统一版本号 (__version__.py) | 无额外依赖 | 无需处理 |

## 7. 依赖列表

打包时会自动包含以下核心依赖：

| 依赖 | 版本要求 | 用途 | 打包注意 |
| --- | --- | --- | --- |
| `httpx` | >=0.27.0 | HTTP 客户端（流式请求、静默重试） | `--collect-all` |
| `rich` | >=13.7.0 | 终端 UI 渲染 (Panel, Markdown, Progress) | `--collect-all` |
| `prompt-toolkit` | >=3.0.43 | 交互式输入与菜单 | `--collect-all` |
| `tiktoken` | >=0.7.0 | Token 精确估算（可选，有降级方案） | `--collect-all` |

---
