# Claude Code CLI 打包指南

## 1. 环境准备

```powershell
# 进入项目目录
cd E:\12-claude-code-xl\2026-02-01\Claude-Code-CLI-main

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 安装打包工具（如果未安装）
pip install pyinstaller
```

## 2. 执行打包

```powershell
pyinstaller --noconfirm --onefile --console `
    --name "ClaudeCode" `
    --paths "src" `
    --add-data "data/config;data/config" `
    --collect-all "rich" `
    --collect-all "prompt_toolkit" `
    --clean `
    src/claude_code/__main__.py
```

**参数说明**：

| 参数 | 说明 |
|------|------|
| `--onefile` | 打包成单个 exe 文件 |
| `--console` | 保留控制台窗口（CLI 必需） |
| `--paths "src"` | 添加 src 到模块搜索路径 |
| `--add-data "data/config;data/config"` | 嵌入配置文件 |
| `--collect-all "rich"` | 收集 Rich 库所有资源 |
| `--collect-all "prompt_toolkit"` | 收集 prompt-toolkit 所有资源 |
| `--clean` | 清理临时文件后重新打包 |

## 3. 部署配置文件

打包后的 exe 在 `dist` 目录。由于程序运行时需要外部配置，需要手动复制：

```powershell
# 创建配置目录
mkdir dist\data\config -Force

# 复制配置文件
copy data\config\api-config.json dist\data\config\
copy data\config\system-prompts.json dist\data\config\

# 创建历史和统计目录（可选）
mkdir dist\data\history -Force
mkdir dist\data\stats -Force
```

## 4. 运行测试

```powershell
cd dist
.\ClaudeCode.exe
```

---

## 常见问题

### Q: 执行 `.ps1` 脚本报错

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

### Q: 打包后运行报错找不到模块

确保 `--collect-all` 参数包含了所有依赖库：
- `rich` - 终端 UI 渲染
- `prompt_toolkit` - 交互式输入

### Q: 配置文件加载失败

确保 `data/config` 目录结构与源码一致：
```
dist/
├── ClaudeCode.exe
└── data/
    └── config/
        ├── api-config.json
        └── system-prompts.json
```

### Q: exe 文件过大

正常现象。由于包含 Python 运行时和所有依赖库，单文件打包通常 15-30 MB。

---

## 依赖列表

打包时会自动包含以下依赖（来自 `pyproject.toml`）：

| 依赖 | 版本 | 用途 |
|------|------|------|
| httpx | >=0.27.0 | HTTP 客户端（流式请求） |
| rich | >=13.7.0 | 终端 UI 渲染 |
| prompt-toolkit | >=3.0.43 | 交互式输入 |

---

## 目录结构

打包后的发布目录：

```
dist/
├── ClaudeCode.exe           # 主程序
└── data/
    ├── config/
    │   ├── api-config.json      # API 配置（含密钥）
    │   └── system-prompts.json  # AI 人格提示词
    ├── history/                 # 会话历史（运行时创建）
    └── stats/                   # 统计数据（运行时创建）
```

---

**版本**：v2.6.1
**更新日期**：2026-03-27