"""Glob 工具 - 按文件名模式搜索"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from collections import Counter
from ..base import Tool, ToolResult
from claude_code.core.path_manager import get_path_manager
from claude_code.utils.paths import EXCLUDED_DIRS
from claude_code.ui.theme import COLORS, ICONS
from rich.markup import escape

class GlobTool(Tool):
    """文件名模式搜索工具"""
    name = "Glob"
    description = (
        "按文件名模式搜索文件。支持通配符：* 匹配任意字符，** 递归匹配目录。\n"
        "重要：\n"
        "- pattern 必须是相对模式（不能是绝对路径），如 **/*.py、src/**/*.js\n"
        "- path 必须是绝对路径，默认使用操作根目录\n"
        "- 必须明确指定 path，如：path=\"E:\\项目目录\\src\""
    )

    MAX_RESULTS = 100

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "glob 模式（相对模式，不能含绝对路径），如 **/*.py, src/**/*.js"
                },
                "path": {
                    "type": "string",
                    "description": "搜索的起始目录（必须使用绝对路径，默认使用操作根目录）",
                    "default": "."
                }
            },
            "required": ["pattern"]
        }

    def execute(
        self,
        parameters: Dict[str, Any],
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> ToolResult:
        """执行搜索"""
        # 参数验证（与 Read/Edit/Bash 工具一致）
        validation_error = self.validate_parameters(parameters)
        if validation_error:
            return ToolResult(success=False, output="", error=validation_error)

        pattern = parameters.get("pattern", "")
        search_path = parameters.get("path", ".")

        # 使用 PathManager 统一路径解析
        pm = get_path_manager()
        search_path, _ = pm.resolve_safe(search_path)

        try:
            base_path = Path(search_path)
            if not base_path.exists():
                return ToolResult(success=False, output="", error=f"目录不存在: {search_path}")

            # 使用迭代器而非 list()，支持中断检查
            raw_matches = []
            check_interval = 50
            file_count = 0

            for path in base_path.glob(pattern):
                # 定期检查中断
                file_count += 1
                if interrupt_check and file_count % check_interval == 0 and interrupt_check():
                    return ToolResult(
                        success=False,
                        output="",
                        error="用户中断执行",
                        interrupted=True
                    )
                raw_matches.append(path)

            matches = [m for m in raw_matches if not self._should_exclude(m, base_path)]
            matches.sort(key=lambda p: str(p).lower())

            if not matches:
                return ToolResult(
                    success=True,
                    output="No files matched.",
                    display_output=f"[dim {COLORS['border_subtle']}]╭─[/] {ICONS.get('glob', '📁')} [bold]Glob[/]\n[dim {COLORS['border_subtle']}]│[/]  未找到匹配: [cyan]{escape(pattern)}[/]\n[dim {COLORS['border_subtle']}]╰{'─' * 40}[/]"
                )

            total_count = len(matches)
            if len(matches) > self.MAX_RESULTS:
                matches = matches[:self.MAX_RESULTS]

            # 给模型的纯文本输出
            output = self._build_model_output(matches, base_path, pattern, total_count)

            # 给终端的简洁显示
            display_output = self._build_terminal_display(pattern, total_count, matches)

            return ToolResult(
                success=True,
                output=output,
                display_output=display_output,
                metadata={
                    "pattern": pattern,
                    "path": search_path,
                    "count": len(matches),
                    "total_count": total_count
                }
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=f"搜索失败: {str(e)}")

    # ============================================================
    # 模型输出（纯文本）
    # ============================================================

    def _build_model_output(self, matches: List[Path], base_path: Path, pattern: str, total: int) -> str:
        """给模型的纯文本输出"""
        parts = []
        parts.append(f"Glob: \"{pattern}\" - {total} results")
        parts.append("")

        # 文件类型统计
        ext_count = Counter()
        dirs_count = 0
        for match in matches:
            if match.is_dir():
                dirs_count += 1
            else:
                ext = match.suffix.lower() or "(no ext)"
                ext_count[ext] += 1

        if ext_count or dirs_count:
            stats_parts = []
            if dirs_count:
                stats_parts.append(f"dirs: {dirs_count}")
            for ext, count in ext_count.most_common(5):
                stats_parts.append(f"{ext}: {count}")
            parts.append(f"Types: {' | '.join(stats_parts)}")
            parts.append("")

        # 文件列表
        for match in matches:
            try:
                rel_path = match.relative_to(base_path)
            except ValueError:
                rel_path = match

            if match.is_dir():
                parts.append(f"  {rel_path}/")
            else:
                try:
                    size = match.stat().st_size
                    parts.append(f"  {rel_path}  ({self._format_size(size)})")
                except Exception:
                    parts.append(f"  {rel_path}")

        if total > self.MAX_RESULTS:
            parts.append(f"\n... ({total} total, showing first {self.MAX_RESULTS})")

        return '\n'.join(parts)

    # ============================================================
    # 终端显示（统一格式）
    # ============================================================

    def _build_terminal_display(self, pattern: str, total: int, matches: List[Path]) -> str:
        """给终端的统一格式显示"""
        parts = []

        # 开头空行，与其他工具分隔
        parts.append("")
        # 标题行：✎ Glob: pattern [N 个匹配]
        parts.append(f"[bold]{ICONS.get('glob', '📁')} Glob:[/] [cyan]{escape(pattern)}[/] [dim]\\[{total} 个匹配][/]")
        # 分隔线
        parts.append(f"[dim]{'─' * 50}[/]")

        # 文件列表（带行号）
        for i, match in enumerate(matches, 1):
            display_path = str(match)
            parts.append(f"[dim]{i:>5}[/]  {escape(display_path)}")

        return '\n'.join(parts)

    # ============================================================
    # 工具属性
    # ============================================================

    def _should_exclude(self, path: Path, base: Path) -> bool:
        """检查路径是否在排除目录下"""
        try:
            rel = path.relative_to(base)
        except ValueError:
            rel = path
        for part in rel.parts:
            if part in EXCLUDED_DIRS or part.endswith('.egg-info'):
                return True
        return False

    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        else:
            return f"{size / 1024 / 1024:.1f}MB"

    def is_read_only(self) -> bool:
        return True

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        pattern = parameters.get("pattern")
        if not pattern:
            return "缺少 pattern 参数"
        return None
    
    def get_security_context(self) -> Dict[str, Any]:
        return {"is_sensitive": False, "paths": [], "command_preview": ""}