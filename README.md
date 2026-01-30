# Claude Code CLI 使用教程

---

## 下载 ZIP 压缩包

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
<img width="1958" height="1143" alt="2026-01-31" src="https://github.com/user-attachments/assets/808ad3e5-776d-450b-af43-acf5de2b468b" />

### 8. 结构

```powershell
claude_code/
├── __main__.py          # 程序入口：启动 CLI 的主脚本
├── app.py               # 核心逻辑：管理应用生命周期与主循环
│
├── core/                # 【后端核心】
│   ├── client.py        # API 通信：负责与 LLM 服务端交互
│   ├── conversation.py  # 对话管理：处理历史记录与上下文切片
│   ├── files.py         # 文件操作：读写本地代码库的工具
│   └── stats.py         # 统计模块：Token 消耗与运行时间统计
│
├── ui/                  # 【界面交互】
│   ├── console.py       # 终端输出：处理富文本渲染 (Rich)
│   ├── input.py         # 用户输入：处理交互式命令与补全
│   ├── renderer.py      # 渲染引擎：将 Markdown/代码高亮输出
│   └── theme.py         # 主题配置：定义配色与 UI 样式
│
├── commands/            # 【命令系统】
│   ├── registry.py      # 命令注册中心
│   └── handlers.py      # 命令处理器：定义如 /help, /model 等指令
│
├── config/              # 【配置管理】
│   ├── settings.py      # 环境读取：加载 api-config.json
│   └── defaults.py      # 默认参数：硬编码的兜底配置
│
└── utils/               # 【通用工具】
    ├── paths.py         # 路径处理：跨平台路径适配
    └── tokens.py        # Token 计算：本地估算 Prompt 长度
```

---
