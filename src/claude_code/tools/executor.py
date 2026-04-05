"""工具执行器 - 执行工具调用并显示进度"""
from typing import List, Optional, Tuple, Callable, Dict
from dataclasses import dataclass, field
import time

from .base import Tool, ToolCall, ToolResult, ToolRegistry, PermissionLevel
from .permission import PermissionManager, PermissionDecision
from .permission_ui import PermissionUI
from .file_cache import file_cache
from claude_code.utils.paths import resolve_path

@dataclass
class ExecutionResult:
    """执行结果"""
    tool_call: ToolCall
    success: bool
    output: str
    error: Optional[str] = None
    skipped: bool = False           # 是否被跳过（用户拒绝或取消）
    permission_denied: bool = False  # 是否因权限拒绝
    duration_ms: int = 0

@dataclass
class ExecutionReport:
    """执行报告"""
    results: List[ExecutionResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.success and not r.skipped)

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.results if r.skipped)

    def add(self, result: ExecutionResult) -> None:
        self.results.append(result)

    def get_summary(self) -> str:
        """获取执行摘要"""
        lines = [f"\n工具执行完成: {self.success_count}/{self.total} 成功"]
        if self.skipped_count > 0:
            lines.append(f"  跳过: {self.skipped_count}")
        if self.failed_count > 0:
            lines.append(f"  失败: {self.failed_count}")
        return "\n".join(lines)


