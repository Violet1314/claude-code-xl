"""主应用类 - 整合所有模块"""
import re
import os
import sys
import json
import time
import signal
import atexit
from typing import Optional, List
from datetime import datetime

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from claude_code.config.settings import Settings, load_settings
from claude_code.config.defaults import VERSION, APP_NAME
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
    show_files_list,
    show_history_list,
    get_input_border,
)
from claude_code.ui.input import InputHandler, interactive_menu
from claude_code.ui.renderer import render_response

# 工具系统
from claude_code.tools import (
    registry,
    register_builtin_tools,
    ToolParser,
    ToolExecutor,
    ToolCall,
    ExecutionReport,
    PermissionManager,
)


class Application:
    """Claude Code Terminal 主应用"""

    # 工具执行限制
    MAX_TOOL_ROUNDS = 5        # 最大循环轮次
    MAX_TOOLS_PER_ROUND = 10   # 每轮最大工具数

    def __init__(self, config_dir: str = "data/config"):
        """
        初始化应用

        Args:
            config_dir: 配置目录路径
        """
        # 加载配置
        self.settings: Settings = load_settings(config_dir)

        # 初始化核心组件
        self.client: APIClient = APIClient(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key,
        )
        self.conversation: Conversation = Conversation()
        self.files: FileManager = FileManager()
        self.stats: StatsManager = StatsManager()

        # 当前状态
        self.current_model = self.settings.get_model()
        self.current_style_id = self.settings.style_ids[0] if self.settings.style_ids else "expert"

        # 初始化工具系统
        register_builtin_tools()  # 注册内置工具
        self.permission_manager = PermissionManager()
        self.tool_executor = ToolExecutor(registry, self.permission_manager)

        # 设置系统提示词（包含工具说明）
        self._setup_system_prompt()

        # 命令系统
        self.commands = CommandRegistry()
        for cmd_class in BUILTIN_COMMANDS:
            self.commands.register(cmd_class, app=self)

        # 输入处理
        self.input_handler = InputHandler(
            commands=self.commands.list_commands()
        )
        self._update_input_state()

        # 历史目录
        self.history_dir = "data/history"
        os.makedirs(self.history_dir, exist_ok=True)

        # 代码导出目录
        self.copy_code_dir = "data/copy_code"
        os.makedirs(self.copy_code_dir, exist_ok=True)

        # 注册退出处理
        atexit.register(self._on_exit)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _setup_system_prompt(self) -> None:
        """设置系统提示词（包含工具说明）"""
        base_prompt = self.settings.get_prompt(self.current_style_id)

        # 获取工具使用说明
        tools_prompt = registry.get_tools_prompt()

        # 组合提示词
        full_prompt = f"{base_prompt}\n\n{tools_prompt}"

        self.conversation.set_system_prompt(full_prompt)

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
        """信号处理"""
        self._on_exit()
        console.print(f"\n[{COLORS['primary']}]{ICONS['claude']} 再见！[/]\n")
        sys.exit(0)

    # ============================================================
    # 对话功能
    # ============================================================

    def chat(self, user_input: str) -> None:
        """
        处理用户对话

        Args:
            user_input: 用户输入
        """
        # 添加用户消息
        self.conversation.add_user_message(user_input)

        # 多轮对话循环
        round_count = 0

        while round_count < self.MAX_TOOL_ROUNDS:
            round_count += 1

            # 获取优化后的消息
            context_limit = self.current_model.context_limit if self.current_model else 100000
            messages = self.conversation.get_optimized_messages(max_tokens=context_limit)

            # 注入文件上下文
            file_context = self.files.build_context()
            if file_context:
                insert_idx = 1 if messages and messages[0].get("role") == "system" else 0
                messages.insert(insert_idx, {"role": "user", "content": file_context})

            # 更新统计
            self.stats.update_input(messages)

            # 发送请求并处理响应
            response, has_tools = self._handle_response(messages)

            if not has_tools:
                # 没有工具调用，结束循环
                break

            # 有工具调用，继续下一轮
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
        full_response = ""
        model_name = self.current_model.name if self.current_model else "AI"
        start_time = time.time()

        try:
            with Progress(
                SpinnerColumn(spinner_name="dots", style=COLORS['primary']),
                TextColumn(f"[bold {COLORS['primary']}]{model_name}[/] [dim]正在思考...[/]"),
                BarColumn(bar_width=20, pulse_style=COLORS['primary']),
                TextColumn("[cyan]已生成 {task.completed:,} 字符[/]"),
                console=console.get_console(),
                transient=True,
            ) as progress:
                task = progress.add_task("", total=None, completed=0)

                for chunk in self.client.send_message(
                    model_id=self.current_model.id if self.current_model else "",
                    messages=messages,
                    stream=True,
                ):
                    content = self.client.extract_content(chunk)
                    if content:
                        full_response += content
                        progress.update(task, completed=len(full_response))

            duration = time.time() - start_time

            if not full_response.strip():
                return "", False

            # 解析工具调用
            tool_calls = ToolParser.parse(full_response)

            # 移除工具代码块，只显示文本内容
            clean_response = ToolParser.remove_tool_blocks(full_response)

            # 渲染清理后的响应
            if clean_response.strip():
                render_response(clean_response, model_name, duration)

            # 保存 AI 响应
            self.stats.update_output(full_response)
            self.conversation.add_assistant_message(full_response)

            # 执行工具调用
            if tool_calls:
                console.print()  # 空行
                report = self._execute_tools(tool_calls)

                # 构建反馈消息
                feedback = self._build_tool_feedback(report)
                if feedback:
                    self.conversation.add_user_message(feedback)

                return full_response, True

            return full_response, False

        except Exception as e:
            console.error(f"生成失败: {e}")
            return "", False

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

        # 执行工具
        report = self.tool_executor.execute_batch(tool_calls)

        # 显示执行摘要
        console.print(report.get_summary())

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

        for result in report.results:
            if result.skipped:
                lines.append(f"<result tool=\"{result.tool_call.name}\" status=\"skipped\">")
                lines.append("用户取消或拒绝执行")
            elif result.success:
                lines.append(f"<result tool=\"{result.tool_call.name}\" status=\"success\">")
                # 限制输出长度
                output = result.output
                if len(output) > 5000:
                    output = output[:5000] + "\n... (输出过长，已截断)"
                lines.append(output)
            else:
                lines.append(f"<result tool=\"{result.tool_call.name}\" status=\"error\">")
                lines.append(result.error or "执行失败")
            lines.append("</result>")

        lines.append("</tool_results>")

        return "\n".join(lines)

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
                console.print(f"  [{COLORS['error']}]{entry['error']}[/]")

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
    # 文件管理
    # ============================================================

    def add_files(self, patterns: list) -> None:
        """添加文件"""
        added, skipped = self.files.add(patterns)

        if added:
            console.success(f"已挂载 {len(added)} 个文件")
            for p in added[:5]:
                console.dim(f"    + {os.path.basename(p)}")
            if len(added) > 5:
                console.dim(f"    ... 及其他 {len(added) - 5} 个")

        if skipped:
            console.warning(f"跳过 {len(skipped)} 个文件")
            for p, reason in skipped[:3]:
                console.dim(f"    - {os.path.basename(p)}: {reason}")

        self._update_input_state()

    def drop_files(self, patterns: list) -> None:
        """移除文件"""
        removed = self.files.drop(patterns)

        if removed:
            console.success(f"已移除 {len(removed)} 个文件")
        else:
            console.warning("未找到匹配的文件")

        self._update_input_state()

    def show_files(self) -> None:
        """显示文件列表"""
        if self.files.is_empty:
            console.warning("当前无挂载文件，使用 /add <路径> 添加")
            return

        files_data = [
            {"path": path, "tokens": f.tokens}
            for path, f in self.files.get_files().items()
        ]
        show_files_list(files_data, self.files.total_tokens)

    def refresh_files(self) -> None:
        """刷新文件"""
        if self.files.is_empty:
            console.warning("当前无挂载文件")
            return

        refreshed, removed = self.files.refresh()

        if refreshed:
            console.success(f"已刷新 {len(refreshed)} 个文件")
        if removed:
            console.warning(f"已移除 {len(removed)} 个失效文件")

        self._update_input_state()

    # ============================================================
    # 会话保存/加载
    # ============================================================

    def export_code(self) -> None:
        """导出最后回复中的代码块到文件"""
        # 获取最后一次 AI 回复
        messages = self.conversation.get_messages()
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]

        if not assistant_msgs:
            console.warning("没有可导出的内容")
            return

        last_response = assistant_msgs[-1]["content"]

        # 提取代码块：```language\ncode\n```
        pattern = r'```(\w*)\n(.*?)```'
        matches = re.findall(pattern, last_response, re.DOTALL)

        if not matches:
            console.warning("最后一次回复中没有代码块")
            return

        # 获取用户最后的请求
        user_msgs = [m for m in messages if m["role"] == "user"]
        user_request = user_msgs[-1]["content"][:200] if user_msgs else "未知请求"

        # 判断代码类型
        user_has_code = bool(re.search(r'```', user_request))
        code_type = "代码修改" if user_has_code else "完整代码"

        # 生成标题
        title = self._generate_code_title(user_request)

        # 生成目录名
        timestamp = datetime.now().strftime("%m%d_%H%M")
        dir_name = f"{timestamp}_{title}"

        # 清理非法字符
        for c in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
            dir_name = dir_name.replace(c, '_')

        dir_path = os.path.join(self.copy_code_dir, dir_name)

        # 处理目录冲突
        if os.path.exists(dir_path):
            counter = 1
            while os.path.exists(f"{dir_path}_{counter}"):
                counter += 1
            dir_path = f"{dir_path}_{counter}"

        # 创建目录
        os.makedirs(dir_path, exist_ok=True)

        # 语言到扩展名映射
        lang_ext = {
            'python': '.py', 'py': '.py',
            'javascript': '.js', 'js': '.js',
            'typescript': '.ts', 'ts': '.ts',
            'java': '.java',
            'c': '.c', 'cpp': '.cpp', 'c++': '.cpp',
            'go': '.go',
            'rust': '.rs',
            'ruby': '.rb',
            'php': '.php',
            'swift': '.swift',
            'kotlin': '.kt',
            'sql': '.sql',
            'html': '.html',
            'css': '.css',
            'json': '.json',
            'yaml': '.yaml', 'yml': '.yaml',
            'xml': '.xml',
            'shell': '.sh', 'bash': '.sh', 'sh': '.sh',
            'powershell': '.ps1', 'ps1': '.ps1',
            'text': '.txt', '': '.txt',
        }

        # 保存代码文件
        saved_files = []
        for idx, (lang, code) in enumerate(matches, 1):
            lang_lower = lang.lower() if lang else ''
            ext = lang_ext.get(lang_lower, '.txt')
            code = code.strip()

            # 代码文件名
            code_filename = f"code_{idx}{ext}"
            code_filepath = os.path.join(dir_path, code_filename)

            # 提取代码说明
            desc = self._extract_code_description(last_response, code, idx)

            # 写入代码文件（带头部注释）
            comment_char = '#' if ext in ['.py', '.rb', '.sh', '.yaml', '.yml'] else '//'
            if ext in ['.html', '.xml']:
                code_header = f"<!-- 来源: {title} | 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} -->\n\n"
            elif ext in ['.css']:
                code_header = f"/* 来源: {title} | 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} */\n\n"
            else:
                code_header = f"{comment_char} 来源: {title}\n{comment_char} 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{comment_char} 说明: {desc}\n\n"

            code_content = code_header + code + '\n'
            code_content = code_content.encode('utf-8', errors='replace').decode('utf-8')

            with open(code_filepath, 'w', encoding='utf-8') as f:
                f.write(code_content)

            saved_files.append(code_filename)

        # 输出结果
        console.success(f"已导出 {len(matches)} 个代码块")
        console.dim(f"  📁 {dir_path}/")
        for f in saved_files:
            console.dim(f"     └─ {f}")

    def _generate_code_title(self, user_request: str) -> str:
        """生成代码文件标题"""
        prefixes = ["帮我", "请", "给我", "写一个", "写个", "生成", "创建"]
        title = user_request.strip()
        for p in prefixes:
            if title.startswith(p):
                title = title[len(p):]

        title = title[:15].strip()
        title = title.replace('\n', ' ').replace('\r', '')

        if not title:
            title = "代码导出"

        return title

    def _extract_code_description(self, response: str, code: str, idx: int) -> str:
        """从 AI 回复中提取代码说明"""
        code_pos = response.find(code)
        if code_pos > 0:
            before_text = response[max(0, code_pos - 200):code_pos]

            for sep in ['：', ':', '。', '\n']:
                if sep in before_text:
                    desc = before_text.split(sep)[-1].strip()
                    if desc and len(desc) > 5:
                        desc = re.sub(r'```\w*', '', desc).strip()
                        if desc:
                            return desc[:50]

        return f"代码块 {idx}"

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

        top_border, bottom_border = get_input_border()

        try:
            while True:
                try:
                    show_status_bar(
                        model_name=self.current_model.name if self.current_model else "Claude",
                        total_tokens=self.stats.session.total_tokens,
                        file_count=self.files.count,
                        price_short=self.current_model.get_price_short() if self.current_model else "",
                    )

                    console.print(f"[{COLORS['primary']}]{top_border}[/]")
                    user_input = self.input_handler.prompt()
                    console.print(f"[{COLORS['primary']}]{bottom_border}[/]")

                    if not user_input:
                        continue

                    if user_input.startswith('/'):
                        result = self.commands.execute(user_input)
                        if result is True:
                            break
                        continue

                    self.chat(user_input)

                except KeyboardInterrupt:
                    continue
                except EOFError:
                    break

        finally:
            self._on_exit()
            console.print(f"\n[{COLORS['primary']}]{ICONS['claude']} 感谢使用 {APP_NAME}！[/]\n")