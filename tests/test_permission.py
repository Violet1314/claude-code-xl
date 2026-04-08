"""权限系统和执行器测试"""
import pytest
import sys
import os
import tempfile
# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from claude_code.tools.base import ToolCall, ToolResult, ToolRegistry, PermissionLevel
from claude_code.tools.permission import PermissionManager, PermissionDecision
from claude_code.tools.executor import ToolExecutor, ExecutionResult, ExecutionReport
from claude_code.tools.builtins import ReadTool, WriteTool


class TestPermissionLevel:
    """权限级别测试"""

    def test_permission_values(self):
        """测试权限值"""
        assert PermissionLevel.ONCE.value == "once"
        assert PermissionLevel.NO_ONCE.value == "no_once"

    def test_permission_comparison(self):
        """测试权限比较"""
        assert PermissionLevel.ONCE != PermissionLevel.NO_ONCE


class TestPermissionDecision:
    """权限决定测试"""

    def test_allowed_decision(self):
        """测试允许决定"""
        decision = PermissionDecision(allowed=True, level=PermissionLevel.ONCE)
        assert decision.allowed is True
        assert decision.level == PermissionLevel.ONCE

    def test_denied_decision(self):
        """测试拒绝决定"""
        decision = PermissionDecision(allowed=False, level=PermissionLevel.NO_ONCE)
        assert decision.allowed is False
        assert decision.level == PermissionLevel.NO_ONCE


class TestPermissionManager:
    """权限管理器测试"""

    def test_set_permission(self):
        """测试设置权限"""
        manager = PermissionManager()
        manager.set_permission("write", PermissionLevel.NO_ONCE, "test.py")
        level = manager.get_cached_permission("write", "test.py")
        assert level == PermissionLevel.NO_ONCE

    def test_clear_session(self):
        """测试清除会话"""
        manager = PermissionManager()
        manager.set_permission("write", PermissionLevel.NO_ONCE, "test.py")
        manager.clear_session()
        decision = manager.get_cached_permission("write", "test.py")
        assert decision is None  # 清除后无缓存规则


class TestToolRegistry:
    """工具注册表测试"""

    def test_register_tool(self):
        """测试注册工具"""
        registry = ToolRegistry()
        registry.register(ReadTool())
        tool = registry.get("Read")
        assert tool is not None
        assert tool.name == "Read"

    def test_get_tool(self):
        """测试获取工具"""
        registry = ToolRegistry()
        registry.register(ReadTool())
        tool = registry.get("Read")
        assert tool.name == "Read"

    def test_get_nonexistent_tool(self):
        """测试获取不存在工具"""
        registry = ToolRegistry()
        tool = registry.get("Nonexistent")
        assert tool is None

    def test_list_tools(self):
        """测试列出工具"""
        registry = ToolRegistry()
        registry.register(ReadTool())
        registry.register(WriteTool())
        tools = registry.list_tools()
        # list_tools 返回 List[Dict]，检查 name 字段
        tool_names = [t.get('name') for t in tools]
        assert "Read" in tool_names
        assert "Write" in tool_names


class TestToolCall:
    """工具调用测试"""

    def test_tool_call_creation(self):
        """测试工具调用创建"""
        call = ToolCall(name="read", parameters={"file_path": "test.txt"})
        assert call.name == "read"
        assert call.parameters == {"file_path": "test.txt"}

    def test_tool_call_defaults(self):
        """测试工具调用默认值"""
        call = ToolCall(name="read", parameters={})
        assert call.parameters == {}


class TestExecutionResult:
    """执行结果测试"""

    def test_success_result(self):
        """测试成功结果"""
        result = ExecutionResult(
            tool_call=ToolCall(name="read", parameters={}),
            success=True,
            output="test output",
            skipped=False
        )
        assert result.success is True
        assert result.output == "test output"

    def test_failure_result(self):
        """测试失败结果"""
        result = ExecutionResult(
            tool_call=ToolCall(name="read", parameters={}),
            success=False,
            output="",
            error="test error",
            skipped=False
        )
        assert result.success is False
        assert result.error == "test error"


class TestExecutionReport:
    """执行报告测试"""

    def test_empty_report(self):
        """测试空报告"""
        report = ExecutionReport()
        assert report.total == 0
        assert report.success_count == 0
        assert report.failed_count == 0

    def test_report_summary(self):
        """测试报告摘要"""
        results = [
            ExecutionResult(
                tool_call=ToolCall(name="read", parameters={}),
                success=True,
                output="test",
                skipped=False
            ),
            ExecutionResult(
                tool_call=ToolCall(name="write", parameters={}),
                success=False,
                output="",
                error="failed",
                skipped=False
            )
        ]
        report = ExecutionReport(results=results)
        assert report.success_count == 1
        assert report.failed_count == 1  # 使用正确的属性名


class TestExecutorMiddleware:
    """v2.8.0 新增：执行器中间件测试"""

    def test_repeat_read_no_limit(self):
        """测试重复读取不再有限制（移除 5 次拦截）"""
        from claude_code.tools.builtins import ReadTool
        from claude_code.tools.file_cache import file_cache
        from claude_code.utils.paths import resolve_path

        # 0. 清理全局缓存
        file_cache.clear()

        # 1. 准备环境
        registry = ToolRegistry()
        registry.register(ReadTool())
        manager = PermissionManager()
        executor = ToolExecutor(registry, manager)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("print('test')\n")
            f.flush()
            temp_path = f.name

        try:
            resolved_path = resolve_path(temp_path)

            # 先让文件进入缓存
            file_cache.read_file(resolved_path, "print('test')\n")

            tool_call = ToolCall(name="Read", parameters={"file_path": temp_path})

            # 手动增加 4 次计数（模拟之前读了 4 次）
            for i in range(4):
                file_cache.record_read(resolved_path, 1, 1, 1)

            # 验证计数为 4
            current_count = file_cache.get_read_count(resolved_path)
            assert current_count == 4, f"期望计数为 4，实际为 {current_count}"

            # 执行第 5 次读取 - 新行为：不再拦截，正常执行
            result = executor.execute_single(tool_call)

            # 断言：不再拦截，正常执行成功
            assert result.skipped is False, "不应被拦截，应正常执行"
            assert result.success is True, "应执行成功"
            assert "print('test')" in result.output, "应返回文件内容"

        finally:
            os.unlink(temp_path)
            file_cache.clear()

    def test_dangerous_command_intercept(self):
        """测试危险命令在执行前被拦截"""
        from claude_code.tools.builtins import BashTool

        registry = ToolRegistry()
        registry.register(BashTool())
        manager = PermissionManager()
        executor = ToolExecutor(registry, manager)

        # 尝试执行 rm -rf / (会被 _check_dangerous 拦截)
        tool_call = ToolCall(name="Bash", parameters={"command": "rm -rf /"})
        result = executor.execute_single(tool_call)

        assert result.success is False
        assert "危险命令" in result.error or "拦截" in result.error


class TestSecurityContextHook:
    """v2.8.0 新增：验证工具的安全上下文钩子"""

    def test_read_tool_context(self):
        """测试 Read 工具返回只读上下文"""
        tool = ReadTool()
        context = tool.get_security_context()
        assert context["is_sensitive"] is False

    def test_write_tool_context(self):
        """测试 Write 工具返回敏感上下文"""
        tool = WriteTool()
        tool.parameters = {"file_path": "test.py"}
        context = tool.get_security_context()
        assert context["is_sensitive"] is True
        assert "test.py" in context["paths"]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])