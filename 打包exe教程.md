
---

# Claude Code CLI v2.8.0 打包指南

## 1. 环境准备

确保你在项目根目录下，且虚拟环境已激活。

```powershell
# 进入项目目录
cd G:\7-Claude-code-cli\Claude-Code-CLI-main

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 确保安装了最新版的 PyInstaller
pip install pyinstaller --upgrade
```

## 2. 执行打包命令

v2.8.0 引入了更多 Rich UI 组件和后台线程，需要确保收集所有相关资源。

```powershell
pyinstaller --noconfirm --onefile --console `
    --name "ClaudeCode" `
    --paths "src" `
    --add-data "data/config;data/config" `
    --collect-all "rich" `
    --collect-all "prompt_toolkit" `
    --collect-all "httpx" `
    --hidden-import "threading" `
    --hidden-import "pathlib" `
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
| `--collect-all "httpx"` | 确保 HTTP 客户端及其证书 bundle 被包含 |
| `--hidden-import` | 显式包含可能被静态分析漏掉的模块 |
| `--clean` | 清理临时文件后重新打包，避免缓存冲突 |

## 3. 部署与配置

打包完成后，`dist` 目录下会生成 `ClaudeCode.exe`。由于程序运行时需要读写外部数据，**必须**保持以下目录结构：

```powershell
# 1. 进入 dist 目录
cd dist

# 2. 创建必要的目录结构
mkdir data\config -Force
mkdir data\history -Force
mkdir data\stats -Force
mkdir workplace -Force   # v2.8.0 核心：隔离工作区

# 3. 复制配置文件 (从项目根目录复制)
copy ..\data\config\api-config.json data\config\
copy ..\data\config\system-prompts.json data\config\
```

### 最终发布目录结构

```text
dist/
├── ClaudeCode.exe           # 主程序 (约 20-30MB)
└── data/
    ├── config/
    │   ├── api-config.json      # API 配置（含密钥）
    │   └── system-prompts.json  # AI 人格提示词 (v2.8.0 强化版)
    ├── history/                 # 会话历史 (运行时自动创建)
    └── stats/                   # 统计数据 (运行时自动创建)
└── workplace/                   # 隔离工作区 (运行时自动创建)
```

## 4. 运行测试

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

4.  **PowerShell 执行策略限制**
    *   如果运行 `.ps1` 脚本报错，先执行：
        ```powershell
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
        ```

## 5. v2.8.0 特别注意事项

*   **Workplace 隔离**：v2.8.0 默认将所有写操作隔离在 `workplace/` 目录。请确保该目录存在且有写入权限。
*   **系统提示词**：`system-prompts.json` 中包含了针对 PowerShell 和路径规则的最新指令，**务必使用最新版本**。
*   **实时计时**：v2.8.0 使用了 `threading` 进行后台 UI 刷新，如果遇到计时器不跳动，请检查杀毒软件是否拦截了多线程行为。

## 6. 依赖列表 (参考)

打包时会自动包含以下核心依赖：

| 依赖 | 版本要求 | 用途 |
| --- | --- | --- |
| `httpx` | >=0.27.0 | HTTP 客户端（流式请求、静默重试） |
| `rich` | >=13.7.0 | 终端 UI 渲染 (Panel, Markdown, Progress) |
| `prompt-toolkit` | >=3.0.43 | 交互式输入与菜单 |
| `pydantic` | (可选) | 如果用于配置验证 |

---