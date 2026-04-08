"""Read 工具 - 读取文件内容（集成缓存 + 进度显示）"""
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import Tool, ToolResult
from ..file_cache import file_cache
from claude_code.utils.paths import resolve_path, get_file_icon
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
    )

    # 文件大小限制 (1MB)
    MAX_FILE_SIZE = 1 * 1024 * 1024
    # 默认读取行数限制
    DEFAULT_LIMIT = 1500
    # 摘要模式阈值（行数）
    SUMMARY_THRESHOLD = 1500
    # 摘要预览行数
    PREVIEW_LINES = 50
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
                    "description": "要读取的文件路径（绝对路径或相对路径）"
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
                },
                "summary": {
                    "type": "boolean",
                    "description": "是否返回摘要模式。大文件默认 true，设置 false 获取完整内容。",
                    "default": True
                }
            },
            "required": ["file_path"]
        }

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行读取操作"""
        file_path = parameters.get("file_path", "")
        try:
            offset = int(parameters.get("offset", 1))
        except (ValueError, TypeError):
            offset = 1
        try:
            limit = int(parameters.get("limit", self.DEFAULT_LIMIT))
        except (ValueError, TypeError):
            limit = self.DEFAULT_LIMIT

        summary = parameters.get("summary", True)
        if isinstance(summary, str):
            summary = summary.lower() not in ("false", "0", "no")

        has_specific_range = offset > 1 or limit < self.DEFAULT_LIMIT

        if not file_path:
            return ToolResult(success=False, output="", error="缺少 file_path 参数")

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
                    content = self._read_file_with_progress(path, progress_bar, task)
                console.print(f"  [{COLORS['success']}]{ICONS['success']}[/] [dim]读取完成[/] ")
            else:
                content = self._read_file(path)

            lines = content.split('\n')
            total_lines = len(lines)
            cache_result = file_cache.read_file(file_path, content)
            reference = cache_result["reference"]
            version = cache_result["version"]
            was_cached = cache_result["cached"]

            use_summary = (
                summary
                and not has_specific_range
                and total_lines >= self.SUMMARY_THRESHOLD
            )
            size_kb = file_size / 1024

            # 构建输出
            output = self._build_model_output(
                path, lines, total_lines, size_kb, reference,
                was_cached, use_summary, offset, limit
            )
            display_output = self._build_terminal_display(
                path, lines, total_lines, size_kb, reference,
                was_cached, use_summary, offset, limit
            )

# 记录读取操作（用于追踪，不再拦截）
            start_line = offset if not use_summary else 1
            end_line = min(offset + limit - 1, total_lines) if not use_summary else total_lines
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
                    "summary_mode": use_summary,
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
        self, path, lines, total_lines, size_kb,
        reference, was_cached, use_summary, offset, limit
    ) -> str:
        """构建给模型的纯文本输出（始终返回完整内容）"""
        parts = []

        # 文件元信息
        parts.append(f"File: {path.name} ({total_lines} lines, {size_kb:.1f}KB)")
        parts.append(f"Path: {path}")
        parts.append(f"Cache: {reference}")
        parts.append("")

        # 始终返回完整内容给模型
        start_line = max(1, offset)
        end_line = min(total_lines, start_line + limit - 1)

        parts.append(f"Content (lines {start_line}-{end_line}):")
        for i in range(start_line - 1, end_line):
            parts.append(f"{i+1:5d} | {lines[i].rstrip()}")

        if end_line < total_lines:
            parts.append(f"  ... ({total_lines - end_line} more lines, use offset to continue)")

        return '\n'.join(parts)

    # ============================================================
    # 终端显示（始终省略模式）
    # ============================================================

    def _build_terminal_display(
        self, path, lines, total_lines, size_kb, reference,
        was_cached, use_summary, offset, limit
    ) -> str:
        """构建给终端的统一格式显示（始终省略模式）

        短文件（< TERMINAL_DISPLAY_THRESHOLD 行）：完整显示
        长文件（≥ TERMINAL_DISPLAY_THRESHOLD 行）：头 + 尾
        """
        cache_status = "[v0]" if was_cached else "[v0]"

        # 格式化大小
        if size_kb < 1024:
            size_str = f"{size_kb:.1f}KB"
        else:
            size_str = f"{size_kb / 1024:.1f}MB"

        parts = []
        # 开头空行，与其他工具分隔
        parts.append("")
        # 标题行：✎ Read: 文件名 [v0] (N lines, X KB)
        parts.append(f"[bold]{ICONS.get('edit', '✎')} Read:[/] [cyan]{escape(path.name)}[/] [dim]{cache_status} ({total_lines} lines, {size_str})[/]")
        # 分隔线
        parts.append(f"[dim]{'─' * 50}[/]")

        # 终端显示始终使用省略模式
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

    def _read_file_with_progress(self, path: Path, progress_bar, task) -> str:
        """读取文件内容（带进度显示）"""
        content_chunks = []
        file_size = path.stat().st_size
        read_bytes = 0
        chunk_size = 8192

        try:
            with open(path, 'r', encoding='utf-8') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    content_chunks.append(chunk)
                    read_bytes += len(chunk.encode('utf-8'))
                    progress = min(100, int(read_bytes / file_size * 100))
                    progress_bar.update(task, completed=progress)

            return ''.join(content_chunks)

        except UnicodeDecodeError:
            with open(path, 'r', encoding='gbk') as f:
                return f.read()

    # ============================================================
    # 结构分析
    # ============================================================

    def _analyze_structure(self, lines: List[str], file_ext: str) -> List[str]:
        """分析文件结构"""
        if file_ext == '.py':
            return self._analyze_python(lines)
        elif file_ext in ('.js', '.ts', '.jsx', '.tsx'):
            return self._analyze_javascript(lines)
        else:
            return self._analyze_generic(lines)

    def _analyze_python(self, lines: List[str]) -> List[str]:
        """分析 Python 文件结构"""
        structure = []
        current_class = None

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            if not stripped or stripped.startswith('#'):
                continue

            if stripped.startswith('class ') and ':' in stripped:
                match = re.match(r'class\s+(\w+)', stripped)
                if match:
                    class_name = match.group(1)
                    structure.append(f"L{i:4d}  class {class_name}")
                    current_class = class_name

            elif stripped.startswith('def ') and ':' in stripped:
                match = re.match(r'def\s+(\w+)', stripped)
                if match:
                    func_name = match.group(1)
                    indent = len(line) - len(line.lstrip())
                    if indent == 0:
                        structure.append(f"L{i:4d}  def {func_name}()")
                        current_class = None
                    elif current_class and indent == 4:
                        structure.append(f"L{i:4d}    def {func_name}()  # in {current_class}")

        if len(structure) > 20:
            structure = structure[:20]
            structure.append("  ... (more)")

        return structure

    def _analyze_javascript(self, lines: List[str]) -> List[str]:
        """分析 JavaScript/TypeScript 文件结构"""
        structure = []

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            if not stripped or stripped.startswith('//'):
                continue

            if re.match(r'(export\s+)?(async\s+)?function\s+\w+', stripped):
                match = re.search(r'function\s+(\w+)', stripped)
                if match:
                    structure.append(f"L{i:4d}  function {match.group(1)}()")

            elif re.match(r'(export\s+)?(const|let)\s+\w+\s*=\s*(async\s*)?\([^)]*\)\s*=>', stripped):
                match = re.match(r'(export\s+)?(const|let)\s+(\w+)', stripped)
                if match:
                    structure.append(f"L{i:4d}  const {match.group(3)}()")

            elif stripped.startswith('class ') and '{' in stripped:
                match = re.match(r'class\s+(\w+)', stripped)
                if match:
                    structure.append(f"L{i:4d}  class {match.group(1)}")

        if len(structure) > 20:
            structure = structure[:20]
            structure.append("  ... (more)")

        return structure

    def _analyze_generic(self, lines: List[str]) -> List[str]:
        """通用结构分析"""
        structure = []
        prev_empty = True  # 上一行是否为空行

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            if not stripped:
                prev_empty = True
                continue

            indent = len(line) - len(line.lstrip())

            # 采集条件：顶层行（缩进为0）且前面有空行分隔（段落开头）
            if indent == 0 and prev_empty:
                content = stripped[:60]
                structure.append(f"L{i:4d}  {content}")

            prev_empty = False

        if len(structure) > 15:
            structure = structure[:15]
            structure.append("  ... (more)")

        return structure

    # ============================================================
    # 工具属性
    # ============================================================

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"

        offset = parameters.get("offset", 1)
        if offset < 1:
            return "offset 必须 >= 1"

        limit = parameters.get("limit", self.DEFAULT_LIMIT)
        if limit < 1:
            return "limit 必须 >= 1"

        return None

    def is_read_only(self) -> bool:
        """只读操作"""
        return True