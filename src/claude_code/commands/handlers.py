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
        console.print("  • [dim]/tools[/]   → 查看工具执行历史")

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
    aliases = ["persona", "p"]
    
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
        from rich.box import ROUNDED
        console.print()
        console.print(Panel(
            f"[bold]{task_description}[/]\n[dim]模型将自动规划步骤并逐步执行[/]",
            title=f"[{COLORS['primary']}]● 计划模式[/]",
            title_align="left",
            border_style=COLORS['primary'],
            box=ROUNDED,
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
    QuitCommand,
]