# Claude Code Terminal 使用教程

---

## 方式一：下载 ZIP 压缩包

### 1. 下载代码

从 GitHub 私人仓库下载 ZIP → 解压到任意目录

### 2. 进入项目目录

```powershell
cd 你的解压路径\Claude-Code-CLI-main
```

### 3. 创建虚拟环境

```powershell
python -m venv .venv
```

### 4. 激活虚拟环境

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows CMD
.\.venv\Scripts\activate.bat

# Linux/Mac
source .venv/bin/activate
```

### 5. 安装依赖

```powershell
pip install -e ".[dev]"
```

### 6. 配置 API（如果配置文件不含密钥）

编辑 `data/config/api-config.json`：

```json
{
  "base_url": "https://yunwu.ai/v1",
  "api_key": "你的API密钥",
  ...
}
```

### 7. 运行

```powershell
python -m claude_code
```

claude_code项目结构:
G:.
└─claude_code
    │  app.py
    │  __init__.py
    │  __main__.py
    │
    ├─commands
    │      base.py
    │      handlers.py
    │      registry.py
    │      __init__.py
    │
    ├─config
    │      defaults.py
    │      settings.py
    │      __init__.py
    │
    ├─core
    │      client.py
    │      conversation.py
    │      files.py
    │      stats.py
    │      __init__.py
    │
    ├─ui
    │      components.py
    │      console.py
    │      input.py
    │      renderer.py
    │      theme.py
    │      __init__.py
    │
    └─utils
            paths.py
            tokens.py
            __init__.py

项目打包教程:
cd G:\7-Claude-code-cli\Claude-Code-CLI-main

# 激活环境
.\.venv\Scripts\Activate.ps1

# 打包使用 --collect-all 收集 rich 的所有内容
pyinstaller --noconfirm --onefile --console --name "ClaudeCode" --paths "src" --add-data "data/config;data/config" --collect-all "rich" --clean src/claude_code/__main__.py

# 创建配置目录
mkdir dist\data\config

# 复制配置文件
copy data\config\api-config.json dist\data\config\
copy data\config\system-prompts.json dist\data\config\

# 运行
cd dist
.\ClaudeCode.exe
---