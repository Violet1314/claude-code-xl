"""权限确认 UI 组件 - 优雅卡片风格"""
from typing import Optional
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED
from claude_code.ui.theme import COLORS, ICONS
from claude_code.ui.input import interactive_menu
from claude_code.ui import console
from .base import PermissionLevel

class PermissionUI:
    """权限确认 UI"""

    @staticmethod
    def show_permission_menu(
        tool_name: str,
        operation_desc: str,
        details: str = " ",
        is_read_only: bool = False,
        path_warning: str = " "
    ) -> Optional[str]:
        """
        显示权限确认菜单 (Panel 风格 - 极简版)
        """
        con = console.get_console()
        
        # 1. 构建标题
        type_hint = "[只读]" if is_read_only else "[写入]"
        type_color = COLORS['info'] if is_read_only else COLORS['warning']
        tool_icon = PermissionUI._get_tool_icon(tool_name)
        
        title_text = Text.assemble(
            (f"{ICONS['warning']} 权限确认 ", f"bold {COLORS['warning']} "),
            ("  ", "default "),
            (f"{tool_icon} {tool_name} ", "bold white "),
            ("  ", "default "),
            (type_hint, f"dim {type_color} ")
        )

        # 2. 构建内容 (只保留核心操作)
        content_lines = []
        
        # 操作描述 (最简洁形式)
        content_lines.append(f"[bold]操作:[/]")
        desc_preview = operation_desc.split('\n')[0]
        if len(desc_preview) > 80:
            desc_preview = desc_preview[:77] + "..."
        content_lines.append(f"  {desc_preview}")
        
        content_lines.append(" ") 
        
        # 路径警告 (如果有)
        if path_warning:
            content_lines.append(f"[{COLORS['warning']}]⚠️ 路径范围警告:[/]")
            for line in path_warning.split('\n')[:2]:
                content_lines.append(f"  [dim]{line}[/]")
            content_lines.append(" ")

        # 【优化】：移除 details 部分

        content_text = "\n".join(content_lines)

        # 3. 渲染 Panel
        panel = Panel(
            content_text,
            title=title_text,
            title_align="left",
            border_style=COLORS['border_default'],
            box=ROUNDED,
            padding=(1, 2),
        )
        
        con.print()
        con.print(panel)
        
        # 4. 交互提示
        con.print(f"  [dim]↑↓ 选择 │ Enter 确认 │ Esc/q 取消[/]\n")

        # 5. 构建菜单选项
        options = [
            {
                "name": "Yes (once)",
                "value": "once",
                "desc": "仅本次允许"
            },
            {
                "name": "No (once)",
                "value": "no_once",
                "desc": "仅本次拒绝"
            },
        ]

        return interactive_menu("权限选择", options)

    @staticmethod
    def _get_tool_icon(tool_name: str) -> str:
        """获取工具图标"""
        icons = {
            "Read": ICONS.get('read', '📄'),
            "Write": ICONS.get('write', '✎'),
            "Edit": ICONS.get('edit', '✐'),
            "Bash": ICONS.get('bash', '⚡'),
            "Grep": ICONS.get('grep', '🔍'),
            "Glob": ICONS.get('glob', '📂'),
            "AskUserQuestion": ICONS.get('ask', '💬'),
        }
        return icons.get(tool_name, ICONS.get('file', '📄'))

    @staticmethod
    def show_result(allowed: bool, level: PermissionLevel) -> None:
        """显示权限结果"""
        if allowed:
            color = COLORS['success']
            msg = "✓ 允许执行"
        else:
            color = COLORS['error']
            msg = "✗ 拒绝执行"

        console.print(f"  [{color}]{msg}[/]\n")

    @staticmethod
    def show_cached_decision(tool_name: str, level: PermissionLevel, operation: str) -> None:
        """显示缓存决策"""
        if level == PermissionLevel.ONCE:
            color = COLORS['success']
            msg = "✓ 已授权：自动通过"
        else:
            color = COLORS['warning']
            msg = "✗ 使用缓存：拒绝"

        console.print(f"  [{color}]{msg}[/]  ", end="")
        console.print_raw(tool_name)

    @staticmethod
    def show_progress(tool_name: str, status: str = "执行中") -> None:
        """显示工具执行进度"""
        console.print(f"  [{COLORS['info']}]{ICONS['info']}[/]  ", end="")
        console.print_raw(tool_name)
        console.print(f": {status}")

    @staticmethod
    def show_tool_result(tool_name: str, success: bool, output: str) -> None:
        """
        显示工具执行结果
        注意：Bash/Read/Glob 等工具现在由 progress_display.py 统一渲染卡片，
        此处主要处理 Write/Edit 等简单工具或 fallback 情况。
        """
        if success:
            # 关键修复：更 robust 地检测 Rich Markup
            # 只要输出中包含 '[' 且不是纯文本，就尝试渲染
            is_rich_output = (
                tool_name in ("Read", "Grep", "Glob", "Edit") or 
                ("[" in output and "]" in output)
            )
            
            if is_rich_output:
                # 对于 Edit 工具，我们希望能看到漂亮的 Diff
                # 如果 output 已经是 Panel 格式（如 Read），直接打印
                # 如果 output 是 Diff 文本，我们也直接打印，让 Rich 解析颜色
                console.print(output)
            else:
                # 普通成功消息
                console.print(f"  [{COLORS['success']}]{ICONS['success']}[/] [dim]{tool_name}[/] 执行成功")
                if output.strip():
                    console.print_raw(output)
        else:
            icon = ICONS['error']
            color = COLORS['error']
            console.print(f"  [{color}]{icon} {tool_name} 失败:[/]  ", end="")
            console.print_raw(output)

    @staticmethod
    def show_tool_start(tool_name: str, operation: str) -> None:
        """显示工具开始执行"""
        tool_icon = PermissionUI._get_tool_icon(tool_name)
        console.print(f"\n  [{COLORS['primary']}]{tool_icon} 执行工具:[/]  ", end="")
        console.print_raw(tool_name)
        console.print(f"   ", end="")
        console.print_raw(operation)