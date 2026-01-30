"""主应用类 - 整合所有模块"""
import os
import sys
import json
import time
import signal
import atexit
from typing import Optional
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

class Application:
    """Claude Code Terminal 主应用"""
    
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
        
        # 设置系统提示词
        self.conversation.set_system_prompt(
            self.settings.get_prompt(self.current_style_id)
        )
        
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
        
        # 注册退出处理
        atexit.register(self._on_exit)
        signal.signal(signal.SIGINT, self._signal_handler)
    
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
        self._handle_response(messages)
        
        # 保存统计
        self.stats.save_session(
            model_id=self.current_model.id if self.current_model else "",
            message_count=self.conversation.message_count,
        )
    
    def _handle_response(self, messages: list) -> None:
        """处理 AI 响应"""
        full_response = ""
        model_name = self.current_model.name if self.current_model else "AI"
        start_time = time.time()
        
        try:
            with Progress(
                SpinnerColumn(style=COLORS['primary']),
                TextColumn(f"[{COLORS['primary']}]{model_name} 正在思考..."),
                BarColumn(bar_width=40, pulse_style=COLORS['primary']),
                console=console.get_console(),
                transient=True,
            ) as progress:
                task = progress.add_task("", total=100)
                
                for chunk in self.client.send_message(
                    model_id=self.current_model.id if self.current_model else "",
                    messages=messages,
                    stream=True,
                ):
                    content = self.client.extract_content(chunk)
                    if content:
                        full_response += content
                        progress.update(task, completed=min(99, len(full_response) / 20))
            
            duration = time.time() - start_time
            
            if full_response.strip():
                render_response(full_response, model_name, duration)
                self.stats.update_output(full_response)
                self.conversation.add_assistant_message(full_response)
                
        except Exception as e:
            console.error(f"生成失败: {e}")
    
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
            self.conversation.set_system_prompt(
                self.settings.get_prompt(choice)
            )
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
    
    def save_conversation(self) -> None:
        """保存会话"""
        if self.conversation.is_empty:
            console.warning("没有对话记录，无法保存")
            return
        
        # 生成标题
        messages = self.conversation.get_messages()
        user_msgs = [m for m in messages if m["role"] == "user"]
        title = user_msgs[0]["content"][:20] if user_msgs else "未命名"
        title = title.replace('\n', ' ').strip()
        
        # 清理文件名
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
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
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
        
        # 构建选项
        options = []
        for f in files[:10]:  # 最多显示 10 条
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
            
            # 恢复模型
            model_id = data.get("model")
            if model_id:
                model = self.settings.get_model(model_id)
                if model:
                    self.current_model = model
            
            self._update_input_state()
            console.clear()
            console.success(f"已加载: {data.get('title', '未命名')}")
            
            # 显示历史消息
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
                    # 显示状态栏
                    show_status_bar(
                        model_name=self.current_model.name if self.current_model else "Claude",
                        total_tokens=self.stats.session.total_tokens,
                        file_count=self.files.count,
                        price_short=self.current_model.get_price_short() if self.current_model else "",  # 新增
                    )

                    # 显示输入框
                    console.print(f"[{COLORS['primary']}]{top_border}[/]")
                    user_input = self.input_handler.prompt()
                    console.print(f"[{COLORS['primary']}]{bottom_border}[/]")
                    
                    if not user_input:
                        continue
                    
                    # 处理命令
                    if user_input.startswith('/'):
                        result = self.commands.execute(user_input)
                        if result is True:  # 退出命令
                            break
                        continue
                    
                    # 处理对话
                    self.chat(user_input)
                    
                except KeyboardInterrupt:
                    continue
                except EOFError:
                    break
                    
        finally:
            self._on_exit()
            console.print(f"\n[{COLORS['primary']}]{ICONS['claude']} 感谢使用 {APP_NAME}！[/]\n")
