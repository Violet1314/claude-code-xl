"""输入处理 - prompt-toolkit 交互"""
from typing import List, Optional, Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame
from prompt_toolkit.application import Application

from claude_code.ui.theme import COLORS, ICONS, PROMPT_STYLE

# ============================================================
# 命令补全器
# ============================================================

class CommandCompleter(Completer):
    """命令自动补全"""
    
    def __init__(self, commands: List[dict] = None):
        """
        初始化补全器
        
        Args:
            commands: 命令列表 [{"name": ..., "description": ...}]
        """
        self.commands = commands or []
    
    def set_commands(self, commands: List[dict]) -> None:
        """更新命令列表"""
        self.commands = commands
    
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        
        if not text.startswith('/'):
            return
        
        word = text.split()[0] if text else ''
        
        for cmd in self.commands:
            name = f"/{cmd['name']}"
            if name.startswith(word):
                yield Completion(
                    text=name,
                    start_position=-len(word),
                    display=name,
                    display_meta=cmd.get('description', ''),
                    style='class:command',
                )

# ============================================================
# 输入会话
# ============================================================

class InputHandler:
    """输入处理器"""
    
    def __init__(self, commands: List[dict] = None):
        """
        初始化输入处理器
        
        Args:
            commands: 命令列表
        """
        self.completer = CommandCompleter(commands)
        self._session: Optional[PromptSession] = None  # 延迟初始化
        # 状态
        self.model_name: str = "Claude"
        self.file_count: int = 0
    
    @property
    def session(self) -> PromptSession:
        """延迟创建 PromptSession"""
        if self._session is None:
            self._session = self._create_session()
        return self._session
    
    def _create_session(self) -> PromptSession:
        """创建 PromptSession"""
        kb = KeyBindings()
        
        @kb.add('escape', 'enter')
        def _(event):
            """Esc + Enter 发送消息"""
            event.current_buffer.validate_and_handle()
        
        @kb.add('enter')
        def _(event):
            """Enter 键处理：命令直接发送，对话换行"""
            text = event.current_buffer.text.strip()
            if text.startswith('/'):
                # 命令模式：直接发送
                event.current_buffer.validate_and_handle()
            else:
                # 对话模式：插入换行
                event.current_buffer.insert_text('\n')
        
        return PromptSession(
            multiline=True,
            prompt_continuation=self._get_continuation,
            key_bindings=kb,
            completer=self.completer,
            complete_while_typing=True,
            complete_in_thread=True,
            style=PROMPT_STYLE,
        )
    
    def _get_prompt(self):
        """获取主提示符"""
        parts = [
            ('class:input-lead', '│'),
            ('class:input-lead', f' {ICONS["user"]} '),
        ]
        
        return parts
    
    def _get_continuation(self, width, line_number, is_soft_wrap):
        """获取续行提示符"""
        return [('class:input-lead', '│   ')]

    def update_state(self, model_name: str = None, file_count: int = None) -> None:
        """
        更新状态
        
        Args:
            model_name: 模型名称
            file_count: 文件数量
        """
        if model_name is not None:
            self.model_name = model_name
        if file_count is not None:
            self.file_count = file_count
    
    def update_commands(self, commands: List[dict]) -> None:
        """更新命令列表"""
        self.completer.set_commands(commands)
    
    def prompt(self) -> str:
        """
        获取用户输入
        
        Returns:
            用户输入的文本
        """
        return self.session.prompt(self._get_prompt()).strip()

# ============================================================
# 交互式菜单
# ============================================================

def interactive_menu(
    title: str,
    options: List[dict],
) -> Optional[any]:
    """
    显示交互式选择菜单
    
    Args:
        title: 菜单标题
        options: 选项列表 [{"name": ..., "value": ..., "desc": ...}]
        
    Returns:
        选中的 value 或 None（取消）
    """
    if not options:
        return None
    
    selected_idx = 0
    kb = KeyBindings()
    
    def get_formatted_text():
        result = []
        for i, opt in enumerate(options):
            is_selected = (i == selected_idx)
            style = 'class:menu-selected' if is_selected else 'class:menu-text'
            
            # 选中指示器
            prefix = ' ❯ ' if is_selected else '   '
            result.append((style, f"{prefix}{opt['name']:<25}"))
            
            # 描述
            if opt.get('desc'):
                desc_style = style if is_selected else 'class:menu-dim'
                result.append((desc_style, f" │ {opt['desc']}"))
            
            result.append(('', '\n'))
        
        return result
    
    @kb.add('up')
    @kb.add('k')
    def _(event):
        nonlocal selected_idx
        selected_idx = (selected_idx - 1) % len(options)
    
    @kb.add('down')
    @kb.add('j')
    def _(event):
        nonlocal selected_idx
        selected_idx = (selected_idx + 1) % len(options)
    
    @kb.add('enter')
    def _(event):
        event.app.exit(result=options[selected_idx]['value'])
    
    @kb.add('escape')
    @kb.add('q')
    def _(event):
        event.app.exit(result=None)
    
    # 数字快捷键
    for i in range(min(9, len(options))):
        @kb.add(str(i + 1))
        def _(event, idx=i):
            event.app.exit(result=options[idx]['value'])
    
    window = Window(
        content=FormattedTextControl(get_formatted_text),
        height=len(options),
    )
    
    app = Application(
        layout=Layout(Frame(body=window, title=f" {title} ", style='class:menu-border')),
        key_bindings=kb,
        style=PROMPT_STYLE,
        full_screen=False,
    )
    
    return app.run()

def input_number(
    prompt: str,
    min_val: int = 1,
    max_val: int = 10,
) -> Optional[int]:
    """
    获取数字输入
    
    Args:
        prompt: 提示文本
        min_val: 最小值
        max_val: 最大值
        
    Returns:
        输入的数字或 None
    """
    from claude_code.ui import console
    
    try:
        session = PromptSession()
        result = session.prompt(f"{prompt} [{min_val}-{max_val}]: ").strip()
        
        if not result:
            return None
        
        num = int(result)
        if min_val <= num <= max_val:
            return num
        
        console.warning(f"请输入 {min_val}-{max_val} 之间的数字")
        return None
        
    except (ValueError, EOFError, KeyboardInterrupt):
        return None