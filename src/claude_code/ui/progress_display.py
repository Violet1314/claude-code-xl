"""工具执行进度显示"""
import sys
import time
from typing import Optional

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.live import Live
from rich.text import Text
from rich.console import Console

from claude_code.ui import console as app_console
from claude_code.ui.theme import COLORS, ICONS


class ToolProgressDisplay:
    """工具执行进度显示"""

    def __init__(self):
        self._progress: Optional[Progress] = None
        self._task_id: Optional[int] = None
        self._start_time: float = 0
        self._tool_name: str = ""

    def start(self, tool_name: str, description: str = "") -> None:
        """
        开始显示进度

        Args:
            tool_name: 工具名称
            description: 描述文本
        """
        self._tool_name = tool_name
        self._start_time = time.time()

        # 获取 icon
        icon = self._get_tool_icon(tool_name)

        # 创建进度条
        self._progress = Progress(
            SpinnerColumn(spinner_name="dots", style=COLORS['primary']),
            TextColumn(f"[bold]{icon}[/] {tool_name}"),
            TextColumn(f"[dim]{description}[/]"),
            BarColumn(bar_width=20, complete_style=COLORS['success']),
            TimeElapsedColumn(),
            console=app_console.get_console(),
            transient=True,  # 完成后自动清除
        )
        self._progress.start()
        self._task_id = self._progress.add_task("", total=100)

    def update(self, advance: float = 0, description: str = None) -> None:
        """
        更新进度

        Args:
            advance: 进度增量（0-100）
            description: 新描述文本
        """
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, advance=advance)
            if description:
                pass

    def set_progress(self, progress: float) -> None:
        """
        设置绝对进度

        Args:
            progress: 进度值（0-100）
        """
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, completed=progress)

    def stop(self, success: bool = True, message: str = "") -> None:
        """
        停止进度显示

        Args:
            success: 是否成功
            message: 完成消息
        """
        if self._progress:
            self._progress.stop()
            self._progress = None

        # 显示完成状态
        duration = time.time() - self._start_time
        icon = ICONS['success'] if success else ICONS['error']
        color = COLORS['success'] if success else COLORS['error']
        tool_icon = self._get_tool_icon(self._tool_name)

        if message:
            app_console.print(
                f"  [{color}]{icon}[/] [dim]{self._tool_name}[/] {message} "
                f"[dim]({duration:.1f}s)[/]"
            )
        else:
            app_console.print(
                f"  [{color}]{icon}[/] [dim]{self._tool_name}[/] "
                f"[dim]({duration:.1f}s)[/]"
            )

    def _get_tool_icon(self, tool_name: str) -> str:
        """获取工具对应的图标"""
        icons = {
            "Read": ICONS.get('read', '📄'),
            "Write": ICONS.get('write', '📝'),
            "Edit": ICONS.get('edit', '✏️'),
            "Bash": ICONS.get('bash', '⚡'),
            "Grep": ICONS.get('grep', '🔍'),
            "Glob": ICONS.get('glob', '📁'),
            "AskUserQuestion": ICONS.get('ask', '❓'),
        }
        return icons.get(tool_name, ICONS.get('file', '📎'))


class BashStreamingDisplay:
    """Bash 命令流式输出显示"""

    def __init__(self, command: str, timeout: int = 120):
        self.command = command
        self.timeout = timeout
        self._start_time = 0
        self._live: Optional[Live] = None
        self._output_lines: list = []

    def start(self) -> None:
        """开始显示"""
        self._start_time = time.time()

        # 截断长命令
        display_cmd = self.command
        if len(display_cmd) > 60:
            display_cmd = display_cmd[:57] + "..."

        # 美化的头部
        app_console.print(f"\n  [dim {COLORS['border_subtle']}]╭─[/] [{COLORS['primary']}]{ICONS.get('bash', '⚡')} Bash[/]")
        app_console.print(f"  [dim {COLORS['border_subtle']}]│[/] [dim]$ {display_cmd}[/]")

    def feed_output(self, line: str) -> None:
        """
        喂入输出行

        Args:
            line: 输出行文本
        """
        # 截断长行
        if len(line) > 100:
            line = line[:97] + "..."

        self._output_lines.append(line)

        # 限制显示行数
        if len(self._output_lines) > 20:
            self._output_lines = self._output_lines[-20:]

        # 实时输出
        app_console.print_raw(f"  {line}")

    def get_elapsed_time(self) -> float:
        """获取已用时间"""
        return time.time() - self._start_time

    def is_timeout(self) -> bool:
        """检查是否超时"""
        return self.get_elapsed_time() > self.timeout

    def stop(self, success: bool, return_code: int = 0) -> None:
        """
        停止显示

        Args:
            success: 是否成功
            return_code: 返回码
        """
        duration = time.time() - self._start_time
        icon = ICONS['success'] if success else ICONS['error']
        color = COLORS['success'] if success else COLORS['error']

        # 底部边框
        app_console.print(f"  [dim {COLORS['border_subtle']}]│[/]")
        app_console.print(
            f"  [dim {COLORS['border_subtle']}]╰─[/] [{color}]{icon}[/] "
            f"[dim]return={return_code} | {duration:.1f}s[/]"
        )


class ReadProgressDisplay:
    """Read 工具进度显示"""

    def __init__(self, file_path: str, total_lines: int = 0):
        self.file_path = file_path
        self.total_lines = total_lines
        self._progress: Optional[Progress] = None
        self._task_id: Optional[int] = None

    def start(self) -> None:
        """开始显示"""
        from pathlib import Path
        path = Path(self.file_path)

        # 截断长路径
        display_path = str(path.name)
        if len(display_path) > 40:
            display_path = display_path[:37] + "..."

        # 美化的头部
        app_console.print(
            f"\n  [dim {COLORS['border_subtle']}]╭─[/] [{COLORS['primary']}]{ICONS.get('read', '📄')} Read[/] "
            f"[cyan]{display_path}[/]"
        )

        # 如果知道总行数，显示进度条
        if self.total_lines > 100:
            self._progress = Progress(
                SpinnerColumn(spinner_name="dots", style=COLORS['primary']),
                TextColumn("[dim]读取中[/]"),
                BarColumn(bar_width=20, complete_style=COLORS['success']),
                TextColumn("[cyan]{task.completed}/{task.total} 行[/]"),
                TimeElapsedColumn(),
                console=app_console.get_console(),
                transient=True,
            )
            self._progress.start()
            self._task_id = self._progress.add_task("", total=self.total_lines)

    def update(self, lines_read: int) -> None:
        """更新已读行数"""
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, completed=lines_read)

    def stop(self, total_lines: int, file_size: int) -> None:
        """停止显示"""
        if self._progress:
            self._progress.stop()
            self._progress = None

        # 显示完成信息
        size_kb = file_size / 1024
        app_console.print(
            f"  [dim {COLORS['border_subtle']}]╰─[/] [{COLORS['success']}]{ICONS['success']}[/] "
            f"[dim]{total_lines} 行 | {size_kb:.1f} KB[/]"
        )


def create_tool_progress(tool_name: str) -> ToolProgressDisplay:
    """创建工具进度显示器的便捷函数"""
    return ToolProgressDisplay()