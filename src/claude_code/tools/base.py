"""工具基类和结果定义"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class PermissionLevel(Enum):
    """权限级别"""
    ONCE = "once"           # 仅本次允许
    ALL = "all"             # 全局授权（所有工具自动通过）
    NO_ONCE = "no_once"     # 仅本次拒绝


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

    def get_tools_prompt(self) -> str:
        """
        生成给 AI 的工具使用提示

        Returns:
            工具使用说明文本
        """
        lines = ["# 可用工具\n"]

        # 重要说明 - 强调文件访问能力
        lines.append("## ⚠️ 重要：你具备文件系统访问能力\n")
        lines.append("**你可以直接访问用户的本地文件系统**，无需让用户手动粘贴内容。")
        lines.append("当用户提供文件路径（如 `E:\\path\\to\\file.py` 或 `/home/user/file.py`）时：")
        lines.append('- **立即调用 Read 工具读取文件**，不要说「我无法访问」或「请粘贴内容」')
        lines.append("- 你可以读取、写入、编辑、搜索用户本机上的任何文件")
        lines.append("- 工具调用使用 **XML 格式**，不要使用 JSON 或其他格式\n")

        # 调用示例
        lines.append("## 调用示例\n")
        lines.append("用户说：\"分析 E:\\project\\app.py\"")
        lines.append("你应该立即调用：")
        lines.append("```xml")
        lines.append("<function_calls>")
        lines.append('<invoke name="Read">')
        lines.append('<parameter name="file_path">E:\\project\\app.py</parameter>')
        lines.append("</invoke>")
        lines.append("</function_calls>")
        lines.append("```\n")

        # 工具使用原则
        lines.append("## 工具使用原则\n")
        lines.append("1. **主动调用**：用户提到文件路径时，立即使用 Read 工具读取")
        lines.append("2. **精确搜索**：使用精确的模式减少搜索结果数量")
        lines.append("3. **分段读取**：大文件使用 offset/limit 参数，只读需要的部分")
        lines.append("4. **批量操作**：尽量一次完成多个相关操作，减少工具调用次数\n")

        # 按需索取原则
        lines.append("## 按需索取原则\n")
        lines.append("1. **摘要优先**：首次读取大文件时，默认获取结构摘要")
        lines.append("2. **精准定位**：根据摘要确定需要的行号范围，用 offset/limit 读取具体部分")
        lines.append("3. **避免重复**：记住已读取的内容，不要多次读取同一文件的相同部分\n")

        lines.append("## 调用格式\n")
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