这是基于 v2.8.1 格式更新的 **README.md**，已同步至 **v2.8.2** 版本。

主要变更点：
*   **版本号**：更新至 `v2.8.2`。
*   **核心优化**：新增 Edit 工具相似行线索反馈、File Cache 版本隔离计数机制。
*   **稳定性增强**：解决大文件编辑匹配死循环问题，优化长对话下的重复读取拦截逻辑。
*   **更新日志**：新增 v2.8.2 重构记录。

---

# Claude Code Terminal

仿照官方 Claude Code 风格构建的 CLI AI 编程助手，支持 AI 驱动的文件操作和命令执行。

**版本：v2.8.2**

## 功能特性

*   **多模型支持** - 支持 GPT、Claude、Gemini、DeepSeek、Qwen 等多种模型
*   **多风格切换** - 5 种 AI 人格（Expert、02、麻衣学姐、吹雪、薇尔莉特）
*   **文件操作** - AI 可直接读取、创建、编辑本地文件
*   **命令执行** - 安全的 Shell 命令执行，敏感/危险命令分级处理
*   **流式输出** - SSE 流式响应，实时显示生成进度
*   **Token 优化** - 文件缓存系统，减少重复传输
*   **权限系统** - 只读工具自动放行，写入/执行操作需用户授权，敏感操作每次确认
*   **主动交互** - AI 可向用户询问选择，澄清需求
*   **卡片式输出** - 工具结果美化显示，边框+图标+颜色
*   **文件图标** - 根据文件类型显示不同图标（.py 🐍、.js 📜 等）
*   **终端压缩显示** - 大文件终端只显示首尾，完整内容给模型
*   **输出分离架构** - 模型拿到完整内容，终端显示可省略
*   **执行进度** - Bash 流式输出 + Read 进度显示
*   **费用统计** - 实时显示会话累计费用，与中转平台一致
*   **Workplace 隔离** - Write/Edit/Bash 默认隔离到 workplace 目录，Read/Glob/Grep 直接访问项目文件
*   **目录自动过滤** - Glob/Grep 自动排除 .venv、node_modules、pycache 等无关目录
*   **智能防死循环** - 连续同质错误自动熔断，防止模型无效重试
*   **Edit 容错增强** - 匹配失败时提供相似行线索，引导模型自我修正
*   **缓存版本隔离** - 文件修改后读取计数重置，避免长对话误拦截
*   **静默重试机制** - API 连接重试不刷屏，仅最终失败时报错

## 快速开始

### 安装

```powershell
# 克隆仓库
git clone https://github.com/Violet1314/Claude-Code-CLI.git
cd Claude-Code-CLI

# 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows

# 安装依赖
pip install -e .[dev]
```

### 配置

编辑 `data/config/api-config.json`：

```json
{
  "api_key": "your-api-key",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o"
}
```

### 运行

```powershell
python -m claude_code
```

## 内置工具

| 工具 | 说明 |
| --- | --- |
| Read | 读取文件内容，支持缓存、摘要模式和智能拦截 |
| Write | 创建或覆盖文件，卡片式输出 |
| Edit | 精确替换文件内容，**v2.8.2 新增相似行线索反馈** |
| Glob | 按文件名模式搜索，自动排除无关目录 |
| Grep | 按内容搜索，支持正则表达式 |
| Bash | 执行 Shell 命令，支持 Unix 命令转换 |
| AskUserQuestion | 向用户询问选择，支持选项菜单 |

## 权限系统

*   **只读工具**（Read、Glob、Grep）：自动放行
*   **写入/执行工具**（Write、Edit、Bash）：需用户确认
*   **敏感操作**（rm、git push 等）：每次都需确认，不缓存权限
*   **危险命令**（rm -rf / 等）：直接拦截

## 测试

```powershell
# 全量测试
python -m pytest tests/ -q

# 工具测试
python -m pytest tests/test_tools.py -q

# 权限测试
python -m pytest tests/test_permission.py -q
```

## 项目结构

```text
claude-code/
├── src/claude_code/
│   ├── app.py              # 主应用
│   ├── config/             # 配置管理
│   ├── core/               # 核心模块（API、会话、缓存）
│   ├── ui/                 # UI 组件
│   ├── tools/              # 工具系统
│   │   ├── base.py         # Tool 基类
│   │   ├── executor.py     # 工具执行器
│   │   ├── permission.py   # 权限管理
│   │   ├── file_cache.py   # 【v2.8.2】文件缓存（版本隔离计数）
│   │   └── builtins/       # 内置工具
│   │       ├── edit.py     # 【v2.8.2】Edit 工具（相似行线索）
│   │       └── read.py     # 【v2.8.2】Read 工具（集成拦截逻辑）
│   └── utils/              # 工具函数
├── tests/                  # 测试文件
├── data/config/            # 配置文件
└── workplace/              # 隔离目录
```

