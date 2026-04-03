"""Write 工具 - 创建或覆盖文件"""
from ..file_cache import file_cache
from pathlib import Path
from typing import Any, Dict, Optional

from ..base import Tool, ToolResult
from claude_code.utils.paths import resolve_workplace_path


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

        # Workplace 隔离：相对路径重定向到 workplace 目录
        file_path = resolve_workplace_path(file_path)

        try:
            path = Path(file_path)

            # 创建父目录
            path.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            # ✅ 新增：更新文件缓存
            cache_result = file_cache.apply_write(file_path, content)

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