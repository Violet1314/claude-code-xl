"""工具基类和结果定义"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum


class PermissionLevel(Enum):
    """权限级别"""
    ONCE = "once"           # 允许本次
    SESSION = "session"     # 允许本次会话全部
    NO_ONCE = "no_once"     # 仅本次拒绝

@dataclass
class ToolResult:
    """工具执行结果（结构化）"""
    success: bool
    output: str  # 返回给模型的完整内容（保持向后兼容）
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    interrupted: bool = False  # 是否因用户 CTRL+C 中断

    # --- 新增字段：用于 UI 渲染的结构化数据 ---
    display_output: Optional[str] = None  # 终端显示的简化版（Rich Markup）
    summary: Optional[str] = None         # 简短摘要（用于卡片标题或日志）
    raw_data: Optional[Any] = None        # 原始数据（如文件列表、Diff 对象，供未来 Web UI 使用）

    def __str__(self) -> str:
        if self.success:
            return f"✓ {self.summary or self.output[:50]}"
        if self.interrupted:
            return f"⚡ {self.error or '用户中断'}"
        return f"✗ {self.error or self.output}"


@dataclass
class ToolCall:
    """工具调用请求"""
    name: str                           # 工具名称
    parameters: Dict[str, Any]          # 参数字典
    id: Optional[str] = None            # 调用 ID（可选）

    def to_dict(self) -> dict:
        """转换为字典"""
        result = {"name": self.name, "parameters": self.parameters}
        if self.id:
            result["id"] = self.id
        return result

    def __str__(self) -> str:
        """返回简洁的字符串表示，长内容会被截断"""
        parts = []
        for k, v in self.parameters.items():
            if k == "content" and len(str(v)) > 100:
                # content 参数：只显示字符数
                parts.append(f"{k}=({len(str(v))} 字符)")
            elif k in ["old_string", "new_string"] and len(str(v)) > 50:
                # Edit 参数：显示前 50 字符
                preview = str(v)[:50].replace('\n', '\\n')
                parts.append(f"{k}=\"{preview}...\"")
            elif isinstance(v, str) and len(v) > 200:
                # 其他长字符串：截断
                preview = v[:100].replace('\n', '\\n')
                parts.append(f"{k}=\"{preview}...\" ({len(v)} 字符)")
            else:
                parts.append(f"{k}={v!r}")
        return f"{self.name}({', '.join(parts)})"


class Tool(ABC):
    """工具基类"""
    # 工具元信息
    name: str = ""
    description: str = ""
    # 当前执行的参数（在 execute 前设置，供 get_security_context 使用）
    parameters: Dict[str, Any] = {}

    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数的 JSON Schema"""
        pass

    @abstractmethod
    def execute(
        self,
        parameters: Dict[str, Any],
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> ToolResult:
        """执行工具

        Args:
            parameters: 工具参数
            interrupt_check: 中断检查函数，返回 True 表示应中断执行
        """
        pass

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        return None

    def is_read_only(self) -> bool:
        """是否为只读操作"""
        return False

    # --- 新增钩子：用于权限系统通用化 ---
    def get_security_context(self) -> Dict[str, Any]:
        """
        返回工具的安全上下文信息。
        权限管理器将基于此信息进行判断，而非硬编码工具名。
        
        Returns:
            {
                "is_sensitive": bool,      # 是否敏感操作
                "paths": List[str],        # 涉及的文件路径
                "command_preview": str     # 命令预览（针对 Bash）
            }
        """
        return {
            "is_sensitive": not self.is_read_only(),
            "paths": [],
            "command_preview": ""
        }


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具"""
        if not tool.name:
            raise ValueError("工具必须定义 name 属性")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有工具的信息"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.get_parameters_schema(),
            }
            for tool in self._tools.values()
        ]

# 全局工具注册表
registry = ToolRegistry()