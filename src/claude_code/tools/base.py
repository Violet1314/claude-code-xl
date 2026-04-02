"""工具基类和结果定义"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class PermissionLevel(Enum):
    """权限级别"""
    ONCE = "once"           # 允许（同工具同路径会话内缓存）
    NO_ONCE = "no_once"     # 仅本次拒绝

@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: str  # 返回给模型的完整内容
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    display_output: Optional[str] = None  # 终端显示用的省略版本（可选）

    def __str__(self) -> str:
        if self.success:
            return f"✓ {self.output}"
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

    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """
        获取参数的 JSON Schema

        Returns:
            参数定义字典
        """
        pass

    @abstractmethod
    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """
        执行工具

        Args:
            parameters: 工具参数

        Returns:
            执行结果
        """
        pass

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """
        验证参数

        Args:
            parameters: 待验证的参数

        Returns:
            错误信息，None 表示验证通过
        """
        return None

    def is_read_only(self) -> bool:
        """
        是否为只读操作

        Returns:
            True 表示只读，False 表示会修改文件系统
        """
        return False


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