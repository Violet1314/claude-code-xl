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
        "**重要**：每个文件只需读取一次，系统会自动检测并阻止重复读取。"
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
                path, total_lines, size_kb, reference,
                was_cached, use_summary, offset, limit
            )

            # 记录读取操作（用于重复读取检测）
            start_line = offset if not use_summary else 1
            end_line = min(offset + limit - 1,  total_lines) if not use_summary else total_lines
            
            # 【优化】检查是否触发拦截
            read_status = file_cache.record_read(str(path.absolute()), total_lines, start_line, end_line)
            if read_status["blocked"]:
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        f"⛔ 读取拦截：文件 {path.name} 已被多次读取（当前版本第 {read_status['count']} 次）。\n"
                        f"原因：系统检测到重复读取行为，为节省资源已拦截。\n"
                        f"解决方案：\n"
                        f"1. 该文件内容已在你的上下文历史中（参考引用: {reference}）。\n"
                        f"2. 如果你需要文件的特定部分，请使用 offset/limit 参数读取【未读取过的行】。\n"
                        f"3. 如果文件已被外部修改，请先确认是否真的需要最新内容。"
                    )
                )

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
        """构建给模型的纯文本输出"""
        parts = []

        # 文件元信息
        parts.append(f"File: {path.name} ({total_lines} lines, {size_kb:.1f}KB)")
        parts.append(f"Path: {path}")
        parts.append(f"Cache: {reference}")
        parts.append("")

        if use_summary:
            # 摘要模式
            structure = self._analyze_structure(lines, path.suffix.lower())
            if structure:
                parts.append("Structure:")
                for item in structure[:15]:
                    parts.append(f"  {item}")
                parts.append("")

            parts.append(f"Preview (first {self.PREVIEW_LINES} lines):")
            for i, line in enumerate(lines[:self.PREVIEW_LINES], 1):
                parts.append(f"{i:5d} | {line.rstrip()}")

            if total_lines > self.PREVIEW_LINES:
                parts.append(f"  ... ({total_lines - self.PREVIEW_LINES} more lines)")
            parts.append("")
            parts.append("Use offset/limit to read specific sections.")
        else:
            # 完整模式
            start_line = max(1, offset)
            end_line = min(total_lines, start_line + limit - 1)

            parts.append(f"Content (lines {start_line}-{end_line}):")
            for i in range(start_line - 1, end_line):
                parts.append(f"{i+1:5d} | {lines[i].rstrip()}")

            if end_line < total_lines:
                parts.append(f"  ... ({total_lines - end_line} more lines, use offset to continue)")

        return '\n'.join(parts)

    # ============================================================
    # 终端显示（Rich markup，简洁摘要）
    # ============================================================

    def _build_terminal_display(
        self, path, total_lines, size_kb, reference,
        was_cached, use_summary, offset, limit
    ) -> str:
        """构建给终端的简洁显示"""
        file_icon = get_file_icon(path.suffix.lower())
        cache_status = "✓ cached" if was_cached else "+ new"
        escaped_ref = escape(reference)

        parts = []
        parts.append(f"[dim {COLORS['border_subtle']}]╭─[/] {file_icon} [bold]{escape(path.name)}[/]")
        parts.append(f"[dim {COLORS['border_subtle']}]│[/]  {total_lines} 行  [dim]│[/]  {size_kb:.1f} KB  [dim]│[/]  {cache_status}")
        parts.append(f"[dim {COLORS['border_subtle']}]│[/]  📌 [cyan]{escaped_ref}[/]")

        if use_summary:
            parts.append(f"[dim {COLORS['border_subtle']}]│[/]  [dim]摘要模式 · 前 {self.PREVIEW_LINES} 行预览 + 结构概览[/]")
        else:
            start_line = max(1, offset)
            end_line = min(total_lines, start_line + limit - 1)
            parts.append(f"[dim {COLORS['border_subtle']}]│[/]  [dim]完整内容 · 行 {start_line}-{end_line}[/]")

        parts.append(f"[dim {COLORS['border_subtle']}]╰{'─' * 40}[/]")

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