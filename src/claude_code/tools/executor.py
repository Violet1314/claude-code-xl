"""工具执行器 - 执行工具调用并显示进度"""
from typing import List, Optional, Tuple, Callable, Dict
from dataclasses import dataclass, field
import time

from .base import Tool, ToolCall, ToolResult, ToolRegistry, PermissionLevel
from .permission import PermissionManager, PermissionDecision
from .permission_ui import PermissionUI
from .file_cache import file_cache
from claude_code.ui.theme import COLORS, ICONS
from claude_code.ui.safe_markup import safe_print

@dataclass
class ExecutionResult:
    """执行结果 — 组合持有 ToolResult，消除字段重叠
    
    独有字段：tool_call, skipped, permission_denied, duration_ms, display_shown
    代理字段（来自 tool_result）：success, output, error, interrupted, display_output
    """
    tool_call: ToolCall
    tool_result: Optional[ToolResult] = None  # 组合持有，替代重复字段
    skipped: bool = False           # 是否被跳过（用户拒绝或取消）
    permission_denied: bool = False  # 是否因权限拒绝
    duration_ms: int = 0
    display_shown: bool = False     # 是否已在 execute_single 中直接打印摘要

    # --- 向后兼容属性代理（委托给 tool_result）---
    @property
    def success(self) -> bool:
        return self.tool_result.success if self.tool_result else False

    @property
    def output(self) -> str:
        return self.tool_result.output if self.tool_result else ""

    @property
    def error(self) -> Optional[str]:
        return self.tool_result.error if self.tool_result else None

    @property
    def interrupted(self) -> bool:
        return self.tool_result.interrupted if self.tool_result else False

    @property
    def display_output(self) -> Optional[str]:
        return self.tool_result.display_output if self.tool_result else None

    @property
    def metadata(self) -> Dict:
        return self.tool_result.metadata if self.tool_result else {}

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

    @property
    def interrupted_count(self) -> int:
        return sum(1 for r in self.results if r.interrupted)

    @property
    def has_interrupted(self) -> bool:
        """是否有任何工具被用户中断"""
        return any(r.interrupted for r in self.results)

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
    MAX_TOOLS_PER_TURN = 40    # 单轮最大工具数
    MAX_EXECUTION_TIME = 120    # 单个工具最大执行时间（秒）

    # 路径类参数名（用于动态注入路径示例）
    PATH_PARAM_NAMES = {"file_path", "path", "cwd", "directory", "dir"}

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
        # 上一轮显示的工具名（用于跨轮次连续同类工具紧凑排列）
        self._last_displayed_tool: Optional[str] = None

    def execute_single(
        self,
        tool_call: ToolCall,
        on_progress: Optional[Callable[[str, str], None]] = None,
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> ExecutionResult:
        """
        执行单个工具调用

        Args:
            tool_call: 工具调用
            on_progress: 进度回调函数
            interrupt_check: 中断检查函数

        Returns:
            执行结果
        """
        # 1. 获取工具
        tool = self.registry.get(tool_call.name)
        if not tool:
            return ExecutionResult(
                tool_call=tool_call,
                tool_result=ToolResult(success=False, output="", error=f"未知工具: {tool_call.name or '(空)'}")
            )

        # 1.5 设置当前参数（供 get_security_context 等方法使用）
        tool.parameters = tool_call.parameters

        # 2. 验证参数
        validation_error = tool.validate_parameters(tool_call.parameters)
        if validation_error:
            # 生成友好的纠正性提示，帮助 AI 快速修正参数
            hint = self._build_validation_hint(tool, validation_error)
            return ExecutionResult(
                tool_call=tool_call,
                tool_result=ToolResult(success=False, output="", error=f"参数错误: {validation_error}\n{hint}")
            )

        # 3. 预处理：安全检查与重复检测
        pre_check_result = self._pre_execute_checks(tool_call, tool)
        if pre_check_result:
            return pre_check_result

        # 4. 权限确认
        decision = self._request_permission(tool_call, tool)
        if decision is None:
            return ExecutionResult(tool_call=tool_call, tool_result=ToolResult(success=False, output=""), skipped=True)
        if not decision.allowed:
            return ExecutionResult(tool_call=tool_call, tool_result=ToolResult(success=False, output=""), skipped=True, permission_denied=True)

        # 5. 执行工具
        PermissionUI.show_tool_start(tool.name, str(tool_call))
        start_time = time.time()

        try:
            # 传入中断检查函数，让工具（如 Bash）能响应 CTRL+C
            result = tool.execute(tool_call.parameters, interrupt_check=interrupt_check)
            duration_ms = int((time.time() - start_time) * 1000)

            # 6. 后处理：记录与显示
            self._post_execute_handling(tool_call, tool, result, duration_ms)

            # 非自有显示的工具：执行完成后直接打印摘要行
            skip_display_tools = {"Bash", "AskUserQuestion"}
            display_shown = False
            if tool_call.name not in skip_display_tools:
                if result.success and result.display_output:
                    from claude_code.ui import console as app_console
                    safe_print(app_console, result.display_output)
                    display_shown = True
                elif not result.success:
                    from claude_code.ui import console as app_console
                    safe_print(app_console, f"  [{COLORS['error']}]{ICONS['error']} {tool_call.name} 失败:[/] {result.error or '执行失败'}")
                    display_shown = True

            return ExecutionResult(
                tool_call=tool_call,
                tool_result=result,
                duration_ms=duration_ms,
                display_shown=display_shown,  # 标记已直接打印摘要
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"执行异常: {str(e)}"
            return ExecutionResult(
                tool_call=tool_call,
                tool_result=ToolResult(success=False, output="", error=error_msg),
                duration_ms=duration_ms,
            )

    def _pre_execute_checks(self, tool_call: ToolCall, tool: Tool) -> Optional[ExecutionResult]:
        """
        执行前的安全检查与重复检测
        """
        # A. Read 工具不再限制读取次数，移除拦截逻辑

        # B. 危险命令拦截 (使用 CommandSafetyChecker)
        if hasattr(tool, '_safety_checker'):
            command = tool_call.parameters.get("command", "")
            is_dangerous, danger_reason = tool._safety_checker.check_dangerous(command)
            if is_dangerous:
                return ExecutionResult(
                    tool_call=tool_call,
                    tool_result=ToolResult(success=False, output="", error=f"🚫 危险命令已拦截: {danger_reason}")
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
        执行后的处理：记录历史、更新缓存（显示由 execute_batch 统一组打印）
        """
        # 记录历史
        self._record_execution(tool_call, result, duration_ms)

    def execute_batch(
        self,
        tool_calls: List[ToolCall],
        on_progress: Optional[Callable[[str, str], None]] = None,
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> ExecutionReport:
        """
        批量执行工具调用（只读工具并行，写操作顺序执行）

        策略：
        - 只读工具（Read、Grep、Glob、ProjectContext、TodoList、AskUserQuestion）可并行
        - 写操作工具（Write、Edit、Bash、TodoCreate、TodoUpdate）必须顺序执行
        - 如果批次中混合了只读和写操作，先并行执行只读，再顺序执行写操作

        Args:
            tool_calls: 工具调用列表
            on_progress: 进度回调
            interrupt_check: 中断检查函数，返回 True 表示应该中断
        """
        report = ExecutionReport()

        if len(tool_calls) > self.MAX_TOOLS_PER_TURN:
            tool_calls = tool_calls[:self.MAX_TOOLS_PER_TURN]

        # 单个工具直接走串行（避免线程开销）
        if len(tool_calls) <= 1:
            for i, tool_call in enumerate(tool_calls, 1):
                if interrupt_check and interrupt_check():
                    from claude_code.ui import console
                    console.print("\n[dim]已中断，跳过后续工具[/]")
                    break
                if on_progress:
                    on_progress(tool_call.name, f"执行 {i}/{len(tool_calls)}")
                result = self.execute_single(tool_call, on_progress, interrupt_check)
                report.add(result)
            self._display_grouped_results(report)
            return report

        # 分类：只读工具和写操作工具
        READ_ONLY_TOOLS = {"Read", "Grep", "Glob", "ProjectContext", "TodoList", "AskUserQuestion"}

        read_only_calls = []
        write_calls = []
        for tc in tool_calls:
            if tc.name in READ_ONLY_TOOLS:
                read_only_calls.append(tc)
            else:
                write_calls.append(tc)

        # 如果全部是只读工具，并行执行
        if write_calls == [] and len(read_only_calls) > 1:
            return self._execute_parallel(read_only_calls, on_progress, interrupt_check, report)

        # 如果全部是写操作，顺序执行
        if read_only_calls == []:
            return self._execute_sequential(tool_calls, on_progress, interrupt_check, report)

        # 混合：先并行只读，再顺序写操作
        if read_only_calls:
            par_report = self._execute_parallel(read_only_calls, on_progress, interrupt_check, report)
            if interrupt_check and interrupt_check():
                self._display_grouped_results(par_report)
                return par_report

        return self._execute_sequential(write_calls, on_progress, interrupt_check, report)

    def _execute_sequential(
        self,
        tool_calls: List[ToolCall],
        on_progress: Optional[Callable[[str, str], None]],
        interrupt_check: Optional[Callable[[], bool]],
        report: ExecutionReport,
    ) -> ExecutionReport:
        """顺序执行工具调用"""
        consecutive_param_errors = 0
        MAX_CONSECUTIVE_PARAM_ERRORS = 3

        for i, tool_call in enumerate(tool_calls, 1):
            if interrupt_check and interrupt_check():
                from claude_code.ui import console
                console.print("\n[dim]已中断，跳过后续工具[/]")
                break

            if on_progress:
                on_progress(tool_call.name, f"执行 {i}/{len(tool_calls)}")

            result = self.execute_single(tool_call, on_progress, interrupt_check)
            report.add(result)

            if not result.success and result.error and result.error.startswith("参数错误"):
                consecutive_param_errors += 1
                if consecutive_param_errors >= MAX_CONSECUTIVE_PARAM_ERRORS:
                    from claude_code.ui import console
                    console.print(
                        f"\n[{COLORS['warning']}]⚠ 连续 {MAX_CONSECUTIVE_PARAM_ERRORS} 个工具参数错误，"
                        f"终止本批次剩余 {len(tool_calls) - i} 个工具[/]"
                    )
                    break
                continue
            else:
                consecutive_param_errors = 0

            if result.skipped and not result.permission_denied:
                break

        self._display_grouped_results(report)
        return report

    def _execute_parallel(
        self,
        tool_calls: List[ToolCall],
        on_progress: Optional[Callable[[str, str], None]],
        interrupt_check: Optional[Callable[[], bool]],
        report: ExecutionReport,
    ) -> ExecutionReport:
        """并行执行只读工具调用"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if on_progress:
            on_progress("parallel", f"并行执行 {len(tool_calls)} 个只读工具")

        with ThreadPoolExecutor(max_workers=min(len(tool_calls), 4)) as executor:
            futures = {}
            for tool_call in tool_calls:
                if interrupt_check and interrupt_check():
                    break
                future = executor.submit(self.execute_single, tool_call, None, interrupt_check)
                futures[future] = tool_call

            for future in as_completed(futures):
                if interrupt_check and interrupt_check():
                    break
                try:
                    result = future.result(timeout=60)
                    report.add(result)
                except Exception as e:
                    tool_call = futures[future]
                    report.add(ExecutionResult(
                        tool_call=tool_call,
                        tool_result=ToolResult(success=False, output="", error=f"并行执行异常: {e}"),
                        duration_ms=0,
                    ))

        self._display_grouped_results(report)
        return report

    def _display_grouped_results(self, report: ExecutionReport) -> None:
        """
        分组显示工具执行结果（仅显示未在 execute_single 中直接打印的结果）
        
        规则：
        - display_shown=True 的结果已在 execute_single 中直接打印，跳过
        - Bash/AskUserQuestion 跳过（它们有自己的显示）
        - 连续同类工具紧凑排列，不同工具间空行分隔
        """
        from claude_code.ui import console as app_console

        # 跳过自有显示的工具 + 已直接打印的结果
        skip_tools = {"Bash", "AskUserQuestion"}

        # 按连续同名工具分组
        groups: List[List[ExecutionResult]] = []
        for result in report.results:
            if result.tool_call.name in skip_tools:
                groups.append([result])
                continue
            # 已在 execute_single 中直接打印的结果，单独成组（后续跳过打印）
            if result.display_shown:
                groups.append([result])
                continue
            if groups and groups[-1] and groups[-1][-1].tool_call.name == result.tool_call.name and groups[-1][0].tool_call.name not in skip_tools and not groups[-1][0].display_shown:
                groups[-1].append(result)
            else:
                groups.append([result])

        # 逐组打印
        last_tool = self._last_displayed_tool
        for group in groups:
            tool_name = group[0].tool_call.name
            # 跳过自有显示的工具
            if tool_name in skip_tools:
                continue
            # 跳过已在 execute_single 中直接打印的结果
            if group[0].display_shown:
                last_tool = tool_name  # 仍然更新追踪，保持间距逻辑
                continue

            # 与上一轮不同工具时，组前空行
            if tool_name != last_tool:
                app_console.print()

            for result in group:
                # 确定显示内容
                display_content = ""
                if result.success:
                    if result.display_output:
                        display_content = result.display_output
                    else:
                        display_content = result.output
                else:
                    display_content = result.error or "执行失败"

                if display_content:
                    safe_print(app_console, display_content)

            last_tool = tool_name

        # 更新跨轮次追踪
        if any(g[0].tool_call.name not in skip_tools for g in groups):
            self._last_displayed_tool = last_tool

    # 路径类参数名集合：这些参数需要动态注入当前操作根目录的路径示例
    PATH_PARAM_NAMES = {"file_path", "path", "cwd", "directory", "dir", "target_path"}

    def _build_validation_hint(self, tool: Tool, error_msg: str) -> str:
        """
        根据工具的参数 Schema 生成友好的纠正性提示

        当参数验证失败时，从 Schema 中提取必填参数及其描述，
        帮助 AI 快速理解正确的参数格式，避免盲目重试。
        对路径类参数，动态注入 PathManager 当前操作根目录的路径示例。
        同时生成完整的调用示例，让 AI 一次就能纠正。
        """
        schema = tool.get_parameters_schema()
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        if not required:
            return ""

        # 尝试获取 PathManager 实例（用于动态生成路径示例）
        pm = self._get_path_manager()

        # 检查是否缺少必填参数（错误消息中包含"缺少"关键字）
        is_missing = "缺少" in error_msg
        missing_params = []
        all_hints = []
        for param_name in required:
            param_schema = properties.get(param_name, {})
            hint_line = self._format_param_hint(param_name, param_schema, pm)
            all_hints.append(hint_line)
            if is_missing and (f"缺少 {param_name}" in error_msg or f"缺少{param_name}" in error_msg):
                missing_params.append(hint_line)

        # 参数描述列表
        if is_missing and missing_params:
            param_section = f"提示: 请补充以下必填参数:\n" + "\n".join(missing_params)
        else:
            param_section = f"提示: {tool.name} 要求以下必填参数:\n" + "\n".join(all_hints)

        # 生成完整调用示例
        call_example = self._build_call_example(tool, required, properties, pm)

        return f"{param_section}\n\n{call_example}"

    def _build_call_example(self, tool: Tool, required: list, properties: dict, pm) -> str:
        """
        生成完整的调用示例，格式如：
        Grep(pattern="正则表达式", path="E:\\项目目录\\src")
        让 AI 直接看到正确的调用格式，一次即可纠正。
        """
        example_parts = []
        for param_name in required:
            param_schema = properties.get(param_name, {})
            example_value = self._get_example_value(param_name, param_schema, pm)
            example_parts.append(f'{param_name}="{example_value}"')

        return f"正确调用示例: {tool.name}({', '.join(example_parts)})"

    def _get_example_value(self, param_name: str, param_schema: dict, pm) -> str:
        """
        根据参数名和 Schema 推断示例值

        优先使用 schema 中的 example 字段，其次根据参数名/类型推断。
        """
        # 1. 优先使用 schema 中定义的 example
        if "example" in param_schema:
            return str(param_schema["example"])

        # 2. 路径类参数：动态注入 PathManager 当前操作根目录
        if param_name in self.PATH_PARAM_NAMES and pm is not None:
            active = pm.active_path.replace("\\", "/")
            if param_name in ("cwd", "directory", "dir"):
                return active
            else:
                return f"{active}/src/app.py"

        # 3. 根据参数名推断常见模式
        param_lower = param_name.lower()
        if param_lower == "pattern":
            return "搜索关键词"
        elif param_lower == "command":
            return "python main.py"
        elif param_lower == "content":
            return "文件内容"
        elif param_lower == "new_string":
            return "替换后的新内容"
        elif param_lower == "question":
            return "要询问的问题"
        elif param_lower == "items":
            return '[{"content": "任务描述"}]'
        elif param_lower == "id":
            return "t1"
        elif param_lower == "status":
            return "in_progress"
        elif param_lower == "label":
            return "选项文本"
        elif param_lower == "value":
            return "选项值"

        # 4. 根据 type 推断
        param_type = param_schema.get("type", "string")
        if param_type == "integer":
            return "1"
        elif param_type == "boolean":
            return "true"

        # 5. 兜底
        return f"<{param_name}>"

    def _format_param_hint(self, param_name: str, param_schema: dict, pm) -> str:
        """
        格式化单个参数的提示行

        对路径类参数，动态注入当前操作根目录的路径示例，
        帮助 AI 理解绝对路径的具体格式。

        Args:
            param_name: 参数名
            param_schema: 参数的 Schema 定义
            pm: PathManager 实例（可能为 None）

        Returns:
            格式化的提示行
        """
        desc = param_schema.get("description", "")
        param_type = param_schema.get("type", "string")
        line = f"  - {param_name} ({param_type}): {desc}"

        # 路径类参数：动态注入当前操作根目录的路径示例
        if param_name in self.PATH_PARAM_NAMES and pm is not None:
            active = pm.active_path.replace("\\", "\\\\")
            if param_name in ("cwd", "directory", "dir"):
                line += f"\n    示例: {param_name}=\"{active}\""
            else:
                line += f"\n    示例: {param_name}=\"{active}\\\\src\\\\app.py\""

        return line

    def _get_path_manager(self):
        """安全获取 PathManager 实例"""
        try:
            from claude_code.core.path_manager import get_path_manager
            return get_path_manager()
        except Exception:
            return None

    def _record_execution(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        duration_ms: int
    ) -> None:
        """记录执行历史"""
        from datetime import datetime
        self.execution_history.append({
            "tool_call_id": tool_call.id,
            "tool": tool_call.name,
            "parameters": tool_call.parameters,
            "success": result.success,
            "output": result.output[:500] if result.output else "",
            "error": result.error,
            "duration_ms": duration_ms,
            "timestamp": datetime.now().strftime('%H:%M:%S'),
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