"""内置命令实现"""
import os
from typing import List, Optional

from claude_code.commands.base import Command
from claude_code.ui import console

class HelpCommand(Command):
    """帮助命令"""

    name = "help"
    description = "显示命令帮助"
    aliases = ["h", "?"]

    def execute(self, args: List[str]) -> None:
        from claude_code.ui.theme import COLORS, ICONS

        console.blank()
        console.print(f"[bold {COLORS['primary']}]{ICONS['info']} 可用命令[/]")
        console.rule()

        if self.app and hasattr(self.app, 'commands'):
            for cmd_info in self.app.commands.list_commands():
                name = cmd_info["name"]
                desc = cmd_info["description"]
                aliases = cmd_info.get("aliases", [])
                alias_str = f" [dim](/{', /'.join(aliases)})[/]" if aliases else ""
                console.print(f"  [bold {COLORS['success']}]/{name:<10}[/] {desc}{alias_str}")

        console.blank()
        console.print(f"[bold {COLORS['info']}]{ICONS['info']} 输入技巧[/]")
        console.print("  • [dim]Enter[/] = 换行（对话模式）")
        console.print("  • [dim]Enter[/] = 直接发送（命令模式，如 /help）")
        console.print("  • [dim]Esc + Enter[/] = 发送消息")
        console.print("  • [dim]Ctrl+C[/] = 中断生成（单击中断，双击退出）")
        console.print("  • [dim]↑/↓ 或 j/k[/] = 菜单上下选择")
        console.print("  • [dim]1-9 数字键[/] = 快速选择菜单项")
        console.print("  • [dim]Esc 或 q[/] = 取消菜单")

        console.blank()
        console.print(f"[bold {COLORS['info']}]{ICONS['edit']} 常用命令示例[/]")
        console.print("  • [dim]/new[/]     → 开始新会话，清空历史")
        console.print("  • [dim]/save[/]    → 保存会话到 data/history/")
        console.print("  • [dim]/history[/] → 加载历史会话")
        console.print("  • [dim]/model[/]   → 切换 AI 模型")
        console.print("  • [dim]/plan[/]    → 进入计划模式，模型自主执行任务")

        console.blank()
        console.print(f"[bold {COLORS['info']}]{ICONS['bash']} 工具系统[/]")
        console.print(f"  {ICONS['read']} [dim]Read[/]    → 读取文件内容（≤1MB）")
        console.print(f"  {ICONS['write']} [dim]Write[/]   → 创建/覆盖文件，自动语法检查")
        console.print(f"  {ICONS['edit']} [dim]Edit[/]    → 精确匹配替换，需先 Read")
        console.print(f"  {ICONS['bash']} [dim]Bash[/]    → 执行命令，流式输出显示")
        console.print(f"  {ICONS['grep']} [dim]Grep[/]    → 正则搜索文件内容")
        console.print(f"  {ICONS['glob']} [dim]Glob[/]    → 文件名模式匹配")
        console.print(f"  {ICONS['ask']} [dim]Ask[/]     → 交互式询问用户")

        console.blank()
        console.print(f"[bold {COLORS['info']}]{ICONS['lock']} 权限确认[/]")
        console.print("  • [dim]允许 (本次)[/] → 仅本次通过，后续需再确认")
        console.print("  • [dim]允许 (会话)[/] → 本次会话同类操作自动通过")
        console.print("  • [dim]拒绝[/]       → 仅本次拒绝")
        console.blank()

class NewCommand(Command):
    """新建会话命令"""
    
    name = "new"
    description = "开始新会话"
    aliases = ["reset", "clear"]
    
    def execute(self, args: List[str]) -> None:
        if self.app:
            self.app.reset_conversation()
        console.success("已开始新会话")

class ModelCommand(Command):
    """切换模型命令"""
    
    name = "model"
    description = "切换 AI 模型"
    aliases = ["m"]
    
    def execute(self, args: List[str]) -> None:
        if self.app:
            self.app.select_model()

