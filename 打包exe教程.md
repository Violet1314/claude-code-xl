---

# 🚀 Claude Code CLI 项目打包指南

本教程将引导你如何使用 `PyInstaller` 将 Python 项目打包成一个独立的 `.exe` 可执行文件。

### 1. 环境准备

在开始打包之前，请确保进入项目根目录并激活虚拟环境，以保证依赖库的完整性。

```powershell
# 进入项目目录
cd G:\7-Claude-code-cli\Claude-Code-CLI-main

# 激活虚拟环境 (PowerShell)
.\.venv\Scripts\Activate.ps1

```

### 2. 执行打包命令

我们使用 `--collect-all` 确保 `rich` 库的样式和资源被完整提取，同时将入口文件指向 `__main__.py`。

```powershell
pyinstaller --noconfirm --onefile --console `
    --name "ClaudeCode" `
    --paths "src" `
    --add-data "data/config;data/config" `
    --collect-all "rich" `
    --clean `
    src/claude_code/__main__.py

```

> **参数说明：**
> * `--onefile`: 将所有内容打包成一个单一的 .exe 文件。
> * `--collect-all "rich"`: 解决 rich 库在打包后可能出现的图标或颜色显示异常。
> * `--add-data`: 包含项目所需的静态配置文件。
> 
> 

### 3. 配置分发环境

打包完成后，`dist` 目录中生成了程序，但仍需手动维护外部配置文件路径（如适用）。

```powershell
# 创建运行所需的配置目录
mkdir dist\data\config

# 复制配置文件到发布目录
copy data\config\api-config.json dist\data\config\
copy data\config\system-prompts.json dist\data\config\

```

### 4. 运行与测试

一切就绪后，进入 `dist` 文件夹即可启动你的 AI 助手。

```powershell
cd dist
.\ClaudeCode.exe

```

---

**💡 提示：** 如果你在打包后遇到“找不到文件”的错误，请检查程序内部引用 `data/config` 时使用的是相对路径还是 `sys._MEIPASS` 路径。
