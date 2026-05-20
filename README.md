# Claude Code Terminal

仿照官方 Claude Code 风格构建的 CLI AI 编程助手，支持 AI 驱动的文件操作和命令执行。

**版本：v2.8.39**

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
| TodoCreate | ● | No | No | 创建任务计划（计划模式，支持 depends_on 依赖关系） |
| TodoUpdate | ● | No | No | 更新任务状态（计划模式，严格状态机 + 单 in_progress 约束 + 支持暂停回退） |
| TodoList | ● | Yes | No | 查看当前计划与进度（计划模式） |
| ProjectContext | ◇ | Yes | No | 项目结构感知（目录扫描+类型识别+符号索引+相关性检索） |

## 更新日志

### v2.8.39 (2025-05-10)
**长对话质量保障 + 工具调度 Token 深度优化：极限压缩保底 + 摘要回溯线索 + 近期窗口压缩 + tool_calls 压缩 + 阈值收紧**
*   ✅ 极限压缩保底：`ANCHOR_USER_MSGS_MIN` 1→2、`RECENT_WINDOW_MIN` 4→6，>90% 时多保留 3 条消息，防止长对话质量断崖
*   ✅ 摘要回溯线索：新增 `_extract_entities_from_messages()` 正则提取文件路径/代码位置实体，`apply_summary()` 摘要尾部追加 `[回溯线索]`，模型不再盲猜
*   ✅ 动态 skip_head/skip_tail：从硬编码 6/4 改为按消息总量比例计算，长对话保留更多头部上下文
*   ✅ Token 预算提醒措辞优化：≥85% 时从"必须极度精简：不解释"改为"精简但保留关键代码和决策逻辑，如信息不足请 Read 确认"
*   ✅ 摘要成本对冲：计划模式仅剩 ≤2 个未完成任务时跳过摘要生成，避免"先花后省"反亏
*   ✅ 近期窗口 tool 消息轻量压缩：阶段2对 >1000 字符的 tool 消息做轻量压缩（首 300+尾 200），修复近期窗口完全不压缩的盲区
*   ✅ compress_tool_output 阈值收紧：压缩阈值从 2000 降至 1000，2000-5000 字符的工具输出不再完整进入历史
*   ✅ assistant 消息 tool_calls 历史压缩：新增 `_compress_tool_calls()` 对中间区域 assistant 消息的 tool_calls 仅保留工具名和 id，参数置空
*   ✅ Bash 默认截断收紧：`DEFAULT_MAX_OUTPUT_LENGTH` 从 5000 降至 3000，verbose 模式保持 10000
*   ✅ 全量测试通过：205 passed

### v2.8.38 (2025-05-09)
**Token深度优化 + 思考模型兼容：推理压缩 + 增量推送 + 语义摘要 + 重复Read消除 + 窗口渐进调参 + 计划提醒合并**
*   ✅ reasoning_content 兼容：Message 类新增 reasoning_content 属性，完全向后兼容
*   ✅ 推理链历史压缩：`_compress_reasoning_content()` 对中间/锚定消息的推理链截断至 150 字符，普通模型零影响
*   ✅ 任务清单增量推送：`TodoList.to_prompt_diff()` + `get_status_snapshot()`，后续轮次仅注入状态变化项
*   ✅ 工具反馈语义压缩：`_extract_semantic_summary()` 对 Read 输出提取函数/类签名，大幅减少历史中冗余代码 Token
*   ✅ 计划提醒合并：检测上一条消息是否为 `[计划提醒]`，是则替换而非追加
*   ✅ 自适应窗口渐进式：从 80%/90% 两档改为 50%/70%/90% 四档渐进压缩
*   ✅ 计划模式摘要早触发：摘要触发阈值从 80% 降至 60%
*   ✅ 消除重复 Read：`FileCacheManager` 新增 `_recent_reads` 追踪，5 分钟内重复读取返回缓存摘要
*   ✅ Token 预算不入历史：预算提示追加到临时 messages，天然不入历史
*   ✅ 全量测试通过：205 passed

### v2.8.37 (2025-05-08)
**智能优化与架构升级：TodoList统一管理 + 缓存摘要增强 + 上下文自适应调参 + 计划模式依赖关系 + 工具并行执行 + 对话摘要生成 + Token预算管理**
*   ✅ TodoList 注册到 ToolContext：消除模块级全局变量，统一收敛至 ToolContext 容器管理生命周期
*   ✅ 缓存摘要增强：Python 函数签名提取 + JSON 值类型提取
*   ✅ 上下文自适应调参：`_adaptive_params(usage_ratio)` 根据使用率动态调整锚定数和窗口
*   ✅ 计划模式依赖关系：`TodoItem` 新增 `depends_on` 字段，`update_status()` 启动前校验前置依赖
*   ✅ 工具并行执行：只读工具使用 ThreadPoolExecutor 并行（最大4线程），写操作顺序执行
*   ✅ 对话摘要生成：上下文>80%时触发 API 生成摘要，替换中间消息为一条摘要消息
*   ✅ Token 预算管理：chat 循环中注入三级提醒（50%/70%/85%）
*   ✅ 全量测试通过：205 passed

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
