"""Edit 工具 - 编辑文件（双模式：精确匹配 + 行号范围，集成缓存，语法检查）

v2.8.21 重构要点：
1. 新增行号范围模式（start_line/end_line）— 替换指定行范围，无需精确复制原文
2. 保留精确匹配模式（old_string/new_string）— 短文本精确替换
3. 行号模式返回被替换的原始内容，供 AI 确认
4. 两种模式互斥，根据参数自动选择
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
from ..base import Tool, ToolResult
from ..file_cache import file_cache
from ..syntax_checker import check_syntax
from claude_code.core.path_manager import get_path_manager
from claude_code.ui.theme import COLORS, ICONS
from rich.markup import escape


class EditTool(Tool):
    """编辑文件工具（双模式：精确匹配 + 行号范围）

    核心设计原则：
    - 精确匹配模式：old_string 必须完全匹配，适合短文本替换
    - 行号范围模式：指定 start_line/end_line，适合大块替换，无需复制原文
    - 行号模式返回被替换的原始内容，供 AI 确认替换正确
    - 两种模式互斥，根据参数自动选择
    """
    name = "Edit"
    description = (
        "替换文件内容。支持两种模式（互斥，根据参数自动选择）：\n"
        "\n"
        "模式 1 — 精确匹配（默认）：\n"
        "  提供 old_string + new_string，old_string 必须完全精确匹配文件内容。\n"
        "  适合短文本替换（1-5行）。长文本建议用行号模式。\n"
        "\n"
        "模式 2 — 行号范围：\n"
        "  提供 start_line + end_line + new_string，替换指定行范围的内容。\n"
        "  适合大块替换（5行以上），无需精确复制原文，直接用 Read 返回的行号定位。\n"
        "  替换结果会返回被替换的原始内容，供确认是否正确。\n"
        "\n"
        "重要：必须使用绝对路径，如 file_path=\"E:\\项目目录\\src\\file.py\"\n"
        "相对路径会自动基于操作根目录解析为绝对路径\n"
        "不要猜测或简化 old_string，必须从 Read 结果中精确复制。"
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
                "old_string": {
                    "type": "string",
                    "description": "要替换的原文（精确匹配模式）。从 Read 结果中精确复制，包括缩进、空格、换行",
                    "example": "print('hello')"
                },
                "new_string": {
                    "type": "string",
                    "description": "替换后的新内容",
                    "example": "print('world')"
                },
                "start_line": {
                    "type": "integer",
                    "description": "行号范围模式：起始行号（从 1 开始，含）。与 end_line 一起使用，替代 old_string",
                    "example": 10
                },
                "end_line": {
                    "type": "integer",
                    "description": "行号范围模式：结束行号（含）。与 start_line 一起使用，替代 old_string",
                    "example": 15
                }
            },
            "required": ["file_path", "new_string"],
            "errorMessage": {
                "file_path": "必须提供 file_path，如 file_path=\"E:\\项目目录\\src\\file.py\"",
                "new_string": "必须提供 new_string（替换后的新内容，可为空字符串表示删除）"
            }
        }

    def execute(
        self,
        parameters: Dict[str, Any],
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> ToolResult:
        """执行编辑操作（自动选择精确匹配模式或行号范围模式）"""
        # 参数验证
        validation_error = self.validate_parameters(parameters)
        if validation_error:
            return ToolResult(success=False, output="", error=validation_error)

        file_path = parameters.get("file_path", "")
        new_string = parameters.get("new_string", "")

        # 使用 PathManager 统一路径解析（含安全边界校验）
        pm = get_path_manager()
        file_path, boundary_ok = pm.resolve_safe(file_path)
        if not boundary_ok:
            return ToolResult(
                success=False, output="",
                error=f"路径越界: {file_path} 不在操作根目录 {pm.active_path} 下，禁止访问"
            )

        # 判断模式：有 start_line/end_line → 行号范围模式，否则 → 精确匹配模式
        start_line = parameters.get("start_line")
        end_line = parameters.get("end_line")

        if start_line is not None and end_line is not None:
            return self._execute_line_range_mode(file_path, start_line, end_line, new_string, pm)
        else:
            old_string = parameters.get("old_string", "")
            return self._execute_exact_match_mode(file_path, old_string, new_string, pm)

    # ============================================================
    # 模式 1：精确匹配
    # ============================================================

    def _execute_exact_match_mode(
        self, file_path: str, old_string: str, new_string: str, pm
    ) -> ToolResult:
        """精确匹配模式执行"""
        try:
            path = Path(file_path)
            if not path.exists():
                # 文件不存在时，自动搜索同名文件
                return self._handle_file_not_found(file_path, pm)

            with open(path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            # ============================================================
            # 精确匹配（不做模糊匹配）
            # ============================================================
            positions = self._find_exact_matches(original_content, old_string)

            if not positions:
                # 精确匹配失败，返回清晰的错误指导
                return self._build_no_match_error(original_content, old_string, file_path)

            match_count = len(positions)

            if match_count > 1:
                # 多处匹配，要求添加上下文
                return self._build_multiple_matches_error(
                    original_content, old_string, positions
                )

            # ============================================================
            # 执行替换
            # ============================================================
            start_pos = positions[0]
            new_content = original_content[:start_pos] + new_string + original_content[start_pos + len(old_string):]

            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # 更新缓存
            cache_result = file_cache.apply_write(file_path, new_content)
            version = cache_result["version"]
            reference = cache_result["reference"]

            # 计算起始行号
            start_line = original_content[:start_pos].count('\n') + 1

            # 语法检查（仅警告，不阻止）
            is_valid, syntax_warning = check_syntax(new_content, file_path)

            output = self._build_model_output(
                path, old_string, new_string, start_line, version, reference, syntax_warning
            )
            display_output = self._build_terminal_display(
                path, old_string, new_string, original_content, new_content,
                start_line, version, reference, syntax_warning
            )

            return ToolResult(
                success=True,
                output=output,
                display_output=display_output,
                summary=f"Edit {path.name}",
                metadata={
                    "file_path": str(path.absolute()),
                    "old_length": len(old_string),
                    "new_length": len(new_string),
                    "start_line": start_line,
                    "cache_version": version,
                    "cache_reference": reference,
                    "syntax_valid": is_valid,
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足，无法写入: {file_path}")
        except FileNotFoundError:
            return self._handle_file_not_found(file_path, pm)
        except OSError as e:
            return ToolResult(success=False, output="", error=f"系统错误: {e.strerror or str(e)} ({file_path})")
        except UnicodeDecodeError as e:
            return ToolResult(success=False, output="", error=f"编码错误: 文件包含无法解码的字符 ({e})")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"编辑失败: {type(e).__name__}: {str(e)}")

    # ============================================================
    # 模式 2：行号范围
    # ============================================================

    def _execute_line_range_mode(
        self, file_path: str, start_line: int, end_line: int, new_string: str, pm
    ) -> ToolResult:
        """行号范围模式执行"""
        try:
            path = Path(file_path)
            if not path.exists():
                return self._handle_file_not_found(file_path, pm)

            with open(path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            original_lines = original_content.splitlines()
            total_lines = len(original_lines)

            # 行号范围校验
            if start_line < 1:
                return ToolResult(
                    success=False, output="",
                    error=f"start_line 必须 >= 1，当前值: {start_line}"
                )
            if end_line < start_line:
                return ToolResult(
                    success=False, output="",
                    error=f"end_line 必须 >= start_line，当前: start_line={start_line}, end_line={end_line}"
                )
            if start_line > total_lines:
                return ToolResult(
                    success=False, output="",
                    error=f"start_line={start_line} 超出文件总行数 {total_lines}"
                )

            # 实际结束行（不超过文件末尾）
            actual_end = min(end_line, total_lines)

            # 提取被替换的原始内容（供 AI 确认）
            replaced_lines = original_lines[start_line - 1 : actual_end]
            old_string = '\n'.join(replaced_lines)

            # 执行替换
            new_lines = new_string.splitlines()
            result_lines = (
                original_lines[: start_line - 1]   # 替换范围之前
                + new_lines                         # 新内容
                + original_lines[actual_end:]       # 替换范围之后
            )
            new_content = '\n'.join(result_lines)

            # 如果原文件末尾有换行，保留
            if original_content.endswith('\n') and not new_content.endswith('\n'):
                new_content += '\n'

            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # 更新缓存
            cache_result = file_cache.apply_write(file_path, new_content)
            version = cache_result["version"]
            reference = cache_result["reference"]

            # 语法检查
            is_valid, syntax_warning = check_syntax(new_content, file_path)

            # 构建输出：包含被替换的原始内容，供 AI 确认
            output = self._build_line_range_model_output(
                path, start_line, actual_end, old_string, new_string,
                version, reference, syntax_warning
            )
            display_output = self._build_line_range_terminal_display(
                path, start_line, actual_end, old_string, new_string,
                version, reference, syntax_warning
            )

            return ToolResult(
                success=True,
                output=output,
                display_output=display_output,
                summary=f"Edit {path.name} (lines {start_line}-{actual_end})",
                metadata={
                    "file_path": str(path.absolute()),
                    "start_line": start_line,
                    "end_line": actual_end,
                    "old_length": len(old_string),
                    "new_length": len(new_string),
                    "replaced_lines": len(replaced_lines),
                    "cache_version": version,
                    "cache_reference": reference,
                    "syntax_valid": is_valid,
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足，无法写入: {file_path}")
        except FileNotFoundError:
            return self._handle_file_not_found(file_path, pm)
        except OSError as e:
            return ToolResult(success=False, output="", error=f"系统错误: {e.strerror or str(e)} ({file_path})")
        except UnicodeDecodeError as e:
            return ToolResult(success=False, output="", error=f"编码错误: 文件包含无法解码的字符 ({e})")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"编辑失败: {type(e).__name__}: {str(e)}")

    # ============================================================
    # 精确匹配辅助
    # ============================================================

    def _find_exact_matches(self, content: str, old_string: str) -> List[int]:
        """精确匹配：查找所有完全匹配的位置

        Returns:
            匹配起始位置的字符索引列表
        """
        positions = []
        start = 0
        while True:
            pos = content.find(old_string, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        return positions

    def _build_no_match_error(self, content: str, old_string: str, file_path: str) -> ToolResult:
        """精确匹配失败时的错误反馈（含上下文指导）"""
        # 提供行号模式建议
        line_count = old_string.count('\n') + 1
        mode_hint = ""
        if line_count > 5:
            mode_hint = (
                "\n\n💡 提示：old_string 超过 5 行，建议改用行号范围模式：\n"
                "  提供 start_line 和 end_line 参数替代 old_string，无需精确复制原文。\n"
                "  例如: start_line=10, end_line=20, new_string=\"新内容\""
            )

        # 尝试部分匹配，给出最接近的位置
        first_line = old_string.split('\n')[0].strip()
        if first_line and len(first_line) >= 10:
            for i, line in enumerate(content.split('\n'), 1):
                if first_line in line:
                    return ToolResult(
                        success=False, output="",
                        error=(
                            f"精确匹配失败: old_string 在文件中未找到完全匹配。\n"
                            f"但找到部分匹配在第 {i} 行附近。\n\n"
                            f"可能原因：\n"
                            f"1. 缩进不一致（空格 vs tab）\n"
                            f"2. 行尾空格或换行符差异\n"
                            f"3. 复制时遗漏了部分内容\n\n"
                            f"建议：\n"
                            f"1. 重新 Read 文件，精确复制要替换的原文（包括缩进）\n"
                            f"2. 或缩小 old_string 范围，只匹配最关键的一两行\n"
                            f"3. 或使用行号范围模式: start_line={i}, end_line={i + line_count - 1}"
                            f"{mode_hint}"
                        )
                    )

        return ToolResult(
            success=False, output="",
            error=(
                f"精确匹配失败: old_string 在文件中未找到。\n\n"
                f"建议：\n"
                f"1. 重新 Read 文件，精确复制要替换的原文（包括缩进）\n"
                f"2. 或缩小 old_string 范围，只匹配最关键的一两行"
                f"{mode_hint}"
            )
        )

    def _build_multiple_matches_error(
        self, content: str, old_string: str, positions: List[int]
    ) -> ToolResult:
        """多处匹配时的错误反馈"""
        # 计算每个匹配的行号
        match_lines = []
        for pos in positions[:5]:  # 最多显示 5 个
            line_num = content[:pos].count('\n') + 1
            match_lines.append(line_num)

        lines_info = ', '.join(str(l) for l in match_lines)
        if len(positions) > 5:
            lines_info += f' 等 {len(positions)} 处'

        # 提供行号模式建议
        first_line = match_lines[0]
        line_count = old_string.count('\n') + 1

        return ToolResult(
            success=False, output="",
            error=(
                f"多处匹配: old_string 在文件中匹配到 {len(positions)} 处（第 {lines_info} 行）。\n"
                f"必须添加更多上下文使匹配唯一。\n\n"
                f"建议：\n"
                f"1. 扩大 old_string 范围，包含更多上下文行使其唯一\n"
                f"2. 或使用行号范围模式: start_line={first_line}, end_line={first_line + line_count - 1}"
            )
        )

    # ============================================================
    # 模型输出（精确匹配模式）
    # ============================================================

    def _build_model_output(
        self, path, old_string, new_string, start_line, version, reference, syntax_warning=None
    ) -> str:
        """构建给模型的纯文本输出（精确匹配模式）"""
        parts = []
        parts.append(f"File: {path.name}")
        parts.append(f"Path: {path}")
        parts.append(f"Cache: [{reference}]")
        parts.append(f"Mode: exact_match")
        parts.append(f"Start line: {start_line}")
        parts.append("")

        # 简洁 diff
        for line in old_string.splitlines():
            parts.append(f"- {line}")
        for line in new_string.splitlines():
            parts.append(f"+ {line}")

        if syntax_warning:
            parts.append("")
            parts.append(f"⚠️ 语法警告: {syntax_warning}")

        return '\n'.join(parts)

    # ============================================================
    # 模型输出（行号范围模式）
    # ============================================================

    def _build_line_range_model_output(
        self, path, start_line, end_line, old_string, new_string,
        version, reference, syntax_warning=None
    ) -> str:
        """构建给模型的纯文本输出（行号范围模式）

        关键：返回被替换的原始内容，供 AI 确认替换正确
        """
        parts = []
        parts.append(f"File: {path.name}")
        parts.append(f"Path: {path}")
        parts.append(f"Cache: [{reference}]")
        parts.append(f"Mode: line_range")
        parts.append(f"Replaced lines: {start_line}-{end_line}")
        parts.append("")

        # 被替换的原始内容（供 AI 确认）
        parts.append("▼ 被替换的原始内容:")
        for i, line in enumerate(old_string.splitlines(), start_line):
            parts.append(f"  {i:5d} | {line}")
        parts.append("")

        # 新内容
        parts.append("▼ 替换后的新内容:")
        for i, line in enumerate(new_string.splitlines(), start_line):
            parts.append(f"  {i:5d} | {line}")

        if syntax_warning:
            parts.append("")
            parts.append(f"⚠️ 语法警告: {syntax_warning}")

        return '\n'.join(parts)

    # ============================================================
    # 终端显示（精确匹配模式）
    # ============================================================

    def _build_terminal_display(
        self, path, old_string, new_string, original_content, new_content,
        start_line, version, reference, syntax_warning=None
    ) -> str:
        """给终端的统一格式 diff 显示（精确匹配模式）"""
        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()
        original_lines = original_content.splitlines()

        context_lines = 2
        added_count = len(new_lines) - len(old_lines)

        result = []
        result.append("")
        line_change = f"-{len(old_lines)} lines, +{len(new_lines)} lines"
        result.append(f"[bold]{ICONS.get('edit', '✎')} Edit:[/] [cyan]{escape(str(path.name))}[/] [dim]\\[{reference}] ({line_change})[/]")
        result.append(f"[dim]{'─' * 50}[/]")

        # 上文
        for i in range(context_lines):
            line_num = start_line - context_lines + i
            if 0 <= line_num - 1 < len(original_lines):
                content = self._truncate_line(original_lines[line_num - 1])
                result.append(f"[dim]{line_num:4d}[/]  [dim]{escape(content)}[/]")

        # 删除的行
        for i, line in enumerate(old_lines):
            line_num = start_line + i
            content = self._truncate_line(line)
            result.append(f"[red]{line_num:4d}[/]  [red]{escape(content)}[/]")

        # 添加的行
        for i, line in enumerate(new_lines):
            line_num = start_line + i
            content = self._truncate_line(line)
            result.append(f"[green]{line_num:4d}[/]  [green]{escape(content)}[/]")

        # 下文
        after_start_new = start_line + added_count
        for i in range(context_lines):
            line_num = after_start_new + i
            new_file_lines = new_content.splitlines()
            if line_num < len(new_file_lines):
                content = self._truncate_line(new_file_lines[line_num])
                result.append(f"[dim]{line_num + 1:4d}[/]  [dim]{escape(content)}[/]")

        if syntax_warning:
            result.append("")
            result.append(f"[yellow]⚠ 语法警告:[/] {escape(syntax_warning[:100])}")

        return '\n'.join(result)

    # ============================================================
    # 终端显示（行号范围模式）
    # ============================================================

    def _build_line_range_terminal_display(
        self, path, start_line, end_line, old_string, new_string,
        version, reference, syntax_warning=None
    ) -> str:
        """给终端的 diff 显示（行号范围模式）"""
        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()

        result = []
        result.append("")
        line_change = f"-{len(old_lines)} lines, +{len(new_lines)} lines"
        result.append(
            f"[bold]{ICONS.get('edit', '✎')} Edit:[/] [cyan]{escape(str(path.name))}[/] "
            f"[dim]\\[{reference}] lines {start_line}-{end_line} ({line_change})[/]"
        )
        result.append(f"[dim]{'─' * 50}[/]")

        # 删除的行（红色）
        for i, line in enumerate(old_lines):
            line_num = start_line + i
            content = self._truncate_line(line)
            result.append(f"[red]{line_num:4d}[/]  [red]{escape(content)}[/]")

        # 添加的行（绿色）
        for i, line in enumerate(new_lines):
            line_num = start_line + i
            content = self._truncate_line(line)
            result.append(f"[green]{line_num:4d}[/]  [green]{escape(content)}[/]")

        if syntax_warning:
            result.append("")
            result.append(f"[yellow]⚠ 语法警告:[/] {escape(syntax_warning[:100])}")

        return '\n'.join(result)

    def _truncate_line(self, line: str, max_len: int = 60) -> str:
        """截断过长的行"""
        if len(line) > max_len:
            return line[:max_len] + "..."
        return line

    # ============================================================
    # 文件不存在时的自动搜索回退
    # ============================================================

    def _handle_file_not_found(self, file_path: str, pm) -> ToolResult:
        """文件不存在时的处理：自动搜索同名文件并给出精确路径建议"""
        from claude_code.utils.paths import format_file_not_found_error
        error_msg = format_file_not_found_error(file_path, pm.active_path)
        return ToolResult(success=False, output="", error=error_msg)

    # ============================================================
    # 工具属性
    # ============================================================

    def is_read_only(self) -> bool:
        return False

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数（支持两种模式）"""
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"

        new_string = parameters.get("new_string")
        if new_string is None:
            return "缺少 new_string 参数"

        # 判断模式
        start_line = parameters.get("start_line")
        end_line = parameters.get("end_line")
        old_string = parameters.get("old_string")

        has_line_range = start_line is not None or end_line is not None
        has_old_string = old_string is not None

        if has_line_range:
            # 行号范围模式：start_line 和 end_line 必须同时提供
            if start_line is None or end_line is None:
                return "行号范围模式需要同时提供 start_line 和 end_line"
            try:
                sl = int(start_line)
                el = int(end_line)
            except (ValueError, TypeError):
                return "start_line 和 end_line 必须是整数"
            if sl < 1:
                return "start_line 必须 >= 1"
            if el < sl:
                return "end_line 必须 >= start_line"
            # 行号范围模式不需要 old_string（如果提供了则忽略）
        else:
            # 精确匹配模式：old_string 必填
            if not old_string:
                return "缺少 old_string 参数（或改用行号范围模式：提供 start_line 和 end_line）"

        return None

    def get_security_context(self) -> Dict[str, Any]:
        """返回安全上下文"""
        return {
            "is_sensitive": True,
            "paths": [self.parameters.get("file_path", "")],
            "command_preview": ""
        }
