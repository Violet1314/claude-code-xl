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

        file_path = resolve_workplace_path(file_path)

        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 更新文件缓存
            cache_result = file_cache.apply_write(file_path, content)
            
            output_msg = f"写入成功: {file_path} ({len(content)} 字符)"
            if file_path.endswith('.py'):
                is_valid, error_msg = self._validate_content(content, file_path)
                if not is_valid:
                    output_msg += f"\n\n⚠️ 语法警告: {error_msg}"

            return ToolResult(
                success=True,
                output=output_msg,
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

    def get_security_context(self) -> Dict[str, Any]:
        """返回安全上下文"""
        return {
            "is_sensitive": True,
            "paths": [self.parameters.get("file_path", "")] if hasattr(self, 'parameters') else [],
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