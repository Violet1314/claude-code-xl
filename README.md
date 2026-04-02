# Claude Code Terminal

仿照官方 Claude Code 风格构建的 CLI AI 编程助手，支持 AI 驱动的文件操作和命令执行。

**版本**：v2.7.20

---

## 功能特性

- **多模型支持** - 支持 GPT、Claude、Gemini、DeepSeek、Qwen 等多种模型
- **多风格切换** - 5 种 AI 人格（Expert、02、麻衣学姐、吹雪、薇尔莉特）
- **文件操作** - AI 可直接读取、创建、编辑本地文件
- **命令执行** - 安全的 Shell 命令执行，敏感/危险命令分级处理
- **流式输出** - SSE 流式响应，实时显示生成进度
- **Token 优化** - 文件缓存系统，减少重复传输
- **权限系统** - 所有操作需用户授权（once/all 模式），敏感操作每次确认
- **主动交互** - AI 可向用户询问选择，澄清需求
- **卡片式输出** - 工具结果美化显示，边框+图标+颜色
- **文件图标** - 根据文件类型显示不同图标（.py 🐍、.js 📜 等）
- **终端压缩显示** - 大文件终端只显示首尾，完整内容给模型
- **输出分离架构** - 模型拿到完整内容，终端显示可省略
- **执行进度** - Bash 流式输出 + Read 进度显示
- **费用统计** - 实时显示会话累计费用，与中转平台一致
- **Workplace 隔离** - 默认隔离目录，保护项目文件不被误操作

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
| **Read** | 读取文件内容（卡片式输出，终端压缩显示，支持缓存引用） |
| **Write** | 创建或覆盖文件（含 Python 语法检查） |
| **Edit** | 精确替换文件内容（含 diff 显示，多处匹配警告） |
| **Glob** | 按文件名模式搜索（卡片式输出，文件类型统计） |
| **Grep** | 按内容正则搜索（卡片式输出） |
| **Bash** | 执行 Shell 命令（流式输出，敏感/危险命令分级处理） |
| **AskUserQuestion** | 向用户询问问题，获取选择或自由输入 |

所有工具操作都需要用户授权。敏感操作（删除、提权等）每次都需确认。

---

## 安全机制

### 权限分级

- **Yes (once)** - 仅允许当前操作
- **Yes (all)** - 全局授权，后续非敏感操作自动通过
- **No (once)** - 拒绝当前操作
- **Esc/q** - 取消并中断后续执行

### 敏感命令检测

以下命令即使全局授权也需每次确认：
- 删除：`rm`, `Remove-Item`, `del`, `rd`
- 提权：`sudo`, `runas`
- 危险操作：`git push`, `git reset --hard`

### 危险命令拦截

以下命令直接拦截，不显示权限菜单：
- `rm -rf /`, `rm -rf /*`
- `mkfs`, `fdisk`
- `curl ... | bash`
- `shutdown`, `reboot`

---

## UI 预览

### 欢迎界面

```
     ██████╗ ██╗       █████╗  ██╗   ██╗ ██████╗  ███████╗
    ██╔════╝ ██║      ██╔══██╗ ██║   ██║ ██╔══██╗ ██╔════╝
    ...

  Claude Code Terminal v2.7.20 │ DeepSeek V3.2
  ────────────────────────────────────────────────────────
  "Code is poetry." — WordPress

  /help 查看命令  │  Tab 自动补全  │  Esc+Enter 发送
```

### 卡片式输出

```
╭─ 🐍 defaults.py
│
│  44 行  │  1.7 KB  │  ✓ 已缓存
│  📌 [file:defaults.py:v0]
│
│     1  """默认配置"""
│     2  from dataclasses import dataclass
│     ...
│
│ 💡 文件已完整缓存，无需再次读取。直接执行任务即可。
╰──────────────────────────────────────────────────
```

### 终端压缩显示（大文件）

```
╭─ 🐍 large_file.py
│
│  282 行  │  8.5 KB  │  ✓ 已缓存
│
│  显示 1-282 行:
│     1  """模块文档"""
│    ...
│   ... 省略 232 行 ...
│    263      demo_generators()
│    ...
│   282      main()
│
│ 💡 文件已完整缓存，无需再次读取。直接执行任务即可。
╰──────────────────────────────────────────────────
```

### 状态栏

```
◆ DeepSeek V3.2  │ $3/4.5 $/M │ 📁 3 │ ◆ 2.5K │ ≈$0.033
```

---

## 项目结构

```
claude-code/
├── pyproject.toml              # 包配置
├── README.md
├── 重构进度总结.md             # 交接文档
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
│   │   └── stats.py            # Token 统计（含费用累计）
│   │
│   ├── ui/                     # 界面模块
│   │   ├── console.py          # Rich 封装
│   │   ├── theme.py            # 主题配置
│   │   ├── components.py       # UI 组件
│   │   ├── input.py            # 输入处理（含中文宽度）
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
│   │
│   └── utils/                  # 工具函数
│
├── tests/                      # 测试文件（104 个用例）
│
├── workplace/                  # 隔离目录（启动时自动创建）
│
└── data/
    ├── config/                 # 配置文件
    ├── history/                # 会话历史
    └── stats/                  # 统计数据
```

---

## 开发

### 运行测试

```powershell
python -m pytest tests/ -q --ignore=tests/test_api_stability.py
```

当前测试覆盖：104 个测试用例

---

## 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| httpx | >=0.27.0 | HTTP 客户端（流式请求） |
| rich | >=13.7.0 | 终端 UI 渲染 |
| prompt-toolkit | >=3.0.43 | 交互式输入 |

---

## 更新日志

### v2.7.20 (2026-04-02)

**工具系统全面验收通过**

- ✅ Read：卡片式输出、缓存引用、分段读取、重复警告
- ✅ Write：创建/覆盖文件、语法检查、workplace 隔离
- ✅ Edit：精确替换、diff 显示、多处匹配警告
- ✅ Glob：文件搜索、无结果处理
- ✅ Grep：内容搜索、正则支持
- ✅ Bash：命令执行、敏感命令检测、危险命令拦截
- ✅ AskUserQuestion：选项菜单、自由输入

**本次修复**：

1. **Rich markup 转义** - 使用 `escape()` 转义文件内容中的特殊字符，避免解析错误
2. **输出分离架构** - `output` 给模型完整内容，`display_output` 给终端省略版本
3. **模型重复读取修复** - 模型拿到完整内容，不再因省略标记重复请求
4. **卡片样式修复** - 检测逻辑修正，样式正确渲染

### v2.7.19 (2026-04-02)

- **工具路径统一**：Read/Glob/Grep 全部支持 workplace 路径重定向

### v2.7.17 (2026-04-02)

- **放宽重复读取限制**：从 2 次改为 5 次

### v2.7.15 (2026-04-02)

- **Bash 输出去重**：成功时只显示一次

### v2.7.13 (2026-04-02)

- **终端显示压缩**：超过 80 行只显示首尾

### v2.7.12 (2026-04-02)

- **Bash 错误信息传递**：模型能看到具体错误

### v2.7.11 (2026-04-02)

- **Workplace 隔离目录**：保护项目文件

### v2.7.10 (2026-03-31)

- **菜单中文对齐**
- **累计费用统计**

### v2.7.9 (2026-03-31)

- **卡片式输出**
- **文件类型图标**
- **编程名言**

### v2.7.7 (2026-03-30)

- **AskUserQuestion 工具**

### v2.7.0 (2026-03-28)

- 统一使用 Native Tool Calling
- 文件缓存系统

---

## License

MIT