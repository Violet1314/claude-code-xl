"""主应用类 - 整合所有模块 (Refactored for Elegance)"""
import re
import os
import sys
import json
import time
import signal
import atexit
import threading
from typing import Optional, List
from datetime import datetime
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text


class SafeTextColumn(TextColumn):
    """安全的 TextColumn，避免 description 中的花括号导致格式化错误"""

    def __init__(self):
        # 使用空的 text_format，避免格式化
        super().__init__("")

    def __call__(self, task):
        # 直接返回 Text 对象，不使用 format()
        if task.description:
            return Text.from_markup(task.description)
        return Text("")
from claude_code.config.settings import Settings, load_settings
from claude_code.config.defaults import VERSION, APP_NAME, WORKPLACE_DIR, TOOL, PLAN
from claude_code.core.client import APIClient
from claude_code.core.conversation import Conversation
from claude_code.core.files import FileManager
from claude_code.core.path_manager import PathManager, get_path_manager, init_path_manager, reset_path_manager
from claude_code.core.stats import StatsManager
from claude_code.commands import CommandRegistry, BUILTIN_COMMANDS
from claude_code.ui import console
from claude_code.ui.theme import COLORS, ICONS
from claude_code.ui.components import (
    show_welcome,
    show_status_bar,
    show_model_list,
    show_style_list,
    show_history_list,
)
from claude_code.ui.input import InputHandler, interactive_menu
from claude_code.ui.renderer import render_response

# 工具系统
from claude_code.tools import (
    registry,
    register_builtin_tools,
    ToolExecutor,
    ToolCall,
    ExecutionReport,
    PermissionManager,
    tool_calling_manager,
    tool_context,
)

