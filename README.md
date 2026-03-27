# Claude Code Terminal

仿照官方 Claude Code 风格构建的 CLI AI 编程助手，支持 AI 驱动的文件操作和命令执行。

**版本**：v2.6.1

---

## 功能特性

- **多模型支持** - 支持 GPT、Claude、Gemini、DeepSeek、Qwen 等多种模型
- **多风格切换** - 5 种 AI 人格（Expert、02、麻衣学姐、吹雪、薇尔莉特）
- **文件操作** - AI 可直接读取、创建、编辑本地文件
- **命令执行** - 安全的 Shell 命令执行，带权限确认
- **流式输出** - SSE 流式响应，实时显示生成进度
- **Token 优化** - 文件缓存系统，减少重复传输
- **权限系统** - 所有敏感操作需用户授权

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
| **Read** | 读取文件内容（支持缓存，limit=1000） |
| **Write** | 创建或覆盖文件 |
| **Edit** | 精确替换文件内容 |
| **Glob** | 按文件名模式搜索 |
| **Grep** | 按内容正则搜索 |
| **Bash** | 执行 Shell 命令 |

所有工具操作都需要用户授权，支持 once/always 两种权限模式。

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
│   │   └── renderer.py         # 响应渲染
│   │
│   ├── commands/               # 命令系统
│   │   ├── base.py             # 命令基类
│   │   ├── registry.py         # 命令注册
│   │   └── handlers.py         # 命令实现
│   │
│   ├── tools/                  # 工具系统
│   │   ├── base.py             # 工具基类
│   │   ├── parser.py           # XML 解析
│   │   ├── executor.py         # 工具执行
│   │   ├── permission.py       # 权限管理
│   │   ├── tool_calling.py     # 多模型兼容
│   │   ├── file_cache.py       # 文件缓存
│   │   └── builtins/           # 内置工具
│   │
│   └── utils/                  # 工具函数
│       ├── tokens.py           # Token 估算
│       └── paths.py            # 路径处理
│
├── tests/                      # 测试文件
│   ├── test_conversation.py    # 会话测试
│   ├── test_file_cache.py      # 缓存测试
│   ├── test_parser.py          # 解析器测试
│   ├── test_tools.py           # 工具测试
│   └── test_permission.py      # 权限测试
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
python -m pytest tests/ -v
```

当前测试覆盖：111 个测试用例

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

### v2.6.1 (2026-03-27)
- 代码质量重构：方法拆分、文档补充
- 异常兜底优化：`httpx.HTTPError` 统一捕获
- 测试覆盖提升：从 48 个增加到 111 个
- 提示词优化：移除 XML 相关残留文字

### v2.6.0
- 文件缓存系统：Token 节省 60-75%
- Read limit 提升：从 500 到 1000 行

### v2.5.0
- 多模型工具调用兼容：native/xml/kimi 三种格式

---

## License

MIT