"""权限确认 UI 组件"""
from typing import Optional

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
        details: str = "",
        is_read_only: bool = False,
        force_limited: bool = False,
        path_warning: str = ""
    ) -> Optional[str]:
        """
        显示权限确认菜单

        Args:
            tool_name: 工具名称
            operation_desc: 操作描述
            details: 详细信息
            is_read_only: 是否为只读操作
            force_limited: 强制只显示三个选项（敏感操作，不含 Yes (all))
            path_warning: 路径范围警告信息

        Returns:
            "once" | "all" | "no_once" | None（取消）
        """
        con = console.get_console()

        # 顶部标题框
        console.print(f"  [dim {COLORS['border_subtle']}]╭─[/] [{COLORS['warning']}]{ICONS['warning']}[/] [bold {COLORS['warning']}]权限确认[/]")

        # 工具信息
        type_hint = "[只读]" if is_read_only else "[写入]"
        type_color = COLORS['info'] if is_read_only else COLORS['warning']

        # 工具图标
        tool_icon = PermissionUI._get_tool_icon(tool_name)

        console.print(f"  [dim {COLORS['border_subtle']}]│[/]")
        console.print(f"  [dim {COLORS['border_subtle']}]│[/] [{COLORS['text_primary']}]{tool_icon} {tool_name}[/] [dim {type_color}]{type_hint}[/]")

        # 操作描述
        console.print(f"  [dim {COLORS['border_subtle']}]│[/] [dim]操作:[/]")
        # 截断长操作描述
        desc_lines = operation_desc.split('\n') if '\n' in operation_desc else [operation_desc]
        for line in desc_lines[:3]:
            if len(line) > 60:
                line = line[:57] + "..."
            console.print(f"  [dim {COLORS['border_subtle']}]│[/]   {line}")

        # 路径范围警告
        if path_warning:
            console.print(f"  [dim {COLORS['border_subtle']}]│[/]")
            console.print(f"  [dim {COLORS['border_subtle']}]│[/] [{COLORS['warning']}]⚠️ 路径范围警告[/]")
            for line in path_warning.split('\n')[:2]:
                console.print(f"  [dim {COLORS['border_subtle']}]│[/]   [dim]{line}[/]")

        # 详细信息
        if details:
            console.print(f"  [dim {COLORS['border_subtle']}]│[/]")
            console.print(f"  [dim {COLORS['border_subtle']}]│[/] [dim]详情:[/]")
            for line in details.split('\n')[:4]:
                if len(line) > 60:
                    line = line[:57] + "..."
                console.print(f"  [dim {COLORS['border_subtle']}]│[/]   [dim]{line}[/]")

        # 敏感操作警告
        if force_limited:
            console.print(f"  [dim {COLORS['border_subtle']}]│[/]")
            console.print(f"  [dim {COLORS['border_subtle']}]│[/] [{COLORS['error']}]⚠️ 敏感操作 - 每次都需要确认[/]")

        # 底部边框
        console.print(f"  [dim {COLORS['border_subtle']}]│[/]")
        console.print(f"  [dim {COLORS['border_subtle']}]╰{'─' * 50}[/]")

        # 快捷键提示
        console.print(f"  [dim]↑↓ 选择 │ Enter 确认 │ Esc/q 取消[/]\n")

        # 构建菜单选项
        if force_limited:
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
        else:
            options = [
                {
                    "name": "Yes (once)",
                    "value": "once",
                    "desc": "仅本次允许"
                },
                {
                    "name": "Yes (all)",
                    "value": "all",
                    "desc": "授予所有工具权限"
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
            "Write": ICONS.get('write', '📝'),
            "Edit": ICONS.get('edit', '✏️'),
            "Bash": ICONS.get('bash', '⚡'),
            "Grep": ICONS.get('grep', '🔍'),
            "Glob": ICONS.get('glob', '📁'),
            "AskUserQuestion": ICONS.get('ask', '❓'),
        }
        return icons.get(tool_name, ICONS.get('file', '📎'))

    @staticmethod
    def show_result(allowed: bool, level: PermissionLevel) -> None:
        """
        显示权限决定结果

        Args:
            allowed: 是否允许
            level: 权限级别
        """
        if allowed:
            icon = ICONS['success']
            color = COLORS['success']
            msg = "✓ 允许执行"
            if level == PermissionLevel.ALL:
                msg += "（全局授权已开启）"
        else:
            icon = ICONS['error']
            color = COLORS['error']
            msg = "✗ 拒绝执行"

        console.print(f"  [{color}]{msg}[/]\n")

    @staticmethod
    def show_cached_decision(tool_name: str, level: PermissionLevel, operation: str) -> None:
        """
        显示缓存的权限决定

        Args:
            tool_name: 工具名称
            level: 权限级别
            operation: 操作描述
        """
        if level == PermissionLevel.ALL:
            color = COLORS['success']
            msg = "✓ 全局授权：自动通过"
        elif level == PermissionLevel.ONCE:
            color = COLORS['success']
            msg = "✓ 使用缓存：允许"
        else:
            color = COLORS['warning']
            msg = "✗ 使用缓存：拒绝"

        console.print(f"  [{color}]{msg}[/] ", end="")
        console.print_raw(tool_name)

    @staticmethod
    def show_progress(tool_name: str, status: str = "执行中") -> None:
        """
        显示工具执行进度

        Args:
            tool_name: 工具名称
            status: 状态文本
        """
        console.print(f"  [{COLORS['info']}]{ICONS['info']}[/] ", end="")
        console.print_raw(tool_name)
        console.print(f": {status}")

    @staticmethod
    def show_tool_result(tool_name: str, success: bool, output: str) -> None:
        """
        显示工具执行结果

        Args:
            tool_name: 工具名称
            success: 是否成功
            output: 输出内容（可能包含 Rich 标记）
        """
        if success:
            # 检查输出是否包含 Rich markup（卡片式输出或 diff 输出）
            # Read/Grep/Glob 工具使用卡片式输出，Edit 使用 diff 输出
            is_rich_output = (
                "[dim" in output or
                "[bold" in output or
                "[cyan]" in output or
                "╭─" in output or
                "[bold green]Update" in output or
                "[white on" in output
            )
            if is_rich_output:
                # Rich markup 输出：使用 console.print 渲染
                console.print(output)
            else:
                # 普通输出：直接打印，不解析 markup
                console.print_raw(output)
        else:
            icon = ICONS['error']
            color = COLORS['error']
            console.print(f"  [{color}]{icon} {tool_name} 失败:[/] ", end="")
            console.print_raw(output)

    @staticmethod
    def show_tool_start(tool_name: str, operation: str) -> None:
        """
        显示工具开始执行

        Args:
            tool_name: 工具名称
            operation: 操作描述
        """
        tool_icon = PermissionUI._get_tool_icon(tool_name)
        console.print(f"\n  [{COLORS['primary']}]{tool_icon} 执行工具:[/] ", end="")
        console.print_raw(tool_name)
        console.print(f"  ", end="")
        console.print_raw(operation)