"""工具调用解析器 - XML 格式"""
import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple
from xml.parsers.expat import ExpatError

from .base import ToolCall


class ToolParser:
    """工具调用解析器 - 从 AI 响应中提取 XML 格式的工具调用"""

    # XML 标签模式
    FUNCTION_CALLS_PATTERN = re.compile(
        r'<function_calls>\s*(.*?)\s*</function_calls>',
        re.DOTALL
    )

    @classmethod
    def parse(cls, text: str) -> List[ToolCall]:
        """
        从文本中提取所有工具调用

        Args:
            text: AI 响应文本

        Returns:
            工具调用列表
        """
        tool_calls = []

        # 查找所有 <function_calls> 块
        for match in cls.FUNCTION_CALLS_PATTERN.finditer(text):
            block = match.group(1)
            calls = cls._parse_invoke_blocks(block)
            tool_calls.extend(calls)

        return tool_calls

    @classmethod
    def _parse_invoke_blocks(cls, block: str) -> List[ToolCall]:
        """
        解析 invoke 块

        Args:
            block: function_calls 内部的内容

        Returns:
            工具调用列表
        """
        tool_calls = []

        # 使用正则匹配 <invoke> 标签
        invoke_pattern = re.compile(r'<invoke\s+name="([^"]+)"[^>]*>(.*?)</invoke>', re.DOTALL)

        for match in invoke_pattern.finditer(block):
            tool_name = match.group(1)
            params_block = match.group(2)

            # 解析参数
            parameters = cls._parse_parameters(params_block)

            tool_call = ToolCall(name=tool_name, parameters=parameters)
            tool_calls.append(tool_call)

        return tool_calls

    @classmethod
    def _parse_parameters(cls, params_block: str) -> dict:
        """
        解析参数块

        Args:
            params_block: <parameter> 标签块

        Returns:
            参数字典
        """
        parameters = {}

        # 匹配 <parameter name="xxx">value</parameter>
        param_pattern = re.compile(
            r'<parameter\s+name="([^"]+)"[^>]*>(.*?)</parameter>',
            re.DOTALL
        )

        for match in param_pattern.finditer(params_block):
            param_name = match.group(1)
            param_value = match.group(2).strip()

            # 尝试解析为合适的数据类型
            parameters[param_name] = cls._parse_value(param_value)

        return parameters

    @classmethod
    def _parse_value(cls, value: str) -> str:
        """
        解析参数值

        Args:
            value: 原始字符串值

        Returns:
            处理后的值
        """
        # 移除可能的 CDATA 包装
        if value.startswith('<![CDATA[') and value.endswith(']]>'):
            value = value[9:-3]

        # 处理转义字符
        value = value.replace('&lt;', '<')
        value = value.replace('&gt;', '>')
        value = value.replace('&amp;', '&')
        value = value.replace('&quot;', '"')
        value = value.replace('&#10;', '\n')

        return value

    @classmethod
    def extract_tool_blocks(cls, text: str) -> List[str]:
        """
        提取工具代码块（原始字符串）

        Args:
            text: AI 响应文本

        Returns:
            工具代码块列表
        """
        return [match.group(0) for match in cls.FUNCTION_CALLS_PATTERN.finditer(text)]

    @classmethod
    def remove_tool_blocks(cls, text: str) -> str:
        """
        从文本中移除所有工具代码块

        Args:
            text: AI 响应文本

        Returns:
            移除工具代码块后的文本
        """
        return cls.FUNCTION_CALLS_PATTERN.sub('', text)

    @classmethod
    def format_tool_call(cls, tool_call: ToolCall) -> str:
        """
        格式化工具调用为 XML

        Args:
            tool_call: 工具调用

        Returns:
            XML 格式字符串
        """
        lines = ['<function_calls>', f'<invoke name="{tool_call.name}">']

        for key, value in tool_call.parameters.items():
            # 转义特殊字符
            if isinstance(value, str):
                value = value.replace('&', '&amp;')
                value = value.replace('<', '&lt;')
                value = value.replace('>', '&gt;')
                value = value.replace('"', '&quot;')
            lines.append(f'<parameter name="{key}">{value}</parameter>')

        lines.append('</invoke>')
        lines.append('</function_calls>')

        return '\n'.join(lines)


def parse_tool_calls(text: str) -> List[ToolCall]:
    """
    便捷函数：从文本中解析工具调用

    Args:
        text: AI 响应文本

    Returns:
        工具调用列表
    """
    return ToolParser.parse(text)


def remove_tool_blocks(text: str) -> str:
    """
    便捷函数：移除工具代码块

    Args:
        text: AI 响应文本

    Returns:
        清理后的文本
    """
    return ToolParser.remove_tool_blocks(text)