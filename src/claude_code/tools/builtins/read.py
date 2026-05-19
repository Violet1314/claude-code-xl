"""Read 工具 - 读取文件内容（集成缓存 + 文件不存在时自动搜索回退）"""
from pathlib import Path
from typing import Any, Dict, Optional, Callable

from ..base import Tool, ToolResult
from ..file_cache import file_cache
from claude_code.core.path_manager import get_path_manager
from claude_code.ui.theme import COLORS, ICONS
from rich.markup import escape

class ReadTool(Tool):
    """读取文件工具（带缓存）"""

    name = "Read"
    description = (
        "读取用户本机文件内容。文件会被完整缓存，后续操作使用缓存引用节省 Token。"
    )

    # 文件大小限制 (1MB)
    MAX_FILE_SIZE = 1 * 1024 * 1024
    # 默认读取行数限制
    DEFAULT_LIMIT = 1500
    # 终端显示阈值
    TERMINAL_DISPLAY_THRESHOLD = 80
    TERMINAL_HEAD_LINES = 30
    TERMINAL_TAIL_LINES = 20
    # 搜索回退结果上限
    MAX_SEARCH_RESULTS = 10

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径",
                    "example": "E:\\项目目录\\src\\file.py"
                },
                "offset": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始），可选",
                    "default": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "读取的最大行数，默认 1500 行。大文件建议分段读取。",
                    "default": 1500
                }
            },
            "required": ["file_path"],
            "errorMessage": {
                "file_path": "必须提供 file_path，如 file_path=\"E:\\项目目录\\src\\file.py\""
            }
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

        # 使用 PathManager 统一路径解析
        pm = get_path_manager()
        file_path, boundary_ok = pm.resolve_safe(file_path)
        if not boundary_ok:
            return ToolResult(
                success=False, output="",
                error=f"路径越界: {file_path} 不在操作根目录 {pm.active_path} 下，禁止访问"
            )

        try:
            path = Path(file_path)
            if not path.exists():
                # 文件不存在时，自动回退到 Glob 搜索同名文件
                return self._handle_file_not_found(file_path, pm)
            if not path.is_file():
                return ToolResult(success=False, output="", error=f"不是文件: {file_path}")

            file_size = path.stat().st_size
            if file_size > self.MAX_FILE_SIZE:
                return ToolResult(
                    success=False, output="",
                    error=f"文件过大 ({file_size / 1024:.1f}KB)，超过 1MB 限制"
                )

            # 统一由 executor 的 Spinner 显示进度，工具内部不再显示
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

            # v2.8.37+ 优化：检测重复读取，返回缓存摘要而非完整内容
            abs_path = str(path.absolute())
            is_recent = file_cache.is_recent_read(abs_path)
            if is_recent and was_cached and not (parameters.get("offset") or parameters.get("limit")):
                cached_summary = file_cache.get_file_summary(abs_path)
                summary_text = cached_summary or f"{path.name} ({total_lines} lines)"
                compact_output = (
                    f"[文件已缓存] {path.name} — 内容未变化，上次已返回完整内容。\n"
                    f"摘要: {summary_text}\n"
                    f"提示: 如需重新查看完整内容，请指定行号范围（如 offset=1, limit=100）"
                )
                file_cache.mark_recent_read(abs_path)
                return ToolResult(
                    success=True,
                    output=compact_output,
                    display_output=f"[dim]◇ 重复读取: {escape(str(path))} → 返回缓存摘要[/]",
                    summary=f"Read {path.name} (cached, recent)",
                    metadata={
                        "file_path": abs_path,
                        "total_lines": total_lines,
                        "cached": True,
                        "recent_read": True,
                    }
                )

            # 构建输出
            output = self._build_model_output(
                path, lines, total_lines, size_kb, reference, offset, limit, was_cached
            )
            display_output = self._build_terminal_display(
                path, lines, total_lines, size_kb, reference, version, was_cached
            )

            # 记录读取操作
            start_line = offset
            end_line = min(offset + limit - 1, total_lines)
            abs_path_full = str(path.absolute())
            file_cache.record_read(abs_path_full, total_lines, start_line, end_line)
            # 标记为最近读取，用于后续重复 Read 检测
            file_cache.mark_recent_read(abs_path_full)

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

    # ============================================================
    # 模型输出（纯文本，无 Rich markup）
    # ============================================================

    def _build_model_output(
        self, path, lines, total_lines, size_kb, reference, offset, limit, was_cached=False
    ) -> str:
        """构建给模型的纯文本输出"""
        parts = []

        # 文件元信息
        parts.append(f"File: {path.name} ({total_lines} lines, {size_kb:.1f}KB)")
        parts.append(f"Path: {path}")
        parts.append(f"Cache: {reference}")
        if was_cached:
            parts.append("⚠ 缓存内容：如 Edit 匹配失败，请重新 Read 获取最新内容")
        parts.append("")

        # 计算读取范围
        start_line = max(1, offset)
        end_line = min(total_lines, start_line + limit)

        parts.append(f"Content (lines {start_line}-{end_line}):")
        for i in range(start_line - 1, end_line):
            # 不使用 rstrip()，保留原始内容（包括行尾空格），确保 Edit 精确匹配
            parts.append(f"{i+1:5d} | {lines[i]}")

        if end_line < total_lines:
            parts.append(f"  ... ({total_lines - end_line} more lines)")

        return '\n'.join(parts)

    # ============================================================
    # 终端显示（省略模式）
    # ============================================================

    def _build_terminal_display(
        self, path, lines, total_lines, size_kb, reference, version, was_cached
    ) -> str:
        """构建给终端的摘要行（文件内容通过 output 传给模型，终端只显示摘要）"""
        # 格式化大小
        if size_kb < 1024:
            size_str = f"{size_kb:.1f}KB"
        else:
            size_str = f"{size_kb / 1024:.1f}MB"

        return f"  {ICONS.get('read', '◇')} Read [cyan]{escape(path.name)}[/]  [dim]{total_lines} lines · {size_str}[/]"

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

    # ============================================================
    # 文件不存在时的自动搜索回退
    # ============================================================

    def _handle_file_not_found(self, file_path: str, pm) -> ToolResult:
        """文件不存在时的处理：自动搜索同名文件并给出精确路径建议"""
        from claude_code.utils.paths import format_file_not_found_error
        error_msg = format_file_not_found_error(file_path, pm.active_path, self.MAX_SEARCH_RESULTS)
        return ToolResult(success=False, output="", error=error_msg)

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
