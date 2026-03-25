"""工具基类和结果定义"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class PermissionLevel(Enum):
    """权限级别"""
    ONCE = "once"       # 仅本次
    ALWAYS = "always"   # 总是允许（当前会话）


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

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
        params_str = ", ".join(f"{k}={v!r}" for k, v in self.parameters.items())
        return f"{self.name}({params_str})"


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

    def get_tools_prompt(self) -> str:
        """
        生成给 AI 的工具使用提示

        Returns:
            工具使用说明文本
        """
        lines = ["# 可用工具\n"]
        lines.append("使用以下 XML 格式调用工具：\n")
        lines.append("```xml")
        lines.append("<function_calls>")
        lines.append('<invoke name="工具名">')
        lines.append('<parameter name="参数名">参数值</parameter>')
        lines.append("</invoke>")
        lines.append("</function_calls>")
        lines.append("```\n")
        lines.append("## 工具列表\n")

        for tool in self._tools.values():
            lines.append(f"### {tool.name}")
            lines.append(f"{tool.description}\n")
            lines.append("参数:")
            schema = tool.get_parameters_schema()
            for param_name, param_info in schema.get("properties", {}).items():
                required = param_name in schema.get("required", [])
                req_mark = "*" if required else ""
                lines.append(f"  - `{param_name}`{req_mark}: {param_info.get('description', '')}")
            lines.append("")

        return "\n".join(lines)


# 全局工具注册表
registry = ToolRegistry()