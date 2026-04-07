"""Write 工具 - 创建或覆盖文件"""
from ..file_cache import file_cache
from pathlib import Path
from typing import Any, Dict, Optional

from ..base import Tool, ToolResult
from claude_code.utils.paths import resolve_workplace_path, get_file_icon
from claude_code.ui.theme import COLORS
from rich.markup import escape


class WriteTool(Tool):
    """写入文件工具"""

    name = "Write"
    description = "创建新文件或覆盖现有文件。慎用，会覆盖已有内容。"

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "content": {
                    "type": "string",
                    "description": "文件内容"
                }
            },
            "required": ["file_path", "content"]
        }

    def _validate_content(self, content: str, file_path: str) -> tuple:
        """
        验证内容是否有明显的语法问题

        Returns:
            (is_valid, error_message)
        """
        # 只对 Python 文件做检查
        if not file_path.endswith('.py'):
            return True, None

        # 尝试编译检查语
        try:
            compile(content, file_path, 'exec')
            return True, None
        except SyntaxError as e:
            return False, f"语法错误: {e.msg} (行 {e.lineno})"

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行写入操作"""
        file_path = parameters.get("file_path", "")
        content = parameters.get("content", "")

        if not file_path:
            return ToolResult(success=False, output="", error="缺少 file_path 参数")

        file_path = resolve_workplace_path(file_path)

        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 更新文件缓存
            cache_result = file_cache.apply_write(file_path, content)
            
            output_msg = f"写入成功: {file_path} ({len(content)} 字符)"
            syntax_warning = None
            if file_path.endswith('.py'):
                is_valid, error_msg = self._validate_content(content, file_path)
                if not is_valid:
                    output_msg += f"\n\n⚠️ 语法警告: {error_msg}"
                    syntax_warning = error_msg

            # 构建终端显示（卡片式）
            display_output = self._build_terminal_display(path, content, syntax_warning)

            return ToolResult(
                success=True,
                output=output_msg,
                display_output=display_output,
                summary=f"Write {path.name}",
                metadata={
                    "file_path": str(path.absolute()),
                    "content_length": len(content),
                    "cache_version": cache_result.get("version", 0)
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足: {file_path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"写入失败: {str(e)}")

    def _build_terminal_display(self, path: Path, content: str, syntax_warning: Optional[str]) -> str:
        """构建终端统一格式显示"""
        from claude_code.ui.theme import ICONS

        lines = content.count('\n') + 1
        # 格式化大小
        content_len = len(content)
        if content_len < 1024:
            size_str = f"{content_len}B"
        else:
            size_str = f"{content_len / 1024:.1f}KB"

        # 判断是创建还是覆盖
        status = "created" if not path.exists() else "overwritten"

        parts = []
        # 开头空行，与其他工具分隔
        parts.append("")
        # 标题行：✎ Write: 文件名 [status] (lines, size)
        parts.append(f"[bold]{ICONS.get('edit', '✎')} Write:[/] [cyan]{escape(path.name)}[/] [dim]\\[{status}] ({lines} lines, {size_str})[/]")
        # 分隔线
        parts.append(f"[dim]{'─' * 50}[/]")

        # 内容预览（带行号，最多显示20行）
        content_lines = content.split('\n')
        max_preview = 20
        if len(content_lines) > max_preview:
            for i, line in enumerate(content_lines[:max_preview], 1):
                # 截断过长的行
                display_line = line[:100] if len(line) > 100 else line
                parts.append(f"[dim]{i:>5}[/]  {escape(display_line)}")
            omitted = len(content_lines) - max_preview
            parts.append(f"[dim]... (省略 {omitted} 行) ...[/]")
        else:
            for i, line in enumerate(content_lines, 1):
                display_line = line[:100] if len(line) > 100 else line
                parts.append(f"[dim]{i:>5}[/]  {escape(display_line)}")

        if syntax_warning:
            parts.append(f"[yellow]⚠ 语法警告:[/] [dim]{escape(syntax_warning[:80])}[/]")

        return '\n'.join(parts)

    def get_security_context(self) -> Dict[str, Any]:
        """返回安全上下文"""
        return {
            "is_sensitive": True,
            "paths": [self.parameters.get("file_path", "")],
            "command_preview": ""
        }

    def is_read_only(self) -> bool:
        """非只读操作"""
        return False

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"

        content = parameters.get("content")
        if content is None:
            return "缺少 content 参数"

        # 检查路径是否合法
        try:
            Path(file_path)
        except Exception:
            return f"无效的文件路径: {file_path}"

        return None