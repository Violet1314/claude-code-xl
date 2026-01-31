---

# 🚀 Claude Code CLI 项目打包指南

### 1. 环境准备与工具安装

首先进入目录并激活虚拟环境。如果尚未安装 `pyinstaller`，请务必执行安装命令，否则系统无法识别打包指令。

```powershell
# 进入项目目录
cd G:\7-Claude-code-cli\2026-02-01\Claude-Code-CLI-main

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 🛠️ 核心步骤：在虚拟环境中安装打包工具
pip install pyinstaller

```

### 2. 执行打包命令

使用以下命令进行封装。注意：PowerShell 中的多行连接符是反引号 ( ``` )。

```powershell
pyinstaller --noconfirm --onefile --console `
    --name "ClaudeCode" `
    --paths "src" `
    --add-data "data/config;data/config" `
    --collect-all "rich" `
    --clean `
    src/claude_code/__main__.py

```

### 3. 部署配置文件

打包生成的单个 `.exe` 文件位于 `dist` 目录。由于程序通常需要读取外部配置，我们需要手动同步 `data` 文件夹：

```powershell
# 创建配置目录
mkdir dist\data\config

# 复制必要的 JSON 配置文件
copy data\config\api-config.json dist\data\config\
copy data\config\system-prompts.json dist\data\config\

```

### 4. 运行测试

最后，进入 `dist` 目录验证打包结果：

```powershell
cd dist
.\ClaudeCode.exe

```

---

**⚠️ 注意事项：**

* **权限问题**：如果执行 `Activate.ps1` 报错，请先运行 `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process`。
* **资源收集**：`--collect-all "rich"` 非常关键，它确保了终端里的彩色输出和漂亮的 UI 能够正常显示。