class Application:
    """Claude Code Terminal 主应用"""
    # 工具执行限制（从 defaults 统一配置）
    MAX_TOOL_ROUNDS = TOOL.MAX_TOOL_ROUNDS
    MAX_TOOLS_PER_ROUND = TOOL.MAX_TOOLS_PER_ROUND

    def __init__(self, config_dir: str = "data/config"):
        """
        初始化应用

        Args:
            config_dir: 配置目录路径
        """
        # 加载配置
        self.settings: Settings = load_settings(config_dir)
        self.client: APIClient = APIClient(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key,
        )
        self.conversation: Conversation = Conversation()
        self.files: FileManager = FileManager()
        self.stats: StatsManager = StatsManager()
        self.current_model = self.settings.get_model()
        self.current_style_id = self.settings.style_ids[0] if self.settings.style_ids else "expert"
        register_builtin_tools()
        self.permission_manager = PermissionManager(project_dir=os.getcwd())
        self.tool_executor = ToolExecutor(registry, self.permission_manager)
        # 路径管理器（统一所有工具的路径解析）
        self.path_manager: PathManager = init_path_manager()
        # 统一注册到 ToolContext，便于测试时替换和生命周期管理
        tool_context.register("registry", registry)
        tool_context.register("permission_manager", self.permission_manager)
        tool_context.register("tool_executor", self.tool_executor)
        tool_context.register("path_manager", self.path_manager)
        self._setup_system_prompt()
        self.commands = CommandRegistry()
        for cmd_class in BUILTIN_COMMANDS:
            self.commands.register(cmd_class, app=self)
        self.input_handler = InputHandler(commands=self.commands.list_commands())
        self._update_input_state()
        self.history_dir = "data/history"
        os.makedirs(self.history_dir, exist_ok=True)
        os.makedirs(WORKPLACE_DIR, exist_ok=True)
        atexit.register(self._on_exit)
        # CTRL+C 中断管理：统一标志 + 时间戳，实现单击中断、双击退出
        # 核心原则：_interrupted 只设不清，直到用户下一轮输入时才重置
        # 这样所有循环入口只需检查 self._interrupted，不会因某处消费而漏检
        self._interrupted: bool = False          # 是否有待处理的中断信号（只读检查，不消费）
        self._last_sigint: float = 0.0          # 上次 SIGINT 时间戳（仅用于双击退出判定）
        self._sigint_double_threshold: float = 1.0  # 双击判定窗口（秒）
        signal.signal(signal.SIGINT, self._signal_handler)

        # 计划模式状态
        self._plan_mode: bool = False            # 是否处于计划模式
        self._plan_task: str = ""                # 计划模式任务描述
        self._plan_reminder_count: int = 0       # 计划模式连续提醒计数（熔断用）


    def _setup_system_prompt(self) -> None:
        """设置系统提示词"""
        base_prompt = self.settings.get_prompt(self.current_style_id)

        # 注入环境信息
        env_info = self._get_environment_info()
        full_prompt = f"{base_prompt}\n\n{env_info}"

        self.conversation.set_system_prompt(full_prompt)

    def _get_environment_info(self) -> str:
        """
        获取当前环境信息（用于注入系统提示词）

        Returns:
            环境信息文本
        """
        import platform

        # 检测操作系统
        system = platform.system()
        if system == "Windows":
            shell_info = (
                "当前环境：Windows PowerShell。\n"
                "重要：必须使用 PowerShell 语法，不支持 Unix 参数。\n"
                "正确示例：\n"
                "  - mkdir data, output（多个目录用逗号分隔）\n"
                "  - Get-ChildItem 或 ls（不带 -la 参数）\n"
                "  - Remove-Item -Recurse -Force path\n"
                "  - Copy-Item -Recurse src dst\n"
                "错误示例（不支持）：\n"
                "  - mkdir -p data output\n"
                "  - ls -la\n"
                "  - rm -rf path\n"
                "  - cp -r src dst"
            )
        elif system == "Darwin":
            shell_info = "当前环境：macOS (Unix-like)。可使用标准 bash 命令。"
        else:
            shell_info = "当前环境：Linux (Unix-like)。可使用标准 bash 命令。"

        # 自主完成指令
        autonomy_info = (
            "## 执行原则\n"
            "遇到错误时，根据报错信息自行分析原因并修复，持续尝试直到任务完成。\n"
            "不要中途放弃或等待用户干预，除非遇到无法解决的问题（如权限不足、路径不存在等）。"
        )

        # 路径环境（由 PathManager 动态生成，每轮对话均有效）
        path_info = self.path_manager.get_environment_text()

        return f"## 环境信息\n{shell_info}\n\n{autonomy_info}\n\n{path_info}"

    def _update_input_state(self) -> None:
        """更新输入处理器状态"""
        self.input_handler.update_state(
            model_name=self.current_model.name if self.current_model else "Claude",
            file_count=self.files.count,
        )

    def _on_exit(self) -> None:
        """退出时清理"""
        if not self.conversation.is_empty:
            self.stats.save_session(
                model_id=self.current_model.id if self.current_model else "",
                message_count=self.conversation.message_count,
                finalize=True,
            )
        self.client.close()
        # 统一清理 ToolContext 中的所有单例
        tool_context.clear()

    def _signal_handler(self, sig, frame) -> None:
        """信号处理：单击中断当前操作，双击退出程序

        注意：信号处理器中不直接调用 console.print()，
        避免 reentrant call inside stdout 错误。
        """
        now = time.time()
        if now - self._last_sigint < self._sigint_double_threshold:
            # 双击：退出程序（直接用 sys.stdout.write，不用 Rich）
            self._on_exit()
            sys.stdout.write(f"\n再见！\n")
            sys.stdout.flush()
            sys.exit(0)
        # 单击：设置布尔标志，让主循环处理显示
        self._interrupted = True
        self._last_sigint = now

    def _is_interrupted(self) -> bool:
        """检查是否有待处理的中断信号（只读，不消费）"""
        return self._interrupted

    def _clear_interrupt(self) -> None:
        """清除中断标志并重建客户端连接（仅在用户下一轮输入时调用）"""
        self._interrupted = False
        # 中断时 _close_client() 会将 _client 置为 None，这里需要重建
        if self.client._client is None:
            self.client._reset_client()

    # ============================================================
    # 对话功能
    # ============================================================
    def chat(self, user_input: str) -> None:
        """
        处理用户对话 (新增连续错误熔断逻辑 + 计划模式支持)
        """
        self.conversation.add_user_message(user_input)
        round_count = 0
        
        # 新一轮用户输入，重置工具显示追踪
        self.tool_executor._last_displayed_tool = None
        
        # 计划模式：注入任务规划提示
        if self._plan_mode:
            from claude_code.tools.builtins.todo import get_todo_list
            todo = get_todo_list()
            plan_prompt = (
                "## 计划模式\n"
                f"你正在计划模式下工作。当前任务清单：\n\n"
                f"{todo.to_prompt_text()}\n\n"
                "执行规则：\n"
                "1. 如果还没有任务清单，先用 TodoCreate 创建完整的执行计划\n"
                "2. 每开始一个任务，先调 TodoUpdate(id, \"in_progress\")\n"
                "3. 完成后调 TodoUpdate(id, \"completed\")\n"
                "4. 失败且无法恢复调 TodoUpdate(id, \"failed\")，继续下一个\n"
                "5. 不要跳过任务，除非有明确依赖关系\n"
                "6. 全部完成后，给出最终总结\n"
                "7. **禁止提前停止**：只要还有未完成的任务，就必须继续调用工具执行，不允许只输出文字就停下\n\n"
                f"进度：{todo.progress_text}"
            )
            self.conversation.add_user_message(plan_prompt)
        
        # 【修改点 2】：连续错误追踪状态
        consecutive_failures = 0
        last_error_signature = ""

        while round_count < self.MAX_TOOL_ROUNDS:
            round_count += 1

            # 每轮注入路径环境提醒（确保长对话不遗忘路径）
            path_reminder = (
                f"[系统提醒] 当前操作根目录: {self.path_manager.active_path}，"
                f"所有文件操作必须基于此路径。"
            )

            context_limit = self.current_model.context_limit if self.current_model else 100000
            messages = self.conversation.get_optimized_messages(max_tokens=context_limit)

            file_context = self.files.build_context()
            if file_context:
                insert_idx = 1 if messages and messages[0].get("role") == "system" else 0
                messages.insert(insert_idx, {"role": "user", "content": file_context})

            # 不再估算输入 token，完全依赖 API 返回的真实 usage 累加
            response, has_tools, report = self._handle_response(messages)

            # 计划模式：工具执行后刷新 Todo 面板
            if self._plan_mode and has_tools and report:
                from claude_code.tools.builtins.todo import get_todo_list
                from claude_code.ui.components import show_todo_panel
                todo = get_todo_list()
                # 有工具执行，说明模型在推进，重置提醒计数
                self._plan_reminder_count = 0
                if todo.items:
                    console.print()
                    show_todo_panel(todo)
                    # 全部完成时退出计划模式
                    if todo.is_all_done:
                        from claude_code.ui.components import show_plan_complete
                        console.print()
                        show_plan_complete(todo)
                        self._plan_mode = False
                        self._plan_task = ""
                        break

            # 检查是否被用户中断（Ctrl+C），中断后直接退出循环
            if self._is_interrupted():
                console.print(f"\n[{COLORS['warning']}]{ICONS['warning']} 已中断请求[/]")
                break

            if not has_tools:
                # 计划模式下，如果还有未完成任务，强制注入提醒让模型继续
                if self._plan_mode:
                    from claude_code.tools.builtins.todo import get_todo_list
                    todo = get_todo_list()
                    if todo.items and not todo.is_all_done:
                        # 熔断检查：连续提醒超过上限则退出计划模式
                        self._plan_reminder_count += 1
                        if self._plan_reminder_count > PLAN.REMINDER_MAX:
                            from claude_code.ui.components import show_plan_aborted
                            show_plan_aborted(
                                f"模型连续 {PLAN.REMINDER_MAX} 次未按计划调用工具推进任务",
                                todo,
                            )
                            self._plan_mode = False
                            self._plan_task = ""
                            self._plan_reminder_count = 0
                            break

                        # 构建具体行动指令：告诉模型该调什么工具、传什么参数
                        in_progress_items = [t for t in todo.items if t.status == "in_progress"]
                        pending_items = [t for t in todo.items if t.status == "pending"]

                        if in_progress_items:
                            task = in_progress_items[0]
                            action_hint = (
                                f"请立即调用 TodoUpdate(id=\"{task.id}\", status=\"completed\") "
                                f"标记当前任务为完成，然后继续执行下一个任务。"
                            )
                        elif pending_items:
                            task = pending_items[0]
                            action_hint = (
                                f"请调用 TodoUpdate(id=\"{task.id}\", status=\"in_progress\") "
                                f"开始下一个任务，然后执行实际工作。"
                            )
                        else:
                            action_hint = "请检查任务状态并继续执行。"

                        # 连续无工具调用加强警告
                        no_tool_warning = ""
                        if self._plan_reminder_count >= PLAN.NO_TOOL_ROUNDS_MAX:
                            no_tool_warning = (
                                f"\n⚠ 你已连续 {self._plan_reminder_count} 轮未调用任何工具！"
                                f"计划模式下必须通过工具调用来推进任务，请立即执行上述行动。"
                            )

                        remind = (
                            f"[系统提醒] 你当前处于计划模式，进度：{todo.progress_text}\n"
                            f"当前任务状态：\n{todo.to_prompt_text()}\n\n"
                            f"行动：{action_hint}\n\n"
                            f"注意：你必须调用工具来推进任务，不允许只输出文字。"
                            f"（提醒 {self._plan_reminder_count}/{PLAN.REMINDER_MAX}）"
                            f"{no_tool_warning}"
                        )
                        self.conversation.add_user_message(remind)
                        console.print(f"[dim]{ICONS['info']} 计划模式：检测到模型提前停止，已注入行动提醒 ({todo.progress_text}) [{self._plan_reminder_count}/{PLAN.REMINDER_MAX}][/]")
                        continue
                break

            # 检查本轮工具执行是否有用户真实中断（Ctrl+C）
            # 直接从 ExecutionReport 判断，不依赖文本内容（避免历史残留误判）
            if report and report.has_interrupted:
                console.print(f"\n[{COLORS['warning']}]{ICONS['warning']} 用户中断执行，停止当前任务[/]")
                break

            # 检查本轮是否有工具执行失败（从 report 结构化数据判断，不解析文本）
            is_error_round = False
            current_error_sig = ""

            if report:
                # 本轮有失败且无成功，视为失败轮次
                if report.failed_count > 0 and report.success_count == 0:
                    is_error_round = True
                    # 取第一个失败的工具名作为签名
                    for r in report.results:
                        if not r.success and not r.skipped and not r.interrupted:
                            current_error_sig = r.tool_call.name
                            break

            if is_error_round:
                if current_error_sig == last_error_signature:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 1
                    last_error_signature = current_error_sig
                
                # 【熔断逻辑】：连续 3 次相同错误
                if consecutive_failures >= 3:
                    stop_msg = (
                        f"⚠️ 检测到连续 {consecutive_failures} 次相同的工具执行错误 ({current_error_sig})。\n"
                        f"请停止重复尝试相同的命令。重新审视你的逻辑，或者向用户报告无法完成此步骤。"
                    )
                    self.conversation.add_user_message(stop_msg)
                    console.warning(f"\n{ICONS['warning']} 触发连续错误熔断，已通知模型停止重试。\n")
                    break # 强制退出循环
            else:
                # 如果本轮有成功，重置计数器
                consecutive_failures = 0
                last_error_signature = ""



        # 保存统计
        self.stats.save_session(
            model_id=self.current_model.id if self.current_model else "",
            message_count=self.conversation.message_count,
        )

    def _handle_response(self, messages: list) -> tuple:
        """
        处理 AI 响应

        Args:
            messages: 消息列表

        Returns:
            (响应文本, 是否有工具调用, ExecutionReport 或 None)
        """
        model_name = self.current_model.name if self.current_model else "AI"

        # 传入工具定义（Native Tool Calling）
        tools_definition = tool_calling_manager.get_tools_definition()

        try:
            # 收集流式响应
            full_response, native_tool_calls, real_usage, duration = self._collect_streaming_response(
                messages, tools_definition, model_name
            )

            if not full_response.strip() and not native_tool_calls:
                return "", False, None

            # 处理响应（解析工具、渲染、保存）
            tool_calls = self._process_response(
                full_response, native_tool_calls, model_name, duration, real_usage
            )

            # 执行工具调用
            if tool_calls:
                report = self._execute_tools(tool_calls)

                # 如果所有工具都被跳过（用户取消），停止循环
                if report.skipped_count == report.total:
                    return full_response, False, report

                # 构建反馈消息
                feedback = self._build_tool_feedback(report)
                if feedback:
                    self.conversation.add_user_message(feedback)

                return full_response, True, report

            return full_response, False, None

        except Exception as e:
            # 区分用户中断和真正的错误
            if self._is_interrupted():
                # 用户主动中断，不是错误
                return "", False, None
            console.error(f"生成失败: {e}")
            return "", False, None

    def _collect_streaming_response(
        self,
        messages: list,
        tools_definition: list,
        model_name: str
    ) -> tuple:
        """
        收集流式响应（完成后一次性渲染）

        Args:
            messages: 消息列表
            tools_definition: 工具定义（原生模式）
            model_name: 模型名称（用于显示）

        Returns:
            (响应文本, 原生工具调用列表, 真实 token 使用量, 耗时)
        """
        import threading

        start_time = time.time()
        full_response = ""
        native_tool_calls = []
        real_usage = {"input": 0, "output": 0}
        streaming_tokens = 0  # 流式输出token计数

        # 【新增】用于控制后台线程停止的标志
        stop_timer_event = threading.Event()

        # 进度条前空行，与输入分隔
        console.print()

        # 思考状态：显示 Spinner（无进度条）
        with Progress(
            SpinnerColumn(spinner_name="dots", style=COLORS['primary']),
            SafeTextColumn(),  # 使用安全的 TextColumn，避免花括号格式化错误
            console=console.get_console(),
            transient=True,
        ) as progress:

            # 初始描述：⠋ thinking...
            initial_desc = f"[{COLORS['primary']}]thinking...[/]"
            task = progress.add_task(initial_desc, total=None)

            # 【新增】后台定时刷新线程：确保时间实时跳动，不依赖 API Chunk
            # 同时检测中断标志，强制关闭阻塞的 httpx 连接（解决等响应头时无法中断的问题）
            def _refresh_timer():
                while not stop_timer_event.is_set():
                    # 检测中断：如果用户按了 Ctrl+C，强制关闭底层连接让阻塞的请求立即退出
                    if self._interrupted:
                        try:
                            self.client._close_client()
                        except Exception:
                            pass
                        break
                    elapsed = time.time() - start_time
                    # ⠋ thinking... 3.2s 120 tok
                    tok_display = f" {streaming_tokens} tok" if streaming_tokens > 0 else ""
                    new_desc = f"[{COLORS['primary']}]thinking...[/] [dim]{elapsed:.1f}s[/] [cyan]{tok_display}[/]"
                    try:
                        progress.update(task, description=new_desc)
                    except Exception:
                        pass  # 忽略进度条已结束时的异常
                    stop_timer_event.wait(0.1)  # 每 0.1s 刷新一次

            timer_thread = threading.Thread(target=_refresh_timer, daemon=True)
            timer_thread.start()

            try:
                for chunk in self.client.send_message(
                    model_id=self.current_model.id if self.current_model else "",
                    messages=messages,
                    tools=tools_definition,
                    stream=True,
                ):
                    # 检查是否被中断（CTRL+C）
                    if self._is_interrupted():
                        break

                    # None 是心跳，跳过处理
                    if chunk is None:
                        continue

                    # 提取文本内容
                    content = self.client.extract_content(chunk)
                    if content:
                        full_response += content
                        streaming_tokens += 1  # 每收到内容就累加（简化计数）

                    # 提取原生工具调用（流式）
                    self._accumulate_native_tool_calls(chunk, native_tool_calls)

                    # 提取真实 token 使用量（最后一个 chunk 包含 usage）
                    usage = self.client.extract_usage(chunk)
                    if usage:
                        real_usage = usage
            finally:
                # 确保退出循环时停止后台线程
                stop_timer_event.set()
                timer_thread.join(timeout=1.0)

        # 在 Progress 上下文外安全显示中断消息
        if self._is_interrupted():
            console.print(f"[{COLORS['warning']}]{ICONS['warning']} 已中断请求[/]")

        duration = time.time() - start_time
        return full_response, native_tool_calls, real_usage, duration

    def _accumulate_native_tool_calls(self, chunk: Optional[dict], native_tool_calls: list) -> None:
        """
        累积原生工具调用（流式）

        Args:
            chunk: API 响应块（None 时跳过）
            native_tool_calls: 工具调用累积列表（会被修改）
        """
        if chunk is None:
            return
        tool_chunks = self.client.extract_tool_calls(chunk)
        for tc in tool_chunks:
            idx = tc.get("index", 0)
            func = tc.get("function", {})

            # 确保列表足够长
            while len(native_tool_calls) <= idx:
                native_tool_calls.append({"id": "", "function": {"name": "", "arguments": ""}})

            # 累积工具调用信息
            if tc.get("id"):
                native_tool_calls[idx]["id"] = tc["id"]
            if func.get("name"):
                native_tool_calls[idx]["function"]["name"] = func["name"]
            if func.get("arguments"):
                native_tool_calls[idx]["function"]["arguments"] += func["arguments"]

    def _process_response(
        self,
        full_response: str,
        native_tool_calls: list,
        model_name: str,
        duration: float,
        real_usage: dict
    ) -> list:
        """
        处理响应（解析工具调用、渲染、保存）

        Args:
            full_response: 完整响应文本
            native_tool_calls: 原生工具调用列表
            model_name: 模型名称
            duration: 响应耗时
            real_usage: 真实 token 使用量

        Returns:
            解析后的工具调用列表
        """
        # 解析工具调用
        tool_calls = tool_calling_manager.parse_tool_calls(native_tool_calls)

        # 渲染响应（完成后一次性渲染）
        if full_response.strip():
            render_response(full_response, model_name, duration, real_usage, has_tools=bool(tool_calls))
            # AI Panel 打印后重置工具追踪，确保下一个工具摘要前有间距
            self.tool_executor._last_displayed_tool = None

        # 保存 AI 响应：优先使用真实 token，否则回退到估算
        if real_usage["input"] > 0:
            # 使用增量计算费用
            input_diff, output_tokens = self.stats.set_real_usage(
                real_usage["input"], real_usage["output"]
            )
            cost = self._calculate_cost(input_diff, output_tokens)
            self.stats.add_cost(cost)
        else:
            self.stats.update_output(full_response)
        self.conversation.add_assistant_message(full_response)

        return tool_calls

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        计算本次请求费用

        Args:
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数

        Returns:
            费用（美元）
        """
        if not self.current_model:
            return 0.0

        input_price, output_price = self.current_model.get_prices()
        if input_price == 0 and output_price == 0:
            return 0.0

        # 费用 = (input × input_price + output × output_price) / 1,000,000
        cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
        return cost

    def _execute_tools(self, tool_calls: List[ToolCall]) -> ExecutionReport:
        """
        执行工具调用

        Args:
            tool_calls: 工具调用列表

        Returns:
            执行报告
        """
        # 限制工具数量
        if len(tool_calls) > self.MAX_TOOLS_PER_ROUND:
            tool_calls = tool_calls[:self.MAX_TOOLS_PER_ROUND]
            console.warning(f"工具调用数量超过限制，仅执行前 {self.MAX_TOOLS_PER_ROUND} 个")

        # 执行工具（传入中断检查函数）
        report = self.tool_executor.execute_batch(tool_calls, interrupt_check=self._is_interrupted)

        # 显示执行摘要 (可选，如果 progress_display 已经展示了详细卡片，这里可以简化)
        # console.print(report.get_summary()) 

        return report

    def _build_tool_feedback(self, report: ExecutionReport) -> Optional[str]:
        """
        构建工具执行反馈消息

        Args:
            report: 执行报告

        Returns:
            反馈消息文本
        """
        if report.total == 0:
            return None

        lines = ["<tool_results>"]

        # 如果有用户中断，添加特殊标记
        if report.has_interrupted:
            lines.append("<system_message type=\"user_interrupt\">")
            lines.append("用户按下 CTRL+C 中断了正在执行的操作。")
            lines.append("这表示用户希望停止当前任务，不要再继续尝试。")
            lines.append("请向用户确认是否需要继续其他工作，或者直接等待用户的新指令。")
            lines.append("</system_message>")

        for result in report.results:
            if result.skipped:
                lines.append(f"<result tool=\"{result.tool_call.name}\" status=\"skipped\">")
                if result.permission_denied:
                    lines.append("权限被拒绝，此操作需要用户明确授权")
                else:
                    lines.append("用户主动取消执行")
            elif result.interrupted:
                # 用户中断：使用特殊状态，让模型理解这不是"失败"
                lines.append(f"<result tool=\"{result.tool_call.name}\" status=\"interrupted\">")
                lines.append("用户按下 CTRL+C 中断了此操作")
            elif result.success:
                lines.append(f"<result tool=\"{result.tool_call.name}\" status=\"success\">")
                # 压缩大结果
                output = self._compress_tool_output(
                    result.output,
                    result.tool_call.name,
                    result.tool_call.parameters
                )
                lines.append(output)
            else:
                lines.append(f"<result tool=\"{result.tool_call.name}\" status=\"error\">")
                lines.append(result.error or "执行失败")
            lines.append("</result>")

        lines.append("</tool_results>")

        return "\n".join(lines)

    def _compress_tool_output(
        self,
        output: str,
        tool_name: str,
        parameters: dict
    ) -> str:
        """
        压缩工具输出（减少历史膨胀）

        Args:
            output: 原始输出
            tool_name: 工具名称
            parameters: 工具参数

        Returns:
            压缩后的输出
        """
        MAX_OUTPUT_LEN = 3000  # 压缩阈值

        if len(output) <= MAX_OUTPUT_LEN:
            return output

        # Read 工具：已经是摘要模式，保留原文
        if tool_name == "Read":
            # 检查是否是摘要输出
            if "○" in output or "结构概览" in output:
                return output  # 摘要已经很精简
            # 非摘要的大输出，压缩
            return self._compress_large_output(output, MAX_OUTPUT_LEN)

        # Grep/Glob：保留结果但压缩
        if tool_name in ("Grep", "Glob"):
            return self._compress_large_output(output, MAX_OUTPUT_LEN)

        # Bash：保留前后部分
        if tool_name == "Bash":
            return self._compress_large_output(output, MAX_OUTPUT_LEN)

        # 其他工具：通用压缩
        return self._compress_large_output(output, MAX_OUTPUT_LEN)

    def _compress_large_output(self, output: str, max_len: int = 3000) -> str:
        """
        压缩大输出（保留前后部分）

        Args:
            output: 原始输出
            max_len: 最大长度

        Returns:
            压缩后的输出
        """
        if len(output) <= max_len:
            return output

        half = max_len // 2
        head = output[:half]
        tail = output[-half:]
        omitted = len(output) - max_len

        return f"{head}\n\n... (省略 {omitted} 字符) ...\n\n{tail}"

    def show_tools_history(self) -> None:
        """显示工具执行历史"""
        history = self.tool_executor.get_history()

        if not history:
            console.warning("暂无工具执行历史")
            return

        console.print(f"\n[{COLORS['primary']}]=== 工具执行历史 ===[/]")

        for entry in history:
            timestamp = datetime.now().strftime('%H:%M:%S')
            status = "✓" if entry.get('success') else "✗"
            tool_name = entry.get('tool', 'unknown')

            console.print(f"[{COLORS['text_muted']}]{timestamp}[/] {status} {tool_name}")

            if entry.get('error'):
                console.print(f"   ", end="")
                console.print(entry['error'], markup=False, highlight=False, style=COLORS['error'])

        console.print()

    def reset_conversation(self) -> None:
        """重置会话"""
        if not self.conversation.is_empty:
            self.stats.save_session(
                model_id=self.current_model.id if self.current_model else "",
                message_count=self.conversation.message_count,
                finalize=True,
            )

        self.conversation.reset()
        self.stats.reset_session()
        self.files.clear()
        self.permission_manager.clear_session()
        self.tool_executor.clear_history()
        self._plan_mode = False
        self._plan_task = ""
        self._plan_reminder_count = 0
        self._setup_system_prompt()  # 重新设置系统提示词（含路径环境）
        self._update_input_state()

        # 重置 TodoList
        from claude_code.tools.builtins.todo import reset_todo_list
        reset_todo_list()

        # 重置 PathManager（回到 workplace 模式）
        self.path_manager = reset_path_manager()

        console.clear()
        show_welcome(self.current_model.name if self.current_model else "Claude")

    # ============================================================
    # 模型/风格切换
    # ============================================================

    def select_model(self) -> None:
        """选择模型"""
        models = self.settings.models
        if not models:
            console.warning("没有可用的模型")
            return

        options = [
            {
                "name": m.name,
                "value": i,
                "desc": f"{m.context_limit // 1000}K Context",
            }
            for i, m in enumerate(models)
        ]

        choice = interactive_menu("SELECT MODEL", options)

        if choice is not None:
            self.current_model = models[choice]
            self._update_input_state()
            console.success(f"已切换至 {self.current_model.name}")

    def select_style(self) -> None:
        """选择风格"""
        style_ids = self.settings.style_ids
        if not style_ids:
            console.warning("没有可用的风格")
            return

        # 风格描述
        descriptions = {
            "expert": "严谨高效的代码专家",
            "02": "热情大胆的 02",
            "mai": "成熟毒舌的麻衣学姐",
            "fubuki": "高雅威严的吹雪",
            "violet": "礼貌平和的薇尔莉特",
        }

        options = [
            {
                "name": sid.upper(),
                "value": sid,
                "desc": descriptions.get(sid, ""),
            }
            for sid in style_ids
        ]

        choice = interactive_menu("AI PERSONA", options)

        if choice:
            self.current_style_id = choice
            self._setup_system_prompt()
            console.success(f"已应用风格: {choice.upper()}")

    # ============================================================
    # 会话保存/加载
    # ============================================================

    def save_conversation(self) -> None:
        """保存会话"""
        if self.conversation.is_empty:
            console.warning("没有对话记录，无法保存")
            return

        messages = self.conversation.get_messages()
        user_msgs = [m for m in messages if m["role"] == "user"]
        title = user_msgs[0]["content"][:20] if user_msgs else "未命名"
        title = title.replace('\n', ' ').strip()

        for c in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
            title = title.replace(c, '_')

        filename = f"chat_{datetime.now().strftime('%m%d_%H%M')}_{title}.json"
        filepath = os.path.join(self.history_dir, filename)

        try:
            data = {
                "title": title,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "model": self.current_model.id if self.current_model else "",
                "messages": messages,
            }

            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            json_str = json_str.encode('utf-8', errors='replace').decode('utf-8')
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(json_str)

            console.success(f"会话已保存: {filename}")

        except Exception as e:
            console.error(f"保存失败: {e}")

    def load_history(self) -> None:
        """加载历史"""
        if not os.path.exists(self.history_dir):
            console.warning("没有历史记录")
            return

        files = sorted(
            [f for f in os.listdir(self.history_dir) if f.endswith('.json')],
            reverse=True,
        )

        if not files:
            console.warning("没有历史记录")
            return

        options = []
        for f in files[:10]:
            try:
                with open(os.path.join(self.history_dir, f), 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                    options.append({
                        "name": data.get("title", "未命名")[:20],
                        "value": f,
                        "desc": data.get("time", ""),
                    })
            except Exception:
                continue

        if not options:
            console.warning("没有可用的历史记录")
            return

        choice = interactive_menu("LOAD HISTORY", options)

        if choice:
            self._load_history_file(choice)

    def _load_history_file(self, filename: str) -> None:
        """加载历史文件"""
        try:
            filepath = os.path.join(self.history_dir, filename)

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.conversation.load_messages(data.get("messages", []))

            model_id = data.get("model")
            if model_id:
                model = self.settings.get_model(model_id)
                if model:
                    self.current_model = model

            self._update_input_state()
            console.clear()
            console.success(f"已加载: {data.get('title', '未命名')}")

            for msg in self.conversation.get_messages():
                if msg["role"] == "user":
                    console.print(f"\n[bold {COLORS['info']}]{ICONS['user']} YOU[/]")
                    console.print(msg["content"])
                elif msg["role"] == "assistant":
                    console.print(f"\n[bold {COLORS['primary']}]{ICONS['claude']} CLAUDE[/]")
                    console.markdown(msg["content"])

        except Exception as e:
            console.error(f"加载失败: {e}")

    # ============================================================
    # 主循环
    # ============================================================

    def run(self) -> None:
        """运行主循环"""
        console.clear()
        show_welcome(self.current_model.name if self.current_model else "Claude")

        try:
            while True:
                try:
                    # 在每次对话开始前，清除上一轮的中断标志
                    self._clear_interrupt()

                    # 在每次对话开始前，显示紧凑的状态头
                    show_status_bar(
                        model_name=self.current_model.name if self.current_model else "Claude",
                        total_tokens=self.stats.session.total_tokens,
                        file_count=self.files.count,
                        price_short=self.current_model.get_price_short() if self.current_model else "",
                        total_cost=self.stats.session.cost,
                    )

                    user_input = self.input_handler.prompt()

                    if not user_input:
                        console.info("请输入内容，或使用 /help 查看帮助")
                        continue

                    if user_input.startswith('/'):
                        result = self.commands.execute(user_input)
                        if result is True:
                            break
                        # 命令执行反馈
                        console.success("命令已执行")
                        continue

                    self.chat(user_input)

                except EOFError:
                    break

        finally:
            self._on_exit()
            console.print(f"\n[{COLORS['primary']}]{ICONS['claude']} 感谢使用 {APP_NAME}！[/]\n")