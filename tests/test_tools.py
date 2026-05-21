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


    def test_edit_fuzzy_match_trailing_whitespace(self):
        """测试模糊匹配：old_string 有行尾空白但文件没有"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # 文件内容没有行尾空格
            f.write("def hello():\n    pass\n    return True\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            # old_string 有行尾空格（AI 从某些编辑器复制时常见）
            result = tool.execute({
                "file_path": temp_path,
                "old_string": "    pass   ",
                "new_string": "    print('hello')"
            })

            assert result.success
            assert result.metadata.get("fuzzy_matched") is True

            with open(temp_path, 'r') as f:
                content = f.read()
            assert "print('hello')" in content
        finally:
            os.unlink(temp_path)

    def test_edit_fuzzy_match_tab_indent(self):
        """测试模糊匹配：tab vs 空格缩进差异"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # 文件内容用 tab 缩进
            f.write("def hello():\n\tpass\n\treturn True\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            # old_string 用空格缩进（AI 常见情况）
            result = tool.execute({
                "file_path": temp_path,
                "old_string": "    pass",
                "new_string": "    print('hello')"
            })

            assert result.success
            assert result.metadata.get("fuzzy_matched") is True

            with open(temp_path, 'r') as f:
                content = f.read()
            assert "print('hello')" in content
        finally:
            os.unlink(temp_path)

    def test_edit_fuzzy_match_crlf(self):
        """测试模糊匹配：old_string 用 CRLF 但文件用 LF"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # 文件内容用 LF 换行（Python open 默认行为）
            f.write("def hello():\n    pass\n    return True\n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            # old_string 用 CRLF 换行（AI 在 Windows 环境下常见）
            result = tool.execute({
                "file_path": temp_path,
                "old_string": "    pass\r\n    return True",
                "new_string": "    print('hello')\n    return False"
            })

            assert result.success
            assert result.metadata.get("fuzzy_matched") is True

            with open(temp_path, 'r') as f:
                content = f.read()
            assert "print('hello')" in content
        finally:
            os.unlink(temp_path)

    def test_edit_fuzzy_match_multiple_results_still_fails(self):
        """测试模糊匹配：多处匹配仍然报错"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("    pass   \n    pass   \n")
            f.flush()
            temp_path = f.name

        try:
            tool = EditTool()
            result = tool.execute({
                "file_path": temp_path,
                "old_string": "pass",
                "new_string": "print('hello')"
            })

            # 多处匹配应该仍然失败
            assert not result.success
        finally:
            os.unlink(temp_path)

    def test_edit_exact_match_no_fuzzy_flag(self):
        """测试精确匹配成功时不标记 fuzzy"""
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
            assert result.metadata.get("fuzzy_matched") is False
        finally:
            os.unlink(temp_path)


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


# ============================================================
# v2.8.41 回归测试：Grep context / Glob / Bash 结构化输出 / Read 精确行段 / Todo 批量部分成功
# ============================================================

class TestGrepContextFix:
    """Grep context 模式修复回归测试"""

    def test_grep_with_context_no_crash(self):
        """Grep context>0 不崩溃，输出包含上下文行"""
        from claude_code.tools.builtins import GrepTool
        tool = GrepTool()
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            for i in range(20):
                f.write(f"line {i+1}: def func_{i}(): pass\n")
            temp_path = f.name
        try:
            result = tool.execute({
                "pattern": r"func_5",
                "path": temp_path,
                "context": 2,
            })
            assert result.success is True
            assert "func_5" in result.output
            # 上下文行也应出现（func_3, func_4, func_6, func_7）
            assert "func_3" in result.output or "func_4" in result.output
        finally:
            os.unlink(temp_path)

    def test_grep_context_zero_no_change(self):
        """Grep context=0 行为不变"""
        from claude_code.tools.builtins import GrepTool
        tool = GrepTool()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            for i in range(10):
                f.write(f"line {i+1}: value_{i}\n")
            temp_path = f.name
        try:
            result = tool.execute({
                "pattern": r"value_5",
                "path": temp_path,
                "context": 0,
            })
            assert result.success is True
            assert "value_5" in result.output
        finally:
            os.unlink(temp_path)

    def test_grep_files_with_matches_mode(self):
        """Grep output_mode=files_with_matches 只返回文件名"""
        from claude_code.tools.builtins import GrepTool
        tool = GrepTool()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write("import os\nimport sys\n")
            temp_path = f.name
        try:
            result = tool.execute({
                "pattern": r"import",
                "path": temp_path,
                "output_mode": "files_with_matches",
            })
            assert result.success is True
            # files_with_matches 模式不应包含行内容
            assert "import os" not in result.output or "found in" in result.output
        finally:
            os.unlink(temp_path)

    def test_grep_error_hint(self):
        """Grep 错误提示包含下一步建议"""
        from claude_code.tools.builtins import GrepTool
        tool = GrepTool()
        result = tool.execute({
            "pattern": r"[invalid",
            "path": ".",
        })
        assert result.success is False
        assert "下一步" in result.error


class TestGlobRegression:
    """Glob 回归测试"""

    def test_glob_no_match(self):
        """Glob 无匹配返回成功+提示"""
        from claude_code.tools.builtins import GlobTool
        tool = GlobTool()
        result = tool.execute({
            "pattern": "*.xyz_no_such_ext_12345",
            "path": ".",
        })
        assert result.success is True
        assert "未找到" in result.display_output or "No files" in result.output

    def test_glob_truncation_prefix(self):
        """Glob 截断提示在首行"""
        from claude_code.tools.builtins import GlobTool
        tool = GlobTool()
        # 使用一个会匹配很多文件的 pattern
        result = tool.execute({
            "pattern": "**/*.py",
        })
        if result.output and "共" in result.output:
            # 截断提示应在首行
            first_line = result.output.split('\n')[0]
            assert "共" in first_line or "条结果" in first_line

    def test_glob_error_hint(self):
        """Glob 目录不存在时包含下一步建议"""
        from claude_code.tools.builtins import GlobTool
        tool = GlobTool()
        result = tool.execute({
            "pattern": "*.py",
            "path": r"C:\no_such_dir_12345",
        })
        assert result.success is False
        assert "下一步" in result.error


class TestBashStructuredOutput:
    """Bash 结构化输出回归测试"""

    def test_bash_structured_error_output(self):
        """Bash 失败输出含 [exit=N] [STDERR] [STDOUT] 标签"""
        from claude_code.tools.builtins import BashTool
        tool = BashTool()
        result = tool.execute({
            "command": "python -c \"import sys; print('err', file=sys.stderr); sys.exit(1)\"",
            "timeout": 10,
        })
        assert result.success is False
        # 失败时结构化标签在 error 字段中
        error_text = result.error
        assert "[exit=" in error_text
        assert "[STDERR]" in error_text

    def test_bash_success_output(self):
        """Bash 成功输出包含内容"""
        from claude_code.tools.builtins import BashTool
        tool = BashTool()
        result = tool.execute({
            "command": "python -c \"print('hello')\"",
            "timeout": 10,
        })
        assert result.success is True
        assert "hello" in result.output


class TestReadExactRange:
    """Read 精确行段模式回归测试"""

    def test_read_with_offset_terminal_hint(self):
        """Read 指定 offset 时终端显示包含精确行段提示"""
        from claude_code.tools.builtins import ReadTool
        tool = ReadTool()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            for i in range(100):
                f.write(f"line {i+1}\n")
            temp_path = f.name
        try:
            result = tool.execute({
                "file_path": temp_path,
                "offset": 10,
                "limit": 5,
            })
            assert result.success is True
            assert "精确行段" in result.display_output
        finally:
            os.unlink(temp_path)

    def test_read_full_file_no_exact_hint(self):
        """Read 不指定 offset/limit 时终端不显示精确行段提示"""
        from claude_code.tools.builtins import ReadTool
        tool = ReadTool()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write("short file\n")
            temp_path = f.name
        try:
            result = tool.execute({
                "file_path": temp_path,
            })
            assert result.success is True
            assert "精确行段" not in result.display_output
        finally:
            os.unlink(temp_path)

    def test_read_error_hint_not_file(self):
        """Read 路径为目录时包含下一步建议"""
        from claude_code.tools.builtins import ReadTool
        tool = ReadTool()
        result = tool.execute({
            "file_path": ".",
        })
        assert result.success is False
        assert "下一步" in result.error


class TestTodoBatchPartialSuccess:
    """Todo 批量模式部分成功提示回归测试"""

    def setup_method(self):
        from claude_code.tools.builtins.todo import reset_todo_list, TodoCreateTool
        reset_todo_list()
        tool = TodoCreateTool()
        tool.execute({
            "items": [
                {"content": "任务1"},
                {"content": "任务2"},
                {"content": "任务3"},
            ]
        })

    def test_batch_all_success(self):
        """批量更新全部成功"""
        from claude_code.tools.builtins.todo import TodoUpdateTool
        tool = TodoUpdateTool()
        result = tool.execute({
            "updates": [
                {"id": "t1", "status": "in_progress"},
                {"id": "t2", "status": "in_progress"},
            ]
        })
        assert result.success is True
        assert "全部成功" in result.output
        assert "全部成功" in result.summary

    def test_batch_partial_success(self):
        """批量更新部分成功，success=True，提示部分成功"""
        from claude_code.tools.builtins.todo import TodoUpdateTool
        tool = TodoUpdateTool()
        # t1 可以 in_progress，t99 不存在
        result = tool.execute({
            "updates": [
                {"id": "t1", "status": "in_progress"},
                {"id": "t99", "status": "in_progress"},
            ]
        })
        assert result.success is True  # 部分成功
        assert "部分成功" in result.output
        assert "部分成功" in result.summary

    def test_batch_all_fail(self):
        """批量更新全部失败"""
        from claude_code.tools.builtins.todo import TodoUpdateTool
        tool = TodoUpdateTool()
        result = tool.execute({
            "updates": [
                {"id": "t99", "status": "in_progress"},
                {"id": "t98", "status": "in_progress"},
            ]
        })
        assert result.success is False
        assert "全部失败" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])