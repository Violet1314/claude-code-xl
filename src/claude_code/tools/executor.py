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
        # 获取工具
        tool = self.registry.get(tool_call.name)
        if not tool:
            return ExecutionResult(
                tool_call=tool_call,
                success=False,
                output="",
                error=f"未知工具: {tool_call.name}"
            )

        # 验证参数
        validation_error = tool.validate_parameters(tool_call.parameters)
        if validation_error:
            return ExecutionResult(
                tool_call=tool_call,
                success=False,
                output="",
                error=f"参数错误: {validation_error}"
            )

        # 检测重复读取（防止模型循环调用 Read）
        resolved_read_path = ""
        if tool_call.name == "Read":
            file_path = tool_call.parameters.get("file_path", "")
            if file_path:
                # ✅ 关键修复：统一解析路径，确保与 file_cache 的 key 完全一致
                resolved_read_path = resolve_path(file_path)
                read_count = file_cache.get_read_count(resolved_read_path)

                # 第 5 次及以后：阻止执行（count >=4 表示已读4次，本次是第5次）
                if read_count >= 4:
                    ranges = file_cache.get_read_ranges(resolved_read_path)
                    return ExecutionResult(
                        tool_call=tool_call,
                        success=True,
                        output=f"⚠️ 文件已读取 {read_count} 次，已达上限。\n📌 缓存引用: {resolved_read_path}\n已读取范围: {ranges}\n请直接执行任务或使用 Edit 工具编辑。",
                        skipped=True
                    )
                # 第 2-4 次读取：显示警告但允许执行（由后续逻辑处理）

        # 检查 Bash 危险命令（在权限确认之前拦截）
        if tool_call.name == "Bash" and hasattr(tool, '_check_dangerous'):
            command = tool_call.parameters.get("command", "")
            is_dangerous, danger_reason = tool._check_dangerous(command)
            if is_dangerous:
                return ExecutionResult(
                    tool_call=tool_call,
                    success=False,
                    output="",
                    error=f"🚫 危险命令已拦截: {danger_reason}"
                )

        # 只读工具自动通过，跳过权限确认
        if tool.is_read_only():
            decision = PermissionDecision(allowed=True, level=PermissionLevel.ONCE)
        else:
            decision = self.permission_manager.request_permission(tool_call, tool)

        if decision is None:
            # 用户取消
            return ExecutionResult(
                tool_call=tool_call,
                success=False,
                output="",
                skipped=True
            )

        if not decision.allowed:
            # 用户拒绝
            return ExecutionResult(
                tool_call=tool_call,
                success=False,
                output="",
                skipped=True,
                permission_denied=True
            )

        # 显示开始执行
        PermissionUI.show_tool_start(tool.name, str(tool_call))

        # 执行工具
        start_time = time.time()
        try:
            result = tool.execute(tool_call.parameters)
            duration_ms = int((time.time() - start_time) * 1000)

            # Read 工具重复读取警告（第 2-4 次时显示）
            if tool_call.name == "Read" and resolved_read_path:
                current_count = file_cache.get_read_count(resolved_read_path) + 1
                if 2 <= current_count <= 4:
                    warning = f"\n\n⚠️ 提示: 该文件已读取 {current_count} 次。建议直接使用缓存内容执行任务。"
                    result.output = result.output + warning
                    # 终端也显示警告
                    from claude_code.ui import console as ui_console
                    ui_console.print(f"  [yellow]⚠️ 该文件已读取 {current_count} 次，建议使用缓存内容[/]")

            # 显示结果（Bash 已有流式卡片输出，跳过重复显示）
            if tool.name != "Bash":
                if result.success and result.display_output:
                    display_content = result.display_output
                else:
                    display_content = result.output if result.success else (result.error or "执行失败")
                PermissionUI.show_tool_result(tool.name, result.success, display_content)

            # 记录历史
            self._record_execution(tool_call, result, duration_ms)

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

    def execute_batch(
        self,
        tool_calls: List[ToolCall],
        on_progress: Optional[Callable[[str, str], None]] = None
    ) -> ExecutionReport:
        """
        批量执行工具调用

        Args:
            tool_calls: 工具调用列表
            on_progress: 进度回调函数

        Returns:
            执行报告
        """
        report = ExecutionReport()

        # 限制工具数量
        if len(tool_calls) > self.MAX_TOOLS_PER_TURN:
            tool_calls = tool_calls[:self.MAX_TOOLS_PER_TURN]

        for i, tool_call in enumerate(tool_calls, 1):
            # 显示进度
            if on_progress:
                on_progress(tool_call.name, f"执行 {i}/{len(tool_calls)}")

            result = self.execute_single(tool_call, on_progress)
            report.add(result)

            # 用户取消时中断后续执行
            if result.skipped and not result.permission_denied:
                # 用户按 Esc 取消，停止执行剩余工具
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

        # 记录 Read 操作到缓存
        if tool_call.name == "Read" and result.success:
            metadata = result.metadata or {}
            file_path = metadata.get("file_path") or tool_call.parameters.get("file_path")
            total_lines = metadata.get("total_lines", 0)
            start_line = metadata.get("start_line", 1)
            end_line = metadata.get("end_line", total_lines)

            if file_path:
                file_cache.record_read(file_path, total_lines, start_line, end_line)

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