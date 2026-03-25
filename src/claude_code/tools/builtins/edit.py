"""Edit 工具 - 编辑文件（精确替换）"""
from pathlib import Path
from typing import Any, Dict, Optional

from ..base import Tool, ToolResult


class EditTool(Tool):
    """编辑文件工具"""

    name = "Edit"
    description = "精确替换文件中的内容。old_string 必须完全匹配才能替换。"

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

        # 参数验证
        if not file_path:
            return ToolResult(success=False, output="", error="缺少 file_path 参数")

        if not old_string:
            return ToolResult(success=False, output="", error="缺少 old_string 参数")

        try:
            path = Path(file_path)

            # 检查文件是否存在
            if not path.exists():
                return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")

            # 读取文件内容
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 检查是否存在 old_string
            if old_string not in content:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"未找到要替换的内容。请确保 old_string 与文件中的内容完全一致。"
                )

            # 统计匹配次数
            match_count = content.count(old_string)
            if match_count > 1:
                # 多次匹配，只替换第一个
                new_content = content.replace(old_string, new_string, 1)
            else:
                new_content = content.replace(old_string, new_string)

            # 写回文件
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            result_msg = f"编辑成功: {file_path}"
            if match_count > 1:
                result_msg += f" (共 {match_count} 处匹配，已替换第 1 处)"

            return ToolResult(
                success=True,
                output=result_msg,
                metadata={
                    "file_path": str(path.absolute()),
                    "old_length": len(old_string),
                    "new_length": len(new_string),
                    "match_count": match_count
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足: {file_path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"编辑失败: {str(e)}")

    def is_read_only(self) -> bool:
        """非只读操作"""
        return False