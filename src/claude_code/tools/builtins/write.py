"""Write 工具 - 创建或覆盖文件"""
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

            return ToolResult(
                success=True,
                output=f"写入成功: {file_path} ({len(content)} 字符)",
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