class StyleCommand(Command):
    """切换风格命令"""
    
    name = "style"
    description = "切换 AI 风格"
    aliases = ["persona"]
    
    def execute(self, args: List[str]) -> None:
        if self.app:
            self.app.select_style()

class SaveCommand(Command):
    """保存会话命令"""

    name = "save"
    description = "保存当前会话"
    aliases = ["s"]

    def execute(self, args: List[str]) -> None:
        if self.app:
            self.app.save_conversation()

class HistoryCommand(Command):
    """历史记录命令"""
    
    name = "history"
    description = "查看历史会话"
    aliases = ["hist"]
    
    def execute(self, args: List[str]) -> None:
        if self.app:
            self.app.load_history()

class QuitCommand(Command):
    """退出命令"""
    
    name = "quit"
    description = "退出程序"
    aliases = ["exit", "q"]
    
    def execute(self, args: List[str]) -> bool:
        """返回 True 表示退出"""
        return True

class ToolsCommand(Command):
    """工具历史命令"""

    name = "tools"
    description = "查看工具执行历史"
    aliases = ["tool", "history_tools"]
    hidden = True
    def execute(self, args: List[str]) -> None:
        if self.app:
            self.app.show_tools_history()

class PlanCommand(Command):
    """计划模式命令"""

    name = "plan"
    description = "进入计划模式，让模型自主规划并执行任务"
    aliases = ["p"]

    def execute(self, args: List[str]) -> None:
        if not self.app:
            return

        from claude_code.ui.theme import COLORS, ICONS
        from claude_code.tools.builtins.todo import get_todo_list, reset_todo_list

        # /plan stop：主动退出计划模式
        if args and args[0].lower() == "stop":
            todo = get_todo_list()
            if not self.app._plan_mode:
                console.info("当前不在计划模式中")
                if todo.items:
                    from claude_code.ui.components import show_plan_status
                    show_plan_status(todo, active=False)
            else:
                self.app._plan_mode = False
                self.app._plan_task = ""
                self.app._plan_reminder_count = 0
                self.app._update_input_state()
                from claude_code.ui.components import show_plan_stopped
                show_plan_stopped(todo)
            return

        # /plan status 或 /plan 无参数：显示当前计划
        if not args or args[0].lower() == "status":
            todo = get_todo_list()
            from claude_code.ui.components import show_plan_status
            show_plan_status(todo, active=self.app._plan_mode)
            return

        # /plan <任务描述>：进入计划模式
        task_description = " ".join(args)

        # 重置旧计划
        reset_todo_list()

        from rich.panel import Panel
        from claude_code.ui.theme import PANEL_STYLES
        console.print()
        console.print(Panel(
            f"[bold]{task_description}[/]\n[dim]模型将自动规划步骤并逐步执行[/]",
            title=f"[{COLORS['primary']}]● 计划模式[/]",
            title_align="left",
            border_style=COLORS['primary'],
            box=PANEL_STYLES['primary'],
            padding=(0, 2),
        ))
        # 设置计划模式标志，让 chat() 知道这是计划模式
        self.app._plan_mode = True
        self.app._plan_task = task_description
        self.app._plan_reminder_count = 0
        self.app._update_input_state()

        # 直接调用 chat()，模型会通过 TodoCreate 工具创建计划
        self.app.chat(task_description)

class CdCommand(Command):
    """切换工作目录命令"""

    name = "cd"
    description = "切换操作根目录（必须使用绝对路径）"
    aliases = ["chdir"]

    def execute(self, args: List[str]) -> None:
        if not self.app:
            return

        from claude_code.ui.theme import COLORS, ICONS

        # /cd 无参数：显示当前路径
        if not args:
            pm = self.app.path_manager
            console.print(f"\n[bold {COLORS['info']}]{ICONS['folder']} 当前操作根目录[/]: {pm.active_path}")
            if pm.is_workplace_mode:
                console.print(f"[dim]（workplace 安全隔离模式，使用 /cd <绝对路径> 切换到项目目录）[/]")
            return

        # /cd <绝对路径>：切换目录
        target_path = " ".join(args).strip().strip('"').strip("'")

        if not os.path.isabs(target_path):
            console.error(f"必须使用绝对路径，如: /cd E:\\你的项目目录")
            return

        pm = self.app.path_manager
        if pm.set_active_path(target_path):
            # 同步更新系统提示词（含新路径环境）
            self.app._setup_system_prompt()
            console.print(f"\n[bold {COLORS['success']}]{ICONS['success']} 操作根目录已切换[/]: {pm.active_path}")
            console.print(f"[dim]后续所有文件操作将基于此目录进行[/]")
        else:
            console.error(f"路径无效: {target_path}")

