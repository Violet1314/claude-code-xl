"""权限系统和执行器测试"""
import pytest
import sys
import os
import tempfile  # <--- 新增这一行
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
        assert decision.cached is False

    def test_cached_decision(self):
        """测试缓存决定"""
        decision = PermissionDecision(
            allowed=True,
            level=PermissionLevel.ONCE,
            cached=True
        )
        assert decision.cached is True

    def test_no_once_decision(self):
        """测试拒绝决定"""
        decision = PermissionDecision(
            allowed=False,
            level=PermissionLevel.NO_ONCE,
            cached=False
        )
        assert decision.allowed is False
        assert decision.level == PermissionLevel.NO_ONCE


class TestPermissionManager:
    """权限管理器测试"""

    def test_set_and_get_permission(self):
        """测试设置和获取权限"""
        manager = PermissionManager()

        manager.set_permission("Read", PermissionLevel.ONCE, "test.py")
        level = manager.get_cached_permission("Read", "test.py")

        assert level == PermissionLevel.ONCE

    def test_get_nonexistent_permission(self):
        """测试获取不存在的权限"""
        manager = PermissionManager()

        level = manager.get_cached_permission("Read", "nonexistent.py")
        assert level is None

    def test_clear_session(self):
        """测试清除会话"""
        manager = PermissionManager()
        manager.set_permission("Read", PermissionLevel.ONCE, "test.py")

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


class TestExecutorMiddleware:
    """v2.8.0 新增：验证执行器中间件逻辑（重复检测、危险拦截）"""
    
    def test_repeat_read_protection(self):
        """测试重复读取熔断机制（第 5 次拦截）"""
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
            # 关键修复 1：统一路径
            resolved_path = resolve_path(temp_path)
            
            # 关键修复 2：先让文件进入缓存（此时 count = 0）
            file_cache.read_file(resolved_path, "print('test')\n")
            
            tool_call = ToolCall(name="Read", parameters={"file_path": temp_path})
            
            # 关键修复 3：手动增加 4 次计数（模拟之前又读了 4 次）
            # 此时总计数 = 0 (初始) + 4 (手动) = 4
            for i in range(4):
                file_cache.record_read(resolved_path, 1, 1, 1)
            
            # 验证：此时计数应该是 4
            current_count = file_cache.get_read_count(resolved_path)
            assert current_count == 4, f"期望计数为 4，实际为 {current_count}"

            # 4. 执行第 5 次读取（实际上是第 5 次尝试，但计数已达阈值 4）
            # executor.py 逻辑：if read_count >= 4: 拦截
            result = executor.execute_single(tool_call)
            
            # 断言拦截成功
            assert result.skipped is True, f"期望被拦截，但实际执行了。Output: {result.output}"
            assert "已达上限" in result.output or "建议直接使用缓存" in result.output
            
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