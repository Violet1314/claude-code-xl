# Claude Code Terminal

仿照官方 Claude Code 风格构建的 CLI AI 编程助手，支持 AI 驱动的文件操作和命令执行。

**版本：v2.8.27**

## 功能特性

### 核心能力
*   **多模型支持** - 支持 GPT、Claude、Gemini、DeepSeek、Qwen 等多种模型
*   **多风格切换** - 5 种 AI 人格（Expert、02、麻衣学姐、吹雪、薇尔莉特）
*   **文件操作** - AI 可直接读取、创建、编辑本地文件
*   **命令执行** - 安全的 Shell 命令执行，敏感/危险命令分级处理
*   **流式输出** - SSE 流式响应，实时显示生成进度

### 智能优化
*   **Token 优化** - 文件缓存系统，减少重复传输
*   **版本隔离** - 写入后版本递增，新版本计数器重置，避免误拦截
*   **智能防死循环** - 连续 3 次同质错误自动熔断，80轮/50工具上限
*   **上下文优化** - 需求锚定 + 滑动窗口 + 工具输出摘要 + assistant差异化截断 + token快速判断

### 安全与权限
*   **统一路径管理** - PathManager 统一所有工具路径解析，`/cd` 切换目录，`/pwd` 查看状态
*   **三级权限系统** - 允许(本次)、允许(会话)、拒绝
*   **危险命令拦截** - rm -rf /、sudo rm、fork bomb 等完全拒绝
*   **交互式命令检测** - vim、top、python -i 等 20+ 种模式提前拦截
*   **路径范围检查** - Bash 文件操作检测是否在项目目录外

### 交互体验
*   **计划模式** - `/plan <任务>` 自主规划并逐步执行；`/plan status` 查看状态；`/plan stop` 主动退出并展示未完成摘要；单任务进行约束 + Unicode 进度面板 + 完成/熔断总结
*   **CTRL+C 中断** - 单击中断当前操作，双击退出程序
*   **主动交互** - AI 可向用户询问选择，澄清需求
*   **轻盈输出** - AI 响应 Panel 卡片 + 工具结果缩进+图标前缀，层级分明
*   **终端摘要显示** - Read 工具终端只显示一行摘要，完整内容给模型；连续同类工具紧凑排列
*   **执行进度** - Bash 流式输出 + Read 进度显示 + 实时计时
*   **多行续行** - 显示行号 `… {N}>`，编辑更清晰
*   **路径容错** - 文件不存在时自动搜索同名文件，返回候选路径；参数验证动态注入路径示例
*   **行号范围编辑** - Edit 支持 `start_line`/`end_line` 行号范围替换，无需精确复制原文
*   **交互反馈** - 空输入提示、命令执行确认、错误建议

### 开发辅助
*   **语法检查** - Write/Edit 后自动检查 10 种文件类型语法
*   **费用统计** - 实时显示会话累计费用
*   **Workplace 隔离** - Write/Edit/Bash 默认隔离到 workplace 目录
*   **目录自动过滤** - Glob/Grep 自动排除 .venv、node_modules、__pycache__ 等
*   **扩充帮助** - 详细的快捷键、命令示例、工具说明

### Edit 精确匹配
*   只做精确匹配，失败时提供 Read + 精确复制指导
*   多处匹配要求添加上下文，不提供候选选择
*   强制模型认真复制原文，从根本上减少语法错误

## 安装

```bash
# 克隆仓库
git clone https://github.com/Violet1314/Claude-Code-CLI.git
cd Claude-Code-CLI

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -e .[dev]
```

## 配置

### API 配置 (`data/config/api-config.json`)

```json
{
  "base_url": "https://your-api-endpoint.com/v1",
  "api_key": "your-api-key",
  "default_model": "claude-sonnet-4-20250514",
  "models": [
    {
      "id": "claude-sonnet-4-20250514",
      "name": "Claude Sonnet 4",
      "context_limit": 200000,
      "price": "Input: 3$/1M Output: 15$/1M"
    }
  ]
}
```

### 系统提示词 (`data/config/system-prompts.json`)

```json
{
  "expert": "You are a helpful coding assistant...",
  "02": "...",
  "mai": "...",
  "fubuki": "...",
  "violet": "..."
}
```

## 使用

```bash
# 启动应用
python -m claude_code

# 运行测试
python -m pytest tests/ -q

# 单个测试文件
python -m pytest tests/test_tools.py -v
```

### 快捷键

