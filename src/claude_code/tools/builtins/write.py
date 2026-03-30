"""Write 工具 - 创建或覆盖文件"""
import re
from pathlib import Path
from typing import Any, Dict, Optional

from ..base import Tool, ToolResult


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

    def _fix_broken_string_newlines(self, content: str) -> str:
        """
        修复模型输出中常见的字符串换行问题

        模型有时会在字符串字面量中直接嵌入真换行，导致语法错误。
        例如：print("hello\nworld") 被输出为 print("hello<真换行>world")

        这个方法尝试检测并修复这类问题。
        """
        # 检测是否可能是 Python 代码
        python_indicators = ['def ', 'class ', 'import ', 'from ', 'print(', 'if __name__']
        is_likely_python = any(indicator in content for indicator in python_indicators)

        if not is_likely_python:
            return content

        # 检测字符串内的非法换行模式
        # 模式：引号后紧跟换行，后面又有内容和闭合引号
        # 例如：print("...\n...") 被错误输出为 print("...<真换行>...")

        lines = content.split('\n')
        result_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # 检测未闭合的字符串（简单启发式）
            # 统计行内引号数量（排除转义的引号）
            single_quotes = len(re.findall(r'(?<!\\)\'', line))
            double_quotes = len(re.findall(r'(?<!\\)"', line))

            # 如果引号数量为奇数，可能字符串跨行了
            if (single_quotes % 2 == 1 or double_quotes % 2 == 1) and i + 1 < len(lines):
                # 检查下一行是否像字符串内容的延续
                next_line = lines[i + 1].strip()

                # 如果当前行以引号结尾（可能被截断），尝试合并
                if line.rstrip().endswith('"') or line.rstrip().endswith("'"):
                    # 不太可能是错误的换行，保留
                    result_lines.append(line)
                    i += 1
                    continue

                # 检测 "xxx"\nyyy 模式（字符串被错误换行）
                # 例如：print("xxx") 被拆成 print("xxx"\n...")
                match = re.search(r'["\'][^"\']*$', line)
                if match:
                    # 当前行的字符串未闭合，检查下一行
                    remaining = lines[i + 1]
                    close_match = re.match(r'^[^"\']*["\']', remaining)
                    if close_match:
                        # 合并这两行，中间加 \n
                        # 但这需要谨慎，我们只是标记问题让用户知道
                        result_lines.append(line)
                        i += 1
                        continue

            result_lines.append(line)
            i += 1

        return '\n'.join(result_lines)

    def _validate_content(self, content: str, file_path: str) -> tuple:
        """
        验证内容是否有明显的语法问题

        Returns:
            (is_valid, error_message)
        """
        # 只对 Python 文件做检查
        if not file_path.endswith('.py'):
            return True, None

        # 尝试编译检查语法
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

        try:
            path = Path(file_path)

            # 创建父目录
            path.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 写入后验证 Python 文件语法（警告而非阻止）
            output_msg = f"写入成功: {file_path} ({len(content)} 字符)"
            if file_path.endswith('.py'):
                is_valid, error_msg = self._validate_content(content, file_path)
                if not is_valid:
                    output_msg += f"\n\n⚠️ 语法警告: {error_msg}\n提示：这可能是模型输出格式问题，建议使用 native tool calling 模式或更强的模型。"

            return ToolResult(
                success=True,
                output=output_msg,
                metadata={
                    "file_path": str(path.absolute()),
                    "content_length": len(content)
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足: {file_path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"写入失败: {str(e)}")

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