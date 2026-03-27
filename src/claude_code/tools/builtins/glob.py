"""Glob 工具 - 按文件名模式搜索"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import Tool, ToolResult


class GlobTool(Tool):
    """文件名模式搜索工具"""

    name = "Glob"
    description = "按文件名模式搜索文件。支持通配符：* 匹配任意字符，** 递归匹配目录。"

    # 最大返回数量
    MAX_RESULTS = 100

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "glob 模式，如 **/*.py, src/**/*.js"
                },
                "path": {
                    "type": "string",
                    "description": "搜索的起始目录，默认当前目录",
                    "default": "."
                }
            },
            "required": ["pattern"]
        }

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行搜索"""
        pattern = parameters.get("pattern", "")
        search_path = parameters.get("path", ".")

        if not pattern:
            return ToolResult(success=False, output="", error="缺少 pattern 参数")

        try:
            base_path = Path(search_path)
            if not base_path.exists():
                return ToolResult(success=False, output="", error=f"目录不存在: {search_path}")

            # 执行 glob 搜索
            matches = list(base_path.glob(pattern))

            # 排序
            matches.sort(key=lambda p: str(p).lower())

            if not matches:
                return ToolResult(success=True, output="未找到匹配的文件")

            # 限制数量
            total_count = len(matches)
            if len(matches) > self.MAX_RESULTS:
                matches = matches[:self.MAX_RESULTS]

            # 格式化输出
            output_lines = []
            for match in matches:
                rel_path = match.relative_to(base_path) if match.is_relative_to(base_path) else match
                if match.is_dir():
                    output_lines.append(f"{rel_path}/")
                else:
                    output_lines.append(str(rel_path))

            output = '\n'.join(output_lines)

            # 添加截断提示
            if total_count > self.MAX_RESULTS:
                output += f"\n... 共 {total_count} 个结果，仅显示前 {self.MAX_RESULTS} 个"

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "pattern": pattern,
                    "path": search_path,
                    "count": len(matches),
                    "total_count": total_count
                }
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=f"搜索失败: {str(e)}")

    def is_read_only(self) -> bool:
        """只读操作"""
        return True