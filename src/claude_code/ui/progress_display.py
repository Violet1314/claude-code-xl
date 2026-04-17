"""工具执行进度显示 - Bash 流式输出"""
import time
from typing import Optional, List
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.box import ROUNDED
from claude_code.ui import console as app_console
from claude_code.ui.theme import COLORS, ICONS


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

    def _escape_for_rich(self, text: str) -> str:
        """转义花括号，避免 Rich 格式化错误"""
        return text.replace('{', '{{').replace('}', '}}')

    def start(self) -> None:
        """开始执行"""
        self._start_time = time.time()

        display_cmd = self.command if len(self.command) <= 60 else self.command[:57] + "..."
        # 转义 PowerShell 花括号，避免 Rich 格式化错误
        safe_cmd = self._escape_for_rich(display_cmd)

        self._display = Progress(
            SpinnerColumn(spinner_name="dots", style=COLORS['primary']),
            TextColumn(f"[bold]{ICONS['bash']} Bash[/] "),
            TextColumn(f"[dim]$ {safe_cmd}[/] "),
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
        """停止并显示结果（混合方案：统一标题 + Panel 包裹）"""
        if self._display:
            self._display.stop()

        duration = time.time() - self._start_time
        status_str = '成功' if success else '失败'
        icon = ICONS.get('bash', '⚡')
        color = COLORS['success'] if success else COLORS['error']

        # 标题行：✎ Bash: command [状态] (耗时 Xs)
        display_cmd = self.command if len(self.command) <= 50 else self.command[:47] + "..."
        app_console.print()
        app_console.print(f"[bold]{icon} Bash:[/] [cyan]{display_cmd}[/] [dim]\\[{status_str}] ({duration:.2f}s)[/]")

        # 输出内容用 Panel 包裹
        if self._output_lines:
            max_lines = 20
            if len(self._output_lines) > max_lines:
                display_lines = self._output_lines[-max_lines:]
                content = "\n".join(display_lines)
                omitted = len(self._output_lines) - max_lines
                content += f"\n\n[dim]... (省略 {omitted} 行) ...[/]"
            else:
                content = "\n".join(self._output_lines)
        else:
            if self._error_message:
                content = f"[red]{self._error_message}[/]"
            else:
                content = "[dim](无输出)[/]"

        panel = Panel(
            content,
            border_style=color,
            box=ROUNDED,
            padding=(1, 2),
        )
        app_console.print(panel)
        app_console.print()
