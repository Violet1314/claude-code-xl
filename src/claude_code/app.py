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
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.text import Text
from rich.table import Column


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
from claude_code.config.defaults import VERSION, APP_NAME, WORKPLACE_DIR
from claude_code.core.client import APIClient
from claude_code.core.conversation import Conversation
from claude_code.core.files import FileManager
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
)

class Application:
    """Claude Code Terminal 主应用"""
    # 工具执行限制
    MAX_TOOL_ROUNDS = 15        # 最大循环轮次
    MAX_TOOLS_PER_ROUND = 40   # 每轮最大工具数

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
        # CTRL+C 中断管理：记录上次信号时间，实现单击中断、双击退出
        self._last_sigint: float = 0.0
        self._sigint_double_threshold: float = 1.0  # 双击判定窗口（秒）
        signal.signal(signal.SIGINT, self._signal_handler)


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

        return f"## 环境信息\n{shell_info}\n\n{autonomy_info}"

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

    def _signal_handler(self, sig, frame) -> None:
        """信号处理：单击中断当前操作，双击退出程序"""
        now = time.time()
        if now - self._last_sigint < self._sigint_double_threshold:
            # 双击：退出程序
            self._on_exit()
            console.print(f"\n[{COLORS['primary']}]{ICONS['claude']} 再见！[/]\n")
            sys.exit(0)
        # 单击：标记中断，不退出
        self._last_sigint = now
        console.print(f"\n[{COLORS['warning']}]{ICONS['warning']} 中断中...，再按一次退出[/]")

    def _is_interrupted(self) -> bool:
        """检查是否有待处理的中断信号"""
        return time.time() - self._last_sigint < self._sigint_double_threshold

    # ============================================================
    # 对话功能
    # ============================================================
    def chat(self, user_input: str) -> None:
        """
        处理用户对话 (新增连续错误熔断逻辑)
        """
        self.conversation.add_user_message(user_input)
        round_count = 0
        
        # 【修改点 2】：连续错误追踪状态
        consecutive_failures = 0
        last_error_signature = ""

        while round_count < self.MAX_TOOL_ROUNDS:
            round_count += 1

            context_limit = self.current_model.context_limit if self.current_model else 100000
            messages = self.conversation.get_optimized_messages(max_tokens=context_limit)

            file_context = self.files.build_context()
            if file_context:
                insert_idx = 1 if messages and messages[0].get("role") == "system" else 0
                messages.insert(insert_idx, {"role": "user", "content": file_context})

            # 不再估算输入 token，完全依赖 API 返回的真实 usage 累加
            response, has_tools = self._handle_response(messages)

            if not has_tools:
                break

            # 【修改点 3】：检查本轮是否有工具执行失败
            # 注意：_handle_response 内部已经执行了工具并构建了 feedback
            # 我们需要从 conversation 的最新消息中提取错误特征，或者更简单地：
            # 在 _execute_tools 或 _build_tool_feedback 中记录状态。
            # 为了简化，我们在 _handle_response 返回后，检查最后一条用户消息（即 feedback）
            
            last_msg = self.conversation.get_messages()[-1]
            is_error_round = False
            is_interrupted = False
            current_error_sig = ""

            if last_msg["role"] == "user" and "<tool_results>" in last_msg["content"]:
                # 检查是否有用户中断
                if 'status="interrupted"' in last_msg["content"] or "user_interrupt" in last_msg["content"]:
                    is_interrupted = True
                    console.print(f"\n[{COLORS['warning']}]{ICONS['warning']} 用户中断执行，停止当前任务[/]")
                    break  # 直接退出循环，不再让模型重试

                # 简单解析：如果反馈中包含多个 error 且没有 success，视为失败轮次
                if '<status="error">' in last_msg["content"] and '<status="success">' not in last_msg["content"]:
                    is_error_round = True
                    # 提取第一个错误工具名作为签名
                    import re
                    match = re.search(r'tool="(.*?)"', last_msg["content"])
                    if match:
                        current_error_sig = match.group(1)

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

            console.print(f"\n[{COLORS['info']}]{ICONS['info']} 继续处理...[/]")

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
            (响应文本, 是否有工具调用)
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
                return "", False

            # 处理响应（解析工具、渲染、保存）
            tool_calls = self._process_response(
                full_response, native_tool_calls, model_name, duration, real_usage
            )

            # 执行工具调用
            if tool_calls:
                console.print()  # 空行
                report = self._execute_tools(tool_calls)

                # 如果所有工具都被跳过（用户取消），停止循环
                if report.skipped_count == report.total:
                    return full_response, False

                # 构建反馈消息
                feedback = self._build_tool_feedback(report)
                if feedback:
                    self.conversation.add_user_message(feedback)

                return full_response, True

            return full_response, False

        except Exception as e:
            console.error(f"生成失败: {e}")
            return "", False

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
        
        # 【新增】用于控制后台线程停止的标志
        stop_timer_event = threading.Event()

        # 思考状态：显示进度条
        with Progress(
            SpinnerColumn(spinner_name="dots", style=COLORS['primary']),
            SafeTextColumn(),  # 使用安全的 TextColumn，避免花括号格式化错误
            BarColumn(bar_width=20, pulse_style=COLORS['primary']),
            console=console.get_console(),
            transient=True,
        ) as progress:
            
            # 初始描述
            initial_desc = f"[bold {COLORS['primary']}]{model_name}[/] [dim]正在思考...[/]"
            task = progress.add_task(initial_desc, total=None, completed=0)

            # 【新增】后台定时刷新线程：确保时间实时跳动，不依赖 API Chunk
            def _refresh_timer():
                while not stop_timer_event.is_set():
                    elapsed = time.time() - start_time
                    # 排版：将时间紧贴在“正在思考...”后面，无括号
                    new_desc = f"[bold {COLORS['primary']}]{model_name}[/] [dim]正在思考... {elapsed:.1f}s[/]"
                    try:
                        progress.update(task, description=new_desc)
                    except Exception:
                        pass # 忽略进度条已结束时的异常
                    stop_timer_event.wait(0.1) # 每 0.1s 刷新一次

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
                        console.print(f"[{COLORS['warning']}]{ICONS['warning']} 已中断请求[/]")
                        break

                    # 提取文本内容
                    content = self.client.extract_content(chunk)
                    if content:
                        full_response += content
                        # 更新 Token/字符计数
                        progress.update(task, completed=len(full_response))

                    # 提取原生工具调用（流式）
                    self._accumulate_native_tool_calls(chunk, native_tool_calls)

                    # 提取真实 token 使用量（最后一个 chunk 包含 usage）
                    usage = self.client.extract_usage(chunk)
                    if usage:
                        real_usage = usage
            finally:
                # 【新增】确保退出循环时停止后台线程
                stop_timer_event.set()
                timer_thread.join(timeout=1.0)

        duration = time.time() - start_time
        return full_response, native_tool_calls, real_usage, duration

    def _accumulate_native_tool_calls(self, chunk: dict, native_tool_calls: list) -> None:
        """
        累积原生工具调用（流式）

        Args:
            chunk: API 响应块
            native_tool_calls: 工具调用累积列表（会被修改）
        """
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
            render_response(full_response, model_name, duration, real_usage)

        # 保存 AI 响应：优先使用真实 token，否则回退到估算
        if real_usage["input"] > 0:
            self.stats.set_real_usage(real_usage["input"], real_usage["output"])
            # 计算并累加费用
            cost = self._calculate_cost(real_usage["input"], real_usage["output"])
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
            if "📄" in output or "结构概览" in output:
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
            status = "✅" if entry.get('success') else "❌"
            tool_name = entry.get('tool', 'unknown')

            console.print(f"[{COLORS['system']}]{timestamp}[/] {status} {tool_name}")

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
        self._setup_system_prompt()  # 重新设置系统提示词
        self._update_input_state()

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
                    console.print(f"\n[bold {COLORS['user']}]{ICONS['user']} YOU[/]")
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