# Claude Code Terminal

仿照官方 Claude Code 风格构建的 CLI AI 编程助手，支持 AI 驱动的文件操作和命令执行。

**版本：v2.8.36**

## 功能特性

### 核心能力
*   **多模型支持** - 支持 GPT、Claude、Gemini、DeepSeek、Qwen 等多种模型
*   **多风格切换** - 5 种 AI 人格（Expert、02、麻衣学姐、吹雪、薇尔莉特）
*   **文件操作** - AI 可直接读取、创建、编辑本地文件
*   **命令执行** - 安全的 Shell 命令执行，敏感/危险命令分级处理
*   **流式输出** - SSE 流式响应，实时显示生成进度

### 智能优化
*   **Token 优化** - tiktoken 精确估算 + 文件缓存系统，减少重复传输
*   **语义摘要** - 缓存文件时自动提取结构化摘要（类名、函数、import），长对话可快速查询文件概览
*   **版本隔离** - 写入后版本递增，新版本计数器重置，避免误拦截
*   **智能防死循环** - 连续 3 次同质错误自动熔断，80轮/50工具上限
*   **上下文优化** - 需求锚定 + 滑动窗口 + 工具输出摘要 + assistant差异化截断 + token快速判断
*   **长对话防幻觉** - 上下文使用 ≥70% 时自动提醒模型先 Read 确认，不依赖模糊记忆

### 安全与权限
*   **统一路径管理** - PathManager 统一所有工具路径解析，`/cd` 切换目录，`/pwd` 查看状态
*   **三级权限系统** - 允许(本次)、允许(会话)、拒绝
*   **危险命令拦截** - rm -rf /、sudo rm、fork bomb 等完全拒绝
*   **交互式命令检测** - vim、top、python -i 等 20+ 种模式提前拦截
*   **路径范围检查** - Bash 文件操作检测是否在项目目录外

### 交互体验
*   **计划模式** - `/plan <任务>` 自主规划并逐步执行；`/plan status` 查看状态；`/plan stop` 主动退出并展示未完成摘要；单任务进行约束（WIP=1）+ 任务暂停回退（in_progress→pending） + Unicode 进度面板 + 完成/熔断总结
*   **命令隐藏** - 低频命令（如 `/tools`）设为 hidden，不在帮助和补全中显示但仍可执行
*   **CTRL+C 中断** - 单击中断当前操作，双击退出程序
*   **主动交互** - AI 可向用户询问选择，澄清需求
*   **轻盈输出** - AI 响应 Panel 卡片 + 工具结果缩进+图标前缀，层级分明
*   **终端摘要显示** - Read 工具终端只显示一行摘要，完整内容给模型；连续同类工具紧凑排列
*   **执行进度** - Bash 流式输出 + Read 进度显示 + 实时计时
*   **多行续行** - 显示行号 `… {N}>`，编辑更清晰
*   **路径容错** - 文件不存在时自动搜索同名文件，返回候选路径；参数验证动态注入路径示例
*   **行号范围编辑** - Edit 支持 `start_line`/`end_line` 行号范围替换，无需精确复制原文
*   **交互反馈** - 空输入提示、命令执行确认、错误建议

### 项目记忆
*   **CLAUDE.md 记忆文件** - 项目根目录 `.claude/CLAUDE.md` 自动加载，`/cd` 切换时重载，无需每次重新探索项目

### 开发辅助
*   **语法检查** - Write/Edit 后自动检查 10 种文件类型语法
*   **费用统计** - 实时显示会话累计费用
*   **Workplace 隔离** - Write/Edit/Bash 默认隔离到 workplace 目录
*   **目录自动过滤** - Glob/Grep 自动排除 .venv、node_modules、__pycache__ 等
*   **扩充帮助** - 详细的快捷键、命令示例、工具说明

