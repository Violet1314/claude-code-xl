"""工具调用管理器 - 兼容多种模型的工具调用方式"""
import re
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from .base import ToolCall, ToolRegistry, registry


@dataclass
class ToolDefinition:
    """工具定义（OpenAI 格式）"""
    type: str = "function"
    function: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "function": self.function,
        }


class ToolCallingManager:
    """
    工具调用管理器

    支持三种模式：
    1. native: 使用 API 原生 tool calling（GPT, Claude, DeepSeek, Qwen, Gemini 等）
    2. xml: 在 prompt 中定义 XML 格式，解析文本
    3. kimi: 解析 KIMI 特殊格式
    """

    # KIMI 格式正则
    KIMI_PATTERN = re.compile(
        r'<\|tool_calls_section_begin\|>.*?<\|tool_call_begin\|>'
        r'functions\.(\w+):(\d+)'
        r'<\|tool_call_argument_begin\|>(\{.*?\})'
        r'<\|tool_call_end\|>',
        re.DOTALL
    )

    def __init__(self, tool_registry: ToolRegistry):
        self.registry = tool_registry

    # ============================================================
    # 生成工具定义
    # ============================================================

    def get_tools_definition(self) -> List[Dict[str, Any]]:
        """
        生成 OpenAI 格式的工具定义列表

        Returns:
            工具定义列表，用于 API 请求的 tools 参数
        """
        tools = []

        for tool in self.registry._tools.values():
            tool_def = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.get_parameters_schema(),
                }
            }
            tools.append(tool_def)

        return tools

    def get_tools_prompt(self) -> str:
        """
        生成 prompt 中的工具说明（用于非原生模式）

        Returns:
            工具使用说明文本
        """
        lines = ["# 可用工具\n"]

        # 重要说明 - 强调文件访问能力
        lines.append("## 重要：你具备文件系统访问能力\n")
        lines.append("**你可以直接访问用户的本地文件系统**，无需让用户手动粘贴内容。")
        lines.append("当用户提供文件路径时，立即调用工具读取。\n")

        # 调用格式
        lines.append("## 调用格式\n")
        lines.append("```xml")
        lines.append("<function_calls>")
        lines.append('<invoke name="工具名">')
        lines.append('<parameter name="参数名">参数值</parameter>')
        lines.append("</invoke>")
        lines.append("</function_calls>")
        lines.append("```\n")

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

        # 工具列表
        lines.append("## 工具列表\n")

        for tool in self.registry._tools.values():
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

    # ============================================================
    # 解析工具调用
    # ============================================================

    def parse_tool_calls(
        self,
        response_text: str,
        native_tool_calls: List[Dict[str, Any]] = None,
        mode: str = "native"
    ) -> List[ToolCall]:
        """
        统一解析工具调用

        Args:
            response_text: AI 响应文本
            native_tool_calls: API 原生返回的 tool_calls
            mode: 解析模式 (native/xml/kimi)

        Returns:
            工具调用列表
        """
        if mode == "native" and native_tool_calls:
            return self._parse_native(native_tool_calls)
        elif mode == "kimi":
            # KIMI 可能同时输出文本和工具调用
            calls = self._parse_kimi(response_text)
            if calls:
                return calls
            # 回退到 XML 解析
            return self._parse_xml(response_text)
        else:
            # 默认使用 XML 解析
            return self._parse_xml(response_text)

    def _parse_native(self, tool_calls: List[Dict[str, Any]]) -> List[ToolCall]:
        """解析原生 tool_calls 格式"""
        result = []

        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")

            # 解析参数
            args_str = func.get("arguments", "{}")
            try:
                if isinstance(args_str, str):
                    parameters = json.loads(args_str)
                else:
                    parameters = args_str
            except json.JSONDecodeError:
                parameters = {}

            result.append(ToolCall(name=name, parameters=parameters))

        return result

    def _parse_xml(self, text: str) -> List[ToolCall]:
        """解析 XML 格式的工具调用"""
        from .parser import ToolParser
        return ToolParser.parse(text)

    def _parse_kimi(self, text: str) -> List[ToolCall]:
        """解析 KIMI 特殊格式"""
        result = []

        for match in self.KIMI_PATTERN.finditer(text):
            tool_name = match.group(1)
            args_str = match.group(3)

            try:
                parameters = json.loads(args_str)
            except json.JSONDecodeError:
                parameters = {}

            # KIMI 使用 file_path 而非 file_path
            if "file_path" in parameters:
                parameters["file_path"] = parameters.pop("file_path")

            result.append(ToolCall(name=tool_name, parameters=parameters))

        return result

    # ============================================================
    # 构建工具结果
    # ============================================================

    def build_tool_result_message(
        self,
        tool_call_id: str,
        result: str
    ) -> Dict[str, Any]:
        """
        构建工具结果消息（用于原生模式的后续请求）

        Args:
            tool_call_id: 工具调用 ID
            result: 工具执行结果

        Returns:
            工具结果消息
        """
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        }


# 全局工具调用管理器
tool_calling_manager = ToolCallingManager(registry)