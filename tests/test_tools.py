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

    def test_edit_multiple_matches(self):
        """测试多处匹配时要求添加上下文"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def foo():\n    pass\n\ndef bar():\n    pass\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            # "pass" 出现两次，应该失败并要求添加上下文
            result = tool.execute({
                "file_path": temp_path,
                "old_string": "pass",
                "new_string": "return True"
            })

            assert not result.success
            assert "多处匹配" in result.error or "多" in result.error
        finally:
            os.unlink(temp_path)

    def test_edit_with_context_unique(self):
        """测试添加上下文后替换成功"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def foo():\n    pass\n\ndef bar():\n    pass\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            # 添加上下文使其唯一
            result = tool.execute({
                "file_path": temp_path,
                "old_string": "def foo():\n    pass",
                "new_string": "def foo():\n    return True"
            })

            assert result.success

            with open(temp_path, 'r') as f:
                content = f.read()
            assert "return True" in content
            assert "def bar():\n    pass" in content  # bar 函数未受影响
        finally:
            os.unlink(temp_path)

    def test_edit_no_match_with_hint(self):
        """测试无匹配时返回清晰指导"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def hello():\n    print('world')\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            result = tool.execute({
                "file_path": temp_path,
                "old_string": "print('hello')",  # 不存在
                "new_string": "print('goodbye')"
            })

            assert not result.success
            # 应提供清晰的操作指导
            assert "Read" in result.error or "读取" in result.error or "精确" in result.error
        finally:
            os.unlink(temp_path)

    def test_edit_preserves_indentation(self):
        """测试保持缩进的精确匹配"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test():\n    if True:\n        pass\n    return None\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            # 精确复制带缩进的代码
            result = tool.execute({
                "file_path": temp_path,
                "old_string": "        pass",
                "new_string": "        return 1"
            })

            assert result.success

            with open(temp_path, 'r') as f:
                content = f.read()
            assert "        return 1" in content
            assert "        pass" not in content
        finally:
            os.unlink(temp_path)

    def test_edit_empty_new_string(self):
        """测试删除内容（new_string 为空）"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test():\n    # TODO: implement\n    pass\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            result = tool.execute({
                "file_path": temp_path,
                "old_string": "    # TODO: implement\n",
                "new_string": ""
            })

            assert result.success

            with open(temp_path, 'r') as f:
                content = f.read()
            assert "# TODO" not in content
        finally:
            os.unlink(temp_path)

    def test_edit_line_range_basic(self):
        """测试行号范围模式：替换指定行"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("alpha\nbeta\ngamma\ndelta\nepsilon\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            result = tool.execute({
                "file_path": temp_path,
                "start_line": 2,
                "end_line": 3,
                "new_string": "BETA\nGAMMA"
            })

            assert result.success

            with open(temp_path, 'r') as f:
                content = f.read()
            assert "BETA" in content
            assert "GAMMA" in content
            assert "alpha" in content
            assert "delta" in content
            assert "epsilon" in content
            assert "beta" not in content
            assert "gamma" not in content
        finally:
            os.unlink(temp_path)

    def test_edit_line_range_single_line(self):
        """测试行号范围模式：替换单行"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def hello():\n    pass\n\ndef world():\n    pass\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            result = tool.execute({
                "file_path": temp_path,
                "start_line": 2,
                "end_line": 2,
                "new_string": "    return True"
            })

            assert result.success

            with open(temp_path, 'r') as f:
                content = f.read()
            assert "return True" in content
            # 第2行的 pass 被替换了，但第5行 world() 的 pass 仍在
            lines = content.splitlines()
            assert lines[1] == "    return True"  # 第2行被替换
            assert "def world" in content  # 其他部分不受影响
        finally:
            os.unlink(temp_path)

    def test_edit_line_range_returns_replaced_content(self):
        """测试行号范围模式：返回被替换的原始内容供确认"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("old1\nold2\nold3\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            result = tool.execute({
                "file_path": temp_path,
                "start_line": 1,
                "end_line": 2,
                "new_string": "new1\nnew2"
            })

            assert result.success
            # 输出中应包含被替换的原始内容
            assert "old1" in result.output
            assert "old2" in result.output
            assert "new1" in result.output
        finally:
            os.unlink(temp_path)

    def test_edit_line_range_out_of_bounds(self):
        """测试行号范围模式：end_line 超出文件行数时自动截断"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("line1\nline2\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            result = tool.execute({
                "file_path": temp_path,
                "start_line": 2,
                "end_line": 999,
                "new_string": "replaced"
            })

            assert result.success

            with open(temp_path, 'r') as f:
                content = f.read()
            assert "line1" in content
            assert "replaced" in content
            assert "line2" not in content
        finally:
            os.unlink(temp_path)

    def test_edit_line_range_invalid_params(self):
        """测试行号范围模式：参数验证"""
        tool = EditTool()

        # 只提供 start_line 没有 end_line
        result = tool.validate_parameters({
            "file_path": "/tmp/test.py",
            "start_line": 1,
            "new_string": "hello"
        })
        assert result is not None
        assert "同时提供" in result

        # start_line < 1
        result = tool.validate_parameters({
            "file_path": "/tmp/test.py",
            "start_line": 0,
            "end_line": 5,
            "new_string": "hello"
        })
        assert result is not None
        assert ">=" in result

        # end_line < start_line
        result = tool.validate_parameters({
            "file_path": "/tmp/test.py",
            "start_line": 5,
            "end_line": 3,
            "new_string": "hello"
        })
        assert result is not None
        assert ">=" in result

    def test_edit_no_old_string_no_line_range(self):
        """测试既没有 old_string 也没有 start_line/end_line 时报错"""
        tool = EditTool()
        result = tool.validate_parameters({
            "file_path": "/tmp/test.py",
            "new_string": "hello"
        })
        assert result is not None
        assert "old_string" in result or "start_line" in result


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
                "pattern": r"def\s+\w+",
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
                "pattern": r"import\s+os",
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


class TestToolResultStructure:
    """v2.8.0 新增：验证 ToolResult 结构化输出"""
    
    def test_read_tool_structured_output(self):
        """测试 Read 工具返回结构化数据"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test():\n    pass\n")
            f.flush()
            temp_path = f.name
        
        try:
            tool = ReadTool()
            result = tool.execute({"file_path": temp_path})
            
            assert result.success
            # 1. 验证 summary 字段存在且非空
            assert result.summary is not None
            # 修复：不要硬编码文件名，而是检查是否包含 .py 后缀
            assert ".py" in result.summary
            
            # 2. 验证 metadata 包含关键信息
            assert "file_path" in result.metadata
            assert "total_lines" in result.metadata
            # 文件 "def test():\n    pass\n" 实际是 2 行（末尾换行表示第2行结束，不是空行）
            assert result.metadata["total_lines"] == 2
            
        finally:
            os.unlink(temp_path)

    def test_write_tool_security_context(self):
        """测试 Write 工具的安全上下文"""
        tool = WriteTool()
        # 模拟设置参数（通常由 executor 传入，这里手动模拟以测试钩子）
        tool.parameters = {"file_path": "test.py"}
        
        context = tool.get_security_context()
        assert context["is_sensitive"] is True
        assert "test.py" in context["paths"]

    def test_read_tool_security_context(self):
        """测试 Read 工具的安全上下文（只读应不敏感）"""
        tool = ReadTool()
        tool.parameters = {"file_path": "test.py"}
        
        context = tool.get_security_context()
        assert context["is_sensitive"] is False


