"""Grep 工具 - 按内容搜索文件"""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import Tool, ToolResult
from claude_code.utils.paths import resolve_workplace_path
from claude_code.ui.theme import COLORS, ICONS


class GrepTool(Tool):
    """文件内容搜索工具"""

    name = "Grep"
    description = "在文件中搜索匹配正则表达式的内容。返回匹配的行及其上下文。建议使用精确模式减少匹配数量。"

    # 搜索限制
    MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB
    MAX_MATCHES = 30  # 最大匹配数（降低以节省 token）
    PREVIEW_WIDTH = 80  # 行内容预览宽度

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "正则表达式模式"
                },
                "path": {
                    "type": "string",
                    "description": "搜索的文件或目录路径",
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
                }
            },
            "required": ["pattern"]
        }

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行搜索"""
        pattern = parameters.get("pattern", "")
        search_path = parameters.get("path", ".")
        file_type = parameters.get("type")
        ignore_case = parameters.get("-i", False)
        output_mode = parameters.get("output_mode", "content")

        if not pattern:
            return ToolResult(success=False, output="", error="缺少 pattern 参数")

        # Workplace 隔离：相对路径重定向到 workplace 目录
        search_path = resolve_workplace_path(search_path)

        try:
            # 编译正则表达式
            flags = re.DOTALL
            if ignore_case:
                flags |= re.IGNORECASE
            regex = re.compile(pattern, flags)

            base_path = Path(search_path)
            if not base_path.exists():
                return ToolResult(success=False, output="", error=f"路径不存在: {search_path}")

            # 收集要搜索的文件
            files_to_search = self._collect_files(base_path, file_type)

            # 执行搜索
            all_matches = []
            matched_files = []

            for file_path in files_to_search:
                matches = self._search_in_file(file_path, regex)
                if matches:
                    matched_files.append(file_path)
                    all_matches.extend(matches)
                    if len(all_matches) >= self.MAX_MATCHES:
                        break

            # 格式化输出
            if output_mode == "files_with_matches":
                output = self._format_files_output(matched_files, pattern)
            else:
                output = self._format_content_output(all_matches[:self.MAX_MATCHES], pattern, len(all_matches))

            if not all_matches:
                output = f"🔍 未找到匹配: {pattern}"

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "pattern": pattern,
                    "path": search_path,
                    "match_count": len(all_matches),
                    "file_count": len(matched_files)
                }
            )

        except re.error as e:
            return ToolResult(success=False, output="", error=f"正则表达式错误: {str(e)}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"搜索失败: {str(e)}")

    def _collect_files(self, base_path: Path, file_type: Optional[str]) -> List[Path]:
        """收集要搜索的文件"""
        files = []

        if base_path.is_file():
            return [base_path]

        # 文件类型到扩展名的映射
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

        for path in base_path.rglob("*"):
            if path.is_file():
                # 跳过大文件
                if path.stat().st_size > self.MAX_FILE_SIZE:
                    continue
                # 跳过二进制文件
                if self._is_binary(path):
                    continue
                # 类型过滤
                if extensions and path.suffix not in extensions:
                    continue
                files.append(path)

        return files

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
                        matches.append((str(file_path), line_num, line.rstrip('\n\r')))
        except (UnicodeDecodeError, PermissionError):
            pass

        return matches

    def _format_files_output(self, matched_files: List[Path], pattern: str) -> str:
        """格式化文件列表输出"""
        lines = []

        # 卡片头部
        lines.append(f"[dim {COLORS['border_subtle']}]╭─[/] {ICONS.get('grep', '🔍')} [bold]Grep 结果[/]")
        lines.append(f"[dim {COLORS['border_subtle']}]│[/]")
        lines.append(f"[dim {COLORS['border_subtle']}]│[/] 搜索 [cyan]\"{pattern}\"[/] 找到 [bold]{len(matched_files)}[/] 个文件")

        if matched_files:
            lines.append(f"[dim {COLORS['border_subtle']}]│[/]")
            for f in matched_files[:15]:
                # 获取文件图标
                file_icon = self._get_file_icon(f.suffix.lower())
                lines.append(f"[dim {COLORS['border_subtle']}]│[/]   {file_icon} {f}")

            if len(matched_files) > 15:
                lines.append(f"[dim {COLORS['border_subtle']}]│[/]   [dim]... 还有 {len(matched_files) - 15} 个文件[/]")

        lines.append(f"[dim {COLORS['border_subtle']}]╰{'─' * 50}[/]")

        return '\n'.join(lines)

    def _format_content_output(self, matches: List[tuple], pattern: str, total: int) -> str:
        """格式化内容输出"""
        lines = []

        # 卡片头部
        lines.append(f"[dim {COLORS['border_subtle']}]╭─[/] {ICONS.get('grep', '🔍')} [bold]Grep 结果[/]")
        lines.append(f"[dim {COLORS['border_subtle']}]│[/]")
        lines.append(f"[dim {COLORS['border_subtle']}]│[/] 搜索 [cyan]\"{pattern}\"[/] 找到 [bold]{total}[/] 处匹配")

        # 按文件分组
        current_file = None
        file_count = 0

        for file_path, line_num, line_content in matches:
            if file_path != current_file:
                if current_file is not None:
                    lines.append(f"[dim {COLORS['border_subtle']}]│[/]")  # 文件间分隔
                # 文件头
                file_icon = self._get_file_icon(Path(file_path).suffix.lower())
                lines.append(f"[dim {COLORS['border_subtle']}]│[/]")
                lines.append(f"[dim {COLORS['border_subtle']}]│[/] {file_icon} [cyan]{file_path}[/]")
                current_file = file_path
                file_count += 1

            # 截断长行
            if len(line_content) > self.PREVIEW_WIDTH:
                line_content = line_content[:self.PREVIEW_WIDTH - 3] + "..."

            lines.append(f"[dim {COLORS['border_subtle']}]│[/]   [dim]{line_num:5d}[/]  {line_content}")

        if total > self.MAX_MATCHES:
            lines.append(f"[dim {COLORS['border_subtle']}]│[/]")
            lines.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]... 共 {total} 处匹配，仅显示前 {self.MAX_MATCHES} 处[/]")

        lines.append(f"[dim {COLORS['border_subtle']}]╰{'─' * 50}[/]")

        return '\n'.join(lines)

    def _get_file_icon(self, file_ext: str) -> str:
        """根据文件扩展名获取图标"""
        icons = {
            '.py': ICONS.get('file_py', '📄'),
            '.js': ICONS.get('file_js', '📄'),
            '.ts': ICONS.get('file_ts', '📄'),
            '.json': ICONS.get('file_json', '📄'),
            '.md': ICONS.get('file_md', '📄'),
            '.txt': ICONS.get('file_txt', '📄'),
            '.yaml': ICONS.get('file_yaml', '📄'),
            '.yml': ICONS.get('file_yaml', '📄'),
            '.html': ICONS.get('file_html', '📄'),
            '.css': ICONS.get('file_css', '📄'),
        }
        return icons.get(file_ext, ICONS.get('file_default', '📄'))

    def is_read_only(self) -> bool:
        """只读操作"""
        return True

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        pattern = parameters.get("pattern")
        if not pattern:
            return "缺少 pattern 参数"

        # 验证正则表达式是否合法
        try:
            re.compile(pattern, re.DOTALL)
        except re.error as e:
            return f"无效的正则表达式: {str(e)}"

        return None