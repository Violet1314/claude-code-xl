"""工具解析器测试"""
import pytest
import sys
import os

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from claude_code.tools.parser import ToolParser, parse_tool_calls
from claude_code.tools.base import ToolCall


class TestToolParser:
    """工具解析器测试"""

    def test_parse_single_read_tool(self):
        """测试解析单个 Read 工具"""
        text = '''这是一些文本

<function_calls>
<invoke name="Read">
<parameter name="file_path">src/app.py</parameter>
</invoke>
</function_calls>

更多文本'''

        tool_calls = ToolParser.parse(text)

        assert len(tool_calls) == 1
        assert tool_calls[0].name == "Read"
        assert tool_calls[0].parameters["file_path"] == "src/app.py"

    def test_parse_multiple_tools(self):
        """测试解析多个工具调用"""
        text = '''<function_calls>
<invoke name="Read">
<parameter name="file_path">file1.py</parameter>
</invoke>
<invoke name="Glob">
<parameter name="pattern">**/*.py</parameter>
</invoke>
</function_calls>'''

        tool_calls = ToolParser.parse(text)

        assert len(tool_calls) == 2
        assert tool_calls[0].name == "Read"
        assert tool_calls[0].parameters["file_path"] == "file1.py"
        assert tool_calls[1].name == "Glob"
        assert tool_calls[1].parameters["pattern"] == "**/*.py"

    def test_parse_edit_tool(self):
        """测试解析 Edit 工具（多行参数）"""
        text = '''<function_calls>
<invoke name="Edit">
<parameter name="file_path">src/utils.py</parameter>
<parameter name="old_string">def hello():
    pass</parameter>
<parameter name="new_string">def hello_world():
    print("Hello")
    return True</parameter>
</invoke>
</function_calls>'''

        tool_calls = ToolParser.parse(text)

        assert len(tool_calls) == 1
        assert tool_calls[0].name == "Edit"
        assert "old_string" in tool_calls[0].parameters
        assert "new_string" in tool_calls[0].parameters
        assert "def hello():" in tool_calls[0].parameters["old_string"]

    def test_parse_write_tool(self):
        """测试解析 Write 工具"""
        text = '''<function_calls>
<invoke name="Write">
<parameter name="file_path">new_file.py</parameter>
<parameter name="content">print("Hello World")</parameter>
</invoke>
</function_calls>'''

        tool_calls = ToolParser.parse(text)

        assert len(tool_calls) == 1
        assert tool_calls[0].name == "Write"
        assert tool_calls[0].parameters["file_path"] == "new_file.py"

    def test_parse_no_tools(self):
        """测试没有工具调用的文本"""
        text = "这是一段普通文本，没有工具调用。"

        tool_calls = ToolParser.parse(text)

        assert len(tool_calls) == 0

    def test_parse_grep_tool(self):
        """测试解析 Grep 工具"""
        text = '''<function_calls>
<invoke name="Grep">
<parameter name="pattern">def\\s+\\w+</parameter>
<parameter name="path">src</parameter>
<parameter name="type">py</parameter>
</invoke>
</function_calls>'''

        tool_calls = ToolParser.parse(text)

        assert len(tool_calls) == 1
        assert tool_calls[0].name == "Grep"
        assert tool_calls[0].parameters["pattern"] == "def\\s+\\w+"
        assert tool_calls[0].parameters["path"] == "src"

    def test_remove_tool_blocks(self):
        """测试移除工具代码块"""
        text = '''开始文本

<function_calls>
<invoke name="Read">
<parameter name="file_path">test.py</parameter>
</invoke>
</function_calls>

结束文本'''

        cleaned = ToolParser.remove_tool_blocks(text)

        assert "<function_calls>" not in cleaned
        assert "开始文本" in cleaned
        assert "结束文本" in cleaned

    def test_format_tool_call(self):
        """测试格式化工具调用"""
        tool_call = ToolCall(
            name="Read",
            parameters={"file_path": "src/app.py"}
        )

        formatted = ToolParser.format_tool_call(tool_call)

        assert "<function_calls>" in formatted
        assert 'name="Read"' in formatted
        assert 'name="file_path"' in formatted
        assert "src/app.py" in formatted

    def test_escape_special_chars(self):
        """测试特殊字符转义"""
        tool_call = ToolCall(
            name="Edit",
            parameters={
                "file_path": "test.py",
                "old_string": "if x < 10 & y > 5:",
                "new_string": "if x >= 10:"
            }
        )

        formatted = ToolParser.format_tool_call(tool_call)

        assert "&lt;" in formatted or "< 10" in formatted  # 转义或原文

    def test_convenience_function(self):
        """测试便捷函数"""
        text = '''<function_calls>
<invoke name="Read">
<parameter name="file_path">test.py</parameter>
</invoke>
</function_calls>'''

        tool_calls = parse_tool_calls(text)

        assert len(tool_calls) == 1
        assert tool_calls[0].name == "Read"

    def test_multiple_function_calls_blocks(self):
        """测试多个独立的 function_calls 块"""
        text = '''<function_calls>
<invoke name="Read">
<parameter name="file_path">file1.py</parameter>
</invoke>
</function_calls>

一些说明文字

<function_calls>
<invoke name="Read">
<parameter name="file_path">file2.py</parameter>
</invoke>
</function_calls>'''

        tool_calls = ToolParser.parse(text)

        assert len(tool_calls) == 2
        assert tool_calls[0].parameters["file_path"] == "file1.py"
        assert tool_calls[1].parameters["file_path"] == "file2.py"


class TestToolCall:
    """ToolCall 数据类测试"""

    def test_to_dict(self):
        """测试转换为字典"""
        tool_call = ToolCall(
            name="Read",
            parameters={"file_path": "test.py"},
            id="call_123"
        )

        result = tool_call.to_dict()

        assert result["name"] == "Read"
        assert result["parameters"]["file_path"] == "test.py"
        assert result["id"] == "call_123"

    def test_str_representation(self):
        """测试字符串表示"""
        tool_call = ToolCall(
            name="Read",
            parameters={"file_path": "test.py"}
        )

        s = str(tool_call)

        assert "Read" in s
        assert "file_path" in s


if __name__ == "__main__":
    pytest.main([__file__, "-v"])