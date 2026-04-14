"""Read 工具 - 读取文件内容（集成缓存 + 进度显示）"""
from pathlib import Path
from typing import Any, Dict, Optional, Callable, Tuple

from ..base import Tool, ToolResult
from ..file_cache import file_cache
from claude_code.utils.paths import resolve_path
from claude_code.ui import console
from claude_code.ui.theme import COLORS, ICONS
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.markup import escape

class ReadTool(Tool):
    """读取文件工具（带缓存）"""

    name = "Read"
    description = (
        "读取用户本机文件内容。你可以直接访问用户提供的任何本地路径，无需用户手动粘贴内容。"
        "文件会被完整缓存，后续操作使用缓存引用节省 Token。"
        "读取后请直接执行任务，不要再次调用 Read。如需编辑，直接使用 Edit 工具。"
        "\n重要：建议使用绝对路径，如 file_path=\"E:\\项目目录\\src\\file.py\""
    )

    # 文件大小限制 (1MB)
    MAX_FILE_SIZE = 1 * 1024 * 1024
    # 默认读取行数限制
    DEFAULT_LIMIT = 1500
    # 终端显示阈值
    TERMINAL_DISPLAY_THRESHOLD = 80
    TERMINAL_HEAD_LINES = 30
    TERMINAL_TAIL_LINES = 20

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径（建议使用绝对路径）"
                },
                "offset": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始），可选",
                    "default": 1
                },
                "limit": {
                    "type": "integer",
                    "description": f"读取的最大行数，默认 {self.DEFAULT_LIMIT} 行。大文件建议分段读取。",
                    "default": self.DEFAULT_LIMIT
                }
            },
            "required": ["file_path"]
        }

    def execute(
        self,
        parameters: Dict[str, Any],
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> ToolResult:
        """执行读取操作"""
        # 参数验证（与 Edit/Bash 工具一致）
        validation_error = self.validate_parameters(parameters)
        if validation_error:
            return ToolResult(success=False, output="", error=validation_error)

        file_path = parameters.get("file_path", "")
        offset = int(parameters.get("offset", 1))
        limit = int(parameters.get("limit", self.DEFAULT_LIMIT))

        file_path = resolve_path(file_path)

        try:
            path = Path(file_path)
            if not path.exists():
                return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")
            if not path.is_file():
                return ToolResult(success=False, output="", error=f"不是文件: {file_path}")

            file_size = path.stat().st_size
            if file_size > self.MAX_FILE_SIZE:
                return ToolResult(
                    success=False, output="",
                    error=f"文件过大 ({file_size / 1024:.1f}KB)，超过 1MB 限制"
                )

            # 大文件显示进度
            show_progress = file_size > 50 * 1024
            if show_progress:
                display_name = path.name
                if len(display_name) > 35:
                    display_name = display_name[:32] + "..."
                with Progress(
                    SpinnerColumn(spinner_name="dots", style=COLORS['primary']),
                    TextColumn(f"[bold]{ICONS.get('file', '📄')} Read[/] [cyan]{display_name}[/] "),
                    BarColumn(bar_width=20, complete_style=COLORS['success']),
                    TextColumn("[dim]读取中[/] "),
                    TimeElapsedColumn(),
                    console=console.get_console(),
                    transient=True,
                ) as progress_bar:
                    task = progress_bar.add_task("", total=100)
                    content, interrupted = self._read_file_with_progress(
                        path, progress_bar, task, interrupt_check
                    )
                    if interrupted:
                        return ToolResult(
                            success=False,
                            output="",
                            error="用户中断执行",
                            interrupted=True
                        )
                console.print(f"  [{COLORS['success']}]{ICONS['success']}[/] [dim]读取完成[/] ")
            else:
                content = self._read_file(path)

            # 使用 splitlines() 计算实际行数，但保留原始内容用于精确匹配
            # splitlines() 不保留末尾空行，更符合"行数"概念
            lines_for_count = content.splitlines()
            total_lines = len(lines_for_count)

            # 但模型输出需要保留完整原始内容（包括末尾换行），确保 Edit 精确匹配
            # 使用 split('\n') 获取每行内容，但最后一行如果是空字符串则不显示
            raw_lines = content.split('\n')
            # 如果文件末尾有换行，最后一项是空字符串，不需要作为单独一行显示
            if raw_lines and raw_lines[-1] == '':
                raw_lines = raw_lines[:-1]
            lines = raw_lines
            cache_result = file_cache.read_file(file_path, content)
            reference = cache_result["reference"]
            version = cache_result["version"]
            was_cached = cache_result["cached"]
            size_kb = file_size / 1024

            # 构建输出
            output = self._build_model_output(
                path, lines, total_lines, size_kb, reference, offset, limit
            )
            display_output = self._build_terminal_display(
                path, lines, total_lines, size_kb, reference, version, was_cached
            )

            # 记录读取操作
            start_line = offset
            end_line = min(offset + limit - 1, total_lines)
            file_cache.record_read(str(path.absolute()), total_lines, start_line, end_line)

            return ToolResult(
                success=True,
                output=output,
                display_output=display_output,
                summary=f"Read {path.name} ({total_lines} lines)",
                metadata={
                    "file_path": str(path.absolute()),
                    "total_lines": total_lines,
                    "start_line": start_line,
                    "end_line": end_line,
                    "file_size": file_size,
                    "cache_version": version,
                    "cache_reference": reference,
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足，无法读取: {file_path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"读取失败: {str(e)}")

    def get_security_context(self) -> Dict[str, Any]:
        """返回安全上下文（只读工具通常不敏感）"""
        return {
            "is_sensitive": False,
            "paths": [self.parameters.get("file_path", "")],
            "command_preview": ""
        }

    # ============================================================
    # 模型输出（纯文本，无 Rich markup）
    # ============================================================

    def _build_model_output(
        self, path, lines, total_lines, size_kb, reference, offset, limit
    ) -> str:
        """构建给模型的纯文本输出"""
        parts = []

        # 文件元信息
        parts.append(f"File: {path.name} ({total_lines} lines, {size_kb:.1f}KB)")
        parts.append(f"Path: {path}")
        parts.append(f"Cache: {reference}")
        parts.append("")

        # 计算读取范围
        start_line = max(1, offset)
        end_line = min(total_lines, start_line + limit - 1)

        parts.append(f"Content (lines {start_line}-{end_line}):")
        for i in range(start_line - 1, end_line):
            # 不使用 rstrip()，保留原始内容（包括行尾空格），确保 Edit 精确匹配
            parts.append(f"{i+1:5d} | {lines[i]}")

        if end_line < total_lines:
            parts.append(f"  ... ({total_lines - end_line} more lines, use offset to continue)")

        return '\n'.join(parts)

    # ============================================================
    # 终端显示（省略模式）
    # ============================================================

    def _build_terminal_display(
        self, path, lines, total_lines, size_kb, reference, version, was_cached
    ) -> str:
        """构建给终端的统一格式显示

        短文件（< TERMINAL_DISPLAY_THRESHOLD 行）：完整显示
        长文件（≥ TERMINAL_DISPLAY_THRESHOLD 行）：头 + 尾
        """
        # 缓存状态：显示版本号
        cache_status = f"[v{version}]" + (" cached" if was_cached else "")

        # 格式化大小
        if size_kb < 1024:
            size_str = f"{size_kb:.1f}KB"
        else:
            size_str = f"{size_kb / 1024:.1f}MB"

        parts = []
        # 开头空行，与其他工具分隔
        parts.append("")
        # 标题行：📖 Read: 文件名 [v0] (N lines, X KB)
        parts.append(f"[bold]{ICONS.get('read', '📖')} Read:[/] [cyan]{escape(path.name)}[/] [dim]{cache_status} ({total_lines} lines, {size_str})[/]")
        # 分隔线
        parts.append(f"[dim]{'─' * 50}[/]")

        # 终端显示使用省略模式
        if total_lines < self.TERMINAL_DISPLAY_THRESHOLD:
            # 短文件：完整显示
            for i, line in enumerate(lines, 1):
                display_line = line.rstrip()[:120] if len(line.rstrip()) > 120 else line.rstrip()
                parts.append(f"[dim]{i:>5}[/]  {escape(display_line)}")
        else:
            # 长文件：头 + 尾
            # 显示头部
            for i in range(self.TERMINAL_HEAD_LINES):
                if i >= total_lines:
                    break
                line = lines[i].rstrip()
                display_line = line[:120] if len(line) > 120 else line
                parts.append(f"[dim]{i+1:>5}[/]  {escape(display_line)}")

            # 省略提示
            omitted_lines = total_lines - self.TERMINAL_HEAD_LINES - self.TERMINAL_TAIL_LINES
            if omitted_lines > 0:
                parts.append(f"[dim]       ... (省略 {omitted_lines} 行) ...[/]")

            # 显示尾部
            tail_start = total_lines - self.TERMINAL_TAIL_LINES
            for i in range(tail_start, total_lines):
                line = lines[i].rstrip()
                display_line = line[:120] if len(line) > 120 else line
                parts.append(f"[dim]{i+1:>5}[/]  {escape(display_line)}")

        return '\n'.join(parts)

    # ============================================================
    # 文件读取
    # ============================================================

    def _read_file(self, path: Path) -> str:
        """读取文件内容"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(path, 'r', encoding='gbk') as f:
                return f.read()

    def _read_file_with_progress(
        self,
        path: Path,
        progress_bar,
        task,
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> Tuple[str, bool]:
        """
        读取文件内容（带进度显示 + 中断检查）

        Returns:
            (内容, 是否被中断)
        """
        content_chunks = []
        file_size = path.stat().st_size
        read_bytes = 0
        chunk_size = 8192

        try:
            with open(path, 'r', encoding='utf-8') as f:
                while True:
                    # 检查中断
                    if interrupt_check and interrupt_check():
                        return '', True  # 用户中断

                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    content_chunks.append(chunk)
                    read_bytes += len(chunk.encode('utf-8'))
                    progress = min(100, int(read_bytes / file_size * 100))
                    progress_bar.update(task, completed=progress)

            return ''.join(content_chunks), False

        except UnicodeDecodeError:
            with open(path, 'r', encoding='gbk') as f:
                return f.read(), False

    # ============================================================
    # 工具属性
    # ============================================================

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"

        # offset 验证（类型 + 范围）
        try:
            offset = int(parameters.get("offset", 1))
        except (ValueError, TypeError):
            return "offset 必须是整数"
        if offset < 1:
            return "offset 必须 >= 1"

        # limit 验证（类型 + 范围）
        try:
            limit = int(parameters.get("limit", self.DEFAULT_LIMIT))
        except (ValueError, TypeError):
            return "limit 必须是整数"
        if limit < 1:
            return "limit 必须 >= 1"

        return None

    def is_read_only(self) -> bool:
        """只读操作"""
        return True