这是基于 v2.8.5 格式更新的 **README.md**，已同步至 **v2.8.7** 版本。

主要变更点：
*   **版本号**：更新至 `v2.8.7`。
*   **工具执行上限提升**：MAX_TOOL_ROUNDS 10→20，MAX_TOOLS_PER_ROUND 20→40，总容量提升 4 倍。
*   **Bash 输出优化**：分离 stdout/stderr，失败时优先保留 stderr，避免丢失关键错误信息。
*   **异常捕获精细化**：Write/Edit 新增 FileNotFoundError、OSError、UnicodeError 等具体异常。
*   **skipped 状态细分**：区分"权限拒绝"和"用户主动取消"，反馈更精准。
*   **交互式命令检测**：新增 20+ 种交互式命令模式检测，提前拦截会卡住的命令。
*   **更新日志**：新增 v2.8.6、v2.8.7 重构记录。

---

# Claude Code Terminal

仿照官方 Claude Code 风格构建的 CLI AI 编程助手，支持 AI 驱动的文件操作和命令执行。

**版本：v2.8.7**

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
*   **Edit 容错增强** - 多层匹配策略（精确→忽略空白→模糊），返回候选和相似度分数

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

在 `config/defaults.py` 中配置：

```python
# API 配置
API_BASE_URL = "https://your-api-endpoint.com/v1"
API_KEY = "your-api-key"

# 模型配置
DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

# 权限配置
DEFAULT_PERMISSION_LEVEL = "once"  # once / no_once
```

## 使用

```bash
# 启动应用
python -m claude_code

# 运行测试
python -m pytest tests/ -q
```

## 项目结构

```
claude-code/
├── pyproject.toml          # 包配置
├── config/
│   └── defaults.py         # 默认配置
├── src/
│   └── claude_code/
│       ├── __init__.py
│       ├── __main__.py     # 入口
│       ├── core/
│       │   ├── app.py      # 主应用
│       │   ├── session.py  # 会话管理
│       │   └── llm.py      # LLM 客户端
│       ├── tools/
│       │   ├── base.py     # 工具基类
│       │   ├── executor.py # 工具执行器
│       │   ├── permission.py # 权限管理
│       │   ├── builtins/   # 内置工具
│       │   │   ├── read.py
│       │   │   ├── write.py
│       │   │   ├── edit.py
│       │   │   ├── bash.py
│       │   │   ├── grep.py
│       │   │   ├── glob.py
│       │   │   └── ask.py
│       │   └── file_cache.py # 文件缓存
│       ├── ui/
│       │   ├── display.py  # 输出渲染
│       │   ├── theme.py    # 主题配置
│       │   └── input.py    # 输入处理
│       └── utils/
│           └── paths.py    # 路径处理
├── tests/
│   ├── test_tools.py       # 工具测试
│   ├── test_permission.py  # 权限测试
│   ├── test_file_cache.py  # 缓存测试
│   └── test_tool_architecture.py # 架构契约测试
└── workplace/              # 工作目录（Write/Edit/Bash 隔离）
```

## 更新日志

### v2.8.7 (2026-04-10)
**工具反馈机制优化**
*   ✅ 工具执行上限提升：MAX_TOOL_ROUNDS 10→20，MAX_TOOLS_PER_ROUND 20→40
*   ✅ Bash 输出分离：stdout/stderr 分离处理，失败时优先保留 stderr
*   ✅ 异常捕获精细化：新增 FileNotFoundError、OSError、UnicodeError 等具体异常
*   ✅ skipped 状态细分：区分"权限拒绝"和"用户主动取消"
*   ✅ 语法警告增强：显眼格式 + 修正建议
*   ✅ 交互式命令检测：20+ 种模式提前拦截（vim、top、python -i 等）
*   ✅ 全量测试通过：100 passed in 0.77s

### v2.8.6 (2026-04-09)
**语法检查模块集成**
*   ✅ 新增 `syntax_checker.py` 模块，支持 13 种文件类型语法检查
*   ✅ Write 工具集成：写入后自动检查语法，显示警告信息
*   ✅ Edit 工具集成：replace/lines 模式均支持语法检查
*   ✅ SafeTextColumn 修复：解决 Progress 花括号格式化错误
*   ✅ 全量测试通过：100 passed in 0.81s

