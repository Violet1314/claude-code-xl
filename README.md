这是更新后的 `README.md`，已同步至 **v2.7.24** 版本，重点突出了最新的交互优化、Bash 安全隔离与防死循环机制。

```markdown
# Claude Code Terminal

仿照官方 Claude Code 风格构建的 CLI AI 编程助手，支持 AI 驱动的文件操作和命令执行。

**版本**：v2.7.24

---

## 功能特性

- **多模型支持** - 支持 GPT、Claude、Gemini、DeepSeek、Qwen 等多种模型
- **多风格切换** - 5 种 AI 人格（Expert、02、麻衣学姐、吹雪、薇尔莉特）
- **文件操作** - AI 可直接读取、创建、编辑本地文件
- **命令执行** - 安全的 Shell 命令执行，敏感/危险命令分级处理
- **流式输出** - SSE 流式响应，实时显示生成进度
- **Token 优化** - 文件缓存系统，减少重复传输
- **权限系统** - 只读工具自动放行，写入/执行操作需用户授权，敏感操作每次确认
- **主动交互** - AI 可向用户询问选择，澄清需求
- **卡片式输出** - 工具结果美化显示，边框+图标+颜色
- **文件图标** - 根据文件类型显示不同图标（.py 🐍、.js 📜 等）
- **终端压缩显示** - 大文件终端只显示首尾，完整内容给模型
- **输出分离架构** - 模型拿到完整内容，终端显示可省略
- **执行进度** - Bash 流式输出 + Read 进度显示
- **费用统计** - 实时显示会话累计费用，与中转平台一致
- **Workplace 隔离** - Write/Edit/Bash 默认隔离到 workplace 目录，Read/Glob/Grep 直接访问项目文件
- **目录自动过滤** - Glob/Grep 自动排除 .venv、node_modules、__pycache__ 等无关目录
- **智能防死循环** - 连续同质错误自动熔断，防止模型无效重试
- **静默重试机制** - API 连接波动时自动恢复，界面不再刷屏
- **Unix 命令兼容** - 自动转换常见 Unix 命令为 PowerShell 等效指令

---

## 快速开始

### 1. 下载与进入目录

```powershell
cd G:\7-Claude-code-cli\Claude-Code-CLI-main
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
  "api_key": "你的API密钥"
}
```

### 6. 运行
```powershell
python -m claude_code
```

---

## 命令列表

| 命令 | 别名 | 说明 |
| --- | --- | --- |
| /help | /h, /? | 显示命令帮助 |
| /new | /reset, /clear | 开始新会话 |
| /model | /m | 切换 AI 模型 |
| /style | /persona, /p | 切换 AI 风格 |
| /save | /s | 保存当前会话 |
| /history | /hist | 查看历史会话 |
| /tools | /tool | 查看工具执行历史 |
| /quit | /q, /exit | 退出程序 |

---

## 内置工具

| 工具 | 说明 |
| --- | --- |
| Read | 读取文件内容（卡片式输出，终端压缩显示，支持缓存引用） |
| Write | 创建或覆盖文件（含 Python 语法检查） |
| Edit | 精确替换文件内容（含 diff 显示，多处匹配警告） |
| Glob | 按文件名模式搜索（卡片式输出，文件类型统计） |
| Grep | 按内容正则搜索（卡片式输出） |
| Bash | 执行 Shell 命令（流式输出，敏感/危险命令分级处理，**默认隔离至 workplace/**） |
| AskUserQuestion | 向用户询问问题，获取选择或自由输入 |

只读工具（Read、Glob、Grep）自动放行，无需确认。写入/执行工具（Write、Edit、Bash）需要用户授权。敏感操作（删除、提权等）每次都需确认。

---

## 安全机制

### 权限分级
- **只读工具自动放行**：Read、Glob、Grep 无需确认，直接执行。
- **写入/执行工具需确认**：
  - `Yes (once)` - 仅允许当前操作（同工具同路径会话内缓存）
  - `No (once)` - 拒绝当前操作
  - `Esc/q` - 取消并中断后续执行

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
```text
     ██████╗ ██╗       █████╗  ██╗   ██╗ ██████╗  ███████╗
    ██╔════╝ ██║      ██╔══██╗ ██║   ██║ ██╔══██╗ ██╔════╝
    ...

  Claude Code Terminal v2.7.24 │ DeepSeek V3.2
  ────────────────────────────────────────────────────────
  "Code is poetry." — WordPress

  /help 查看命令  │  Tab 自动补全  │  Esc+Enter 发送
