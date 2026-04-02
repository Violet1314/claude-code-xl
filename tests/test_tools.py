"""工具系统测试"""
import pytest
import sys
import os
import tempfile
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from claude_code.tools.base import Tool, ToolResult, ToolCall, ToolRegistry
from claude_code.tools.builtins import ReadTool, GlobTool, GrepTool, WriteTool, EditTool


class TestToolRegistry:
    """工具注册表测试"""

    def test_register_tool(self):
        """测试注册工具"""
        registry = ToolRegistry()
        read_tool = ReadTool()
        registry.register(read_tool)

        assert registry.get("Read") == read_tool

    def test_list_tools(self):
        """测试列出工具"""
        registry = ToolRegistry()
        registry.register(ReadTool())
        registry.register(WriteTool())

        tools = registry.list_tools()

        assert len(tools) == 2
        tool_names = [t["name"] for t in tools]
        assert "Read" in tool_names
        assert "Write" in tool_names

class TestReadTool:
    """Read 工具测试"""

    def test_read_existing_file(self):
        """测试读取存在的文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("print('hello')\nprint('world')\n")
            f.flush()
            temp_path = f.name

        try:
            tool = ReadTool()
            result = tool.execute({"file_path": temp_path})

            assert result.success
            assert "print('hello')" in result.output
            assert "print('world')" in result.output
        finally:
            os.unlink(temp_path)

    def test_read_nonexistent_file(self):
        """测试读取不存在的文件"""
        tool = ReadTool()
        result = tool.execute({"file_path": "/nonexistent/path/file.py"})

        assert not result.success
        assert "不存在" in result.error

    def test_read_with_offset(self):
        """测试带偏移量读取"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("line1\nline2\nline3\nline4\nline5\n")
            f.flush()
            temp_path = f.name

        try:
            tool = ReadTool()
            result = tool.execute({"file_path": temp_path, "offset": 3, "limit": 2})

            assert result.success
            assert "line3" in result.output
            assert "line4" in result.output
            assert "line1" not in result.output
        finally:
            os.unlink(temp_path)

    def test_read_only_flag(self):
        """测试只读标志"""
        tool = ReadTool()
        assert tool.is_read_only() is True


class TestWriteTool:
    """Write 工具测试"""

    def test_write_new_file(self):
        """测试写入新文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "new_file.py")

            tool = WriteTool()
            result = tool.execute({
                "file_path": file_path,
                "content": "print('hello')"
            })

            assert result.success
            assert os.path.exists(file_path)

            with open(file_path, 'r') as f:
                content = f.read()
            assert content == "print('hello')"

    def test_overwrite_existing_file(self):
        """测试覆盖现有文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("old content")
            temp_path = f.name

        try:
            tool = WriteTool()
            result = tool.execute({
                "file_path": temp_path,
                "content": "new content"
            })

            assert result.success

            with open(temp_path, 'r') as f:
                content = f.read()
            assert content == "new content"
        finally:
            os.unlink(temp_path)

    def test_write_create_directories(self):
        """测试自动创建目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "subdir", "deep", "file.py")

            tool = WriteTool()
            result = tool.execute({
                "file_path": file_path,
                "content": "test"
            })

            assert result.success
            assert os.path.exists(file_path)

    def test_write_not_read_only(self):
        """测试非只读标志"""
        tool = WriteTool()
        assert tool.is_read_only() is False


class TestEditTool:
    """Edit 工具测试"""

    def test_edit_exact_match(self):
        """测试精确替换"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def hello():\n    pass\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            result = tool.execute({
                "file_path": temp_path,
                "old_string": "pass",
                "new_string": "print('hello')"
            })

            assert result.success

            with open(temp_path, 'r') as f:
                content = f.read()
            assert "print('hello')" in content
            assert "pass" not in content
        finally:
            os.unlink(temp_path)

    def test_edit_not_found(self):
        """测试找不到匹配内容"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("some content")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            result = tool.execute({
                "file_path": temp_path,
                "old_string": "nonexistent",
                "new_string": "replacement"
            })

            assert not result.success
            assert "未找到" in result.error
        finally:
            os.unlink(temp_path)

    def test_edit_nonexistent_file(self):
        """测试编辑不存在的文件"""
        tool = EditTool()
        result = tool.execute({
            "file_path": "/nonexistent/file.py",
            "old_string": "old",
            "new_string": "new"
        })

        assert not result.success


class TestGlobTool:
    """Glob 工具测试"""

    def test_glob_find_files(self):
        """测试查找文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一些文件
            Path(tmpdir, "file1.py").touch()
            Path(tmpdir, "file2.py").touch()
            Path(tmpdir, "readme.md").touch()

            tool = GlobTool()
            result = tool.execute({"pattern": "*.py", "path": tmpdir})

            assert result.success
            assert "file1.py" in result.output
            assert "file2.py" in result.output
            assert "readme.md" not in result.output

    def test_glob_recursive(self):
        """测试递归查找"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建嵌套目录
            subdir = Path(tmpdir, "src", "utils")
            subdir.mkdir(parents=True)
            Path(subdir, "helper.py").touch()

            tool = GlobTool()
            result = tool.execute({"pattern": "**/*.py", "path": tmpdir})

            assert result.success
            assert "helper.py" in result.output


class TestGrepTool:
    """Grep 工具测试"""

    def test_grep_find_pattern(self):
        """测试搜索模式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir, "test.py")
            file_path.write_text("def hello():\n    print('hello')\n    return True\n")

            tool = GrepTool()
            result = tool.execute({
                "pattern": "def\\s+\\w+",
                "path": str(tmpdir)
            })

            assert result.success
            assert "def hello" in result.output

    def test_grep_no_match(self):
        """测试无匹配"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir, "test.py")
            file_path.write_text("print('hello')")

            tool = GrepTool()
            result = tool.execute({
                "pattern": "import\\s+os",
                "path": str(tmpdir)
            })

            assert result.success
            assert "No matches found" in result.output

class TestToolCall:
    """ToolCall 数据类测试"""

    def test_create_tool_call(self):
        """测试创建工具调用"""
        call = ToolCall(
            name="Read",
            parameters={"file_path": "test.py"}
        )

        assert call.name == "Read"
        assert call.parameters["file_path"] == "test.py"

    def test_tool_call_to_dict(self):
        """测试转换为字典"""
        call = ToolCall(
            name="Edit",
            parameters={
                "file_path": "test.py",
                "old_string": "old",
                "new_string": "new"
            },
            id="call_123"
        )

        d = call.to_dict()

        assert d["name"] == "Edit"
        assert d["parameters"]["file_path"] == "test.py"
        assert d["id"] == "call_123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])