### v2.8.5 (2026-04-08)
**Read 工具优化**
*   ✅ Read 终端显示优化：短文件(<80行)完整显示，长文件(≥80行)显示头30行+尾20行
*   ✅ Read 模型输出：始终返回完整内容给模型，不再使用摘要模式
*   ✅ 取消读取次数限制：移除 5 次重复读取拦截，保留读取追踪功能
*   ✅ 工具调用上限提升：单轮工具上限从 10 提升到 20
*   ✅ 全量测试通过：95 passed in 1.27s

### v2.8.4 (2026-04-07)
**工具显示格式统一**
*   ✅ 统一格式：`✎ 工具名: 目标对象 [状态] (元信息)` + 分隔线 + 带行号内容
*   ✅ Bash 混合方案：统一标题行 + Panel 包裹输出
*   ✅ Edit diff 显示：删除行红色字体，新增行绿色字体
*   ✅ 工具间隔优化：每个工具输出前添加空行分隔
*   ✅ 全量测试通过：95 passed in 0.79s

### v2.8.3 (2026-04-07)
**Edit 工具多层匹配重构**
*   ✅ 引入 difflib.SequenceMatcher 相似度计算
*   ✅ 三层匹配策略：精确匹配 → 忽略空白匹配 → 模糊匹配（阈值 0.8）
*   ✅ 多候选返回：多处匹配时返回候选位置和相似度分数
*   ✅ 智能错误反馈：建议添加更多上下文行
*   ✅ 保持红绿 diff 显示不变
*   ✅ 全量测试通过：95 passed

### v2.8.2 (2026-04-06)
**容错性与缓存逻辑优化**
*   ✅ Edit 工具增强：新增 `_find_similar_lines` 辅助方法，匹配失败时提供相似行线索
*   ✅ 文件缓存优化：引入 `version_stats` 实现版本隔离计数
*   ✅ Read 工具拦截逻辑：集成智能拦截判断，提供明确修正建议
*   ✅ 测试通过：95 passed in 0.45s

### v2.8.1 (2026-04-05)
**架构稳固与测试完善**
*   ✅ 工具架构标准化：所有工具统一继承 `Tool` 基类，实现 `get_parameters_schema()`、`execute()`、`get_security_context()` 三大接口
*   ✅ 执行器预处理重构：拆分为预处理/后处理链，消除硬编码分支
*   ✅ 测试体系升级：新增 `test_tool_architecture.py` 架构契约测试
*   ✅ 全量回归通过：95 个测试用例全部通过

### v2.7.25 (2026-04-04)
**交互体验优化与测试精简**
*   ✅ UI 静默重试：API 连接重试过程不再刷屏，仅在最终失败时报错
*   ✅ 实时思考计时：引入后台线程，实现 0.1s 频率的实时时间跳动
*   ✅ 测试套件精简：删除非核心网络测试，简化全量测试命令

### v2.7.24 (2026-04-04)
**交互体验优化与安全加固**
*   ✅ 权限卡片精简：移除冗长的 Details 字段，只保留核心操作描述
*   ✅ Bash 路径隔离：默认 `cwd` 强制指向 `workplace/`，防止污染项目根目录
*   ✅ Unix 命令兼容：自动转换 `ls/cat/rm` 等常见 Unix 命令为 PowerShell 等效指令
*   ✅ 防死循环机制：连续 3 次同质错误触发熔断，强制模型停止无效重试

### v2.7.23 (2026-04-03)
**UI 系统全链路重构**
*   ✅ 全面采用 Rich Panel 卡片体系，移除手动边框
*   ✅ 统一语义化配色与圆角渲染
*   ✅ 修复 Prompt Toolkit 样式映射泄露问题

### v2.7.22 (2026-04-03)
**工具系统稳固与代码清理**
*   ✅ 路径解析与缓存版本链彻底打通
*   ✅ 重复读取拦截机制生效
*   ✅ 全模块代码级空格/断字清理

### v2.7.21 (2026-04-03)
**路径与权限优化**
*   ✅ Read/Glob/Grep 取消 workplace 隔离
*   ✅ 只读工具自动放行
*   ✅ Glob/Grep 自动排除无关目录

### v2.7.20 (2026-04-02)
**工具系统全面验收**
*   ✅ 7 个内置工具全量测试通过
*   ✅ 敏感/危险命令分级处理落地

## 许可证

MIT License