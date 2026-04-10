"""Edit 工具 - 编辑文件（精确匹配，集成缓存，语法检查）

v2.8.8 重构要点：
1. 移除模糊匹配 - 只保留精确匹配，逼模型认真复制原文
2. 移除 lines 模式 - 行号模式对国产模型太危险
3. 加强多处匹配处理 - 要求添加更多上下文，不提供候选选择
4. 简化错误反馈 - 更明确的操作步骤指导
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from ..base import Tool, ToolResult
from ..file_cache import file_cache
from ..syntax_checker import check_syntax
from claude_code.utils.paths import resolve_workplace_path
from claude_code.ui.theme import COLORS, ICONS
from rich.markup import escape


class EditTool(Tool):
    """编辑文件工具（精确匹配模式）

    核心设计原则：
    - 只做精确匹配，不接受模糊匹配
    - 多处匹配时要求添加更多上下文，不自动选择
    - 错误反馈清晰明确，提供具体操作步骤
    """
    name = "Edit"
    description = (
        "精确替换文件内容。必须提供 old_string（要替换的原文）和 new_string（新内容）。\n"
        "\n"
        "重要规则：\n"
        "1. old_string 必须**完全精确匹配**文件中的内容，包括缩进、空格、换行\n"
        "2. 如果 old_string 在文件中出现多次，必须添加更多上下文使其唯一\n"
        "3. 操作前应先用 Read 工具查看文件内容，复制精确的原文\n"
        "\n"
        "不要猜测或简化 old_string，必须从 Read 结果中精确复制。"
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义（简化版，移除 lines 模式）"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "old_string": {
                    "type": "string",
                    "description": "要替换的原文（必须从 Read 结果中精确复制，包含正确的缩进和换行）"
                },
                "new_string": {
                    "type": "string",
                    "description": "替换后的新内容"
                }
            },
            "required": ["file_path", "old_string", "new_string"]
        }

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行编辑操作（精确匹配模式）"""
        # 参数验证（与 Read/Bash 工具一致）
        validation_error = self.validate_parameters(parameters)
        if validation_error:
            return ToolResult(success=False, output="", error=validation_error)

        file_path = parameters.get("file_path", "")
        old_string = parameters.get("old_string", "")
        new_string = parameters.get("new_string", "")

        file_path = resolve_workplace_path(file_path)

        try:
            path = Path(file_path)
            if not path.exists():
                return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")

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

            # 单处匹配，执行替换
            start_pos = positions[0]
            end_pos = start_pos + len(old_string)
            new_content = original_content[:start_pos] + new_string + original_content[end_pos:]

            # 写入文件
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
            return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")
        except OSError as e:
            return ToolResult(success=False, output="", error=f"系统错误: {e.strerror or str(e)} ({file_path})")
        except UnicodeDecodeError as e:
            return ToolResult(success=False, output="", error=f"编码错误: 文件包含无法解码的字符 ({e})")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"编辑失败: {type(e).__name__}: {str(e)}")

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

    def _build_no_match_error(
        self, content: str, old_string: str, file_path: str
    ) -> ToolResult:
        """构建无匹配时的错误信息（提供清晰的指导）"""
        content_lines = content.splitlines()
        old_lines = old_string.splitlines()

        # 尝试找到最相似的行（仅用于提示，不用于匹配）
        similar_info = self._find_similar_lines_hint(content_lines, old_lines)

        error_parts = [
            "❌ 未找到精确匹配",
            "",
            f"文件: {Path(file_path).name}",
            f"查找内容长度: {len(old_string)} 字符, {len(old_lines)} 行",
            "",
            "精确匹配要求 old_string 与文件内容**完全一致**，包括：",
            "- 缩进（空格/tab）",
            "- 换行符",
            "- 注释和空行",
            "",
        ]

        if similar_info:
            error_parts.append("🔍 文件中相似的代码位置：")
            error_parts.append(similar_info)
            error_parts.append("")

        error_parts.extend([
            "💡 请按以下步骤操作：",
            "",
            "1. 使用 Read 工具重新读取文件:",
            f"   Read {{\"file_path\": \"{file_path}\"}}",
            "",
            "2. 从 Read 结果中**精确复制**要替换的代码块",
            "   - 包含完整缩进",
            "   - 包含前后各 2-3 行上下文（确保唯一性）",
            "",
            "3. 使用复制的内容作为 old_string 参数",
            "",
            "⚠️ 不要猜测或简化代码，必须精确复制原文！",
        ])

        return ToolResult(
            success=False,
            output="",
            error='\n'.join(error_parts)
        )

    def _build_multiple_matches_error(
        self, content: str, old_string: str, positions: List[int]
    ) -> ToolResult:
        """构建多处匹配时的错误信息（要求添加上下文）"""
        content_lines = content.splitlines()
        old_lines = old_string.splitlines()

        # 计算所有匹配位置的行号
        match_lines = []
        for pos in positions[:5]:  # 只显示前 5 个
            line_num = content[:pos].count('\n') + 1
            match_lines.append(line_num)

        error_parts = [
            "⚠️ 发现多处匹配",
            "",
            f"匹配数量: {len(positions)} 处",
            f"匹配内容长度: {len(old_lines)} 行",
            "",
            "匹配位置（行号）:",
        ]

        for i, line_num in enumerate(match_lines):
            end_line = line_num + len(old_lines) - 1
            error_parts.append(f"  {i+1}. 第 {line_num}-{end_line} 行")

        if len(positions) > 5:
            error_parts.append(f"  ... 还有 {len(positions) - 5} 处")

        error_parts.extend([
            "",
            "💡 请添加更多上下文使 old_string 唯一：",
            "",
            "方法：在 old_string 前后各添加 2-3 行代码",
            "",
            "示例（假设要替换第 10 行）：",
            "",
            "❌ 错误做法（只复制单行）：",
            "old_string = \"def hello():\"",
            "",
            "✅ 正确做法（添加上下文）：",
            "old_string = \"\"",
            "# 前面的上下文",
            "def hello():",
            "    pass  # 要替换的行",
            "# 后面的上下文",
            "\"\"",
            "",
            "这样 old_string 只会匹配一处，替换成功。",
        ])

        return ToolResult(
            success=False,
            output="",
            error='\n'.join(error_parts)
        )

    def _find_similar_lines_hint(
        self, content_lines: List[str], old_lines: List[str], max_hints: int = 3
    ) -> str:
        """查找文件中与 old_string 最相似的代码位置（仅用于提示）"""
        if not old_lines:
            return ""

        # 取 old_string 的首行作为关键词
        first_line = old_lines[0].strip()
        if not first_line:
            if len(old_lines) > 1:
                first_line = old_lines[1].strip()
            else:
                return ""

        # 搜索包含关键词的行
        hints = []
        for i, line in enumerate(content_lines):
            if first_line in line:
                # 提取该位置前后几行作为上下文
                start = max(0, i - 2)
                end = min(len(content_lines), i + len(old_lines) + 2)

                hint_lines = []
                for j in range(start, end):
                    line_num = j + 1
                    prefix = "  >>> " if j == i else "      "
                    hint_lines.append(f"{prefix}{line_num:4d} | {self._truncate_line(content_lines[j], 50)}")

                hints.append(f"\n位置 {len(hints) + 1}（第 {i+1} 行附近）：\n" + '\n'.join(hint_lines))

                if len(hints) >= max_hints:
                    break

        return '\n'.join(hints) if hints else ""

    def get_security_context(self) -> Dict[str, Any]:
        """返回安全上下文"""
        return {
            "is_sensitive": True,
            "paths": [self.parameters.get("file_path", "")],
            "command_preview": ""
        }

    # ============================================================
    # 模型输出（纯文本）
    # ============================================================

    def _build_model_output(
        self, path, old_string, new_string, start_line, version, reference, syntax_warning=None
    ) -> str:
        """给模型的纯文本输出"""
        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()

        parts = []
        parts.append(f"✓ Edit 成功: {path.name}")
        parts.append(f"  版本: v{version}")
        parts.append(f"  位置: 第 {start_line} 行")
        parts.append(f"  变化: -{len(old_lines)} 行, +{len(new_lines)} 行")
        parts.append("")

        # 简洁 diff
        for line in old_lines:
            parts.append(f"- {line}")
        for line in new_lines:
            parts.append(f"+ {line}")

        if syntax_warning:
            parts.append("")
            parts.append(f"⚠️ 语法警告: {syntax_warning}")

        return '\n'.join(parts)

    # ============================================================
    # 终端显示（Rich markup）
    # ============================================================

    def _build_terminal_display(
        self, path, old_string, new_string, original_content, new_content,
        start_line, version, reference, syntax_warning=None
    ) -> str:
        """给终端的统一格式 diff 显示"""
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
        before_start = max(0, start_line - 1 - context_lines)
        for i in range(before_start, start_line - 1):
            if i < len(original_lines):
                content = self._truncate_line(original_lines[i])
                result.append(f"     [dim]{i + 1:4d}[/]  [dim]{escape(content)}[/]")

        # 删除行（红色）
        for i, line in enumerate(old_lines):
            content = self._truncate_line(line)
            result.append(f"     [dim]{start_line + i:4d}[/]  [red]- {escape(content)}[/]")

        # 新增行（绿色）
        for i, line in enumerate(new_lines):
            content = self._truncate_line(line)
            result.append(f"     [dim]{start_line + i:4d}[/]  [green]+ {escape(content)}[/]")

        # 下文
        new_file_lines = new_content.splitlines()
        after_start_new = start_line + added_count
        for i in range(context_lines):
            line_num = after_start_new + i
            if line_num < len(new_file_lines):
                content = self._truncate_line(new_file_lines[line_num])
                result.append(f"     [dim]{line_num + 1:4d}[/]  [dim]{escape(content)}[/]")

        if syntax_warning:
            result.append("")
            result.append(f"[yellow]⚠ 语法警告:[/] {escape(syntax_warning[:100])}")

        return '\n'.join(result)

    def _truncate_line(self, line: str, max_len: int = 60) -> str:
        """截断过长的行"""
        if len(line) > max_len:
            return line[:max_len] + "..."
        return line

    def is_read_only(self) -> bool:
        return False

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"

        old_string = parameters.get("old_string")
        if not old_string:
            return "缺少 old_string 参数"

        # new_string 允许为空（删除内容）

        return None