class LastOutputCommand(Command):
    """查看最后一次 Bash 命令的完整输出"""

    name = "last-output"
    description = "查看最后一次 Bash 命令的完整输出"
    aliases = ["lo"]

    def execute(self, args: List[str]) -> None:
        from claude_code.ui.theme import COLORS, ICONS

        if not self.app:
            return

        if not self.app._last_bash_output:
            console.info("暂无 Bash 输出记录")
            return

        from rich.panel import Panel
        from claude_code.ui.safe_markup import escape_markup

        command = self.app._last_bash_command
        output = self.app._last_bash_output

        # 截断显示命令
        display_cmd = command if len(command) <= 60 else command[:57] + "..."
        console.print()
        console.print(f"[bold]{ICONS['bash']} Bash:[/] [cyan]{escape_markup(display_cmd)}[/]")
        console.print(f"[dim]{'─' * 60}[/]")

        # 完整输出（不做行数限制）
        for line in output.splitlines():
            console.print(f"  {escape_markup(line)}", markup=True, highlight=False)

        console.print(f"[dim]{'─' * 60}[/]")
        console.print(f"[dim]共 {len(output.splitlines())} 行, {len(output)} 字符[/]")


class PwdCommand(Command):
    """显示当前路径命令"""

    name = "pwd"
    description = "显示当前操作根目录"
    aliases = []

    def execute(self, args: List[str]) -> None:
        if not self.app:
            return
        pm = self.app.path_manager
        from claude_code.ui.theme import COLORS, ICONS
        console.print(f"\n[bold {COLORS['info']}]{ICONS['folder']} 操作根目录[/]: {pm.active_path}")
        console.print(f"[dim]Workplace 目录[/]: {pm.workplace}")
        mode = "workplace 安全隔离" if pm.is_workplace_mode else "用户指定目录"
        console.print(f"[dim]当前模式[/]: {mode}")


