"""权限系统和执行器测试"""
import pytest
import sys
import os

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
        assert PermissionLevel.ALWAYS.value == "always"

    def test_permission_comparison(self):
        """测试权限比较"""
        assert PermissionLevel.ONCE != PermissionLevel.ALWAYS


class TestPermissionDecision:
    """权限决定测试"""

    def test_allowed_decision(self):
        """测试允许决定"""
        decision = PermissionDecision(allowed=True, level=PermissionLevel.ONCE)
        assert decision.allowed is True
        assert decision.level == PermissionLevel.ONCE
        assert decision.cached is False

    def test_cached_decision(self):
        """测试缓存决定"""
        decision = PermissionDecision(
            allowed=True,
            level=PermissionLevel.ALWAYS,
            cached=True
        )
        assert decision.cached is True


class TestPermissionManager:
    """权限管理器测试"""

    def test_set_and_get_permission(self):
        """测试设置和获取权限"""
        manager = PermissionManager()

        manager.set_permission("Read", PermissionLevel.ALWAYS, "test.py")
        level = manager.get_cached_permission("Read", "test.py")

        assert level == PermissionLevel.ALWAYS

    def test_get_nonexistent_permission(self):
        """测试获取不存在的权限"""
        manager = PermissionManager()

        level = manager.get_cached_permission("Read", "nonexistent.py")
        assert level is None

    def test_clear_session(self):
        """测试清除会话"""
        manager = PermissionManager()
        manager.set_permission("Read", PermissionLevel.ALWAYS, "test.py")

        manager.clear_session()

        assert len(manager.session_rules) == 0

    def test_rule_key_format(self):
        """测试规则 key 格式"""
        manager = PermissionManager()

        key_with_id = manager._get_rule_key("Read", "test.py")
        assert key_with_id == "Read:test.py"

        key_without_id = manager._get_rule_key("Read")
        assert key_without_id == "Read"


class TestExecutionResult:
    """执行结果测试"""

    def test_success_result(self):
        """测试成功结果"""
        tool_call = ToolCall(name="Read", parameters={"file_path": "test.py"})
        result = ExecutionResult(
            tool_call=tool_call,
            success=True,
            output="file content"
        )

        assert result.success is True
        assert result.skipped is False
        assert result.permission_denied is False

    def test_skipped_result(self):
        """测试跳过结果"""
        tool_call = ToolCall(name="Read", parameters={"file_path": "test.py"})
        result = ExecutionResult(
            tool_call=tool_call,
            success=False,
            output="",
            skipped=True
        )

        assert result.skipped is True
        assert result.success is False


class TestExecutionReport:
    """执行报告测试"""

    def test_empty_report(self):
        """测试空报告"""
        report = ExecutionReport()

        assert report.total == 0
        assert report.success_count == 0
        assert report.failed_count == 0
        assert report.skipped_count == 0

    def test_add_results(self):
        """测试添加结果"""
        report = ExecutionReport()

        tool_call = ToolCall(name="Read", parameters={"file_path": "test.py"})

        report.add(ExecutionResult(tool_call=tool_call, success=True, output="ok"))
        report.add(ExecutionResult(tool_call=tool_call, success=False, output="", error="fail"))
        report.add(ExecutionResult(tool_call=tool_call, success=False, output="", skipped=True))

        assert report.total == 3
        assert report.success_count == 1
        assert report.failed_count == 1
        assert report.skipped_count == 1

    def test_get_summary(self):
        """测试获取摘要"""
        report = ExecutionReport()
        tool_call = ToolCall(name="Read", parameters={"file_path": "test.py"})

        report.add(ExecutionResult(tool_call=tool_call, success=True, output="ok"))
        report.add(ExecutionResult(tool_call=tool_call, success=True, output="ok"))

        summary = report.get_summary()

        assert "2/2 成功" in summary


class TestToolExecutor:
    """工具执行器测试"""

    def test_execute_unknown_tool(self):
        """测试执行未知工具"""
        registry = ToolRegistry()
        manager = PermissionManager()
        executor = ToolExecutor(registry, manager)

        tool_call = ToolCall(name="UnknownTool", parameters={})
        result = executor.execute_single(tool_call)

        assert result.success is False
        assert "未知工具" in result.error


class TestToolCall:
    """ToolCall 测试"""

    def test_str_representation(self):
        """测试字符串表示"""
        call = ToolCall(name="Read", parameters={"file_path": "test.py"})
        s = str(call)

        assert "Read" in s
        assert "file_path" in s


if __name__ == "__main__":
    pytest.main([__file__, "-v"])