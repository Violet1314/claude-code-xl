"""Edit 工具 - 编辑文件（精确替换，集成缓存）"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import Tool, ToolResult
from ..file_cache import file_cache
from claude_code.utils.paths import resolve_workplace_path
from claude_code.ui.theme import COLORS
from rich.markup import escape

class EditTool(Tool):
    """编辑文件工具（带缓存）"""

    name = "Edit"
    description = "精确替换文件中的内容。编辑后文件缓存自动更新，无需重新读取。"

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "old_string": {
                    "type": "string",
                    "description": "要替换的原始内容（必须完全匹配）"
                },
                "new_string": {
                    "type": "string",
                    "description": "替换后的新内容"
                }
            },
            "required": ["file_path", "old_string", "new_string"]
        }

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行编辑操作"""
        file_path = parameters.get("file_path", "")
        old_string = parameters.get("old_string", "")
        new_string = parameters.get("new_string", "")

        if not file_path:
            return ToolResult(success=False, output="", error="缺少 file_path 参数")

        file_path = resolve_workplace_path(file_path)

        if not old_string:
            return ToolResult(success=False, output="", error="缺少 old_string 参数")

        try:
            path = Path(file_path)

            if not path.exists():
                return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")

            with open(path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            if old_string not in original_content:
                return ToolResult(
                    success=False, output="",
                    error="未找到要替换的内容。请确保 old_string 与文件中的内容完全一致。"
                )

            match_count = original_content.count(old_string)
            if match_count > 1:
                new_content = original_content.replace(old_string, new_string, 1)
            else:
                new_content = original_content.replace(old_string, new_string)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # 更新缓存
            cache_result = file_cache.apply_write(file_path, new_content)
            reference = cache_result.get("reference", "")
            version = cache_result.get("version", 0)

            # 给模型的纯文本输出
            output = self._build_model_output(
                path, old_string, new_string,
                original_content, new_content,
                reference, version, match_count
            )

            # 给终端的 Rich 显示
            display_output = self._build_terminal_display(
                path, old_string, new_string,
                original_content,  new_content,
                reference, version, match_count
            )

            return ToolResult(
                success=True,
                output=output,
                display_output=display_output,
                metadata={
                    "file_path": str(path.absolute()),
                    "old_length": len(old_string),
                    "new_length": len(new_string),
                    "match_count": match_count,
                    "cache_version": version,
                    "cache_reference": reference,
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足: {file_path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"编辑失败: {str(e)}")

    # ============================================================
    # 模型输出（纯文本）
    # ============================================================

    def _build_model_output(
        self, path, old_string, new_string,
        original_content, new_content,
        reference, version, match_count
    ) -> str:
        """给模型的纯文本输出"""
        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()
        start_line = self._find_start_line(original_content.splitlines(), old_string)

        parts = []
        parts.append(f"Edit: {path.name} - {reference} (v{version})")
        parts.append(f"  -{len(old_lines)} lines, +{len(new_lines)} lines at line {start_line}")
        parts.append("")

        # 简洁 diff
        for line in old_lines:
            parts.append(f"- {line}")
        for line in new_lines:
            parts.append(f"+ {line}")

        if match_count > 1:
            parts.append(f"\nWarning: {match_count} matches found, replaced first occurrence only.")

        return '\n'.join(parts)

    # ============================================================
    # 终端显示（Rich markup）
    # ============================================================

    def _build_terminal_display(
        self, path, old_string, new_string,
        original_content, new_content,
        reference, version, match_count
    ) -> str:
        """给终端的 diff 显示"""
        original_lines = original_content.splitlines()
        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()

        removed_count = len(old_lines)
        added_count = len(new_lines)
        start_line = self._find_start_line(original_lines, old_string)

        escaped_ref = escape(reference)

        result = []
        result.append(f"[bold green]Update[/]([cyan]{escape(str(path))}[/])")
        result.append(f"  [dim]  [/][green bold]+{added_count}[/] [red bold]-{removed_count}[/]  📌 [cyan]{escaped_ref}[/]")
        result.append("")

        context_lines = 2

        # 上文
        for i in range(max(0, start_line - context_lines - 1), start_line - 1):
            if i < len(original_lines):
                content = self._truncate_line(original_lines[i])
                result.append(f"     [dim]{i + 1:4d}[/]  [dim]{escape(content)}[/]")

        # 删除行
        for i, line in enumerate(old_lines):
            content = self._truncate_line(line)
            result.append(f"     [dim]{start_line + i:4d}[/]  [white on #b85450]- {escape(content)}[/]")

        # 新增行
        for i, line in enumerate(new_lines):
            content = self._truncate_line(line)
            result.append(f"     [dim]{start_line + i:4d}[/]  [white on #3d8c40]+ {escape(content)}[/]")

        # 下文
        new_file_lines = new_content.splitlines()
        after_start_new = start_line + added_count
        for i in range(context_lines):
            line_num = after_start_new + i
            if line_num < len(new_file_lines):
                content = self._truncate_line(new_file_lines[line_num])
                result.append(f"     [dim]{line_num + 1:4d}[/]  [dim]{escape(content)}[/]")

        if match_count > 1:
            result.append(f"\n[yellow]⚠️ 共 {match_count} 处匹配，已替换第 1 处[/]")

        return '\n'.join(result)

    # ============================================================
    # 辅助方法
    # ============================================================

    def _find_start_line(self, original_lines: List[str], old_string: str) -> int:
        """找到 old_string 在文件中的起始行号（1-based）"""
        old_lines = old_string.splitlines()
        if not old_lines:
            return 1

        # 精确匹配
        for i in range(len(original_lines) - len(old_lines) + 1):
            match = True
            for j, old_line in enumerate(old_lines):
                if i + j >= len(original_lines):
                    match = False
                    break
                if original_lines[i + j] != old_line:
                    match = False
                    break
            if match:
                return i + 1

        # 宽松匹配
        first_line_stripped = old_lines[0].strip()
        for i in range(len(original_lines) - len(old_lines) + 1):
            if original_lines[i].strip() == first_line_stripped:
                match = True
                for j, old_line in enumerate(old_lines):
                    if i + j >= len(original_lines):
                        match = False
                        break
                    if original_lines[i + j].strip() != old_line.strip():
                        match = False
                        break
                if match:
                    return i + 1

        return 1

    def _truncate_line(self, line: str, max_len: int = 60) -> str:
        """截断过长的行"""
        if len(line) > max_len:
            return line[:max_len] + "..."
        return line

    def is_read_only(self) -> bool:
        return False

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"
        old_string = parameters.get("old_string")
        if not old_string:
            return "缺少 old_string 参数"
        return None