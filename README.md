# Claude Code Terminal

仿照官方 Claude Code 风格构建的 CLI AI 编程助手，支持 AI 驱动的文件操作和命令执行。

**版本：v2.8.43**

## 功能特性

### 核心能力
*   **多模型支持** - 支持 GPT、GLM、Kimi、DeepSeek 等模型，支持 `/provider` 在公司中转与 DeepSeek 官方 API 间切换
*   **多风格切换** - 5 种 AI 人格（Expert、02、麻衣学姐、吹雪、薇尔莉特）
*   **文件操作** - AI 可直接读取、创建、编辑本地文件
*   **命令执行** - 安全的 Shell 命令执行，敏感/危险命令分级处理
*   **流式输出** - SSE 流式响应，实时显示生成进度
*   **Provider Profile** - `active_profile + profiles` 配置结构，`/provider` 菜单式切换公司中转/DeepSeek 官方接入

### 智能优化
*   **Token 优化** - tiktoken 精确估算 + 文件缓存系统，减少重复传输
*   **语义摘要** - 缓存文件时自动提取结构化摘要（类名、函数、import），长对话可快速查询文件概览
*   **版本隔离** - 写入后版本递增，新版本计数器重置，避免误拦截
*   **智能防死循环** - 连续 3 次同质错误自动熔断，80轮/50工具上限
*   **上下文优化** - 需求锚定 + 滑动窗口 + 工具输出摘要 + assistant差异化截断 + token快速判断
*   **历史回放增强** - `/save` 保存 assistant metadata、tool replay 与 active_profile，`/history recent/full` 支持轻量恢复或完整回放
*   **计划感知摘要** - 长任务自动保存 plan_state、执行证据与失败记录，压缩摘要保留 `[PLAN]` / `[PLAN_REMINDER]` 关键状态
*   **长对话防幻觉** - 上下文使用 ≥70% 时自动提醒模型先 Read 确认，不依赖模糊记忆

### 安全与权限
*   **统一路径管理** - PathManager 统一所有工具路径解析，`/cd` 切换目录，`/pwd` 查看状态
*   **三级权限系统** - 允许(本次)、允许(会话)、拒绝
*   **危险命令拦截** - rm -rf /、sudo rm、fork bomb 等完全拒绝
*   **交互式命令检测** - vim、top、python -i 等 20+ 种模式提前拦截
*   **路径范围检查** - Bash 文件操作检测是否在项目目录外