```

### 卡片式输出
```text
╭─ 🐍 defaults.py
│  44 行  │  1.7 KB  │  ✓ cached
│  📌 [file:defaults.py:v0]
│  完整内容 · 行 1-44
╰──────────────────────────────────────────
```

### 终端压缩显示（大文件）
```text
╭─ 🐍 large_file.py
│  282 行  │  8.5 KB  │  ✓ cached
│  显示 1-282 行:
│     1  """模块文档"""
│    ...
│   ... 省略 232 行 ...
│    263      demo_generators()
│    ...
╰──────────────────────────────────────────
```

### 状态栏
```text
◆ DEEPSEEK V3.2  │ $6/9 $/M │ ◆ 4.0K │ ≈$0.226
```

---

## 项目结构

```text
claude-code/
├── pyproject.toml              # 包配置
├── README.md
├── 重构进度总结.md             # 交接文档
│
├── src/claude_code/
│   ├── __init__.py             # 版本信息
│   ├── __main__.py             # 入口点
│   ├── app.py                  # 主应用类（含防死循环逻辑）
│   │
│   ├── config/                 # 配置管理
│   │   ├── defaults.py         # 常量配置
│   │   └── settings.py         # 配置加载
│   │
│   ├── core/                   # 核心模块
│   │   ├── client.py           # API 客户端（静默重试）
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
│   │   └── progress_display.py # 进度显示（Bash 卡片化）
│   │
│   ├── commands/               # 命令系统
│   │   ├── base.py             # 命令基类
│   │   ├── registry.py         # 命令注册
│   │   └── handlers.py         # 内置命令实现
│   │
│   ├── tools/                  # 工具系统
│   │   ├── base.py             # 工具基类
│   │   ├── executor.py         # 工具执行
│   │   ├── permission.py       # 权限管理
│   │   ├── permission_ui.py    # 权限确认 UI（极简卡片）
│   │   ├── tool_calling.py     # Native Tool Calling
│   │   ├── file_cache.py       # 文件缓存
│   │   └── builtins/           # 内置工具
│   │       └── bash.py         # Bash 工具（路径隔离 + Unix 转换）
│   │
│   └── utils/                  # 工具函数
│
├── tests/                      # 测试文件（93 passed）
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
python -m pytest tests/ -q --ignore=tests/test_api_stability.py --ignore=tests/test_connection_recovery.py
```
当前测试覆盖：`93 passed in 0.30s` (工具链全量验证通过)

### 依赖
| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| httpx | >=0.27.0 | HTTP 客户端（流式请求） |
| rich | >=13.7.0 | 终端 UI 渲染 |
| prompt-toolkit | >=3.0.43 | 交互式输入 |

---

## 更新日志

### v2.7.24 (2026-04-04)
**交互体验优化与安全加固**
- ✅ **UI 静默重试**：API 连接重试过程不再刷屏，仅在最终失败时报错
- ✅ **权限卡片精简**：移除冗长的 Details 字段，只保留核心操作描述
- ✅ **Bash 路径隔离**：默认 `cwd` 强制指向 `workplace/`，防止污染项目根目录
- ✅ **Unix 命令兼容**：自动转换 `ls/cat/rm` 等常见 Unix 命令为 PowerShell 等效指令
- ✅ **防死循环机制**：连续 3 次同质错误触发熔断，强制模型停止无效重试
- ✅ **Prompt 强化**：明确告知模型 Bash 环境的“位置感知”，消除路径认知偏差
- ✅ **最大循环提升**：`MAX_TOOL_ROUNDS` 提升至 10，配合熔断机制使用

### v2.7.23 (2026-04-03)
**UI 系统全链路重构**
- ✅ 全面采用 Rich Panel 卡片体系，移除手动边框
- ✅ 统一语义化配色与圆角渲染
- ✅ 修复 Prompt Toolkit 样式映射泄露问题
- ✅ Bash/Read 工具输出卡片化，折叠长输出

### v2.7.22 (2026-04-03)
**工具系统稳固与代码清理**
- ✅ 路径解析与缓存版本链彻底打通
- ✅ 重复读取拦截机制生效
- ✅ 全模块代码级空格/断字清理
- ✅ Bash 流式卡片架构收敛

### v2.7.21 (2026-04-03)
**路径与权限优化**
- ✅ Read/Glob/Grep 取消 workplace 隔离
- ✅ 只读工具自动放行
- ✅ Glob/Grep 自动排除无关目录

### v2.7.20 (2026-04-02)
**工具系统全面验收**
- ✅ 7 个内置工具全量测试通过
- ✅ 敏感/危险命令分级处理落地