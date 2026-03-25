"""Read 工具 - 读取文件内容"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..base import Tool, ToolResult


class ReadTool(Tool):
    """读取文件工具"""

    name = "Read"
    description = "读取文件内容。支持读取单个文件，返回文件内容。"

    # 文件大小限制 (1MB)
    MAX_FILE_SIZE = 1 * 1024 * 1024

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要读取的文件路径（绝对路径或相对路径）"
                },
                "offset": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始），可选",
                    "default": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "读取的最大行数，可选",
                    "default": 2000
                }
            },
            "required": ["file_path"]
        }

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行读取操作"""
        file_path = parameters.get("file_path", "")
        offset = parameters.get("offset", 1)
        limit = parameters.get("limit", 2000)

        # 参数验证
        if not file_path:
            return ToolResult(success=False, output="", error="缺少 file_path 参数")

        try:
            path = Path(file_path)

            # 检查文件是否存在
            if not path.exists():
                return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")

            # 检查是否为文件
            if not path.is_file():
                return ToolResult(success=False, output="", error=f"不是文件: {file_path}")

            # 检查文件大小
            file_size = path.stat().st_size
            if file_size > self.MAX_FILE_SIZE:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"文件过大 ({file_size / 1024:.1f}KB)，超过 1MB 限制"
                )

            # 读取文件
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                # 尝试其他编码
                try:
                    with open(path, 'r', encoding='gbk') as f:
                        lines = f.readlines()
                except UnicodeDecodeError:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"文件编码不支持: {file_path}"
                    )

            # 处理行号
            total_lines = len(lines)
            start_line = max(1, offset)
            end_line = min(total_lines, start_line + limit - 1)

            # 提取内容
            selected_lines = lines[start_line - 1:end_line]

            # 格式化输出（带行号）
            output_lines = []
            for i, line in enumerate(selected_lines, start=start_line):
                # 移除末尾换行符
                line_content = line.rstrip('\n\r')
                output_lines.append(f"{i:6d}\t{line_content}")

            output = '\n'.join(output_lines)

            # 添加元信息
            meta_info = f"文件: {file_path}"
            if total_lines > limit:
                meta_info += f" (显示 {start_line}-{end_line} 行，共 {total_lines} 行)"
            else:
                meta_info += f" ({total_lines} 行)"

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "file_path": str(path.absolute()),
                    "total_lines": total_lines,
                    "start_line": start_line,
                    "end_line": end_line,
                    "file_size": file_size
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足，无法读取: {file_path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"读取失败: {str(e)}")

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"

        offset = parameters.get("offset", 1)
        if offset < 1:
            return "offset 必须 >= 1"

        limit = parameters.get("limit", 2000)
        if limit < 1:
            return "limit 必须 >= 1"

        return None

    def is_read_only(self) -> bool:
        """只读操作"""
        return True