class DoctorCommand(Command):
    """系统诊断命令"""

    name = "doctor"
    description = "运行系统诊断，检查配置和环境"
    aliases = ["diag"]

    def execute(self, args: List[str]) -> None:
        import sys
        import platform
        from claude_code.ui.theme import COLORS, ICONS
        from claude_code.__version__ import __version__, __author__

        results = []

        # 1. Python 版本
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        py_ok = sys.version_info >= (3, 10)
        results.append(("Python 版本", py_ver, py_ok, "需要 >= 3.10"))

        # 2. 核心依赖检查
        deps = {"httpx": "httpx", "rich": "rich", "prompt_toolkit": "prompt_toolkit", "tiktoken": "tiktoken"}
        for mod_name, pip_name in deps.items():
            try:
                mod = __import__(mod_name)
                ver = getattr(mod, "__version__", "已安装")
                results.append((f"依赖: {pip_name}", str(ver), True, ""))
            except ImportError:
                results.append((f"依赖: {pip_name}", "未安装", False, f"pip install {pip_name}"))

        # 3. API 配置
        if self.app and hasattr(self.app, 'settings'):
            settings = self.app.settings
            has_url = bool(settings.base_url)
            has_key = bool(settings.api_key)
            has_models = bool(settings.models)
            results.append(("API base_url", "已配置" if has_url else "未配置", has_url, "检查 data/config/api-config.json"))
            results.append(("API api_key", "已配置" if has_key else "未配置", has_key, "检查 data/config/api-config.json"))
            results.append(("模型列表", f"{len(settings.models)} 个模型", has_models, "至少配置一个模型"))

            # 4. 模型价格配置
            if settings.models:
                missing_price = [m.name for m in settings.models if not m.price]
                if missing_price:
                    results.append(("模型价格", f"{len(missing_price)} 个模型缺少价格", False, f"缺少: {', '.join(missing_price[:3])}"))
                else:
                    results.append(("模型价格", "全部已配置", True, ""))

        # 5. 路径状态
        if self.app and hasattr(self.app, 'path_manager'):
            pm = self.app.path_manager
            import os
            path_exists = os.path.isdir(pm.active_path)
            path_writable = os.access(pm.active_path, os.W_OK) if path_exists else False
            results.append(("操作根目录", pm.active_path, path_exists, "路径不存在"))
            results.append(("目录可写", "是" if path_writable else "否", path_writable, "检查目录权限"))
            results.append(("Workplace 模式", "是" if pm.is_workplace_mode else "否", True, ""))

        # 6. 项目记忆
        if self.app and hasattr(self.app, 'path_manager'):
            import os
            memory_path = os.path.join(self.app.path_manager.active_path, ".claude", "CLAUDE.md")
            has_memory = os.path.isfile(memory_path)
            results.append(("项目记忆 CLAUDE.md", "存在" if has_memory else "不存在", True, "可创建 .claude/CLAUDE.md 提升项目理解"))

        # 7. 版本一致性
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                tomllib = None

        if tomllib:
            try:
                import os
                toml_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "pyproject.toml")
                if os.path.isfile(toml_path):
                    with open(toml_path, "rb") as f:
                        toml_data = tomllib.load(f)
                    toml_ver = toml_data.get("project", {}).get("version", "")
                    ver_match = toml_ver == __version__
                    results.append(("版本一致性", f"pyproject={toml_ver}, code={__version__}", ver_match, "运行 clean_pycache.py 同步版本"))
                else:
                    results.append(("版本一致性", "pyproject.toml 未找到", True, ""))
            except Exception:
                results.append(("版本一致性", "无法读取", True, ""))
        else:
            results.append(("版本一致性", "无法检查（缺少 tomllib）", True, ""))

        # 8. PowerShell 兼容性
        import os
        is_windows = os.name == 'nt'
        results.append(("操作系统", f"{platform.system()} {platform.release()}", True, ""))
        if is_windows:
            results.append(("Shell 环境", "Windows PowerShell", True, "Unix 参数（-p/-r/-rf）不兼容"))

        # 9. 自动保存状态
        if self.app and hasattr(self.app, '_autosave'):
            has_autosave = self.app._autosave.has_data()
            results.append(("崩溃恢复", "有未恢复会话" if has_autosave else "无", True, ""))

        # 渲染结果
        from rich.panel import Panel
        from rich.table import Table

        console.print()
        table = Table(title=f"{ICONS['info']} 系统诊断", show_header=True, header_style="bold")
        table.add_column("检查项", style="cyan", width=20)
        table.add_column("状态", width=30)
        table.add_column("结果", width=6)
        table.add_column("说明", style="dim", width=30)

        for item, status, ok, note in results:
            icon = f"[{COLORS['success']}]{ICONS['success']}[/]" if ok else f"[{COLORS['error']}]{ICONS['error']}[/]"
            table.add_row(item, status, icon, note)

        console.print(table)

        # 统计
        total = len(results)
        passed = sum(1 for _, _, ok, _ in results if ok)
        failed = total - passed

        if failed == 0:
            console.print(f"\n[bold {COLORS['success']}]{ICONS['success']} 全部检查通过 ({passed}/{total})[/]")
        else:
            console.print(f"\n[bold {COLORS['error']}]{ICONS['error']} {failed} 项检查未通过 ({passed}/{total})[/]")
            console.print(f"[dim]请根据说明修复上述问题[/]")


# 所有内置命令
BUILTIN_COMMANDS = [
    HelpCommand,
    NewCommand,
    ModelCommand,
    StyleCommand,
    SaveCommand,
    HistoryCommand,
    ToolsCommand,
    PlanCommand,
    CdCommand,
    PwdCommand,
    LastOutputCommand,
    DoctorCommand,
    QuitCommand,
]