"""内置命令实现"""
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
        console.print(f"[bold {COLORS['primary']}]📖 可用命令[/]")
        console.rule()

        if self.app and hasattr(self.app, 'commands'):
            for cmd_info in self.app.commands.list_commands():
                name = cmd_info["name"]
                desc = cmd_info["description"]
                aliases = cmd_info.get("aliases", [])
                alias_str = f" [dim](/{', /'.join(aliases)})[/]" if aliases else ""
                console.print(f"  [bold {COLORS['success']}]/{name:<10}[/] {desc}{alias_str}")

        console.blank()
        console.print(f"[bold {COLORS['info']}]💡 输入技巧[/]")
        console.print("  • [dim]Enter[/] = 换行（对话模式）")
        console.print("  • [dim]Enter[/] = 直接发送（命令模式，如 /help）")
        console.print("  • [dim]Esc + Enter[/] = 发送消息")
        console.print("  • [dim]Ctrl+C[/] = 中断生成（单击中断，双击退出）")
        console.print("  • [dim]↑/↓ 或 j/k[/] = 菜单上下选择")
        console.print("  • [dim]1-9 数字键[/] = 快速选择菜单项")
        console.print("  • [dim]Esc 或 q[/] = 取消菜单")

        console.blank()
        console.print(f"[bold {COLORS['info']}]📝 常用命令示例[/]")
        console.print("  • [dim]/new[/]     → 开始新会话，清空历史")
        console.print("  • [dim]/save[/]    → 保存会话到 data/history/")
        console.print("  • [dim]/history[/] → 加载历史会话")
        console.print("  • [dim]/model[/]   → 切换 AI 模型")
        console.print("  • [dim]/tools[/]   → 查看工具执行历史")

        console.blank()
        console.print(f"[bold {COLORS['info']}]🔧 工具系统[/]")
        console.print(f"  {ICONS['read']} [dim]Read[/]    → 读取文件内容（≤1MB）")
        console.print(f"  {ICONS['write']} [dim]Write[/]   → 创建/覆盖文件，自动语法检查")
        console.print(f"  {ICONS['edit']} [dim]Edit[/]    → 精确匹配替换，需先 Read")
        console.print(f"  {ICONS['bash']} [dim]Bash[/]    → 执行命令，流式输出显示")
        console.print(f"  {ICONS['grep']} [dim]Grep[/]    → 正则搜索文件内容")
        console.print(f"  {ICONS['glob']} [dim]Glob[/]    → 文件名模式匹配")
        console.print(f"  {ICONS['ask']} [dim]Ask[/]     → 交互式询问用户")

        console.blank()
        console.print(f"[bold {COLORS['info']}]🔒 权限确认[/]")
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

# 所有内置命令
BUILTIN_COMMANDS = [
    HelpCommand,
    NewCommand,
    ModelCommand,
    StyleCommand,
    SaveCommand,
    HistoryCommand,
    ToolsCommand,
    QuitCommand,
]