class TestBashToolBasics:
    """Bash 工具基础测试（v2.8.0 补充）"""
    
    def test_bash_simple_command(self):
        """测试简单的 Bash 命令（Windows PowerShell 兼容）"""
        from claude_code.tools.builtins import BashTool
        tool = BashTool()
        
        # 使用 echo 命令，它在 PowerShell 中也通用
        result = tool.execute({"command": "echo 'Hello World'"})
        
        assert result.success
        assert "Hello World" in result.output
    
    def test_bash_dangerous_check_method(self):
        """测试 CommandSafetyChecker 的危险命令检测"""
        from claude_code.tools.builtins import BashTool
        from claude_code.tools.command_safety import CommandSafetyChecker
        checker = CommandSafetyChecker()
        
        # 1. 测试危险命令
        is_dangerous, reason = checker.check_dangerous("rm -rf /")
        assert is_dangerous is True
        assert "危险" in reason or "损坏" in reason
        
        # 2. 测试安全命令
        is_dangerous, reason = checker.check_dangerous("ls")
        assert is_dangerous is False
        
        # 3. 测试 BashTool 委托
        tool = BashTool()
        assert tool._safety_checker is checker or isinstance(tool._safety_checker, CommandSafetyChecker)

    def test_bash_security_context(self):
        """测试 Bash 工具的安全上下文"""
        from claude_code.tools.builtins import BashTool
        tool = BashTool()
        tool.parameters = {"command": "ls"}
        
        context = tool.get_security_context()
        assert "command_preview" in context
        assert context["command_preview"] == "ls"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])