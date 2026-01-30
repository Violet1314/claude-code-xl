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
    description = "切换 AI 人格风格"
    aliases = ["persona", "p"]
    
    def execute(self, args: List[str]) -> None:
        if self.app:
            self.app.select_style()

class AddCommand(Command):
    """添加文件命令"""
    
    name = "add"
    description = "挂载文件 (支持通配符)"
    aliases = ["attach", "a"]
    
    def execute(self, args: List[str]) -> None:
        if not args:
            console.warning("用法: /add <路径> [路径2] ... 或 /add *.py")
            return
        
        if self.app:
            self.app.add_files(args)

class DropCommand(Command):
    """移除文件命令"""
    
    name = "drop"
    description = "移除挂载文件"
    aliases = ["remove", "rm"]
    
    def execute(self, args: List[str]) -> None:
        if not args:
            console.warning("用法: /drop <路径> 或 /drop all")
            return
        
        if self.app:
            self.app.drop_files(args)

class FilesCommand(Command):
    """查看文件命令"""
    
    name = "files"
    description = "查看挂载文件列表"
    aliases = ["ls", "list"]
    
    def execute(self, args: List[str]) -> None:
        if self.app:
            self.app.show_files()

class RefreshCommand(Command):
    """刷新文件命令"""
    
    name = "refresh"
    description = "刷新挂载文件内容"
    aliases = ["reload"]
    
    def execute(self, args: List[str]) -> None:
        if self.app:
            self.app.refresh_files()

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

# 所有内置命令
BUILTIN_COMMANDS = [
    HelpCommand,
    NewCommand,
    ModelCommand,
    StyleCommand,
    AddCommand,
    DropCommand,
    FilesCommand,
    RefreshCommand,
    SaveCommand,
    HistoryCommand,
    QuitCommand,
]