## 更新日志

### v2.8.2 (2026-04-06)
**容错性与缓存逻辑优化**
*   ✅ **Edit 容错增强**：新增 `_find_similar_lines` 方法，匹配失败时返回相似行线索，打破死循环
*   ✅ **缓存版本隔离**：引入 `version_stats`，文件修改后新版本读取计数从 0 开始，防止误拦截
*   ✅ **Read 智能拦截**：在 `execute` 中集成拦截判断，被拦截时返回详细修正建议
*   ✅ **全量回归通过**：95 个测试用例全部通过，Edit 匹配与缓存重置验收通过

### v2.8.1 (2026-04-05)
**代码质量优化与技术债清理**
*   ✅ 移除硬编码：`executor.py` 和 `permission.py` 中的工具名硬编码已清理
*   ✅ 公共常量抽取：`EXCLUDED_DIRS` 抽取到 `utils/paths.py`，Glob/Grep 统一使用
*   ✅ 统一实现模式：Tool 基类新增 `parameters` 属性，各工具 `get_security_context()` 移除 `hasattr` 检查
*   ✅ Write 卡片输出：新增 `display_output` 卡片式终端显示，图标正确渲染
*   ✅ Bug 修复：删除 `bash.py` 中重复定义的 `is_read_only()` 方法
*   ✅ 全量回归通过：95 个测试用例全部通过

### v2.8.0 (2026-04-04)
**工具系统架构重构与测试体系升级**
*   ✅ 结构化输出：`ToolResult` 新增 `summary`、`metadata` 字段，实现视图与逻辑解耦
*   ✅ 安全上下文钩子：引入 `get_security_context()`，权限系统不再硬编码工具名
*   ✅ 执行器中间件化：`executor.py` 拆分为预处理/后处理链，消除硬编码分支
*   ✅ 测试体系升级：新增 `test_tool_architecture.py` 架构契约测试，删除过时 `test_parser.py`
*   ✅ 全量回归通过：95 个测试用例全部通过，确保重构未引入回归错误

### v2.7.25 (2026-04-04)
**交互体验优化与测试精简**
*   ✅ UI 静默重试：API 连接重试过程不再刷屏，仅在最终失败时报错
*   ✅ 实时思考计时：引入后台线程，实现 0.1s 频率的实时时间跳动
*   ✅ 测试套件精简：删除非核心网络测试，简化全量测试命令

### v2.7.24 (2026-04-04)
**交互体验优化与安全加固**
*   ✅ UI 静默重试：API 连接重试过程不再刷屏，仅在最终失败时报错
*   ✅ 权限卡片精简：移除冗长的 Details 字段，只保留核心操作描述
*   ✅ Bash 路径隔离：默认 `cwd` 强制指向 `workplace/`，防止污染项目根目录
*   ✅ Unix 命令兼容：自动转换 `ls/cat/rm` 等常见 Unix 命令为 PowerShell 等效指令
*   ✅ 防死循环机制：连续 3 次同质错误触发熔断，强制模型停止无效重试
*   ✅ Prompt 强化：明确告知模型 Bash 环境的"位置感知"，消除路径认知偏差
*   ✅ 最大循环提升：`MAX_TOOL_ROUNDS` 提升至 10，配合熔断机制使用

### v2.7.23 (2026-04-03)
**UI 系统全链路重构**
*   ✅ 全面采用 Rich Panel 卡片体系，移除手动边框
*   ✅ 统一语义化配色与圆角渲染
*   ✅ 修复 Prompt Toolkit 样式映射泄露问题
*   ✅ Bash/Read 工具输出卡片化，折叠长输出

### v2.7.22 (2026-04-03)
**工具系统稳固与代码清理**
*   ✅ 路径解析与缓存版本链彻底打通
*   ✅ 重复读取拦截机制生效
*   ✅ 全模块代码级空格/断字清理
*   ✅ Bash 流式卡片架构收敛

### v2.7.21 (2026-04-03)
**路径与权限优化**
*   ✅ Read/Glob/Grep 取消 workplace 隔离
*   ✅ 只读工具自动放行
*   ✅ Glob/Grep 自动排除无关目录

### v2.7.20 (2026-04-02)
**工具系统全面验收**
*   ✅ 7 个内置工具全量测试通过
*   ✅ 敏感/危险命令分级处理落地