class ToolExecutor:
    """工具执行器"""
    # 执行限制
    MAX_TOOLS_PER_TURN = 20    # 单轮最大工具数
    MAX_EXECUTION_TIME = 120    # 单个工具最大执行时间（秒）

    def __init__(self, registry: ToolRegistry, permission_manager: PermissionManager):
        """
        初始化执行器

        Args:
            registry: 工具注册表
            permission_manager: 权限管理器
        """
        self.registry = registry
        self.permission_manager = permission_manager

        # 执行历史
        self.execution_history: List[dict] = []

    def execute_single(
        self,
        tool_call: ToolCall,
        on_progress: Optional[Callable[[str, str], None]] = None
    ) -> ExecutionResult:
        """
        执行单个工具调用

        Args:
            tool_call: 工具调用
            on_progress: 进度回调函数

        Returns:
            执行结果
        """
        # 1. 获取工具
        tool = self.registry.get(tool_call.name)
        if not tool:
            return ExecutionResult(
                tool_call=tool_call,
                success=False,
                output="",
                error=f"未知工具: {tool_call.name}"
            )

        # 2. 验证参数
        validation_error = tool.validate_parameters(tool_call.parameters)
        if validation_error:
            return ExecutionResult(
                tool_call=tool_call,
                success=False,
                output="",
                error=f"参数错误: {validation_error}"
            )

        # 3. 预处理：安全检查与重复检测
        pre_check_result = self._pre_execute_checks(tool_call, tool)
        if pre_check_result:
            return pre_check_result

        # 4. 权限确认
        decision = self._request_permission(tool_call, tool)
        if decision is None:
            return ExecutionResult(tool_call=tool_call, success=False, output="", skipped=True)
        if not decision.allowed:
            return ExecutionResult(tool_call=tool_call, success=False, output="", skipped=True, permission_denied=True)

        # 5. 执行工具
        PermissionUI.show_tool_start(tool.name, str(tool_call))
        start_time = time.time()
        
        try:
            result = tool.execute(tool_call.parameters)
            duration_ms = int((time.time() - start_time) * 1000)

            # 6. 后处理：记录与显示
            self._post_execute_handling(tool_call, tool, result, duration_ms)

            return ExecutionResult(
                tool_call=tool_call,
                success=result.success,
                output=result.output,
                error=result.error,
                duration_ms=duration_ms
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"执行异常: {str(e)}"
            PermissionUI.show_tool_result(tool.name, False, error_msg)
            return ExecutionResult(
                tool_call=tool_call,
                success=False,
                output="",
                error=error_msg,
                duration_ms=duration_ms
            )

    def _pre_execute_checks(self, tool_call: ToolCall, tool: Tool) -> Optional[ExecutionResult]:
        """
        执行前的安全检查与重复检测
        """
        # A. 重复读取检测 (利用 file_cache)
        if tool_call.name == "Read":
            file_path = tool_call.parameters.get("file_path", "")
            if file_path:
                resolved_path = resolve_path(file_path)
                read_count = file_cache.get_read_count(resolved_path)
                
                # 第 5 次及以后：阻止执行
                if read_count >= 4:
                    ranges = file_cache.get_read_ranges(resolved_path)
                    return ExecutionResult(
                        tool_call=tool_call,
                        success=True,
                        output=f"⚠️ 文件已读取 {read_count} 次，已达上限。\n📌 缓存引用: {resolved_path}\n已读取范围: {ranges}\n请直接执行任务或使用 Edit 工具编辑。",
                        skipped=True
                    )

        # B. 危险命令拦截 (利用工具自身的钩子)
        if hasattr(tool, '_check_dangerous'):
            command = tool_call.parameters.get("command", "")
            is_dangerous, danger_reason = tool._check_dangerous(command)
            if is_dangerous:
                return ExecutionResult(
                    tool_call=tool_call,
                    success=False,
                    output="",
                    error=f"🚫 危险命令已拦截: {danger_reason}"
                )
        
        return None

    def _request_permission(self, tool_call: ToolCall, tool: Tool) -> Optional[PermissionDecision]:
        """
        请求权限（支持通用化安全上下文）
        """
        if tool.is_read_only():
            return PermissionDecision(allowed=True, level=PermissionLevel.ONCE)

        # 这里依然调用 permission_manager，但未来可以传入 tool.get_security_context()
        return self.permission_manager.request_permission(tool_call, tool)

    def _post_execute_handling(self, tool_call: ToolCall, tool: Tool, result: ToolResult, duration_ms: int):
        """
        执行后的处理：显示结果、记录历史、更新缓存
        """
        # A. 重复读取警告 (Read 工具)
        if tool_call.name == "Read" and result.success:
            file_path = tool_call.parameters.get("file_path", "")
            if file_path:
                resolved_path = resolve_path(file_path)
                current_count = file_cache.get_read_count(resolved_path) + 1
                if 2 <= current_count <= 4:
                    warning = f"\n\n⚠️ 提示: 该文件已读取 {current_count} 次。建议直接使用缓存内容执行任务。"
                    result.output = result.output + warning
                    from claude_code.ui import console as ui_console
                    ui_console.print(f"  [yellow]⚠️ 该文件已读取 {current_count} 次，建议使用缓存内容[/]  ")

        # B. 显示结果
        # Bash 已有流式卡片，跳过重复显示
        if tool.name != "Bash":
            # 确定要显示的内容
            display_content = ""
            if result.success:
                # 优先使用结构化 display_output (含 Rich Markup)
                if result.display_output:
                    display_content = result.display_output
                else:
                    display_content = result.output
            else:
                display_content = result.error or "执行失败"

            # 关键修复：直接使用 app_console 打印，并开启 markup=True
            # 这样 Glob/Grep/Read 的 [dim]...[/] 标签会被正确渲染
            if display_content:
                from claude_code.ui import console as app_console
                # 使用 print 而不是 PermissionUI，确保 Markup 被解析
                # end="" 避免多余换行，因为 display_content 通常已包含结尾格式
                app_console.print(display_content, markup=True, highlight=False)

        # C. 记录历史
        self._record_execution(tool_call, result, duration_ms)

    def execute_batch(
        self,
        tool_calls: List[ToolCall],
        on_progress: Optional[Callable[[str, str], None]] = None
    ) -> ExecutionReport:
        """
        批量执行工具调用
        """
        report = ExecutionReport()

        if len(tool_calls) > self.MAX_TOOLS_PER_TURN:
            tool_calls = tool_calls[:self.MAX_TOOLS_PER_TURN]

        for i, tool_call in enumerate(tool_calls, 1):
            if on_progress:
                on_progress(tool_call.name, f"执行 {i}/{len(tool_calls)}")

            result = self.execute_single(tool_call, on_progress)
            report.add(result)

            if result.skipped and not result.permission_denied:
                break

        return report

    def _record_execution(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        duration_ms: int
    ) -> None:
        """记录执行历史"""
        self.execution_history.append({
            "tool": tool_call.name,
            "parameters": tool_call.parameters,
            "success": result.success,
            "output": result.output[:500] if result.output else "",
            "error": result.error,
            "duration_ms": duration_ms,
        })
        # 注意：Read 操作的缓存记录已移至 ReadTool.execute() 内部

    def get_history(self, limit: int = 10) -> List[dict]:
        """获取执行历史"""
        return self.execution_history[-limit:]

    def get_read_files(self) -> Dict[str, Tuple[int, List[Tuple[int, int]]]]:
        """获取已读文件列表"""
        return file_cache.get_read_files()

    def has_read_file(self, file_path: str) -> bool:
        """检查是否已读取过该文件"""
        return file_cache.has_read(file_path)

    def clear_history(self) -> None:
        """清空执行历史"""
        self.execution_history.clear()
        file_cache.clear()

def create_executor(registry: ToolRegistry) -> ToolExecutor:
    """创建工具执行器的便捷函数"""
    return ToolExecutor(registry, PermissionManager())