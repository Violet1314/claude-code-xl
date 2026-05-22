"""主应用类 - 整合所有模块 (Refactored for Elegance)"""
import re
import os
import sys
import json
import time
import signal
import atexit
import threading
from typing import Optional, List, Any
from dataclasses import replace
from datetime import datetime
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

from claude_code.core.tool_feedback import build_tool_feedback, compress_tool_output
from claude_code.core.autosave import AutosaveManager
from claude_code.utils.tokens import estimate_messages_tokens


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
        self.config_dir = config_dir
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
        # 计划模式状态（必须在 _update_input_state 之前初始化）
        self._plan_mode: bool = False            # 是否处于计划模式
        self._plan_task: str = ""                # 计划模式任务描述
        self._plan_reminder_count: int = 0       # 计划模式连续提醒计数（熔断用）
        self._plan_prev_statuses: dict = {}      # 上轮任务状态快照 {id: status}（增量推送用）
        self._plan_started_at: str = ""
        self._plan_completed_at: str = ""
        self._plan_final_summary: str = ""
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
        # 缓存最后一次 Bash 工具的完整输出（供 /last-output 命令查看）
        self._last_bash_output: str = ""
        self._last_bash_command: str = ""
        # 自动保存管理器（崩溃恢复）
        self._autosave = AutosaveManager()
        signal.signal(signal.SIGINT, self._signal_handler)

    def _setup_system_prompt(self) -> None:
        """设置系统提示词"""
        base_prompt = self.settings.get_prompt(self.current_style_id)

        # 注入环境信息
        env_info = self._get_environment_info()

        # 注入项目记忆文件
        memory_info = self._load_project_memory()

        full_prompt = f"{base_prompt}\n\n{env_info}"
        if memory_info:
            full_prompt = f"{full_prompt}\n\n{memory_info}"

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

    def _load_project_memory(self) -> Optional[str]:
        """
        加载项目记忆文件（.claude/CLAUDE.md）

        在操作根目录下查找 .claude/CLAUDE.md，如果存在则将其内容
        注入到系统提示词中，让 AI 每次启动时立即理解项目上下文。

        Returns:
            项目记忆文本，不存在则返回 None
        """
        from pathlib import Path as PathLib

        # 在 active_path 下查找
        active = self.path_manager.active_path
        memory_path = PathLib(active) / ".claude" / "CLAUDE.md"

        if not memory_path.exists():
            # 如果是 workplace 模式，不再查找其他位置
            return None

        try:
            content = memory_path.read_text(encoding='utf-8').strip()
            if not content:
                return None
            # 限制最大长度，避免占用过多 token
            MAX_MEMORY_LEN = 4000
            if len(content) > MAX_MEMORY_LEN:
                content = content[:MAX_MEMORY_LEN] + f"\n\n... (项目记忆文件过长，已截断至 {MAX_MEMORY_LEN} 字符)"
            return f"## 项目记忆\n来源: {memory_path}\n\n{content}"
        except (OSError, UnicodeDecodeError):
            return None

    def _update_input_state(self) -> None:
        """更新输入处理器状态"""
        self.input_handler.update_state(
            model_name=self.current_model.name if self.current_model else "Claude",
            file_count=self.files.count,
            plan_mode=self._plan_mode,
        )

    # ============================================================
    # 自动保存 / 崩溃恢复
    # ============================================================
    def _estimate_context_usage(self) -> int:
        """估算当前对话消息占用的上下文 token 数

        注意：这与 stats.session.total_tokens（累计 API 消耗）不同。
        上下文窗口用量 = 当前对话历史所有消息的 token 之和，
        而累计消耗包含多轮工具调用的重复计数。
        """
        try:
            messages = self.conversation.get_optimized_messages(max_tokens=None)
            return estimate_messages_tokens(messages)
        except Exception:
            # 降级：使用 API 返回的最新 input_tokens 作为近似值
            return self.stats.session.input_tokens

    def _build_autosave_data(self) -> dict:
        """构建自动保存数据"""
        from claude_code.tools.builtins.todo import get_todo_list
        todo = get_todo_list()

        provider = self.settings.get_provider(self.current_model) if self.current_model else None
        path_state = {}
        if hasattr(self, 'path_manager') and self.path_manager:
            path_state = {
                "active_path": str(self.path_manager.active_path),
                "workplace": str(self.path_manager.workplace),
                "is_workplace_mode": self.path_manager.is_workplace_mode,
            }

        return {
            "messages": self.conversation.get_messages(),
            "model": self.current_model.id if self.current_model else "",
            "active_profile": getattr(self.settings, 'active_profile', ""),
            "provider_profile": provider.profile if provider else "",
            "style_id": self.current_style_id,
            "active_path": str(self.path_manager.active_path),
            "path_state": path_state,
            "tool_history": self.tool_executor.get_history(limit=100) if hasattr(self, 'tool_executor') else [],
            "plan_mode": self._plan_mode,
            "plan_task": self._plan_task,
            "plan_title": self._plan_task[:40] if self._plan_task else "",
            "plan_started_at": getattr(self, '_plan_started_at', ""),
            "plan_completed_at": getattr(self, '_plan_completed_at', ""),
            "plan_final_summary": getattr(self, '_plan_final_summary', ""),
            "plan_prev_statuses": getattr(self, '_plan_prev_statuses', {}),
            "todos": [item.__dict__ for item in todo.items] if todo.items else [],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _check_autosave_recovery(self) -> None:
        """启动时检查是否有未恢复的自动保存"""
        data = self._autosave.load()
        if not data:
            return

        timestamp = data.get("timestamp", "未知时间")
        msg_count = len(data.get("messages", []))
        plan_mode = data.get("plan_mode", False)
        plan_info = " [计划模式]" if plan_mode else ""

        from claude_code.ui.input import interactive_menu
        options = [
            {"name": "恢复会话", "value": "restore", "desc": f"恢复 {timestamp} 的会话（{msg_count} 条消息{plan_info}）"},
            {"name": "放弃", "value": "discard", "desc": "丢弃自动保存，开始新会话"},
        ]
        choice = interactive_menu("AUTOSAVE RECOVERY", options)
        if choice == "restore":
            self._restore_autosave(data)
        else:
            self._autosave.clear()

    def _restore_autosave(self, data: dict) -> None:
        """从自动保存数据恢复会话"""
        # 1. 先恢复 Provider Profile（不持久化到配置文件）
        active_profile = data.get("active_profile")
        if active_profile and active_profile in getattr(self.settings, 'profiles', {}):
            self.switch_provider_profile(active_profile, persist=False)

        # 2. 恢复对话
        self.conversation.load_messages(data.get("messages", []))

        # 2. 恢复模型
        model_id = data.get("model")
        if model_id:
            model = self.settings.get_model(model_id)
            if model:
                self.current_model = model

        # 3. 恢复风格
        style_id = data.get("style_id")
        if style_id:
            self.current_style_id = style_id

        # 4. 恢复路径
        path_state = data.get("path_state", {})
        active_path = path_state.get("active_path") or data.get("active_path")
        if active_path:
            self.path_manager.set_active_path(active_path)

        # 5. 恢复计划模式
        plan_mode = data.get("plan_mode", False)
        plan_task = data.get("plan_task", "")
        self._plan_mode = plan_mode
        self._plan_task = plan_task
        self._plan_started_at = data.get("plan_started_at", "")
        self._plan_completed_at = data.get("plan_completed_at", "")
        self._plan_final_summary = data.get("plan_final_summary", "")
        self._plan_prev_statuses = data.get("plan_prev_statuses", {}) or {}
        self._update_input_state()

        # 6. 恢复工具执行历史
        tool_history = data.get("tool_history", [])
        if tool_history and hasattr(self.tool_executor, 'execution_history'):
            self.tool_executor.execution_history = tool_history

        # 7. 恢复 Todo
        todos_data = data.get("todos", [])
        if todos_data:
            from claude_code.tools.context import tool_context
            from claude_code.core.todo import TodoList, TodoItem
            todo_list = TodoList()
            for item_data in todos_data:
                item = TodoItem(
                    id=item_data.get("id", ""),
                    content=item_data.get("content", ""),
                    status=item_data.get("status", "pending"),
                    priority=item_data.get("priority", "medium"),
                    depends_on=item_data.get("depends_on", []),
                    notes=item_data.get("notes", ""),
                    evidence=item_data.get("evidence", ""),
                    files=item_data.get("files", []),
                    tests=item_data.get("tests", []),
                    error=item_data.get("error", ""),
                    started_at=item_data.get("started_at"),
                    completed_at=item_data.get("completed_at"),
                    last_failure_tool=item_data.get("last_failure_tool", ""),
                    last_error_signature=item_data.get("last_error_signature", ""),
                    retry_count=item_data.get("retry_count", 0),
                )
                todo_list.items.append(item)
            tool_context.todo_list = todo_list

        # 恢复后清除自动保存文件（避免重复恢复）
        self._autosave.clear()

        # 回放对话消息（使用与正常对话一致的渲染风格）
        messages = self.conversation.get_messages()
        self._replay_messages(messages)

        # 恢复计划模式视觉反馈
        if self._plan_mode:
            from claude_code.tools.builtins.todo import get_todo_list
            from claude_code.ui.components import show_plan_status
            todo = get_todo_list()
            show_plan_status(todo, active=True)

        console.success(f"已恢复会话（{len(data.get('messages', []))} 条消息）")

    def _on_exit(self) -> None:
        """退出时清理（幂等，可安全调用多次）"""
        if getattr(self, '_exit_done', False):
            return
        self._exit_done = True
        if not self.conversation.is_empty:
            self.stats.save_session(
                model_id=self.current_model.id if self.current_model else "",
                message_count=self.conversation.message_count,
                finalize=True,
            )
        # 正常退出时清除自动保存（避免下次启动误恢复）
        self._autosave.clear()
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
    def _build_plan_prompt(self, todo, first_injection: bool) -> str:
        """构建紧凑计划模式提示，减少重复 token。"""
        rules = f"规则:无任务先TodoCreate; pending→in_progress→completed/failed; 并行≤{PLAN.MAX_IN_PROGRESS}; 不要提前停止。"
        if first_injection:
            return f"[PLAN] {todo.progress_text}\n{todo.to_prompt_text()}\n{rules}"
        return todo.to_prompt_diff(self._plan_prev_statuses)

    def _build_plan_reminder(self, todo, action_hint: str) -> str:
        """构建紧凑计划提醒。"""
        warning = ""
        if self._plan_reminder_count >= PLAN.NO_TOOL_ROUNDS_MAX:
            warning = f"\nWARN: 连续{self._plan_reminder_count}轮无工具调用，必须调用工具推进。"
        return (
            f"[PLAN_REMINDER] {todo.progress_text} ({self._plan_reminder_count}/{PLAN.REMINDER_MAX})\n"
            f"NEXT: {action_hint}{warning}"
        )

    def _record_plan_tool_failures(self, report: Optional[ExecutionReport]) -> None:
        """记录计划模式中当前任务的工具失败信息，帮助模型换策略恢复。"""
        if not self._plan_mode or not report or report.failed_count <= 0:
            return
        try:
            from claude_code.tools.builtins.todo import get_todo_list
            todo = get_todo_list()
            if not todo.items:
                return
            failures = [
                r for r in report.results
                if not r.success and not r.skipped and not r.interrupted
            ]
            if not failures:
                return
            first = failures[0]
            tool_name = first.tool_call.name if first.tool_call else "unknown"
            error = first.error or "工具执行失败"
            signature = f"{tool_name}:{error[:80]}"
            item = todo.record_current_failure(tool_name, error, signature)
            if item:
                self._plan_prev_statuses = todo.get_status_snapshot()
        except Exception:
            pass

    def chat(self, user_input: str) -> None:
        """
        处理用户对话 (新增连续错误熔断逻辑 + 计划模式支持)
        """
        self.conversation.add_user_message(user_input)
        round_count = 0
        
        # 新一轮用户输入，重置工具显示追踪
        self.tool_executor._last_displayed_tool = None
        
        # 计划模式：注入任务规划提示（首轮注入完整规则，后续只注入增量变化）
        if self._plan_mode:
            from claude_code.tools.builtins.todo import get_todo_list
            todo = get_todo_list()
            has_rules_injected = any(
                m.role == "user" and "规则:" in (m.content or "") and "计划模式" in (m.content or "")
                for m in self.conversation._messages
            )
            if not has_rules_injected:
                # 首轮：注入完整规则 + 全量任务清单（模型需要首次了解全貌）
                plan_prompt = self._build_plan_prompt(todo, first_injection=True)
                # 初始化状态快照
                self._plan_prev_statuses = todo.get_status_snapshot()
            else:
                # 后续：只注入状态变化的增量（大幅节省 token，不丢失关键信息）
                plan_prompt = self._build_plan_prompt(todo, first_injection=False)
                # 更新快照供下一轮对比
                self._plan_prev_statuses = todo.get_status_snapshot()
            self.conversation.add_user_message(plan_prompt)
        
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

            # v2.8.37：Token 预算管理 — 注入上下文使用率，让模型自主调整输出策略
            context_usage = self._estimate_context_usage()
            if self.current_model and self.current_model.context_limit > 0 and context_usage > 0:
                usage_pct = context_usage / self.current_model.context_limit
                if usage_pct >= 0.5 and usage_pct < 0.70:
                    # 中等使用率：温和提示
                    budget_hint = (
                        f"[token预算] 上下文已用 {usage_pct:.0%}，"
                        f"剩余约 {(1 - usage_pct) * self.current_model.context_limit:.0f} token。"
                        f"正常输出即可。"
                    )
                    messages.append({"role": "user", "content": budget_hint})
                elif usage_pct >= 0.70 and usage_pct < 0.85:
                    # 较高使用率：建议精简
                    budget_hint = (
                        f"[token预算] 上下文已用 {usage_pct:.0%}，"
                        f"剩余约 {(1 - usage_pct) * self.current_model.context_limit:.0f} token。"
                        f"请适度精简回复，减少不必要的解释，优先输出关键信息。"
                    )
                    messages.append({"role": "user", "content": budget_hint})
                elif usage_pct >= 0.85:
                    # 高使用率：精简但保留关键信息
                    budget_hint = (
                        f"[token预算⚠] 上下文已用 {usage_pct:.0%}，"
                        f"仅剩约 {(1 - usage_pct) * self.current_model.context_limit:.0f} token！"
                        f"请精简输出，但必须保留关键代码和决策逻辑，省略冗余解释。"
                        f"如信息不足请 Read 确认，不要猜测。"
                        f"如无法完成，请告知用户使用 /new 开始新会话。"
                    )
                    messages.append({"role": "user", "content": budget_hint})

            # 不再估算输入 token，完全依赖 API 返回的真实 usage 累加
            response, has_tools, report = self._handle_response(messages)

            # 计划模式：工具执行后刷新 Todo 面板
            if self._plan_mode and has_tools and report:
                from claude_code.tools.builtins.todo import get_todo_list
                from claude_code.ui.components import show_todo_panel
                todo = get_todo_list()
                # 有工具执行，说明模型在推进，重置提醒计数
                self._plan_reminder_count = 0
                # 同步状态快照（工具执行后任务状态可能已变化）
                self._plan_prev_statuses = todo.get_status_snapshot()
                if todo.items:
                    # 收集刚完成的任务 ID，用于闪烁高亮
                    flash_ids = []
                    for result in report.results:
                        if result.success and result.tool_call.name == "TodoUpdate":
                            metadata = result.metadata or {}
                            # 兼容批量 flash_ids 和单任务 flash_id
                            batch_flash = metadata.get('flash_ids')
                            if batch_flash:
                                flash_ids.extend(batch_flash)
                            flash_id = metadata.get('flash_id')
                            if flash_id and flash_id not in flash_ids:
                                flash_ids.append(flash_id)
                    
                    console.print()
                    show_todo_panel(todo, flash_ids=flash_ids if flash_ids else None)
                    # 全部完成时退出计划模式
                    if todo.is_all_done:
                        from claude_code.ui.components import show_plan_complete
                        console.print()
                        show_plan_complete(todo)
                        self._plan_completed_at = datetime.now().isoformat(timespec="seconds")
                        self._plan_final_summary = f"计划完成：{todo.progress_text}，共 {todo.total_count} 个任务。"
                        self._plan_mode = False
                        self._plan_task = ""
                        self._update_input_state()
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
                            self._update_input_state()
                            break

                        # 构建具体行动指令：告诉模型该调什么工具、传什么参数
                        in_progress_items = [t for t in todo.items if t.status == "in_progress"]
                        pending_items = [t for t in todo.items if t.status == "pending"]

                        if in_progress_items:
                            task = in_progress_items[0]
                            if task.error:
                                action_hint = (
                                    f"当前任务 {task.id} 最近失败：{task.error[:120]}。"
                                    f"请不要重复同一失败操作，先换策略修复，"
                                    f"成功后调用 TodoUpdate(id=\"{task.id}\", status=\"completed\", evidence=\"完成证据\", tests=[...])，"
                                    f"无法推进则 TodoUpdate(id=\"{task.id}\", status=\"pending\", error=\"阻塞原因\") 暂停后换任务。"
                                )
                            else:
                                action_hint = (
                                    f"请调用 TodoUpdate(id=\"{task.id}\", status=\"completed\", evidence=\"完成证据\") 标记完成，"
                                    f"或 TodoUpdate(id=\"{task.id}\", status=\"pending\", error=\"阻塞原因\") 暂停后换任务。"
                                )
                        elif pending_items:
                            task = pending_items[0]
                            action_hint = (
                                f"请调用 TodoUpdate(id=\"{task.id}\", status=\"in_progress\") "
                                f"开始下一个任务，然后执行实际工作。"
                            )
                        else:
                            action_hint = "请检查任务状态并继续执行。"

                        remind = self._build_plan_reminder(todo, action_hint)
                        # 合并策略：替换上一条计划提醒（避免历史中堆积重复提醒）
                        if self.conversation._messages:
                            last_msg = self.conversation._messages[-1]
                            if last_msg.role == "user" and ("[计划提醒]" in (last_msg.content or "") or "[PLAN_REMINDER]" in (last_msg.content or "")):
                                last_msg.content = remind
                            else:
                                self.conversation.add_user_message(remind)
                        else:
                            self.conversation.add_user_message(remind)
                        console.print(f"[dim]{ICONS['info']} 计划模式：检测到模型提前停止，已注入行动提醒 ({todo.progress_text}) [{self._plan_reminder_count}/{PLAN.REMINDER_MAX}][/]")
                        continue
                break

            # 记录计划模式工具失败，供后续提醒/增量状态注入恢复使用
            self._record_plan_tool_failures(report)

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

            # 上下文窗口用量检查：基于当前对话消息的实际占用
            if self.current_model and self.current_model.context_limit > 0:
                context_usage = self._estimate_context_usage()
                usage_pct = context_usage / self.current_model.context_limit
                if usage_pct >= 0.9:
                    console.print(
                        f"\n[{COLORS['error']}]{ICONS['warning']} 上下文窗口已使用 {usage_pct:.0%}，"
                        f"剩余空间不足，建议使用 /new 开始新会话[/]\n"
                    )
                elif usage_pct >= 0.75:
                    remaining = self.current_model.context_limit - context_usage
                    if remaining >= 1_000_000:
                        remaining_str = f"{remaining / 1_000_000:.1f}M"
                    elif remaining >= 1_000:
                        remaining_str = f"{remaining / 1_000:.1f}K"
                    else:
                        remaining_str = str(remaining)
                    console.print(
                        f"[{COLORS['warning']}]{ICONS['warning']} 上下文窗口已使用 {usage_pct:.0%}，"
                        f"剩余 {remaining_str} tok[/]"
                    )

                # v2.8.36：长对话防幻觉提醒（上下文 >70% 时注入）
                if usage_pct >= 0.70:
                    # 检查本轮是否已注入过（避免重复）
                    last_msg = self.conversation._messages[-1] if self.conversation._messages else None
                    if last_msg is None or not (
                        last_msg.role == "user"
                        and "[系统提醒] 长对话记忆可能不完整" in (last_msg.content or "")
                    ):
                        self.conversation.add_user_message(
                            "[系统提醒] 长对话记忆可能不完整。涉及具体代码内容时，"
                            "请先 Read 确认当前内容，不要依赖模糊记忆。"
                            "若 Edit 匹配失败，请先重新 Read 获取最新内容。"
                        )

                # v2.8.37：对话摘要生成（计划模式更早触发，普通模式 80% 触发）
                summary_threshold = 0.60 if self._plan_mode else 0.80
                if usage_pct >= summary_threshold:
                    self._try_generate_summary()

            # 自动保存检查点（每 20 轮保存一次，崩溃恢复用）
            if round_count % 20 == 0:
                self._autosave.save(self._build_autosave_data())


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
            full_response, native_tool_calls, real_usage, duration, thinking_content = self._collect_streaming_response(
                messages, tools_definition, model_name
            )

            if not full_response.strip() and not native_tool_calls:
                return "", False, None

            # 处理响应（解析工具、渲染、保存）
            tool_calls = self._process_response(
                full_response, native_tool_calls, model_name, duration, real_usage, thinking_content
            )

            # 执行工具调用
            if tool_calls:
                report = self._execute_tools(tool_calls)

                # 缓存最后一次 Bash 输出（供 /last-output 命令查看）
                for result in report.results:
                    if result.tool_call.name == "Bash" and result.success:
                        self._last_bash_output = result.output
                        self._last_bash_command = result.tool_call.parameters.get("command", "")

                # 如果所有工具都被跳过（用户取消），停止循环
                if report.skipped_count == report.total:
                    return full_response, False, report

                # 构建工具反馈（原生 tool role 消息）
                feedback = self._build_tool_feedback(report)
                if feedback:
                    self.conversation.add_tool_messages(feedback)

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
        thinking_content = ""  # 思考链内容累积
        thinking_tokens = 0    # 思考链 token 计数

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
                    # 区分思考阶段和生成阶段
                    if streaming_tokens > 0:
                        # 生成阶段：显示生成状态
                        tok_display = f" {streaming_tokens} tok"
                        new_desc = f"[{COLORS['success']}]generating...[/] [dim]{elapsed:.1f}s[/] [cyan]{tok_display}[/]"
                    elif thinking_tokens > 0:
                        # 思考阶段：显示思考 token 计数
                        think_display = f" {thinking_tokens} tok"
                        new_desc = f"[{COLORS['warning']}]thinking...[/] [dim]{elapsed:.1f}s[/] [cyan]{think_display}[/]"
                    else:
                        # 等待阶段
                        new_desc = f"[{COLORS['primary']}]thinking...[/] [dim]{elapsed:.1f}s[/]"
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
                    model_config=self.current_model,
                    provider_config=self.settings.get_provider(self.current_model),
                ):
                    # 检查是否被中断（CTRL+C）
                    if self._is_interrupted():
                        break

                    # None 是心跳，跳过处理
                    if chunk is None:
                        continue

                    # 提取思考链内容（extended thinking）
                    thinking_chunk = self.client.extract_thinking(chunk)
                    if thinking_chunk:
                        thinking_content += thinking_chunk
                        thinking_tokens += 1

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

        # 思考链摘要已关闭（用户不需要看到）
        # if thinking_content.strip():
        #     self._show_thinking_summary(thinking_content, thinking_tokens)

        duration = time.time() - start_time
        return full_response, native_tool_calls, real_usage, duration, thinking_content

    def _show_thinking_summary(self, thinking_content: str, thinking_tokens: int) -> None:
        """
        展示思考链摘要（extended thinking 可视化）

        策略：
        - 短内容（≤200字符）：直接展示
        - 长内容：展示首尾摘要 + 省略中间
        - 使用 Panel 包裹，与 AI 响应风格一致

        Args:
            thinking_content: 思考链完整内容
            thinking_tokens: 思考链 token 计数
        """
        from rich.panel import Panel
        from claude_code.ui.theme import PANEL_STYLES
        from rich.text import Text

        MAX_DISPLAY = 300  # 摘要最大显示字符数

        content = thinking_content.strip()

        if len(content) <= MAX_DISPLAY:
            display = content
        else:
            # 保留首尾，省略中间
            head = content[:200]
            tail = content[-80:]
            omitted = len(content) - 280
            display = f"{head}\n\n... (省略 {omitted} 字符) ...\n\n{tail}"

        # Token 计数显示
        tok_str = f"{thinking_tokens} tok" if thinking_tokens < 1000 else f"{thinking_tokens / 1000:.1f}K tok"

        panel = Panel(
            Text(display, style=COLORS['text_secondary']),
            title=f"[{COLORS['warning']}]◈ 思考过程[/] [dim]{tok_str}[/]",
            title_align="left",
            border_style=COLORS['border'],
            box=PANEL_STYLES['secondary'],
            padding=(0, 2),
        )
        console.print(panel)

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

            # 确保列表足够长（必须包含 type 字段，OpenAI API 要求 tool_calls 每项有 type:"function"）
            while len(native_tool_calls) <= idx:
                native_tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})

            # 累积工具调用信息
            if tc.get("id"):
                native_tool_calls[idx]["id"] = tc["id"]
            if tc.get("type"):
                native_tool_calls[idx]["type"] = tc["type"]
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
        real_usage: dict,
        thinking_content: str = "",               # 新增参数
    ) -> list:
        """
        处理响应（解析工具调用、渲染、保存）
        """
        # 解析工具调用
        tool_calls = tool_calling_manager.parse_tool_calls(native_tool_calls)

        # 过滤掉空名工具调用（流式累积不完整时可能产生）
        tool_calls = [tc for tc in tool_calls if tc.name.strip()]

        # 渲染响应（完成后一次性渲染）
        if full_response.strip():
            render_response(full_response, model_name, duration, real_usage, has_tools=bool(tool_calls))
            # AI Panel 打印后重置工具追踪，确保下一个工具摘要前有间距
            self.tool_executor._last_displayed_tool = None

        # 保存 AI 响应：优先使用真实 token，否则回退到估算
        if real_usage["input"] > 0:
            # 使用真实 token 计算费用（set_real_usage 返回传入的绝对值）
            input_tokens, output_tokens = self.stats.set_real_usage(
                real_usage["input"], real_usage["output"]
            )
            cost = self._calculate_cost(input_tokens, output_tokens)
            self.stats.add_cost(cost)
        else:
            # API 未返回 usage 时，估算 input 和 output
            self.stats.update_input(self.conversation.get_messages())
            self.stats.update_output(full_response)

        # 保存助手消息，带上 reasoning_content 和历史渲染元数据
        assistant_metadata = {
            "model_id": self.current_model.id if self.current_model else "",
            "model_name": model_name,
            "active_profile": getattr(self.settings, 'active_profile', ""),
            "duration": duration,
            "tokens": real_usage if real_usage else None,
            "usage": real_usage if real_usage else None,
            "has_tools": bool(tool_calls),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.conversation.add_assistant_message(
            full_response,
            tool_calls=native_tool_calls if tool_calls else None,
            reasoning_content=thinking_content if thinking_content else None,  # 新增
            metadata=assistant_metadata,
        )

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

    def _build_tool_feedback(self, report: ExecutionReport):
        """构建工具执行反馈消息（委托给 tool_feedback 模块，返回原生 tool role 消息列表）"""
        return build_tool_feedback(report)

    def _compress_tool_output(
        self,
        output: str,
        tool_name: str,
        parameters: dict
    ) -> str:
        """压缩工具输出（委托给 tool_feedback 模块）"""
        return compress_tool_output(output, tool_name, parameters)

    def _generate_plan_summary_messages(self) -> list:
        """生成计划模式专用摘要请求，保留任务、证据、失败和关键文件。"""
        try:
            from claude_code.tools.builtins.todo import get_todo_list
            todo = get_todo_list()
            if not todo.items:
                return self.conversation.generate_summary_messages()

            todo_lines = []
            for item in todo.items:
                parts = [f"{item.id} {item.status} {item.content}"]
                if item.evidence:
                    parts.append(f"证据:{item.evidence}")
                if item.files:
                    parts.append(f"文件:{', '.join(item.files[:5])}")
                if item.tests:
                    parts.append(f"测试:{', '.join(item.tests[:3])}")
                if item.error:
                    parts.append(f"失败:{item.error} 工具:{item.last_failure_tool} 重试:{item.retry_count}")
                todo_lines.append(" | ".join(parts))

            recent = []
            for msg in self.conversation._messages[-30:]:
                if msg.role == "system":
                    continue
                content = (msg.content or "").strip()
                if not content:
                    continue
                if msg.role == "tool":
                    content = content[:200]
                    recent.append(f"[tool] {content}")
                elif msg.role == "assistant":
                    recent.append(f"[assistant] {content[:300]}")
                elif msg.role == "user" and not content.startswith("[PLAN") and not content.startswith("[计划"):
                    recent.append(f"[user] {content[:300]}")

            prompt = (
                "请生成计划模式专用摘要，保留：目标、Todo状态、已完成证据、相关文件、测试结果、失败尝试、关键决策。"
                "压缩重复工具输出和闲聊。只输出摘要，300字以内。\n\n"
                f"目标: {self._plan_task}\n"
                f"计划状态:\n" + "\n".join(todo_lines) + "\n\n"
                f"近期上下文:\n" + "\n".join(recent)
            )
            return [{"role": "user", "content": prompt[:8000]}]
        except Exception:
            return self.conversation.generate_summary_messages()

    def _try_generate_summary(self) -> None:
        """
        尝试对中间轮次生成对话摘要（上下文 >80% 时触发）

        策略：
        1. 检查是否已存在摘要（避免重复生成）
        2. 提取中间轮次内容，构造摘要请求
        3. 调用 API 生成摘要
        4. 将摘要应用到对话历史，替换中间消息

        这是一个成本决策：多花一次 API 调用，但节省后续多轮的 token。
        """
        # 检查是否已经生成过摘要
        has_summary = any(
            m.role == "user" and "[对话摘要]" in (m.content or "")
            for m in self.conversation._messages
        )
        if has_summary:
            return  # 已有摘要，不重复生成

        # 计划模式成本对冲：仅剩≤2个未完成任务时跳过摘要生成
        # 此时对话即将结束，花一次 API 生成摘要的"先花后省"反而亏了
        if self._plan_mode:
            try:
                from claude_code.tools.builtins.todo import get_todo_list
                todo = get_todo_list()
                if todo and todo.items:
                    remaining = todo.total_count - todo.done_count
                    if remaining <= 2:
                        return  # 快结束了，跳过摘要
            except Exception:
                pass  # 获取失败时安全放行

        # 生成摘要请求消息
        summary_msgs = self._generate_plan_summary_messages() if self._plan_mode else self.conversation.generate_summary_messages()
        if not summary_msgs:
            return  # 中间轮次内容太少，不值得摘要

        try:
            console.print(f"[dim]{ICONS['info']} 上下文使用率较高，正在生成对话摘要以节省空间...[/]")

            # 调用 API 生成摘要（非流式，快速获取）
            summary_response = ""
            for chunk in self.client.send_message(
                model_id=self.current_model.id if self.current_model else "",
                messages=summary_msgs,
                tools=None,  # 不传工具，纯粹文本生成
                stream=True,
                model_config=self.current_model,
                provider_config=self.settings.get_provider(self.current_model),
            ):
                if chunk is None:
                    continue
                content = self.client.extract_content(chunk)
                if content:
                    summary_response += content

            if not summary_response.strip():
                return

            # 应用摘要到对话历史
            self.conversation.apply_summary(summary_response.strip())

            console.print(f"[dim]{ICONS['success']} 对话摘要已生成并应用，中间轮次已压缩[/]")
        except Exception:
            # 摘要生成失败不影响正常流程
            pass

    def show_tools_history(self) -> None:
        """显示工具执行历史"""
        history = self.tool_executor.get_history()

        if not history:
            console.warning("暂无工具执行历史")
            return

        from rich.panel import Panel
        from claude_code.ui.theme import PANEL_STYLES

        # 工具图标映射
        tool_icons = {
            "Read": ICONS.get('read', '◇'),
            "Write": ICONS.get('write', '▼'),
            "Edit": ICONS.get('edit', '✎'),
            "Bash": ICONS.get('bash', '▶'),
            "Grep": ICONS.get('grep', '⌕'),
            "Glob": ICONS.get('glob', '◎'),
            "AskUserQuestion": ICONS.get('ask', '◈'),
            "TodoCreate": "●",
            "TodoUpdate": "●",
            "TodoList": "●",
        }

        lines = []
        for entry in history:
            timestamp = entry.get('timestamp', '??:??:??')
            tool_name = entry.get('tool', 'unknown')
            icon = tool_icons.get(tool_name, ICONS.get('file', '○'))
            success = entry.get('success', False)
            duration_ms = entry.get('duration_ms', 0)

            # 状态图标 + 颜色
            if success:
                status_icon = ICONS['success']
                status_color = COLORS['success']
            else:
                status_icon = ICONS['error']
                status_color = COLORS['error']

            # 耗时显示
            duration_str = ""
            if duration_ms > 0:
                if duration_ms >= 1000:
                    duration_str = f" [{duration_ms / 1000:.1f}s]"
                else:
                    duration_str = f" [{duration_ms}ms]"

            lines.append(
                f"  {icon} [{COLORS['text_muted']}]{timestamp}[/] "
                f"[{status_color}]{status_icon}[/] {tool_name}{duration_str}"
            )

            if entry.get('error'):
                lines.append(f"    [{COLORS['error']}]{entry['error'][:80]}[/]")

        panel = Panel(
            "\n".join(lines),
            title=f"[bold {COLORS['primary']}]{ICONS['claude']} 工具执行历史[/]",
            title_align="left",
            border_style=COLORS['border'],
            box=PANEL_STYLES['secondary'],
            padding=(0, 2),
        )
        console.get_console().print(panel)

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

    def switch_provider_profile(self, profile_id: str, persist: bool = True) -> bool:
        """切换 Provider Profile"""
        if not self.settings.switch_profile(profile_id):
            return False

        self.client.close()
        self.client = APIClient(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key,
        )
        self.current_model = self.settings.get_model()
        self._update_input_state()
        if persist:
            self.settings.persist_active_profile()
        return True

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

    def _fallback_history_title(self, messages: list) -> str:
        """使用首条用户消息生成兼容标题。"""
        user_msgs = [m for m in messages if m.get("role") == "user"]
        title = user_msgs[0].get("content", "")[:20] if user_msgs else "未命名"
        title = title.replace('\n', ' ').strip() or "未命名"
        return self._sanitize_history_title(title)

    def _sanitize_history_title(self, title: str, max_length: int = 40) -> str:
        """清理历史标题，确保可作为文件名片段。"""
        title = re.sub(r'[\r\n]+', ' ', title or "").strip().strip('"\'“”‘’')
        for c in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
            title = title.replace(c, '_')
        title = re.sub(r'\s+', ' ', title).strip()
        return (title[:max_length].strip() or "未命名")

    def _get_history_title_model(self):
        """获取用于历史标题生成的 DeepSeek 官方 Flash 模型配置。"""
        profile = getattr(self.settings, 'profiles', {}).get("deepseek")
        if not profile:
            return None, None
        model = next((m for m in profile.models if m.id == "deepseek-v4-flash"), None)
        if not model:
            model = next((m for m in profile.models if m.id == profile.default_model), None)
        return profile, model

    def _generate_history_title(self, messages: list) -> tuple[str, dict]:
        """用 DeepSeek 官方 Flash 生成短标题，失败时回退首条用户消息。"""
        fallback = self._fallback_history_title(messages)
        meta = {
            "title_model": "",
            "title_profile": "",
            "title_generated": False,
            "title_error": "",
        }
        try:
            profile, model = self._get_history_title_model()
            provider = profile.primary_provider if profile else None
            if not profile:
                meta["title_error"] = "missing profile: deepseek"
                return fallback, meta
            if not model:
                meta["title_error"] = "missing model: deepseek-v4-flash"
                return fallback, meta
            if not provider:
                meta["title_error"] = "missing provider: deepseek"
                return fallback, meta

            prompt_messages = [
                {
                    "role": "system",
                    "content": "请为这段对话生成一个简短中文标题。只输出标题，不要解释，不要引号，最多20个字。",
                },
                {
                    "role": "user",
                    "content": "\n\n".join(
                        f"{m.get('role', '')}: {str(m.get('content', ''))[:1000]}"
                        for m in messages
                        if m.get("role") in {"user", "assistant"} and m.get("content")
                    )[:6000],
                },
            ]
            title_model = replace(
                model,
                capabilities={
                    **(model.capabilities or {}),
                    "tools": False,
                    "thinking": False,
                    "reasoning_effort": False,
                    "stream_usage": False,
                },
                thinking=None,
                reasoning_effort=None,
                max_output_tokens=64,
            )
            client = APIClient(base_url=provider.base_url, api_key=provider.api_key, max_retries=1)
            try:
                title = ""
                for chunk in client.send_message(
                    model_id=model.id,
                    messages=prompt_messages,
                    tools=None,
                    stream=True,
                    temperature=0.2,
                    max_tokens=64,
                    model_config=title_model,
                    provider_config=provider,
                ):
                    title += client.extract_content(chunk)
            finally:
                client.close()

            title = self._sanitize_history_title(title)
            if not title or title == "未命名":
                meta["title_error"] = "empty title response"
                return fallback, meta
            meta.update({
                "title_model": model.id,
                "title_profile": profile.id,
                "title_generated": True,
            })
            return title, meta
        except Exception as e:
            meta["title_error"] = f"{type(e).__name__}: {str(e)[:200]}"
            return fallback, meta

    def save_conversation(self) -> None:
        """保存会话（增强版：包含完整对话+工具执行记录+挂载文件+路径状态）"""
        if self.conversation.is_empty:
            console.warning("没有对话记录，无法保存")
            return

        messages = self.conversation.get_messages()
        title, title_meta = self._generate_history_title(messages)

        filename = f"chat_{datetime.now().strftime('%m%d_%H%M')}_{title}.json"
        filepath = os.path.join(self.history_dir, filename)

        try:
            # 收集工具执行历史
            tool_history = []
            if hasattr(self, 'tool_executor') and self.tool_executor:
                tool_history = self.tool_executor.get_history(limit=100)

            # 收集挂载文件信息
            mounted_files = []
            if hasattr(self, 'files') and self.files:
                mounted_files = self.files.list_files()

            # 收集路径管理器状态
            path_state = {}
            if hasattr(self, 'path_manager') and self.path_manager:
                path_state = {
                    "active_path": str(self.path_manager.active_path),
                    "workplace": str(self.path_manager.workplace),
                    "is_workplace_mode": self.path_manager.is_workplace_mode,
                }

            # 收集计划模式状态
            from claude_code.tools.builtins.todo import get_todo_list
            todo = get_todo_list()
            plan_state = {
                "plan_mode": self._plan_mode,
                "plan_task": self._plan_task,
                "plan_title": self._plan_task[:40] if self._plan_task else "",
                "goal": self._plan_task,
                "started_at": getattr(self, '_plan_started_at', ""),
                "completed_at": getattr(self, '_plan_completed_at', ""),
                "final_summary": getattr(self, '_plan_final_summary', ""),
                "plan_prev_statuses": getattr(self, '_plan_prev_statuses', {}),
                "todos": [item.__dict__ for item in todo.items] if todo.items else [],
            }

            data = {
                "version": VERSION,
                "title": title,
                **title_meta,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "model": self.current_model.id if self.current_model else "",
                "active_profile": getattr(self.settings, 'active_profile', ""),
                "provider_profile": (
                    self.settings.get_provider(self.current_model).profile
                    if self.current_model and self.settings.get_provider(self.current_model)
                    else ""
                ),
                "style_id": self.current_style_id if hasattr(self, 'current_style_id') else "",
                "messages": messages,
                "tool_history": tool_history,
                "mounted_files": mounted_files,
                "path_state": path_state,
                "plan_state": plan_state,
                "stats": {
                    "total_tokens": self.stats.session.total_tokens if hasattr(self, 'stats') else 0,
                    "accumulated_input": self.stats.session.accumulated_input if hasattr(self, 'stats') else 0,
                    "accumulated_output": self.stats.session.accumulated_output if hasattr(self, 'stats') else 0,
                    "cost": self.stats.session.cost if hasattr(self, 'stats') else 0.0,
                },
            }

            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            json_str = json_str.encode('utf-8', errors='replace').decode('utf-8')
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(json_str)

            console.success(f"会话已保存: {title}")
            console.print(f"[dim]路径: {filepath}[/]")
            console.print(f"[dim]包含: {len(messages)} 条消息, {len(tool_history)} 条工具记录, {len(mounted_files)} 个挂载文件[/]")

        except Exception as e:
            console.error(f"保存失败: {e}")
    def load_history(self, args: Optional[List[str]] = None) -> None:
        """加载历史"""
        replay_mode = "recent"
        if args:
            mode = args[0].lower().strip()
            if mode in {"full", "all"}:
                replay_mode = "full"
            elif mode == "recent":
                replay_mode = "recent"
            else:
                console.warning("未知 history 模式，可用: /history recent 或 /history full")
                return
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
            self._load_history_file(choice, replay_mode=replay_mode)

    def _load_history_file(self, filename: str, replay_mode: str = "recent") -> None:
        """加载历史文件（完整恢复上下文状态）"""
        try:
            filepath = os.path.join(self.history_dir, filename)

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 1. 先恢复 Provider Profile，再恢复对话消息/模型
            active_profile = data.get("active_profile")
            if active_profile and active_profile in getattr(self.settings, 'profiles', {}):
                self.switch_provider_profile(active_profile, persist=False)

            # 2. 恢复对话消息
            self.conversation.load_messages(data.get("messages", []))

            # 3. 恢复模型
            model_id = data.get("model")
            if model_id:
                model = self.settings.get_model(model_id)
                if model:
                    self.current_model = model

            # 3. 恢复风格
            style_id = data.get("style_id")
            if style_id and style_id in self.settings.style_ids:
                self.current_style_id = style_id
                self._setup_system_prompt()

            # 4. 恢复工具执行历史
            tool_history = data.get("tool_history", [])
            if tool_history and hasattr(self.tool_executor, 'execution_history'):
                self.tool_executor.execution_history = tool_history

            # 5. 恢复文件挂载（将保存的列表还原为 AttachedFile 字典）
            mounted_files = data.get("mounted_files", [])
            if mounted_files and hasattr(self.files, '_files'):
                self.files._files.clear()
                for f_info in mounted_files:
                    path = f_info.get("path", "")
                    if path and os.path.isfile(path):
                        try:
                            with open(path, 'r', encoding='utf-8') as fp:
                                content = fp.read()
                            from claude_code.core.files import AttachedFile
                            self.files._files[path] = AttachedFile(
                                path=path,
                                content=content,
                                size=f_info.get("size", len(content)),
                                tokens=f_info.get("tokens", 0),
                            )
                        except Exception:
                            continue

            # 6. 恢复路径状态
            path_state = data.get("path_state", {})
            if path_state and hasattr(self, 'path_manager'):
                active_path = path_state.get("active_path")
                workplace = path_state.get("workplace")
                if active_path and os.path.isdir(active_path):
                    self.path_manager.set_active_path(active_path)
                    self._setup_system_prompt()

            # 7. 恢复统计信息（total_tokens 是只读 property，需设置底层累加字段）
            stats_data = data.get("stats", {})
            if stats_data and hasattr(self, 'stats'):
                # 优先使用 accumulated_input/output（新版保存格式）
                acc_input = stats_data.get("accumulated_input")
                acc_output = stats_data.get("accumulated_output")
                if acc_input is not None and acc_output is not None:
                    self.stats.session.accumulated_input = acc_input
                    self.stats.session.accumulated_output = acc_output
                else:
                    # 回退：旧版只有 total_tokens，全部归入 accumulated_input
                    total = stats_data.get("total_tokens", 0)
                    self.stats.session.accumulated_input = total
                    self.stats.session.accumulated_output = 0
                self.stats.session.cost = stats_data.get("cost", 0.0)

            # 8. 恢复计划模式状态
            plan_state = data.get("plan_state", {})
            if plan_state:
                self._plan_mode = plan_state.get("plan_mode", False)
                self._plan_task = plan_state.get("plan_task", "")
                self._plan_started_at = plan_state.get("started_at", "")
                self._plan_completed_at = plan_state.get("completed_at", "")
                self._plan_final_summary = plan_state.get("final_summary", "")
                self._plan_prev_statuses = plan_state.get("plan_prev_statuses", {}) or {}
                # 恢复 Todo 列表
                todos_data = plan_state.get("todos", [])
                if todos_data:
                    from claude_code.tools.context import tool_context
                    from claude_code.core.todo import TodoList, TodoItem
                    todo_list = TodoList()
                    for item_data in todos_data:
                        item = TodoItem(
                            id=item_data.get("id", ""),
                            content=item_data.get("content", ""),
                            status=item_data.get("status", "pending"),
                            priority=item_data.get("priority", "medium"),
                            depends_on=item_data.get("depends_on", []),
                            notes=item_data.get("notes", ""),
                            evidence=item_data.get("evidence", ""),
                            files=item_data.get("files", []),
                            tests=item_data.get("tests", []),
                            error=item_data.get("error", ""),
                            started_at=item_data.get("started_at"),
                            completed_at=item_data.get("completed_at"),
                            last_failure_tool=item_data.get("last_failure_tool", ""),
                            last_error_signature=item_data.get("last_error_signature", ""),
                            retry_count=item_data.get("retry_count", 0),
                        )
                        todo_list.items.append(item)
                    tool_context.todo_list = todo_list

            # 9. 更新输入状态
            self._update_input_state()

            # 10. 显示恢复结果（不清屏，保留终端滚动历史）
            console.brand_rule()
            console.success(f"已加载: {data.get('title', '未命名')}")
            console.print(f"[dim]包含: {len(data.get('messages', []))} 条消息, {len(tool_history)} 条工具记录, {len(mounted_files)} 个挂载文件[/]")

            # 11. 回放对话内容（使用与正常对话一致的渲染风格）
            messages = self.conversation.get_messages()
            self._replay_messages(messages, replay_mode=replay_mode)

            # 12. 恢复计划模式视觉反馈
            if self._plan_mode:
                from claude_code.tools.builtins.todo import get_todo_list
                from claude_code.ui.components import show_plan_status
                todo = get_todo_list()
                show_plan_status(todo, active=True)

            # 13. 显示状态栏（用上下文实际占用，不是累计 API 消耗）
            show_status_bar(
                model_name=self.current_model.name if self.current_model else "Claude",
                total_tokens=self._estimate_context_usage(),
                file_count=self.files.count,
                price_short=self.current_model.get_price_short() if self.current_model else "",
                total_cost=self.stats.session.cost,
                context_limit=self.current_model.context_limit if self.current_model else 0,
            )

        except Exception as e:
            console.error(f"加载失败: {e}")

    @staticmethod
    def _summarize_tool_arguments(tool_call: dict) -> str:
        """提取工具调用关键参数用于历史回放。"""
        try:
            func = tool_call.get("function", {})
            args = json.loads(func.get("arguments") or "{}")
        except Exception:
            return ""
        keep = []
        for key in ("file_path", "path", "pattern", "command", "query", "id"):
            if key in args:
                value = str(args[key]).replace("\n", " ")
                if len(value) > 80:
                    value = value[:77] + "..."
                keep.append(f"{key}={value}")
        return ", ".join(keep)

    def _build_tool_replay_index(self) -> tuple[dict, list]:
        """构建工具历史索引，兼容无 tool_call_id 的旧历史。"""
        history = []
        if hasattr(self, 'tool_executor') and hasattr(self.tool_executor, 'execution_history'):
            history = self.tool_executor.execution_history or []
        by_id = {
            item.get("tool_call_id"): item
            for item in history
            if item.get("tool_call_id")
        }
        legacy = [item for item in history if not item.get("tool_call_id")]
        return by_id, legacy

    def _replay_messages(self, messages: list, replay_mode: str = "recent") -> None:
        """回放对话消息；recent 最多 50 条，full 回放全部。"""
        from claude_code.ui.renderer import render_response
        from claude_code.ui.safe_markup import escape_markup

        chat_msgs = [m for m in messages if m.get("role") != "system"]
        if not chat_msgs:
            return

        MAX_REPLAY = 50
        if replay_mode != "full" and len(chat_msgs) > MAX_REPLAY:
            omitted = len(chat_msgs) - MAX_REPLAY
            console.print(f"[dim]... (省略前 {omitted} 条消息；使用 /history full 可完整回放) ...[/]\n")
            chat_msgs = chat_msgs[-MAX_REPLAY:]

        default_model_name = self.current_model.name if self.current_model else "Claude"
        tool_by_id, legacy_tool_history = self._build_tool_replay_index()
        legacy_tool_index = 0

        for msg in chat_msgs:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                console.print(f"\n[bold {COLORS['info']}]{ICONS['user']} YOU[/]")
                if content:
                    console.print(escape_markup(content))

            elif role == "assistant":
                metadata = msg.get("metadata") or {}
                tool_calls = msg.get("tool_calls", [])
                has_tools = metadata.get("has_tools") if "has_tools" in metadata else bool(tool_calls)
                if content and content.strip():
                    render_response(
                        content,
                        metadata.get("model_name") or default_model_name,
                        duration=metadata.get("duration", 0.0) or 0.0,
                        tokens=metadata.get("tokens") or metadata.get("usage"),
                        has_tools=bool(has_tools),
                    )

                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "unknown")
                    tool_icon = ICONS.get(tool_name.lower(), ICONS.get('file', '○'))
                    args_summary = self._summarize_tool_arguments(tc)
                    suffix = f" [dim]{escape_markup(args_summary)}[/]" if args_summary else ""
                    console.print(f"  [{COLORS['primary']}]{tool_icon}[/] [dim]{tool_name}[/]{suffix}")

            elif role == "tool":
                entry = tool_by_id.get(msg.get("tool_call_id"))
                if not entry and legacy_tool_index < len(legacy_tool_history):
                    entry = legacy_tool_history[legacy_tool_index]
                    legacy_tool_index += 1

                if entry:
                    tool_name = entry.get("tool", "tool")
                    success = entry.get("success", True)
                    status_icon = ICONS['success'] if success else ICONS['error']
                    status_color = COLORS['success'] if success else COLORS['error']
                    duration_ms = entry.get("duration_ms", 0) or 0
                    duration = f" {duration_ms / 1000:.1f}s" if duration_ms >= 1000 else (f" {duration_ms}ms" if duration_ms else "")
                    params = entry.get("parameters") or {}
                    param_text = ", ".join(f"{k}={str(v)[:60]}" for k, v in params.items() if v)
                    if len(param_text) > 120:
                        param_text = param_text[:117] + "..."
                    output = entry.get("error") or entry.get("output") or content or ""
                    display = output[:500] + (f"... (省略 {len(output) - 500} 字符)" if len(output) > 500 else "")
                    param_suffix = f" [dim]{escape_markup(param_text)}[/]" if param_text else ""
                    console.print(
                        f"  [{status_color}]{status_icon}[/] [dim]{tool_name}{duration}[/]{param_suffix} "
                        f"[{COLORS['text_muted']}]{escape_markup(display)}[/]"
                    )
                else:
                    display = content[:200] + (f"... (省略 {len(content) - 200} 字符)" if len(content) > 200 else "")
                    console.print(
                        f"  [{COLORS['success']}]{ICONS['success']}[/] [dim]tool_result[/] "
                        f"[{COLORS['text_muted']}]{escape_markup(display)}[/]"
                    )


    # ============================================================
    # 主循环
    # ============================================================

    def run(self) -> None:
        """运行主循环"""
        console.clear()
        show_welcome(self.current_model.name if self.current_model else "Claude")

        # 检查是否有未恢复的自动保存
        self._check_autosave_recovery()

        try:
            while True:
                try:
                    # 在每次对话开始前，清除上一轮的中断标志
                    self._clear_interrupt()

                    # 在每次对话开始前，显示紧凑的状态头（用上下文实际占用）
                    show_status_bar(
                        model_name=self.current_model.name if self.current_model else "Claude",
                        total_tokens=self._estimate_context_usage(),
                        file_count=self.files.count,
                        price_short=self.current_model.get_price_short() if self.current_model else "",
                        total_cost=self.stats.session.cost,
                        context_limit=self.current_model.context_limit if self.current_model else 0,
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