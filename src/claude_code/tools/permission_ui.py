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
        # 显示确认对话框
        console.print(f"\n[{COLORS['warning']}]{ICONS['warning']} 权限确认[/]")
        console.print(f"[{COLORS['primary']}]{'─' * 60}[/]")

        # 显示工具名称
        type_hint = "[只读]" if is_read_only else "[写入]"
        console.print(f"\n[bold]工具:[/] ", end="")
        console.print_raw(tool_name)
        console.print(f" [dim]{type_hint}[/]")

        # 显示操作描述
        console.print(f"[bold]操作:[/]")
        console.print(f"  ", end="")
        console.print_raw(operation_desc)

        # 显示路径范围警告
        if path_warning:
            console.print(f"\n[bold {COLORS['warning']}]⚠️ 路径范围警告[/]")
            for line in path_warning.split('\n'):
                console.print(f"  ", end="")
                console.print_raw(line)

        # 显示详细信息
        if details:
            console.print(f"\n[dim]详细信息:[/]")
            for line in details.split('\n'):
                console.print(f"  ", end="")
                console.print_raw(line)

        console.print(f"\n[{COLORS['primary']}]{'─' * 60}[/]")
        console.print(f"[dim]↑↓ 选择 | Enter 确认 | Esc/q 取消[/]\n")

        # 构建菜单选项
        # 敏感操作强制只显示三个选项（不含 Yes (all))
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

        # 使用项目中现有的交互式菜单
        return interactive_menu("权限选择", options)

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

        console.print(f"[{color}]{msg}[/]\n")

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
            icon = ICONS['success']
            color = COLORS['success']
            msg = "✓ 全局授权：自动通过"
        elif level == PermissionLevel.ONCE:
            icon = ICONS['success']
            color = COLORS['success']
            msg = "✓ 使用缓存：允许"
        else:
            icon = ICONS['warning']
            color = COLORS['warning']
            msg = "✗ 使用缓存：拒绝"

        console.print(f"[{color}]{msg}[/] ", end="")
        console.print_raw(tool_name)

    @staticmethod
    def show_progress(tool_name: str, status: str = "执行中") -> None:
        """
        显示工具执行进度

        Args:
            tool_name: 工具名称
            status: 状态文本
        """
        console.print(f"[{COLORS['info']}]{ICONS['info']}[/] ", end="")
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
            # 检查输出是否是 Edit 工具的 diff 输出
            # Edit diff 包含 "[bold green]Update" 或 "[white on" 颜色标记
            is_edit_diff = "[bold green]Update" in output or "[white on" in output
            if is_edit_diff:
                # Edit diff 输出：使用 Rich markup（安全的，是我们自己生成的）
                console.print(output)
            else:
                # 普通输出：直接打印，不解析 markup
                console.print_raw(output)
        else:
            icon = ICONS['error']
            color = COLORS['error']
            # 分开打印，避免 output 中的 markup 标签被解析
            console.print(f"[{color}]{icon} {tool_name} 失败:[/] ", end="")
            console.print_raw(output)

    @staticmethod
    def show_tool_start(tool_name: str, operation: str) -> None:
        """
        显示工具开始执行

        Args:
            tool_name: 工具名称
            operation: 操作描述
        """
        console.print(f"\n[{COLORS['primary']}]{ICONS['claude']} 执行工具:[/] ", end="")
        console.print_raw(tool_name)
        console.print(f"  ", end="")
        console.print_raw(operation)