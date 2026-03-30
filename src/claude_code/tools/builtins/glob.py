"""Glob 工具 - 按文件名模式搜索"""
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import Counter

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
            output = self._format_output(matches, base_path, pattern, total_count)

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

    def _format_output(self, matches: List[Path], base_path: Path, pattern: str, total: int) -> str:
        """格式化输出"""
        lines = []
        lines.append(f"📁 Glob \"{pattern}\" 找到 {total} 个结果")
        lines.append("")

        # 统计文件类型
        ext_count = Counter()
        dirs_count = 0

        for match in matches:
            if match.is_dir():
                dirs_count += 1
            else:
                ext = match.suffix.lower() or "无扩展名"
                ext_count[ext] += 1

        # 显示文件类型统计
        if ext_count or dirs_count:
            stats_parts = []
            if dirs_count:
                stats_parts.append(f"{dirs_count} 个目录")
            if ext_count:
                top_exts = ext_count.most_common(5)
                for ext, count in top_exts:
                    stats_parts.append(f"{ext}: {count}")
            lines.append(f"  [dim]类型: {' | '.join(stats_parts)}[/]")
            lines.append("")

        # 按目录分组
        current_dir = None
        for match in matches[:30]:  # 限制显示数量
            rel_path = match.relative_to(base_path) if match.is_relative_to(base_path) else match
            parent = str(rel_path.parent) if rel_path.parent != Path('.') else "."

            if parent != current_dir:
                if current_dir is not None:
                    lines.append("")  # 目录间空行
                lines.append(f"  📂 {parent}/")
                current_dir = parent

            if match.is_dir():
                lines.append(f"      📁 {match.name}/")
            else:
                # 显示文件大小
                try:
                    size = match.stat().st_size
                    size_str = self._format_size(size)
                    lines.append(f"      📄 {match.name} [dim]({size_str})[/]")
                except:
                    lines.append(f"      📄 {match.name}")

        if total > 30:
            lines.append("")
            lines.append(f"  [dim]... 还有 {total - 30} 个结果[/]")

        return '\n'.join(lines)

    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        else:
            return f"{size / 1024 / 1024:.1f}MB"

    def is_read_only(self) -> bool:
        """只读操作"""
        return True

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        pattern = parameters.get("pattern")
        if not pattern:
            return "缺少 pattern 参数"
        return None