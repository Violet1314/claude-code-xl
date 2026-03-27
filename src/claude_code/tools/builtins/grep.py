"""Grep 工具 - 按内容搜索文件"""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import Tool, ToolResult


class GrepTool(Tool):
    """文件内容搜索工具"""

    name = "Grep"
    description = "在文件中搜索匹配正则表达式的内容。返回匹配的行及其上下文。建议使用精确模式减少匹配数量。"

    # 搜索限制
    MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB
    MAX_MATCHES = 30  # 最大匹配数（降低以节省 token）

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
                    "description": "文件类型过滤，如 py, js, md",
                    "default": None
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
                output = '\n'.join(str(f) for f in matched_files)
            else:
                output_lines = []
                for match in all_matches[:self.MAX_MATCHES]:
                    file_path, line_num, line_content = match
                    output_lines.append(f"{file_path}:{line_num}:{line_content}")
                output = '\n'.join(output_lines)

            if not all_matches:
                output = "未找到匹配的内容"

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

    def is_read_only(self) -> bool:
        """只读操作"""
        return True