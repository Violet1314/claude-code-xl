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
# 工具函数：中文宽度处理
# ============================================================
def display_width(s: str) -> int:
    """计算字符串的终端显示宽度（中文=2，英文=1）"""
    width = 0
    for ch in s:
        # CJK 字符范围：U+4E00-U+9FFF（常用汉字）
        if '\u4e00' <= ch <= '\u9fff':
            width += 2
        else:
            width += 1
    return width

def pad_to_width(s: str, width: int) -> str:
    """将字符串 pad 到指定显示宽度"""
    current = display_width(s)
    if current >= width:
        return s
    return s + ' ' * (width - current)

# ============================================================
# 命令补全器
# ============================================================
class CommandCompleter(Completer):
    """命令自动补全"""
    def __init__(self, commands: List[dict] = None):
        self.commands = commands or []

    def set_commands(self, commands: List[dict]) -> None:
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        
        if not text.startswith('/'):
            return
        
        # 只在输入命令名阶段补全（没有空格或换行时）
        # 一旦输入了空格/换行，说明命令名已完成，不再补全
        if ' ' in text or '\n' in text:
            return
        
        word = text
        
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
        self.completer = CommandCompleter(commands)
        self._session: Optional[PromptSession] = None
        # 状态
        self.model_name: str = "Claude"
        self.file_count: int = 0

    @property
    def session(self) -> PromptSession:
        if self._session is None:
            self._session = self._create_session()
        return self._session

    def _create_session(self) -> PromptSession:
        kb = KeyBindings()
        
        @kb.add('escape', 'enter')
        def _(event):
            """Esc + Enter 发送消息"""
            event.current_buffer.validate_and_handle()
        
        @kb.add('enter')
        def _(event):
            """Enter 键处理：多行命令换行，单行命令直接发送，对话换行"""
            text = event.current_buffer.text.strip()
            if text.startswith('/'):
                # 提取命令名（取第一个词）
                cmd_name = text.split()[0] if text else ''
                # 需要多行输入的命令：Enter 换行（和对话模式一致）
                multiline_commands = {'/plan', '/p'}
                if cmd_name in multiline_commands:
                    event.current_buffer.insert_text('\n')
                else:
                    # 单行命令：直接发送
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
            style=PROMPT_STYLE,  # 确保样式被应用
        )

    def _get_prompt(self):
        """获取主提示符"""
        # 统一格式：固定3位宽度右对齐，无前缀
        return [
            ('class:input-lead', '  1> '),
        ]

    def _get_continuation(self, width, line_number, is_soft_wrap):
        """获取续行提示符 - 显示行号（固定3位宽度右对齐）"""
        # line_number 从 1 开始，+1 得到实际行号
        line_num = line_number + 1
        # 固定宽度：1-9 加两空格，10-99 加一空格，100+ 不加
        if line_num < 10:
            display = f'  {line_num}> '
        elif line_num < 100:
            display = f' {line_num}> '
        else:
            display = f'{line_num}> '
        return [('class:input-lead', display)]

    def update_state(self, model_name: str = None, file_count: int = None) -> None:
        if model_name is not None:
            self.model_name = model_name
        if file_count is not None:
            self.file_count = file_count

    def update_commands(self, commands: List[dict]) -> None:
        self.completer.set_commands(commands)

    def prompt(self) -> str:
        return self.session.prompt(self._get_prompt()).strip()

# ============================================================
# 交互式菜单
# ============================================================
def interactive_menu(
    title: str,
    options: List[dict],
) -> Optional[any]:
    if not options:
        return None

    selected_idx = 0
    kb = KeyBindings()

    # 计算名称最大显示宽度（考虑中文字符）
    name_width = max(display_width(opt['name']) for opt in options)

    def get_formatted_text():
        result = []
        for i, opt in enumerate(options):
            is_selected = (i == selected_idx)
            style = 'class:menu-selected' if is_selected else 'class:menu-text'

            # 选中指示器 + 名称（动态宽度左对齐）
            prefix = ' ❯ ' if is_selected else '   '
            result.append((style, prefix + pad_to_width(opt['name'], name_width)))

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