| 操作 | 功能 |
|------|------|
| Enter | 换行（对话模式）/ 直接发送（命令模式） |
| Esc + Enter | 发送消息 |
| Ctrl+C（单击） | 中断当前操作（流式请求/工具执行） |
| Ctrl+C（双击） | 退出程序 |
| ↑/↓ 或 j/k | 菜单上下选择 |
| 1-9 数字键 | 快速选择菜单项 |
| Esc 或 q | 取消菜单 |

### 命令列表

| 命令 | 别名 | 功能 |
|------|------|------|
| /help | h, ? | 显示命令帮助（扩充版） |
| /new | reset, clear | 开始新会话 |
| /model | m | 切换 AI 模型 |
| /style | persona | 切换 AI 风格 |
| /plan | p | 计划模式：`/plan <任务描述>` 启动执行，`/plan status` 查看状态，`/plan stop` 主动退出 |
| /cd | chdir | 切换操作根目录（必须绝对路径） |
| /pwd | - | 显示当前路径信息 |
| /save | s | 保存当前会话 |
| /history | hist | 加载历史会话 |
| /tools | tool | 查看工具执行历史 |
| /quit | exit, q | 退出程序 |

### 权限选项

| 选项 | 效果 |
|------|------|
| ✓ 允许 (本次) | 仅本次通过，后续需再确认 |
| ✓ 允许 (会话) | 本次会话所有同类操作自动通过 |
| ✗ 拒绝 | 仅本次拒绝 |

## 项目结构

```
claude-code/
├── pyproject.toml              # 包配置（hatchling）
├── data/
│   ├── config/
│   │   ├── api-config.json     # API 配置（敏感）
│   │   └── system-prompts.json # 多风格提示词
│   ├── history/                # 会话历史保存
│   └── stats/                  # Token 统计持久化
├── src/claude_code/
│   ├── __init__.py             # 版本导出
│   ├── __main__.py             # 入口点（Windows 编码修复）
│   ├── app.py                  # 主应用类
│   ├── config/
│   │   ├── defaults.py         # 常量配置
│   │   └ settings.py            # 配置加载器
│   ├── core/
│   │   ├── client.py           # APIClient（流式+错误建议）
│   │   ├── conversation.py     # 会话管理（需求锚定+滑动窗口+摘要压缩）
│   │   ├── files.py            # 文件挂载管理
│   │   ├── path_manager.py     # PathManager（统一路径管理+安全边界）
│   │   ├── todo.py             # TodoList（计划模式数据模型）
│   │   └ stats.py               # Token 统计
│   ├── tools/
│   │   ├── base.py             # Tool 基类 + PermissionLevel(3级)
│   │   ├── executor.py         # 工具执行器（中断支持）
│   │   ├── permission.py       # 权限管理器
│   │   ├── permission_ui.py    # 权限 UI（中文选项）
│   │   ├── file_cache.py       # 文件缓存
│   │   ├── syntax_checker.py   # 语法检查器
│   │   ├── command_safety.py   # 命令安全检查（危险/交互/Unix语法）
│   │   ├── tool_calling.py     # Native Tool Calling
│   │   ├── context.py          # ToolContext（工具执行上下文）
│   │   └ builtins/
│   │       ├── read.py         # ◇ Read
│   │       ├── write.py        # ▼ Write
│   │       ├── edit.py         # ✎ Edit
│   │       ├── bash.py         # ▶ Bash
│   │       ├── grep.py         # ◆ Grep
│   │       ├── glob.py         # ◎ Glob
│   │       ├── ask_user.py     # ◈ AskUserQuestion
│   │       └ todo.py           # ● TodoCreate/TodoUpdate/TodoList
│   ├── commands/
│   │   ├── base.py             # Command 基类
│   │   ├── registry.py         # 命令注册表
│   │   └ handlers.py           # 10 个内置命令
│   ├── ui/
│   │   ├── theme.py            # 颜色 + 图标
│   │   ├── console.py          # Rich 封装
│   │   ├── components.py       # Logo + 状态栏
│   │   ├── renderer.py         # Markdown 渲染
│   │   ├── input.py            # 输入处理（行号续行）
│   │   ├── safe_markup.py      # Rich Markup 安全转义
│   │   └ progress_display.py   # 进度显示
│   └ utils/
│       ├── paths.py            # 路径处理
│       └ tokens.py             # Token 估算
├── tests/
│   ├── test_tools.py           # 工具测试
│   ├── test_file_cache.py      # 缓存测试
│   ├── test_permission.py      # 权限测试
│   ├── test_tool_architecture.py # 架构契约测试
│   ├── test_conversation.py    # 会话测试
│   ├── test_path_manager.py    # 路径管理器测试
│   └ test_todo.py              # 计划模式测试
└── workplace/                  # 命令执行隔离目录
```

