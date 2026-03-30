# Claude Code Terminal

仿照官方 Claude Code 风格构建的 CLI AI 编程助手，支持 AI 驱动的文件操作和命令执行。

**版本**：v2.7.7

---

## 功能特性

- **多模型支持** - 支持 GPT、Claude、Gemini、DeepSeek、Qwen 等多种模型
- **多风格切换** - 5 种 AI 人格（Expert、02、麻衣学姐、吹雪、薇尔莉特）
- **文件操作** - AI 可直接读取、创建、编辑本地文件
- **命令执行** - 安全的 Shell 命令执行，带权限确认
- **流式输出** - SSE 流式响应，实时显示生成进度
- **Token 优化** - 文件缓存系统，减少重复传输
- **权限系统** - 所有敏感操作需用户授权
- **主动交互** - AI 可向用户询问选择，澄清需求
- **美化输出** - 工具结果格式化显示，易于阅读
- **执行进度** - 工具执行时显示进度和状态

---

## 快速开始

### 1. 下载与进入目录

```powershell
cd E:\12-claude-code-xl\2026-02-01\Claude-Code-CLI-main
```

### 2. 创建虚拟环境

```powershell
python -m venv .venv
```

### 3. 激活虚拟环境

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows CMD
.\.venv\Scripts\activate.bat

# Linux/Mac
source .venv/bin/activate
```

### 4. 安装依赖

```powershell
pip install -e ".[dev]"
```

### 5. 配置 API

编辑 `data/config/api-config.json`，设置你的 API 密钥：

```json
{
  "base_url": "https://yunwu.ai/v1",
  "api_key": "你的API密钥",
  ...
}
```

### 6. 运行

```powershell
python -m claude_code
```

---

## 命令列表

| 命令 | 别名 | 说明 |
|------|------|------|
| `/help` | `/h`, `/?` | 显示命令帮助 |
| `/new` | `/reset`, `/clear` | 开始新会话 |
| `/model` | `/m` | 切换 AI 模型 |
| `/style` | `/persona`, `/p` | 切换 AI 风格 |
| `/save` | `/s` | 保存当前会话 |
| `/history` | `/hist` | 查看历史会话 |
| `/tools` | `/tool` | 查看工具执行历史 |
| `/quit` | `/q`, `/exit` | 退出程序 |

---

## 内置工具

| 工具 | 说明 |
|------|------|
| **Read** | 读取文件内容（支持缓存，≤1500 行完整显示） |
| **Write** | 创建或覆盖文件（含语法检查） |
| **Edit** | 精确替换文件内容（含 diff 显示） |
| **Glob** | 按文件名模式搜索（美化输出） |
| **Grep** | 按内容正则搜索（美化输出） |
| **Bash** | 执行 Shell 命令（流式输出） |
| **AskUserQuestion** | 向用户询问问题，获取选择或输入 |

所有工具操作都需要用户授权，支持 once/all 两种权限模式。

---

## 项目结构

```
claude-code/
├── pyproject.toml              # 包配置
├── README.md
├── 重构进度总结.md             # 交接文档
├── 打包exe教程.md              # 打包指南
│
├── src/claude_code/
│   ├── __init__.py             # 版本信息
│   ├── __main__.py             # 入口点
│   ├── app.py                  # 主应用类
│   │
│   ├── config/                 # 配置管理
│   │   ├── defaults.py         # 常量配置
│   │   └── settings.py         # 配置加载
│   │
│   ├── core/                   # 核心模块
│   │   ├── client.py           # API 客户端
│   │   ├── conversation.py     # 会话管理
│   │   ├── files.py            # 文件挂载
│   │   └── stats.py            # Token 统计
│   │
│   ├── ui/                     # 界面模块
│   │   ├── console.py          # Rich 封装
│   │   ├── theme.py            # 主题配置
│   │   ├── components.py       # UI 组件
│   │   ├── input.py            # 输入处理
│   │   ├── renderer.py         # 响应渲染
│   │   └── progress_display.py # 进度显示
│   │
│   ├── commands/               # 命令系统
│   │   ├── base.py             # 命令基类
│   │   ├── registry.py         # 命令注册
│   │   └── handlers.py         # 命令实现
│   │
│   ├── tools/                  # 工具系统
│   │   ├── base.py             # 工具基类
│   │   ├── executor.py         # 工具执行
│   │   ├── permission.py       # 权限管理
│   │   ├── permission_ui.py    # 权限确认 UI
│   │   ├── tool_calling.py     # Native Tool Calling
│   │   ├── file_cache.py       # 文件缓存
│   │   └── builtins/           # 内置工具
│   │       ├── read.py         # Read 工具
│   │       ├── write.py        # Write 工具
│   │       ├── edit.py         # Edit 工具
│   │       ├── glob.py         # Glob 工具
│   │       ├── grep.py         # Grep 工具
│   │       ├── bash.py         # Bash 工具
│   │       └── ask_user.py     # AskUserQuestion 工具
│   │
│   └── utils/                  # 工具函数
│       ├── tokens.py           # Token 估算
│       └── paths.py            # 路径处理
│
├── tests/                      # 测试文件
│   ├── test_conversation.py    # 会话测试
│   ├── test_file_cache.py      # 缓存测试
│   ├── test_tools.py           # 工具测试
│   ├── test_permission.py      # 权限测试
│   └── test_connection_recovery.py  # 连接恢复测试
│
└── data/
    ├── config/                 # 配置文件
    │   ├── api-config.json     # API 配置
    │   └── system-prompts.json # 提示词
    ├── history/                # 会话历史
    └── stats/                  # 统计数据
```

---

## 开发

### 运行测试

```powershell
python -m pytest tests/ -v --ignore=tests/test_api_stability.py
```

当前测试覆盖：104+ 个测试用例

### 打包 EXE

参见 `打包exe教程.md`

---

## 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| httpx | >=0.27.0 | HTTP 客户端（流式请求） |
| rich | >=13.7.0 | 终端 UI 渲染 |
| prompt-toolkit | >=3.0.43 | 交互式输入 |

---

## 更新日志

### v2.7.7 (2026-03-30)
- **AskUserQuestion 工具**：AI 可主动询问用户，获取选择或输入
- **输出格式增强**：Read/Grep/Glob 美化输出，图标+颜色+结构
- **工具执行进度**：Bash 流式输出 + Read 大文件进度条
- **权限系统优化**：Yes (once/all)、No (once) 三级权限

### v2.7.6 (2026-03-30)
- PowerShell 兼容性：检测 Unix 语法并返回错误提示
- 环境信息注入 system prompt
- 执行轮次从 3 提升到 5

### v2.7.0 (2026-03-28)
- 统一使用 Native Tool Calling（OpenAI 格式）
- 文件缓存系统优化
- Edit diff 显示

### v2.6.0 (2026-03-27)
- 文件缓存系统：Token 节省 60-75%
- Read limit 提升：从 500 到 1500 行

### v2.5.0
- 多模型工具调用兼容

---

## License

MIT