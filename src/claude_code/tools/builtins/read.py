"""Read 工具 - 读取文件内容（集成缓存 + 进度显示）"""
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import Tool, ToolResult
from ..file_cache import file_cache
from claude_code.utils.paths import resolve_workplace_path
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
    # 默认读取行数限制（提高到1500，小文件一次读完）
    DEFAULT_LIMIT = 1500
    # 摘要模式阈值（行数）- 超过 1500 行才显示摘要
    SUMMARY_THRESHOLD = 1500
    # 摘要预览行数
    PREVIEW_LINES = 50
    # 终端显示阈值 - 超过此行数时，终端只显示首尾
    TERMINAL_DISPLAY_THRESHOLD = 80
    # 终端显示头部行数
    TERMINAL_HEAD_LINES = 30
    # 终端显示尾部行数
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

        # 参数类型转换
        try:
            offset = int(parameters.get("offset", 1))
        except (ValueError, TypeError):
            offset = 1

        try:
            limit = int(parameters.get("limit", self.DEFAULT_LIMIT))
        except (ValueError, TypeError):
            limit = self.DEFAULT_LIMIT

        # summary 参数（默认 True）
        summary = parameters.get("summary", True)
        if isinstance(summary, str):
            summary = summary.lower() not in ("false", "0", "no")

        # 判断是否指定了具体的读取范围
        has_specific_range = offset > 1 or limit < self.DEFAULT_LIMIT

        if not file_path:
            return ToolResult(success=False, output="", error="缺少 file_path 参数")

        # Workplace 隔离：相对路径重定向到 workplace 目录
        file_path = resolve_workplace_path(file_path)

        try:
            path = Path(file_path)

            if not path.exists():
                return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")

            if not path.is_file():
                return ToolResult(success=False, output="", error=f"不是文件: {file_path}")

            file_size = path.stat().st_size
            if file_size > self.MAX_FILE_SIZE:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"文件过大 ({file_size / 1024:.1f}KB)，超过 1MB 限制"
                )

            # 显示读取进度（对于大文件 > 50KB）
            show_progress = file_size > 50 * 1024

            if show_progress:
                # 截断文件名显示
                display_name = path.name
                if len(display_name) > 35:
                    display_name = display_name[:32] + "..."

                with Progress(
                    SpinnerColumn(spinner_name="dots", style=COLORS['primary']),
                    TextColumn(f"[bold]{ICONS.get('file', '📄')} Read[/] [cyan]{display_name}[/]"),
                    BarColumn(bar_width=20, complete_style=COLORS['success']),
                    TextColumn("[dim]读取中[/]"),
                    TimeElapsedColumn(),
                    console=console.get_console(),
                    transient=True,
                ) as progress_bar:
                    task = progress_bar.add_task("", total=100)

                    # 读取文件
                    content = self._read_file_with_progress(path, progress_bar, task)

                # 显示完成
                console.print(
                    f"  [{COLORS['success']}]{ICONS['success']}[/] "
                    f"[dim]读取完成[/]"
                )
            else:
                # 小文件直接读取
                content = self._read_file(path)

            lines = content.split('\n')
            total_lines = len(lines)

            # 存入缓存
            cache_result = file_cache.read_file(file_path, content)
            reference = cache_result["reference"]
            version = cache_result["version"]
            was_cached = cache_result["cached"]

            # 决定输出模式
            use_summary = (
                summary
                and not has_specific_range
                and total_lines >= self.SUMMARY_THRESHOLD
            )

            # 获取文件图标
            file_icon = self._get_file_icon(path.suffix.lower())

            # 卡片头部
            size_kb = file_size / 1024
            cache_status = "✓ 已缓存" if was_cached else "+ 新缓存"
            escaped_reference = escape(reference)

            # ========================================
            # 1. 构建给模型的完整输出（不省略）
            # ========================================
            output_parts = []
            output_parts.append(f"[dim {COLORS['border_subtle']}]╭─[/] {file_icon} [bold]{path.name}[/]")
            output_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
            output_parts.append(f"[dim {COLORS['border_subtle']}]│[/]  {total_lines} 行  [dim]│[/]  {size_kb:.1f} KB  [dim]│[/]  {cache_status}")
            output_parts.append(f"[dim {COLORS['border_subtle']}]│[/]  📌 [cyan]{escaped_reference}[/]")

            if use_summary:
                # 摘要模式：给模型也显示结构 + 预览（大文件合理行为）
                structure = self._analyze_structure(lines, path.suffix.lower())
                if structure:
                    output_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
                    output_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]结构概览:[/]")
                    for item in structure[:15]:
                        output_parts.append(f"[dim {COLORS['border_subtle']}]│[/]   {escape(item)}")
                    if len(structure) > 15:
                        output_parts.append(f"[dim {COLORS['border_subtle']}]│[/]   [dim]... (更多结构省略)[/]")

                output_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
                output_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]预览 (前 {self.PREVIEW_LINES} 行):[/]")
                for i, line in enumerate(lines[:self.PREVIEW_LINES], 1):
                    line_content = line.rstrip('\n\r')
                    output_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]{i:5d}[/]  {escape(line_content)}")

                output_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
                output_parts.append(f"[dim {COLORS['border_subtle']}]│[/] 💡 [dim]大文件已缓存结构，使用 offset/limit 读取具体部分[/]")
                output_parts.append(f"[dim {COLORS['border_subtle']}]╰{'─' * 50}[/]")
            else:
                # 完整模式：给模型返回完整内容
                start_line = max(1, offset)
                end_line = min(total_lines, start_line + limit - 1)

                output_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
                output_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]显示 {start_line}-{end_line} 行:[/]")

                # 完整内容，不省略
                for i in range(start_line - 1, end_line):
                    line = lines[i]
                    output_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]{i+1:5d}[/]  {escape(line.rstrip(chr(10)))}")

                if end_line < total_lines:
                    output_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]  ... 还有 {total_lines - end_line} 行（使用 offset 继续读取）[/]")

                output_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
                output_parts.append(f"[dim {COLORS['border_subtle']}]│[/] 💡 [dim]文件已完整缓存，无需再次读取。直接执行任务即可。[/]")
                output_parts.append(f"[dim {COLORS['border_subtle']}]╰{'─' * 50}[/]")

            output = '\n'.join(output_parts)

            # ========================================
            # 2. 构建给终端的显示输出（可省略）
            # ========================================
            display_parts = []
            display_parts.append(f"[dim {COLORS['border_subtle']}]╭─[/] {file_icon} [bold]{path.name}[/]")
            display_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
            display_parts.append(f"[dim {COLORS['border_subtle']}]│[/]  {total_lines} 行  [dim]│[/]  {size_kb:.1f} KB  [dim]│[/]  {cache_status}")
            display_parts.append(f"[dim {COLORS['border_subtle']}]│[/]  📌 [cyan]{escaped_reference}[/]")

            if use_summary:
                # 摘要模式：终端也显示摘要
                structure = self._analyze_structure(lines, path.suffix.lower())
                if structure:
                    display_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
                    display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]结构概览:[/]")
                    for item in structure[:15]:
                        display_parts.append(f"[dim {COLORS['border_subtle']}]│[/]   {escape(item)}")
                    if len(structure) > 15:
                        display_parts.append(f"[dim {COLORS['border_subtle']}]│[/]   [dim]... (更多结构省略)[/]")

                display_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
                display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]预览 (前 {self.PREVIEW_LINES} 行):[/]")
                for i, line in enumerate(lines[:self.PREVIEW_LINES], 1):
                    line_content = line.rstrip('\n\r')
                    if len(line_content) > 80:
                        line_content = line_content[:77] + "..."
                    display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]{i:5d}[/]  {escape(line_content)}")

                if total_lines > self.PREVIEW_LINES:
                    display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]  ... 省略 {total_lines - self.PREVIEW_LINES} 行[/]")

                display_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
                display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] 💡 [dim]大文件已缓存结构，使用 offset/limit 读取具体部分[/]")
                display_parts.append(f"[dim {COLORS['border_subtle']}]╰{'─' * 50}[/]")
            else:
                # 完整模式：终端可以省略显示
                start_line = max(1, offset)
                end_line = min(total_lines, start_line + limit - 1)
                display_lines = end_line - start_line + 1

                display_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
                display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]显示 {start_line}-{end_line} 行:[/]")

                # 终端显示优化：超过阈值时省略中间
                if display_lines > self.TERMINAL_DISPLAY_THRESHOLD:
                    # 显示头部
                    head_end = min(start_line + self.TERMINAL_HEAD_LINES - 1, end_line)
                    for i in range(start_line - 1, head_end):
                        line = lines[i]
                        if len(line) > 100:
                            line = line[:97] + "..."
                        display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]{i+1:5d}[/]  {escape(line.rstrip(chr(10)))}")

                    # 省略中间
                    tail_start = max(head_end + 1, end_line - self.TERMINAL_TAIL_LINES + 1)
                    omitted = tail_start - head_end - 1
                    if omitted > 0:
                        display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]  ... 省略 {omitted} 行 ...[/]")

                    # 显示尾部
                    for i in range(tail_start - 1, end_line):
                        line = lines[i]
                        if len(line) > 100:
                            line = line[:97] + "..."
                        display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]{i+1:5d}[/]  {escape(line.rstrip(chr(10)))}")
                else:
                    # 行数较少，完整显示
                    for i in range(start_line - 1, end_line):
                        line = lines[i]
                        if len(line) > 100:
                            line = line[:97] + "..."
                        display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]{i+1:5d}[/]  {escape(line.rstrip(chr(10)))}")

                if end_line < total_lines:
                    display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]  ... 还有 {total_lines - end_line} 行[/]")

                display_parts.append(f"[dim {COLORS['border_subtle']}]│[/]")
                display_parts.append(f"[dim {COLORS['border_subtle']}]│[/] 💡 [dim]文件已完整缓存，无需再次读取。直接执行任务即可。[/]")
                display_parts.append(f"[dim {COLORS['border_subtle']}]╰{'─' * 50}[/]")

            display_output = '\n'.join(display_parts)

            return ToolResult(
                success=True,
                output=output,  # 给模型的完整内容
                display_output=display_output,  # 给终端的省略版本
                metadata={
                    "file_path": str(path.absolute()),
                    "total_lines": total_lines,
                    "start_line": offset if not use_summary else 1,
                    "end_line": min(offset + limit - 1, total_lines) if not use_summary else total_lines,
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

    def _read_file(self, path: Path) -> str:
        """读取文件内容（简单模式）"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(path, 'r', encoding='gbk') as f:
                return f.read()

    def _read_file_with_progress(self, path: Path, progress_bar, task) -> str:
        """读取文件内容（带进度显示）"""
        import time

        content_chunks = []
        file_size = path.stat().st_size
        read_bytes = 0
        chunk_size = 8192  # 8KB chunks

        try:
            with open(path, 'r', encoding='utf-8') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break

                    content_chunks.append(chunk)
                    read_bytes += len(chunk.encode('utf-8'))

                    # 更新进度
                    progress = min(100, int(read_bytes / file_size * 100))
                    progress_bar.update(task, completed=progress)

            return ''.join(content_chunks)

        except UnicodeDecodeError:
            # 重试 GBK 编码
            with open(path, 'r', encoding='gbk') as f:
                return f.read()

    def _analyze_structure(self, lines: List[str], file_ext: str) -> List[str]:
        """
        分析文件结构

        Args:
            lines: 文件行列表
            file_ext: 文件扩展名

        Returns:
            结构描述列表
        """
        structure = []

        # Python 文件
        if file_ext == '.py':
            structure = self._analyze_python(lines)
        # JavaScript/TypeScript
        elif file_ext in ('.js', '.ts', '.jsx', '.tsx'):
            structure = self._analyze_javascript(lines)
        # 通用：识别缩进块
        else:
            structure = self._analyze_generic(lines)

        return structure

    def _analyze_python(self, lines: List[str]) -> List[str]:
        """分析 Python 文件结构"""
        structure = []
        current_class = None

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # 跳过空行和注释
            if not stripped or stripped.startswith('#'):
                continue

            # class 定义
            if stripped.startswith('class ') and ':' in stripped:
                match = re.match(r'class\s+(\w+)', stripped)
                if match:
                    class_name = match.group(1)
                    structure.append(f"L{i:4d}  class {class_name}")
                    current_class = class_name

            # def 定义（顶级方法或类方法）
            elif stripped.startswith('def ') and ':' in stripped:
                match = re.match(r'def\s+(\w+)', stripped)
                if match:
                    func_name = match.group(1)
                    # 判断缩进级别
                    indent = len(line) - len(line.lstrip())
                    if indent == 0:
                        structure.append(f"L{i:4d}  def {func_name}()")
                        current_class = None
                    elif current_class and indent == 4:
                        structure.append(f"L{i:4d}    def {func_name}()  # in {current_class}")

        # 限制输出数量
        if len(structure) > 20:
            structure = structure[:20]
            structure.append("  ... (更多结构省略)")

        return structure

    def _analyze_javascript(self, lines: List[str]) -> List[str]:
        """分析 JavaScript/TypeScript 文件结构"""
        structure = []

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            if not stripped or stripped.startswith('//'):
                continue

            # function 定义
            if re.match(r'(export\s+)?(async\s+)?function\s+\w+', stripped):
                match = re.search(r'function\s+(\w+)', stripped)
                if match:
                    structure.append(f"L{i:4d}  function {match.group(1)}()")

            # const/let function = () =>
            elif re.match(r'(export\s+)?(const|let)\s+\w+\s*=\s*(async\s*)?\([^)]*\)\s*=>', stripped):
                match = re.match(r'(export\s+)?(const|let)\s+(\w+)', stripped)
                if match:
                    structure.append(f"L{i:4d}  const {match.group(3)}()")

            # class 定义
            elif stripped.startswith('class ') and '{' in stripped:
                match = re.match(r'class\s+(\w+)', stripped)
                if match:
                    structure.append(f"L{i:4d}  class {match.group(1)}")

        if len(structure) > 20:
            structure = structure[:20]
            structure.append("  ... (更多结构省略)")

        return structure

    def _analyze_generic(self, lines: List[str]) -> List[str]:
        """通用结构分析（基于缩进）"""
        structure = []
        prev_indent = -1

        for i, line in enumerate(lines, start=1):
            if not line.strip():
                continue

            indent = len(line) - len(line.lstrip())

            # 检测缩进变化（新块开始）
            if indent > prev_indent and indent == 0:
                content = line.strip()[:60]
                if content:
                    structure.append(f"L{i:4d}  {content}")

            prev_indent = indent

        if len(structure) > 15:
            structure = structure[:15]
            structure.append("  ... (更多结构省略)")

        return structure

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

    def _get_file_icon(self, file_ext: str) -> str:
        """根据文件扩展名获取图标"""
        icons = {
            '.py': ICONS.get('file_py', '📄'),
            '.js': ICONS.get('file_js', '📄'),
            '.ts': ICONS.get('file_ts', '📄'),
            '.jsx': ICONS.get('file_js', '📄'),
            '.tsx': ICONS.get('file_ts', '📄'),
            '.json': ICONS.get('file_json', '📄'),
            '.md': ICONS.get('file_md', '📄'),
            '.txt': ICONS.get('file_txt', '📄'),
            '.yaml': ICONS.get('file_yaml', '📄'),
            '.yml': ICONS.get('file_yaml', '📄'),
            '.html': ICONS.get('file_html', '📄'),
            '.css': ICONS.get('file_css', '📄'),
            '.scss': ICONS.get('file_css', '📄'),
        }
        return icons.get(file_ext, ICONS.get('file_default', '📄'))