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

---
