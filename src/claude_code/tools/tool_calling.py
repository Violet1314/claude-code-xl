"""工具调用管理器 - Native Tool Calling"""
import json
from typing import List, Dict, Any
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

    使用 Native Tool Calling 模式，通过 API 原生支持实现工具调用。
    支持的模型：GPT、Claude、DeepSeek、Qwen、Gemini、GLM 等主流模型。
    """

    def __init__(self, tool_registry: ToolRegistry):
        self.registry = tool_registry

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

    def parse_tool_calls(
        self,
        native_tool_calls: List[Dict[str, Any]]
    ) -> List[ToolCall]:
        """
        解析原生 tool_calls 格式

        Args:
            native_tool_calls: API 原生返回的 tool_calls

        Returns:
            工具调用列表
        """
        result = []

        for tc in native_tool_calls:
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

    def build_tool_result_message(
        self,
        tool_call_id: str,
        result: str
    ) -> Dict[str, Any]:
        """
        构建工具结果消息（用于后续请求）

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