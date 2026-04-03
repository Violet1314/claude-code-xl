"""工具执行进度显示 - 优雅极简风格"""
import sys
import time
from typing import Optional, List
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED
from claude_code.ui import console as app_console
from claude_code.ui.theme import COLORS, ICONS

class ToolProgressDisplay:
    """工具执行进度显示 (Spinner Only)"""
    def __init__(self):
        self._progress: Optional[Progress] = None
        self._task_id: Optional[int] = None
        self._start_time: float = 0
        self._tool_name: str = ""

    def start(self, tool_name: str, description: str = "") -> None:
        """开始显示进度"""
        self._tool_name = tool_name
        self._start_time = time.time()
        icon = self._get_tool_icon(tool_name)
        
        # 创建简洁的 Spinner
        self._progress = Progress(
            SpinnerColumn(spinner_name="dots", style=COLORS['primary']),
            TextColumn(f"[bold]{icon} {tool_name}[/]"),
            TextColumn(f"[dim]{description}[/]"),
            console=app_console.get_console(),
            transient=True,
        )
        self._progress.start()
        self._task_id = self._progress.add_task("", total=None)

    def stop(self, success: bool = True, message: str = "") -> None:
        """停止进度显示"""
        if self._progress:
            self._progress.stop()
            self._progress = None
        
        duration = time.time() - self._start_time
        icon = ICONS['success'] if success else ICONS['error']
        color = COLORS['success'] if success else COLORS['error']
        
        # 显示简洁的完成状态
        status_text = f"[{color}]{icon}[/] [dim]{self._tool_name}[/] [dim]({duration:.1f}s)[/]"
        if message:
            status_text += f" [dim]- {message}[/]"
            
        app_console.print(status_text)

    def _get_tool_icon(self, tool_name: str) -> str:
        icons = {
            "Read": ICONS.get('read', '📄'),
            "Write": ICONS.get('write', '✎'),
            "Edit": ICONS.get('edit', '✐'),
            "Bash": ICONS.get('bash', '⚡'),
            "Grep": ICONS.get('grep', '🔍'),
            "Glob": ICONS.get('glob', '📂'),
            "AskUserQuestion": ICONS.get('ask', '💬'),
        }
        return icons.get(tool_name, ICONS.get('file', '📄'))


class BashStreamingDisplay:
    """Bash 命令执行显示 (最终卡片风格)"""
    def __init__(self, command: str, timeout: int = 120):
        self.command = command
        self.timeout = timeout
        self._start_time = 0
        self._output_lines: List[str] = []
        self._display: Optional[Progress] = None
        self._task_id: Optional[int] = None
        self._error_message: Optional[str] = None

    def start(self) -> None:
        """开始执行"""
        self._start_time = time.time()
        
        display_cmd = self.command if len(self.command) <= 60 else self.command[:57] + "..."
        
        self._display = Progress(
            SpinnerColumn(spinner_name="dots", style=COLORS['primary']),
            TextColumn(f"[bold]{ICONS['bash']} Bash[/] "),
            TextColumn(f"[dim]$ {display_cmd}[/] "),
            console=app_console.get_console(),
            transient=True,
        )
        self._display.start()
        self._task_id = self._display.add_task(" ", total=None)

    def is_timeout(self) -> bool:
        """检查是否超时"""
        return (time.time() - self._start_time) > self.timeout

    def set_error(self, message: str) -> None:
        """设置错误信息"""
        self._error_message = message

    def feed_output(self, line: str) -> None:
        """接收输出行"""
        if len(line) > 120:
            line = line[:117] + "..."
        self._output_lines.append(line)

    def stop(self, success: bool, return_code: int = 0) -> None:
        """停止并显示结果卡片"""
        if self._display:
            self._display.stop()
            
        duration = time.time() - self._start_time
        color = COLORS['success'] if success else COLORS['error']
        icon = ICONS['success'] if success else ICONS['error']
        
        status_str = 'Success' if success else 'Failed'
        title = f"{icon} Bash ({status_str} • {duration:.1f}s)"
        
        content = ""
        if self._output_lines:
            max_lines = 20
            if len(self._output_lines) > max_lines:
                omitted = len(self._output_lines) - max_lines
                display_lines = self._output_lines[-max_lines:]
                content = "\n".join(display_lines)
                content += f"\n\n[dim]... omitted {omitted} lines ...[/]"
            else:
                content = "\n".join(self._output_lines)
        else:
            if self._error_message:
                content = f"[red]{self._error_message}[/]"
            else:
                content = "[dim](No output)[/]"
            
        panel = Panel(
            content,
            title=title,
            title_align="left",
            border_style=color,
            box=ROUNDED,
            padding=(1, 2),
        )
        app_console.print()
        app_console.print(panel)
        app_console.print()


class ReadProgressDisplay:
    """Read 工具进度显示"""
    def __init__(self, file_path: str, total_lines: int = 0):
        self.file_path = file_path
        self.total_lines = total_lines
        self._display: Optional[Progress] = None
        self._task_id: Optional[int] = None

    def start(self) -> None:
        """开始读取"""
        from pathlib import Path
        display_name = Path(self.file_path).name
        if len(display_name) > 40:
            display_name = display_name[:37] + "..."
            
        self._display = Progress(
            SpinnerColumn(spinner_name="dots", style=COLORS['primary']),
            TextColumn(f"[bold]{ICONS['read']} Reading[/]"),
            TextColumn(f"[cyan]{display_name}[/]"),
            console=app_console.get_console(),
            transient=True,
        )
        self._display.start()
        self._task_id = self._display.add_task("", total=None)

    def stop(self, total_lines: int, file_size: int) -> None:
        """停止读取"""
        if self._display:
            self._display.stop()
            
        size_kb = file_size / 1024
        app_console.print(f"[dim]  ✓ {total_lines} lines • {size_kb:.1f} KB[/]")


def create_tool_progress(tool_name: str) -> ToolProgressDisplay:
    """工厂函数"""
    return ToolProgressDisplay()