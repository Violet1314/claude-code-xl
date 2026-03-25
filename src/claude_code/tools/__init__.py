"""工具系统"""
from .base import (
    Tool,
    ToolCall,
    ToolResult,
    ToolRegistry,
    PermissionLevel,
    registry,
)
from .parser import ToolParser, parse_tool_calls, remove_tool_blocks
from .permission import PermissionManager, PermissionDecision
from .permission_ui import PermissionUI
from .executor import ToolExecutor, ExecutionResult, ExecutionReport, create_executor

# 便捷函数
def register_builtin_tools() -> None:
    """注册所有内置工具"""
    from .builtins import register_all_tools
    register_all_tools(registry)


__all__ = [
    # 基类
    "Tool",
    "ToolCall",
    "ToolResult",
    "ToolRegistry",
    "PermissionLevel",
    # 解析器
    "ToolParser",
    "parse_tool_calls",
    "remove_tool_blocks",
    # 权限
    "PermissionManager",
    "PermissionDecision",
    "PermissionUI",
    # 执行器
    "ToolExecutor",
    "ExecutionResult",
    "ExecutionReport",
    "create_executor",
    # 全局注册表
    "registry",
    # 便捷函数
    "register_builtin_tools",
]