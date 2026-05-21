"""Grep 工具 - 按内容搜索文件"""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from ..base import Tool, ToolResult
from claude_code.core.path_manager import get_path_manager
from claude_code.utils.paths import get_file_icon, EXCLUDED_DIRS
from claude_code.ui.theme import COLORS, ICONS
from rich.markup import escape


class GrepTool(Tool):
    """文件内容搜索工具"""
    name = "Grep"
    description = (
        "在文件中搜索匹配正则表达式的内容。返回匹配的行及其上下文。\n"
        "建议使用精确模式减少匹配数量。context 参数可显示匹配行的上下文行数，减少额外 Read 操作。"
    )

    MAX_FILE_SIZE = 1 * 1024 * 1024
    MAX_MATCHES = 30
    PREVIEW_WIDTH = 80

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "正则表达式模式",
                    "example": "def my_function"
                },
                "path": {
                    "type": "string",
                    "description": "搜索的文件或目录路径（默认使用操作根目录）",
                    "default": "."
                },
                "type": {
                    "type": "string",
                    "description": "文件类型过滤，如 py, js, md（可选）"
                },
                "-i": {
                    "type": "boolean",
                    "description": "忽略大小写",
                    "default": False
                },
                "output_mode": {
                    "type": "string",
                    "description": "输出模式：content(显示内容) 或 files_with_matches(仅文件名)",
                    "default": "content"
                },
                "context": {
                    "type": "integer",
                    "description": "上下文行数：显示匹配行前后各 N 行（默认 0，不显示上下文）",
                    "default": 0
                }
            },
            "required": ["pattern"],
            "errorMessage": {
                "pattern": "必须提供 pattern（正则表达式），如 pattern=\"def my_function\""
            }
        }

    def execute(
        self,
        parameters: Dict[str, Any],
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> ToolResult:
        """执行搜索"""
        # 参数验证（与 Read/Edit/Bash 工具一致）
        validation_error = self.validate_parameters(parameters)
        if validation_error:
            return ToolResult(success=False, output="", error=validation_error)

        pattern = parameters.get("pattern", "")
        search_path = parameters.get("path", ".")
        file_type = parameters.get("type")
        ignore_case = parameters.get("-i", False)
        output_mode = parameters.get("output_mode", "content")
        context_lines = max(0, int(parameters.get("context", 0)))

        # 使用 PathManager 统一路径解析
        pm = get_path_manager()
        search_path, _ = pm.resolve_safe(search_path)

        try:
            flags = re.DOTALL
            if ignore_case:
                flags |= re.IGNORECASE
            regex = re.compile(pattern, flags)

            base_path = Path(search_path)
            if not base_path.exists():
                return ToolResult(
                    success=False, output="",
                    error=(
                        f"路径不存在: {search_path}\n"
                        f"ℹ 当前操作根目录: {pm.active_path}\n"
                        f"请确保路径在操作根目录下，如: path=\"{pm.active_path}\\src\""
                    )
                )

            # 收集文件时检查中断
            files_to_search = self._collect_files(base_path, file_type, interrupt_check)

            # 如果被中断，直接返回
            if files_to_search is None:
                return ToolResult(
                    success=False,
                    output="",
                    error="用户中断执行",
                    interrupted=True
                )

            all_matches = []
            matched_files = []

            for file_path in files_to_search:
                # 检查中断
                if interrupt_check and interrupt_check():
                    return ToolResult(
                        success=False,
                        output="",
                        error="用户中断执行",
                        interrupted=True
                    )

                matches = self._search_in_file(file_path, regex)
                if matches:
                    matched_files.append(file_path)
                    # 如果需要上下文，扩展匹配结果
                    if context_lines > 0:
                        matches = self._add_context_to_matches(file_path, matches, context_lines)
                    all_matches.extend(matches)
                    if len(all_matches) >= self.MAX_MATCHES:
                        break

            truncated = all_matches[:self.MAX_MATCHES]

            # 给模型的纯文本输出
            if output_mode == "files_with_matches":
                output = self._build_model_files_output(matched_files, pattern)
            else:
                output = self._build_model_content_output(truncated, pattern, len(all_matches))

            # 给终端的统一格式显示
            if not all_matches:
                output = f"No matches found for: {pattern}"
                display_output = f"[bold]{ICONS.get('grep', '◆')} Grep:[/] [cyan]\"{escape(pattern)}\"[/] [dim]\\[0 处匹配][/]"
            else:
                display_output = self._build_terminal_display(pattern, truncated, len(all_matches))

            return ToolResult(
                success=True,
                output=output,
                display_output=display_output,
                metadata={
                    "pattern": pattern,
                    "path": search_path,
                    "match_count": len(all_matches),
                    "file_count": len(matched_files)
                }
            )

        except re.error as e:
            return ToolResult(success=False, output="", error=f"正则表达式错误: {str(e)}\n下一步: 检查正则语法，或简化 pattern 后重试")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"搜索失败: {str(e)}\n下一步: 尝试缩小搜索范围(path参数)或使用更简单的 pattern")

    # ============================================================
    # 模型输出（纯文本）
    # ============================================================

    def _build_model_files_output(self, matched_files: List[Path], pattern: str) -> str:
        """给模型的文件列表输出"""
        parts = []
        parts.append(f"Grep: \"{pattern}\" found in {len(matched_files)} files")
        parts.append("")
        for f in matched_files:
            parts.append(f"  {f}")
        return '\n'.join(parts)

    def _build_model_content_output(self, matches: List[tuple], pattern: str, total: int) -> str:
        """给模型的内容输出（截断信息置于首行，确保压缩时不被裁掉）"""
        parts = []
        if total > self.MAX_MATCHES:
            parts.append(f"Grep: \"{pattern}\" — 共 {total} 条匹配，显示前 {self.MAX_MATCHES} 条")
        else:
            parts.append(f"Grep: \"{pattern}\" — {total} 条匹配")
        parts.append("")

        current_file = None
        prev_context_start = None
        prev_context_end = None

        for match in matches:
            file_path, line_num, line_content, is_match = match
            if file_path != current_file:
                parts.append("")
                parts.append(f"--- {file_path} ---")
                current_file = file_path
                prev_context_start = None
                prev_context_end = None

            if is_match:
                if prev_context_start is not None:
                    if prev_context_start == prev_context_end:
                        parts.append(f"    (上下文 L{prev_context_start})")
                    else:
                        parts.append(f"    (上下文 L{prev_context_start}-{prev_context_end})")
                    prev_context_start = None
                    prev_context_end = None
                parts.append(f"  ▸{line_num:5d} | {line_content}  ✎Edit(L{line_num})")
            else:
                parts.append(f"    {line_num:5d} | {line_content}")
                if prev_context_start is None:
                    prev_context_start = line_num
                prev_context_end = line_num

        return '\n'.join(parts)

    def _build_terminal_display(self, pattern: str, matches: List[tuple], total: int) -> str:

        """给终端的统一格式显示"""
        parts = []

        # 开头空行，与其他工具分隔
        parts.append("")
        # 标题行：◆ Grep: "pattern" [N 处匹配]
        parts.append(f"[bold]{ICONS.get('grep', '◆')} Grep:[/] [cyan]\"{escape(pattern)}\"[/] [dim]\\[{total} 处匹配][/]")

        # 匹配列表（2空格缩进）
        for i, match in enumerate(matches, 1):
            file_path, line_num, line_content = match[0], match[1], match[2]
            is_match = match[3] if len(match) > 3 else True
            # 截断过长的行
            display_line = line_content[:100] + "..." if len(line_content) > 100 else line_content
            if is_match:
                parts.append(f"  [dim]{i:>4}[/]  [dim]{escape(file_path)}:{line_num}:[/] {escape(display_line)}")
            else:
                parts.append(f"       [dim]{escape(file_path)}:{line_num}:[/] [dim]{escape(display_line)}[/]")

        return '\n'.join(parts)

    # ============================================================
    # 搜索逻辑
    # ============================================================

    def _collect_files(
        self,
        base_path: Path,
        file_type: Optional[str],
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> Optional[List[Path]]:
        """
        收集要搜索的文件

        Returns:
            文件列表，或 None（用户中断）
        """
        files = []

        if base_path.is_file():
            return [base_path]

        type_to_ext = {
            "py": [".py"],
            "js": [".js", ".jsx", ".mjs"],
            "ts": [".ts", ".tsx"],
            "java": [".java"],
            "go": [".go"],
            "rs": [".rs"],
            "c": [".c", ".h"],
            "cpp": [".cpp", ".hpp", ".cc"],
            "cs": [".cs"],
            "rb": [".rb"],
            "php": [".php"],
            "swift": [".swift"],
            "kt": [".kt"],
            "scala": [".scala"],
            "md": [".md"],
            "json": [".json"],
            "yaml": [".yaml", ".yml"],
            "xml": [".xml"],
            "html": [".html", ".htm"],
            "css": [".css", ".scss", ".sass"],
            "sh": [".sh", ".bash"],
            "sql": [".sql"],
        }

        extensions = type_to_ext.get(file_type, []) if file_type else None

        # 每遍历一定数量文件后检查中断
        check_interval = 50
        file_count = 0

        for path in base_path.rglob("*"):
            # 定期检查中断
            file_count += 1
            if interrupt_check and file_count % check_interval == 0 and interrupt_check():
                return None  # 用户中断

            if path.is_file():
                if self._should_exclude(path, base_path):
                    continue
                if path.stat().st_size > self.MAX_FILE_SIZE:
                    continue
                if self._is_binary(path):
                    continue
                if extensions and path.suffix not in extensions:
                    continue
                files.append(path)

        return files

        return files

    def _should_exclude(self, path: Path, base: Path) -> bool:
        """检查路径是否在排除目录下"""
        try:
            rel = path.relative_to(base)
        except ValueError:
            rel = path
        for part in rel.parts:
            if part in EXCLUDED_DIRS or part.endswith('.egg-info'):
                return True
        return False

    def _is_binary(self, path: Path) -> bool:
        """检查是否为二进制文件"""
        try:
            with open(path, 'rb') as f:
                chunk = f.read(8192)
                return b'\x00' in chunk
        except Exception:
            return True

    def _search_in_file(self, file_path: Path, regex: re.Pattern) -> List[tuple]:
        """在单个文件中搜索"""
        matches = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if regex.search(line):
                        matches.append((str(file_path), line_num, line.rstrip('\n\r'), True))
        except (UnicodeDecodeError, PermissionError):
            pass
        return matches

    def _add_context_to_matches(self, file_path: Path, matches: List[tuple], context_lines: int) -> List[tuple]:
        """为匹配结果添加上下文行

        Args:
            file_path: 文件路径
            matches: 原始匹配列表 [(file_path_str, line_num, line_content, is_match), ...]
            context_lines: 上下文行数

        Returns:
            包含上下文行的匹配列表，上下文行标记为 "context" 类型
        """
        if not matches or context_lines <= 0:
            return matches

        # 读取文件所有行
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
        except (UnicodeDecodeError, PermissionError):
            return matches

        # 收集需要显示的行号（匹配行 ± 上下文）
        result = []
        seen_lines = set()
        match_line_nums = {m[1] for m in matches}

        for match in matches:
            file_path_str, line_num, line_content = match[0], match[1], match[2]
            # 添加匹配行之前的上下文
            for ctx_num in range(max(1, line_num - context_lines), line_num):
                if ctx_num not in seen_lines:
                    seen_lines.add(ctx_num)
                    ctx_content = all_lines[ctx_num - 1].rstrip('\n\r') if ctx_num <= len(all_lines) else ""
                    is_match = ctx_num in match_line_nums
                    result.append((file_path_str, ctx_num, ctx_content, is_match))

            # 添加匹配行本身
            if line_num not in seen_lines:
                seen_lines.add(line_num)
                result.append((file_path_str, line_num, line_content, True))

            # 添加匹配行之后的上下文
            for ctx_num in range(line_num + 1, min(len(all_lines) + 1, line_num + context_lines + 1)):
                if ctx_num not in seen_lines:
                    seen_lines.add(ctx_num)
                    ctx_content = all_lines[ctx_num - 1].rstrip('\n\r')
                    is_match = ctx_num in match_line_nums
                    result.append((file_path_str, ctx_num, ctx_content, is_match))

        # 按行号排序
        result.sort(key=lambda x: x[1])
        return result

    # ============================================================
    # 工具属性
    # ============================================================

    def is_read_only(self) -> bool:
        return True

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        pattern = parameters.get("pattern")
        if not pattern:
            return "缺少 pattern 参数"
        try:
            re.compile(pattern, re.DOTALL)
        except re.error as e:
            return f"无效的正则表达式: {str(e)}\n下一步: 检查正则语法，或简化 pattern 后重试"
        return None
    
    def get_security_context(self) -> Dict[str, Any]:
        return {"is_sensitive": False, "paths": [], "command_preview": ""}