## 工具一览

| 工具 | 图标 | 只读 | 敏感 | 功能 |
|------|------|------|------|------|
| Read | ◇ | Yes | No | 读取文件（≤1MB，缓存集成） |
| Write | ▼ | No | Yes | 创建/覆盖文件（自动语法检查） |
| Edit | ✎ | No | Yes | 精确替换 + 行号范围（双模式） |
| Bash | ▶ | No | 动态 | 执行命令（流式输出、危险拦截） |
| Grep | ◆ | Yes | No | 正则搜索（≤30匹配） |
| Glob | ◎ | Yes | No | 文件名搜索（≤100结果） |
| AskUserQuestion | ◈ | Yes | No | 向用户询问 |
| TodoCreate | ● | No | No | 创建任务计划（计划模式，超限/空项会提示） |
| TodoUpdate | ● | No | No | 更新任务状态（计划模式，严格状态机 + 单 in_progress 约束） |
| TodoList | ● | Yes | No | 查看当前计划与进度（计划模式） |

## 更新日志

### v2.8.27 (2026-04-27)
**计划模式执行闭环增强：单任务进行约束 + status/stop 摘要 + 完成/熔断总结 + Todo 透明提示**
*   ✅ 单任务进行约束：同一时间最多一个 `in_progress`，避免任务并发开启后遗漏收尾
*   ✅ `/plan status`：可随时查看当前计划模式状态、进度与任务列表
*   ✅ `/plan stop` 增强：主动退出时展示当前进度和未完成任务摘要
*   ✅ 完成/熔断总结面板：计划完成后展示统计；连续提醒熔断时说明原因、进度和建议
*   ✅ Todo 透明提示：`TodoCreate` 对空任务/超上限截断给出明确提示；`TodoUpdate` 错误提示更具体
*   ✅ 全量测试通过：190 passed

### v2.8.26 (2026-04-25)
**全局 UI 美学优化：图标纯净化 + 色彩收敛 + Panel 克制化 + 排版韵律 + 流式体验**
*   ✅ 图标纯净化：Emoji（📖✏️⚡🔍📁❓🐍📜）→ Unicode 几何符号（◇▼▶◆◎◈▹），等宽对齐，终端宽度不再错位
*   ✅ 色彩收敛：6种灰色+新旧两套命名 → 三层灰+统一边框(#4A4A4A)+品牌色+状态色，清理 `system`/`user`/`border_subtle`/`border_default` 等旧命名
*   ✅ Panel 克制化：Bash 输出去掉 Panel，改为缩进+图标前缀；AI 响应、权限确认保留 Panel
*   ✅ 排版韵律：状态栏分层显示（模型名突出，次要信息 dim）；工具输出统一缩进层级（标题 Level 0，内容 Level 1 = 2空格）；移除冗余分隔线
*   ✅ 流式体验：思考状态简化为 `⠋ thinking... 3.2s 120 tok`，等待时更安静
*   ✅ 全量测试通过：185 passed

### v2.8.25 (2026-04-24)
**计划模式 UI 品质重构 + `/plan stop` 命令**
*   ✅ 图标语言统一：Emoji（✅❌⏳🔄）→ Unicode（✓✗○●），与全局主题系统一致
*   ✅ 删除冗余"← 进行中"标记，图标+颜色已足够表达
*   ✅ 极简进度条：`████████░░░░░░░` 品牌色填充，一目了然
*   ✅ 任务 ID 右对齐：t9→t10 不再错位
*   ✅ 计划完成仪式感：Rule 分隔线 + 绿色总结面板
*   ✅ `/plan` 入口 Panel 视觉框架，风格统一
*   ✅ 统计行精简：`完成:3 | 失败:0 | 待处理:4` → `✓3  ✗0  ○4`
*   ✅ `/plan stop` 主动退出计划模式，不清空会话
*   ✅ 全量测试通过：185 passed
## Windows PowerShell 注意事项

```powershell
# 正确示例
mkdir data, output          # 多目录用逗号分隔
Get-ChildItem               # 或简写 ls
Remove-Item -Recurse -Force path
Copy-Item -Recurse src dst
New-Item -Type File -Path name -Force  # 替代 touch

# 错误示例（不支持）
mkdir -p data output        # Unix 参数
ls -la                      # Unix 参数
rm -rf path                 # Unix 参数
cp -r src dst               # Unix 参数
touch file.txt              # 无此命令
which python                # 无此命令
```

## 许可证

MIT License