### Edit 精确匹配 + 模糊容错
*   精确匹配优先，失败时自动尝试容错匹配（行尾空白归一化、换行符统一、缩进 tab→空格）
*   容错匹配成功标注 `[fuzzy]`，保证匹配结果等价，减少 50%+ 重试
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
| /plan | p | 计划模式：`/plan <任务描述>` 启动执行，`/plan status` 或 `/plan` 无参数 查看状态，`/plan stop` 主动退出 |
| /cd | chdir | 切换操作根目录（必须绝对路径） |
| /pwd | - | 显示当前路径信息 |
| /last-output | lo | 查看最后一次 Bash 工具的完整输出 |
| /doctor | - | 一键系统诊断（12 项检查） |
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
│   │   ├── defaults.py         # 常量配置（dataclass 分组）
│   │   └ settings.py            # 配置加载器
│   ├── core/
│   │   ├── client.py           # APIClient（流式+错误建议）
│   │   ├── conversation.py     # 会话管理（需求锚定+滑动窗口+摘要压缩）
│   │   ├── files.py            # 文件挂载管理
│   │   ├── path_manager.py     # PathManager（统一路径管理+安全边界）
│   │   ├── tool_feedback.py   # 工具反馈构建与压缩（从app.py提取）
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
│   │       ├── grep.py         # ⌕ Grep
│   │       ├── glob.py         # ◎ Glob
│   │       ├── ask_user.py     # ◈ AskUserQuestion
│   │       ├── todo.py         # ● TodoCreate/TodoUpdate/TodoList
│   │       └ project_context.py  # ◇ ProjectContext（项目结构感知）
│   ├── commands/
│   │   ├── base.py             # Command 基类
│   │   ├── registry.py         # 命令注册表
│   │   └ handlers.py           # 13 个命令（12 可见 + 1 hidden）
│   ├── ui/
│   │   ├── theme.py            # 颜色 + 图标 + Panel层级
│   │   ├── console.py          # Rich 封装（含Markup安全猴子补丁）
│   │   ├── components.py       # Logo + 状态栏 + 计划面板（todo/complete/status/stopped/aborted）
│   │   ├── renderer.py         # Markdown 渲染（含代码块语言标签栏）
│   │   ├── input.py            # 输入处理（行号续行+命令补全过滤路径）
│   │   ├── safe_markup.py      # Rich Markup 安全防护（safe_print/safe_markup/validate_markup）
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
│   ├── test_todo.py              # 计划模式测试
│   └ test_project_memory.py    # 项目记忆测试
└── workplace/                  # 命令执行隔离目录
```

## 工具一览

| 工具 | 图标 | 只读 | 敏感 | 功能 |
|------|------|------|------|------|
| Read | ◇ | Yes | No | 读取文件（≤1MB，缓存集成） |
| Write | ▼ | No | Yes | 创建/覆盖文件（自动语法检查） |
| Edit | ✎ | No | Yes | 精确替换 + 行号范围（双模式） |
| Bash | ▶ | No | 动态 | 执行命令（流式输出、危险拦截） |
| Grep | ⌕ | Yes | No | 正则搜索（≤30匹配） |
| Glob | ◎ | Yes | No | 文件名搜索（≤100结果） |
| AskUserQuestion | ◈ | Yes | No | 向用户询问 |
| TodoCreate | ● | No | No | 创建任务计划（计划模式，超限/空项会提示） |
| TodoUpdate | ● | No | No | 更新任务状态（计划模式，严格状态机 + 单 in_progress 约束 + 支持暂停回退） |
| TodoList | ● | Yes | No | 查看当前计划与进度（计划模式） |
| ProjectContext | ◇ | Yes | No | 项目结构感知（目录扫描+类型识别+符号索引+相关性检索） |

## 更新日志

### v2.8.36 (2025-05-07)
**长对话质量优化：语义摘要 + 防幻觉提醒 + Edit 新鲜度校验 + autosave 崩溃修复**
*   ✅ 文件内容语义摘要：`FileCacheManager` 对 Python/JS/TS/JSON/YAML 提取结构化摘要（类名、函数、import、顶层键），长对话可快速查询文件概览
*   ✅ 长对话防幻觉提醒：上下文窗口使用 ≥70% 时自动注入 user 角色提醒，建议先 Read 确认
*   ✅ Edit 缓存新鲜度校验：执行前检查文件是否已缓存/当前版本是否被读取过，未读则附加提示建议先 Read
*   ✅ autosave 崩溃修复：修复 API 响应含 surrogate 字符时编码崩溃；异常捕获扩展
*   ✅ 自动保存间隔调整：从每 5 轮调整为每 20 轮
*   ✅ 全量测试通过：205 passed

### v2.8.35 (2025-05-06)
**API 接入体验优化：原生 tool role + 路径去重 + description 精简 + 变更确认上下文 + 错误增强 + 策略引导 + 增量提醒 + 缓存新鲜度**
*   ✅ 工具反馈改用原生 tool role：`build_tool_feedback()` 从 XML+user role 改为原生 tool role 消息列表，每条带 `tool_call_id`，模型可精确关联 tool_call 与结果
*   ✅ 旧 XML 兼容代码清理：移除 `_replay_legacy_tool_results`、`_summarize_tool_results` 及相关检测分支
*   ✅ 路径规则去重：移除 6 个工具 description 和参数 schema 中的重复路径规则，统一收敛至 system prompt + PathManager
*   ✅ 工具 description 精简：行为指引移至 system prompt 的 **工具使用规范** 段，description 只保留功能说明
*   ✅ Edit 返回变更确认上下文：精确匹配成功后附加修改后文件上下文（前后各3行），无需额外 Read
*   ✅ Write 返回首尾摘要：短文件完整显示，长文件首10+尾5行，一次调用即可确认结果
*   ✅ Bash 错误增强：失败时附加 exit code + 常见原因提示（127=命令未找到、pip/pytest/git 特定提示）
*   ✅ 工具组合策略引导：system prompt 新增 **工具组合策略** 段（5 条最佳实践）
*   ✅ 计划模式提醒增量优化：首轮注入完整规则，后续只注入增量进度，每轮节省 ~200 token
*   ✅ Read 缓存新鲜度提示：缓存命中时附加"如 Edit 匹配失败，请重新 Read"提示
*   ✅ Conversation 增强：Message 新增 `tool_call_id`/`tool_calls` 字段；新增 `add_tool_message()` 等方法
*   ✅ Todo 状态机回退：新增 `in_progress → pending` 合法转换，任务暂无法推进时可暂停并释放进行中名额
*   ✅ 全量测试通过：205 passed

### v2.8.34 (2025-05-05)
**功能性增强：版本统一 + Token精确化 + 统计修正 + ProjectContext增强 + Bash体验 + 崩溃恢复 + 诊断命令**
*   ✅ 版本号统一：创建 `__version__.py` 单一来源，`defaults.py`/`pyproject.toml`/`__init__.py` 统一引用
*   ✅ Token 估算精确化：集成 tiktoken 库，主流模型精确计数；不可用时自动降级到字符估算
*   ✅ 统计累加逻辑修正：`stats.py` 新增 `accumulated_input/output` 字段
*   ✅ ProjectContext 双重增强：新增 `query` 参数按关键词检索；新增 JS/TS 符号索引
*   ✅ Bash 体验全面提升：Unix→PowerShell 转换建议；新增 `/last-output`（别名 `/lo`）
*   ✅ 会话崩溃自动恢复：每 5 轮自动保存检查点，启动时检测并提示恢复
*   ✅ `/doctor` 诊断命令：一键检查 12 项
*   ✅ 全量测试通过：199 passed

---

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
