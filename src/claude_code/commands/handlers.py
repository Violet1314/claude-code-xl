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
        from claude_code.ui.theme import COLORS
        
        console.blank()
        console.print(f"[bold {COLORS['primary']}]📖 可用命令[/]")
        console.rule()
        
        if self.app and hasattr(self.app, 'commands'):
            for cmd_info in self.app.commands.list_commands():
                name = cmd_info["name"]
                desc = cmd_info["description"]
                console.print(f"  [bold {COLORS['success']}]/{name:<12}[/] {desc}")
        
        console.blank()
        console.print(f"[bold {COLORS['info']}]💡 输入技巧[/]")
        console.print("  • [dim]Enter[/] = 换行")
        console.print("  • [dim]Esc + Enter[/] = 发送消息")
        console.print("  • [dim]Ctrl+C[/] = 中断生成")
        console.blank()
        console.print(f"[bold {COLORS['info']}]🔧 工具系统[/]")
        console.print("  • AI 可以读取、创建、编辑文件")
        console.print("  • 每次操作前会请求权限确认")
        console.print("  • 支持 once/always 两种权限模式，或按Esc取消")
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

class CopyCommand(Command):
    """导出代码块命令"""

    name = "copy"
    description = "导出最后回复中的代码块到文件"
    aliases = ["cp"]

    def execute(self, args: str) -> None:
        self.app.export_code()

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
    CopyCommand,
    ToolsCommand,
    QuitCommand,
]