"""Write 工具 - 创建或覆盖文件"""
from ..file_cache import file_cache
from ..syntax_checker import check_syntax
from pathlib import Path
from typing import Any, Dict, Optional, Callable

from ..base import Tool, ToolResult
from claude_code.core.path_manager import get_path_manager
from claude_code.utils.paths import get_file_icon, format_size
from claude_code.ui.theme import COLORS, ICONS
from rich.markup import escape


class WriteTool(Tool):
    """写入文件工具"""

    name = "Write"
    description = (
        "创建新文件或覆盖文件。慎用，会覆盖已有内容。"
        "\n重要：必须使用绝对路径，如 file_path=\"E:\\项目目录\\src\\file.py\""
        "\n相对路径会自动基于操作根目录解析为绝对路径"
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径（必须使用绝对路径，相对路径基于操作根目录解析）",
                    "example": "E:\\项目目录\\src\\file.py"
                },
                "content": {
                    "type": "string",
                    "description": "文件内容",
                    "example": "# Hello World\nprint('hello')\n"
                }
            },
            "required": ["file_path", "content"],
            "errorMessage": {
                "file_path": "必须提供 file_path，如 file_path=\"E:\\项目目录\\src\\file.py\"",
                "content": "必须提供 content（文件内容字符串）"
            }
        }

    def execute(
        self,
        parameters: Dict[str, Any],
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> ToolResult:
        """执行写入操作"""
        # 参数验证（与 Read/Edit/Bash 工具一致）
        validation_error = self.validate_parameters(parameters)
        if validation_error:
            return ToolResult(success=False, output="", error=validation_error)

        file_path = parameters.get("file_path", "")
        content = parameters.get("content", "")

        # 使用 PathManager 统一路径解析（含安全边界校验）
        pm = get_path_manager()
        file_path, boundary_ok = pm.resolve_safe(file_path)
        if not boundary_ok:
            return ToolResult(
                success=False, output="",
                error=f"路径越界: {file_path} 不在操作根目录 {pm.active_path} 下，禁止访问"
            )

        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 更新文件缓存
            cache_result = file_cache.apply_write(file_path, content)

            # 语法检查（支持多种文件类型）
            is_valid, syntax_warning = check_syntax(content, file_path)

            # 构建输出（语法警告更显眼）
            if syntax_warning:
                output_msg = f"写入成功: {file_path} ({len(content)} 字符)\n\n【语法警告】{syntax_warning}\n建议：检查并修正语法错误后再继续。"
            else:
                output_msg = f"写入成功: {file_path} ({len(content)} 字符)"

            # 构建终端显示（卡片式）
            display_output = self._build_terminal_display(path, content, is_valid, syntax_warning)

            return ToolResult(
                success=True,
                output=output_msg,
                display_output=display_output,
                summary=f"Write {path.name} ({len(content)} chars)",
                metadata={
                    "file_path": str(path.absolute()),
                    "size": len(content),
                    "lines": content.count('\n') + 1,
                    "syntax_valid": is_valid,
                    "cache_version": cache_result.get("version", 1),
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足，无法写入: {file_path}")
        except FileNotFoundError:
            return ToolResult(success=False, output="", error=f"无法创建目录或路径无效: {file_path}")
        except OSError as e:
            return ToolResult(success=False, output="", error=f"系统错误: {e.strerror or str(e)} ({file_path})")
        except UnicodeEncodeError as e:
            return ToolResult(success=False, output="", error=f"编码错误: 内容包含无法编码的字符 ({e})")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"写入失败: {type(e).__name__}: {str(e)}")

    def _build_terminal_display(self, path: Path, content: str, is_valid: bool, syntax_warning: str = None) -> str:
        """构建终端显示（Rich markup）"""
        # 确定状态
        if is_valid:
            status = "created"
            status_color = COLORS['success']
            status_icon = ICONS.get('success', '✓')
        else:
            status = "warning"
            status_color = COLORS['warning']
            status_icon = ICONS.get('warning', '⚠')

        # 文件信息
        lines = content.count('\n') + 1
        size_str = format_size(len(content))
        file_icon = get_file_icon(str(path))

        parts = []
        # 开头空行
        parts.append("")
        # 标题行
        parts.append(f"[bold]{ICONS.get('write', '✏️')} Write:[/] [cyan]{escape(path.name)}[/] [dim]\\[{status}] ({lines} lines, {size_str})[/]")
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

        # 语法警告
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