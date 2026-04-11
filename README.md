# Claude Code Terminal

仿照官方 Claude Code 风格构建的 CLI AI 编程助手，支持 AI 驱动的文件操作和命令执行。

**版本：v2.8.12**

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
*   **智能防死循环** - 连续 3 次同质错误自动熔断，防止模型无效重试
*   **会话优化修剪** - 倒序优先级填充，保证 system + 最后一条消息

### 安全与权限
*   **三级权限系统** - 允许(本次)、允许(会话)、拒绝
*   **危险命令拦截** - rm -rf /、sudo rm、fork bomb 等完全拒绝
*   **交互式命令检测** - vim、top、python -i 等 20+ 种模式提前拦截
*   **路径范围检查** - Bash 文件操作检测是否在项目目录外

### 交互体验
*   **CTRL+C 中断** - 单击中断当前操作，双击退出程序
*   **主动交互** - AI 可向用户询问选择，澄清需求
*   **卡片式输出** - 工具结果美化显示，边框+图标+颜色
*   **终端压缩显示** - 大文件终端只显示首尾，完整内容给模型
*   **执行进度** - Bash 流式输出 + Read 进度显示 + 实时计时
*   **多行续行** - 显示行号 `… {N}>`，编辑更清晰
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
| /style | persona, p | 切换 AI 风格 |
| /save | s | 保存当前会话 |
| /history | hist | 加载历史会话 |
| /tools | tool | 查看工具执行历史 |
| /quit | exit, q | 退出程序 |

### 权限选项

| 选项 | 效果 |
|------|------|
| ✓ 允许 (本次) | 仅本次通过，后续需再确认 |
| ✓ 允许 (会话) | 本次会话同类操作自动通过 |
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
│   │   ├── conversation.py     # 会话管理（倒序修剪）
│   │   ├── files.py            # 文件挂载管理
│   │   └ stats.py               # Token 统计
│   ├── tools/
│   │   ├── base.py             # Tool 基类 + PermissionLevel(3级)
│   │   ├── executor.py         # 工具执行器（中断支持）
│   │   ├── permission.py       # 权限管理器
│   │   ├── permission_ui.py    # 权限 UI（中文选项）
│   │   ├── file_cache.py       # 文件缓存
│   │   ├── syntax_checker.py   # 语法检查器
│   │   └ builtins/
│   │       ├── read.py         # 📖 Read
│   │       ├── write.py        # ✏️ Write
│   │       ├── edit.py         # ✎ Edit
│   │       ├── bash.py         # ⚡ Bash
│   │       ├── grep.py         # 🔍 Grep
│   │       ├── glob.py         # 📁 Glob
│   │       └ ask_user.py       # ❓ AskUserQuestion
│   ├── commands/
│   │   ├── base.py             # Command 基类
│   │   ├── registry.py         # 命令注册表
│   │   └ handlers.py           # 8 个内置命令
│   ├── ui/
│   │   ├── theme.py            # 颜色 + 图标
│   │   ├── console.py          # Rich 封装
│   │   ├── components.py       # Logo + 状态栏
│   │   ├── renderer.py         # Markdown 渲染
│   │   ├── input.py            # 输入处理（行号续行）
│   │   └ progress_display.py   # 进度显示
│   └ utils/
│       ├── paths.py            # 路径处理
│       └ tokens.py             # Token 估算
├── tests/
│   ├── test_tools.py           # 工具测试
│   ├── test_file_cache.py      # 缓存测试
│   ├── test_permission.py      # 权限测试
│   ├── test_tool_architecture.py # 架构契约测试
│   └ test_conversation.py      # 会话测试
└── workplace/                  # 命令执行隔离目录
```

## 工具一览

| 工具 | 图标 | 只读 | 敏感 | 功能 |
|------|------|------|------|------|
| Read | 📖 | Yes | No | 读取文件（≤1MB，缓存集成） |
| Write | ✏️ | No | Yes | 创建/覆盖文件（自动语法检查） |
| Edit | ✎ | No | Yes | 精确替换（需先 Read） |
| Bash | ⚡ | No | 动态 | 执行命令（流式输出、危险拦截） |
| Grep | 🔍 | Yes | No | 正则搜索（≤30匹配） |
| Glob | 📁 | Yes | No | 文件名搜索（≤100结果） |
| AskUserQuestion | ❓ | Yes | No | 向用户询问 |

## 更新日志

### v2.8.12 (2026-04-11)
**用户体验优化**
*   ✅ 主循环反馈：空输入提示 + 命令执行确认
*   ✅ 权限会话级：新增 "允许 (会话)" 选项，减少确认次数
*   ✅ 中文选项：`✓ 允许 (本次)` / `✓ 允许 (会话)` / `✗ 拒绝`
*   ✅ 扩充帮助：6 条快捷键 + 5 条命令示例 + 7 个工具说明
*   ✅ 续行行号：多行输入显示 `… {N}>` 格式
*   ✅ 状态栏优化：`│` 分隔 + Token 含义说明
*   ✅ 错误建议：API 失败时提供具体解决建议
*   ✅ CTRL+C 中断：单击中断当前操作，双击退出程序
*   ✅ 全量测试通过：100 passed

### v2.8.11 (2026-04-10)
**全工具一致性修复**
*   ✅ 7 个工具 execute() 开头统一调用 validate_parameters()
*   ✅ Icon 规范化：Grep→🔍、Glob→📁、AskUserQuestion→❓
*   ✅ 全量测试通过：100 passed

### v2.8.10 (2026-04-10)
**Bash 工具重构**
*   ✅ execute() 拆分：213行→70行，减少 67%
*   ✅ 新增 _run_pre_checks()、_run_subprocess()、_build_final_output()
*   ✅ Icon 修复：正确显示 ⚡

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