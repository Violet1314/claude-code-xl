"""工具执行进度显示 - Bash 流式输出"""
import time
from typing import Optional, List
from rich.progress import Progress, SpinnerColumn, TextColumn
from claude_code.ui import console as app_console
from claude_code.ui.theme import COLORS, ICONS
from claude_code.ui.safe_markup import escape_markup


class BashStreamingDisplay:
    """Bash 命令执行显示 (缩进+图标前缀，轻盈风格)"""
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
        icon = ICONS.get('bash', '▶')
        color = COLORS['success'] if success else COLORS['error']

        # 标题行：▶ Bash: command [状态] (耗时 Xs)
        display_cmd = self.command if len(self.command) <= 50 else self.command[:47] + "..."
        app_console.print()
        app_console.print(f"[bold]{icon} Bash:[/] [cyan]{display_cmd}[/] [dim]\\[{status_str}] ({duration:.2f}s)[/]")

        # 输出内容：缩进+图标前缀，轻盈风格（去掉 Panel）
        if self._output_lines:
            max_lines = 20
            if len(self._output_lines) > max_lines:
                display_lines = self._output_lines[-max_lines:]
                for line in display_lines:
                    app_console.print(f"  {escape_markup(line)}", markup=True, highlight=False)
                omitted = len(self._output_lines) - max_lines
                app_console.print(f"  [dim]... (省略 {omitted} 行) ...[/]")
            else:
                for line in self._output_lines:
                    app_console.print(f"  {escape_markup(line)}", markup=True, highlight=False)
        else:
            if self._error_message:
                app_console.print(f"  [{COLORS['error']}]{escape_markup(self._error_message)}[/]")
            else:
                app_console.print("  [dim](无输出)[/]")
