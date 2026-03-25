"""权限管理器"""
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from .base import ToolCall, Tool, ToolResult, PermissionLevel


@dataclass
class PermissionDecision:
    """权限决定"""
    allowed: bool
    level: PermissionLevel
    cached: bool = False


class PermissionManager:
    """权限管理器 - 管理工具操作的权限确认"""

    def __init__(self):
        """初始化权限管理器"""
        # 会话级权限规则: {规则key: PermissionLevel}
        self.session_rules: Dict[str, PermissionLevel] = {}

    def _get_rule_key(self, tool_name: str, identifier: str = "") -> str:
        """
        生成权限规则的唯一标识

        Args:
            tool_name: 工具名称
            identifier: 额外标识（如文件路径）

        Returns:
            规则key
        """
        if identifier:
            return f"{tool_name}:{identifier}"
        return tool_name

    def get_cached_permission(self, tool_name: str, identifier: str = "") -> Optional[PermissionLevel]:
        """
        获取缓存的权限决定

        Args:
            tool_name: 工具名称
            identifier: 额外标识

        Returns:
            缓存的权限级别，如果没有缓存则返回None
        """
        rule_key = self._get_rule_key(tool_name, identifier)
        return self.session_rules.get(rule_key)

    def set_permission(self, tool_name: str, level: PermissionLevel, identifier: str = "") -> None:
        """
        设置权限规则

        Args:
            tool_name: 工具名称
            level: 权限级别
            identifier: 额外标识
        """
        rule_key = self._get_rule_key(tool_name, identifier)
        self.session_rules[rule_key] = level

    def clear_session(self) -> None:
        """清除会话所有权限规则"""
        self.session_rules.clear()

    def get_rule_summary(self) -> str:
        """
        获取权限规则摘要

        Returns:
            规则摘要字符串
        """
        if not self.session_rules:
            return "当前没有缓存的权限规则"

        lines = ["会话权限规则:"]
        for key, level in self.session_rules.items():
            lines.append(f"  {key} → {level.value}")

        return "\n".join(lines)

    def request_permission(
        self,
        tool_call: ToolCall,
        tool: Tool
    ) -> Optional[PermissionDecision]:
        """
        请求权限

        Args:
            tool_call: 工具调用
            tool: 工具实例

        Returns:
            PermissionDecision 或 None（取消）
        """
        from .permission_ui import PermissionUI

        # 获取标识符（对于文件操作，使用文件路径）
        identifier = tool_call.parameters.get("file_path", "")

        # 检查缓存权限
        cached_level = self.get_cached_permission(tool.name, identifier)
        if cached_level:
            PermissionUI.show_cached_decision(tool.name, cached_level, str(tool_call))
            return PermissionDecision(
                allowed=cached_level in [PermissionLevel.ONCE, PermissionLevel.ALWAYS],
                level=cached_level,
                cached=True
            )

        # 获取工具详情
        details = self._build_tool_details(tool_call, tool)

        # 显示权限确认菜单
        choice = PermissionUI.show_permission_menu(
            tool_name=tool.name,
            operation_desc=str(tool_call),
            details=details,
            is_read_only=tool.is_read_only()
        )

        if choice is None:
            return None  # 用户取消

        # 转换为 PermissionLevel
        level = PermissionLevel(choice)

        # 记录权限决定（只有 always 才缓存）
        if level == PermissionLevel.ALWAYS:
            self.set_permission(tool.name, level, identifier)

        # 显示决定结果
        allowed = level in [PermissionLevel.ONCE, PermissionLevel.ALWAYS]
        PermissionUI.show_result(allowed, level)

        return PermissionDecision(allowed=allowed, level=level, cached=False)

    def _build_tool_details(self, tool_call: ToolCall, tool: Tool) -> str:
        """
        构建工具详细信息

        Args:
            tool_call: 工具调用
            tool: 工具实例

        Returns:
            详细信息字符串
        """
        lines = [f"工具: {tool.name}"]
        lines.append(f"描述: {tool.description}")

        # 参数信息
        for key, value in tool_call.parameters.items():
            if key == "content" and len(str(value)) > 100:
                lines.append(f"  {key}: ({len(str(value))} 字符)")
            elif key in ["old_string", "new_string"] and len(str(value)) > 50:
                lines.append(f"  {key}: \"{str(value)[:50]}...\" ({len(str(value))} 字符)")
            else:
                lines.append(f"  {key}: {value!r}")

        return "\n".join(lines)