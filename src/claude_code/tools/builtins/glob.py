"""Glob 工具 - 按文件名模式搜索"""
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import Counter

from ..base import Tool, ToolResult
from claude_code.utils.paths import resolve_workplace_path
from claude_code.ui.theme import COLORS, ICONS
from rich.markup import escape


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

        # Workplace 隔离：相对路径重定向到 workplace 目录
        search_path = resolve_workplace_path(search_path)

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

        # 卡片头部
        lines.append(f"[dim {COLORS['border_subtle']}]╭─[/] {ICONS.get('glob', '📁')} [bold]Glob 结果[/]")
        lines.append(f"[dim {COLORS['border_subtle']}]│[/]")
        lines.append(f"[dim {COLORS['border_subtle']}]│[/] 模式 [cyan]\"{escape(pattern)}\"[/] 找到 [bold]{total}[/] 个结果")

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
            lines.append(f"[dim {COLORS['border_subtle']}]│[/]")
            stats_parts = []
            if dirs_count:
                stats_parts.append(f"目录: {dirs_count}")
            if ext_count:
                top_exts = ext_count.most_common(5)
                for ext, count in top_exts:
                    # 转义扩展名
                    stats_parts.append(f"{escape(ext)}: {count}")
            lines.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]类型: {' | '.join(stats_parts)}[/]")

        # 按目录分组
        lines.append(f"[dim {COLORS['border_subtle']}]│[/]")

        current_dir = None
        display_count = 0

        for match in matches[:25]:  # 限制显示数量
            rel_path = match.relative_to(base_path) if match.is_relative_to(base_path) else match
            parent = str(rel_path.parent) if rel_path.parent != Path('.') else "."

            if parent != current_dir:
                if current_dir is not None:
                    lines.append(f"[dim {COLORS['border_subtle']}]│[/]")  # 目录间分隔
                lines.append(f"[dim {COLORS['border_subtle']}]│[/] {ICONS.get('folder', '📂')} [dim]{escape(parent)}/[/]")
                current_dir = parent

            if match.is_dir():
                lines.append(f"[dim {COLORS['border_subtle']}]│[/]     {ICONS.get('folder', '📁')} {escape(match.name)}/")
            else:
                # 获取文件图标
                file_icon = self._get_file_icon(match.suffix.lower())
                # 显示文件大小
                try:
                    size = match.stat().st_size
                    size_str = self._format_size(size)
                    lines.append(f"[dim {COLORS['border_subtle']}]│[/]     {file_icon} {escape(match.name)} [dim]({size_str})[/]")
                except:
                    lines.append(f"[dim {COLORS['border_subtle']}]│[/]     {file_icon} {escape(match.name)}")

            display_count += 1

        if total > 25:
            lines.append(f"[dim {COLORS['border_subtle']}]│[/]")
            lines.append(f"[dim {COLORS['border_subtle']}]│[/] [dim]... 还有 {total - 25} 个结果[/]")

        lines.append(f"[dim {COLORS['border_subtle']}]╰{'─' * 50}[/]")

        return '\n'.join(lines)

    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        else:
            return f"{size / 1024 / 1024:.1f}MB"

    def _get_file_icon(self, file_ext: str) -> str:
        """根据文件扩展名获取图标"""
        icons = {
            '.py': ICONS.get('file_py', '📄'),
            '.js': ICONS.get('file_js', '📄'),
            '.ts': ICONS.get('file_ts', '📄'),
            '.jsx': ICONS.get('file_js', '📄'),
            '.tsx': ICONS.get('file_ts', '📄'),
            '.json': ICONS.get('file_json', '📄'),
            '.md': ICONS.get('file_md', '📄'),
            '.txt': ICONS.get('file_txt', '📄'),
            '.yaml': ICONS.get('file_yaml', '📄'),
            '.yml': ICONS.get('file_yaml', '📄'),
            '.html': ICONS.get('file_html', '📄'),
            '.css': ICONS.get('file_css', '📄'),
            '.scss': ICONS.get('file_css', '📄'),
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
        return None