### 交互体验
*   **计划模式** - `/plan <任务>` 自主规划并逐步执行；`/plan status` 查看状态；`/plan stop` 主动退出并展示未完成摘要；最多 3 个并行 in_progress + Todo evidence/error 执行证据 + 失败恢复记录 + 紧凑 `[PLAN]` / `[PLAN_REMINDER]` 提示 + plan-aware summary
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
  "active_profile": "company",
  "profiles": {
    "company": {
      "name": "Company Gateway",
      "provider": {
        "id": "company",
        "base_url": "https://your-company-gateway/v1",
        "api_key": "your-company-key",
        "api_style": "openai_compatible",
        "profile": "generic_openai_compatible"
      },
      "default_model": "glm-5.1",
      "models": [
        {
          "id": "glm-5.1",
          "name": "GLM 5.1",
          "context_limit": 200000,
          "price": "Input: $9.14/1M Output: $28.71/1M"
        }
      ]
    },
    "deepseek": {
      "name": "DeepSeek Official",
      "provider": {
        "id": "deepseek",
        "base_url": "https://api.deepseek.com",
        "api_key": "your-deepseek-key",
        "api_style": "openai_compatible",
        "profile": "deepseek_official"
      },
      "default_model": "deepseek-v4-flash",
      "models": [
        {
          "id": "deepseek-v4-flash",
          "name": "DeepSeek V4 Flash",
          "context_limit": 1000000,
          "price": "Input: $2.00/1M Output: $4.00/1M",
          "capabilities": {
            "thinking": true,
            "reasoning_effort": true
          },
          "thinking": {"type": "enabled"},
          "reasoning_effort": "max"
        }
      ]
    }
  }
}
```

> 旧格式 `base_url/api_key/models/default_model` 仍兼容；新配置推荐用 `/provider` 在 profile 间切换。

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
| /provider | profile | 切换 API Provider Profile（菜单式选择或 `/provider <id>` 直切） |
| /style | persona | 切换 AI 风格 |
| /plan | p | 计划模式：`/plan <任务描述>` 启动执行，`/plan status` 或 `/plan` 无参数 查看状态，`/plan stop` 主动退出 |
| /cd | chdir | 切换操作根目录（必须绝对路径） |
| /pwd | - | 显示当前路径信息 |
| /last-output | lo | 查看最后一次 Bash 工具的完整输出 |
| /doctor | - | 一键系统诊断（含 Provider Profile 检查） |
| /save | s | 保存当前会话 |
| /history | hist | 加载历史会话（支持 `recent` 轻量恢复与 `full` 完整回放） |
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
│   │   └ settings.py            # 配置加载器（Provider Profile + 旧格式兼容）
│   ├── core/
│   │   ├── client.py           # APIClient（OpenAI兼容适配+参数白名单+流式）
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
│   │   └ handlers.py           # 14 个命令（13 可见 + 1 hidden）
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
│   ├── test_history.py           # 会话保存/历史回放测试
│   ├── test_plan_mode.py         # Plan 状态机与恢复测试
│   ├── test_api_config.py      # API配置/Profile测试
│   ├── test_api_client.py      # API payload 参数白名单测试
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
| TodoUpdate | ● | No | No | 更新任务状态（计划模式，幂等 no-op + 最多 3 个并行 + 批量更新 + evidence/files/tests/error 失败记录） |
| TodoList | ● | Yes | No | 查看当前计划与进度（计划模式） |
| ProjectContext | ◇ | Yes | No | 项目结构感知（目录扫描+类型识别+符号索引+相关性检索） |

## 更新日志

### v2.8.43 (2026-05-14)
**历史会话与计划模式可靠性增强**
*   ✅ `/save` 标题生成升级：使用 DeepSeek 官方 Flash 生成标题，并记录 `title_error` 诊断信息
*   ✅ `/history full/recent`：支持完整回放与轻量恢复，保留 assistant metadata 与 tool replay
*   ✅ Profile 状态恢复：会话保存/恢复包含 `active_profile` 与 `provider_profile`，跨会话保持 Provider 选择
*   ✅ Todo 可靠性增强：幂等更新变为 no-op，新增 evidence/files/tests/error 执行证据与失败恢复记录
*   ✅ Plan 长任务状态增强：autosave 保存扩展状态、`plan_state` 元数据、紧凑 `[PLAN]` / `[PLAN_REMINDER]` 提示与 plan-aware summary
*   ✅ 回归测试覆盖：新增/更新历史会话、Plan 状态机与恢复测试
*   ✅ 全量测试通过：253 passed，0 回归

### v2.8.42 (2026-05-13)
**Provider Profile 接入重构：公司中转/DeepSeek 官方一键切换 + 参数白名单 + 满血推理**
*   ✅ Provider Profile 配置：新增 `active_profile + profiles`，当前支持 `company` 与 `deepseek`，未来可扩展更多官方/中转 profile
*   ✅ `/provider` 菜单式切换：无参数打开与 `/model` 一致的交互菜单，仍保留 `/provider <id>` 直接切换
*   ✅ 模型列表按 profile 隔离：company 显示 5 个中转模型，deepseek 仅显示 `deepseek-v4-flash` / `deepseek-v4-pro`
*   ✅ DeepSeek 官方满血接入：官方 profile 自动发送顶级 `thinking={"type":"enabled"}` 与 `reasoning_effort=max`
*   ✅ 公司中转保守兼容：默认不发送 DeepSeek 专属 `thinking/reasoning_effort`，避免中转参数不兼容
*   ✅ OpenAI-compatible 参数构建层：按模型 capabilities 白名单控制 `tools`、`max_tokens`、`stream_options`、`reasoning_effort`
*   ✅ 旧配置兼容：保留旧格式 `base_url/api_key/models/default_model` 与 P0 `providers + models` 加载能力
*   ✅ `/doctor` 增强：显示当前 Active Profile、Provider 状态与 DeepSeek 官方满血模式
*   ✅ 回归测试覆盖：新增/更新 API config、profile、payload 测试
*   ✅ 全量测试通过：232 passed，0 回归

### v2.8.41 (2026-05-12)
**工具质量加固 + API 侧体验优化：Grep 崩溃修复 + 工具输出增强 + 智能压缩 + 长对话质量保障**
*   ✅ Grep context 崩溃修复：`_add_context_to_matches()` 3 元组解包改为 `match[0:3]` 安全取值
*   ✅ 工具错误提示增加"下一步"建议：Grep/Read/Glob 共 7 处错误追加可执行建议
*   ✅ Bash Windows 统一 UTF-8：PowerShell 前缀扩展 OutputEncoding + InputEncoding + `$OutputEncoding`
*   ✅ Read 精确行段模式：用户指定 offset/limit 时终端标记"精确行段，不省略"
*   ✅ Todo 批量模式部分成功提示：区分全部成功/部分成功/全部失败三种状态
*   ✅ Read 结构概览头部：首次全量 Read 注入 `[结构] class App L42 | def chat L520 | ...` 符号位置索引，一次定位精准读取
*   ✅ Grep 醒目行号 + 上下文范围标注：匹配行 `▸L42  ✎Edit(L42)` 格式，context 模式标注 `(上下文 L38-40)`
*   ✅ Edit 三级匹配容错自动降级：精确→模糊→行级归一化，找到唯一匹配自动执行，失败时给出具体行号建议
*   ✅ Bash 智能截断 + CWD 跟踪：失败时 stderr 优先保留+stdout 关键行提取，成功时语义关键行+首尾保留；跨调用 cd 目录追踪
*   ✅ 工具反馈语义压缩：Read/Grep/Glob/Edit/Bash 按工具类型定制压缩策略，长对话中保留操作意图而非简单头尾截断
*   ✅ 长对话操作摘要链：中间压缩阶段将连续工具操作替换为 `[操作摘要链] Read→Edit L42→Bash pytest ✓→Write`，Token 极低信息密度极高
*   ✅ 回归测试覆盖增强：新增 15 个测试覆盖 Grep/Glob/Bash/Read/Todo
*   ✅ 全量测试通过：220 passed，0 回归
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
