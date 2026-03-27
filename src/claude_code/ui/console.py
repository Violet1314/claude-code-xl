"""控制台输出 - 统一的 Rich 封装"""
import sys

from rich.console import Console as RichConsole
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.padding import Padding
from rich.rule import Rule

from claude_code.ui.theme import COLORS, ICONS

# Windows 终端编码修复
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 全局 Console 实例
_console = RichConsole()

def get_console() -> RichConsole:
    """获取全局 Console 实例"""
    return _console

# ============================================================
# 状态消息
# ============================================================

def success(msg: str) -> None:
    """显示成功消息"""
    # 分开打印，避免消息内容被解析为 markup
    _console.print(f"  [{COLORS['success']}]{ICONS['success']}[/] ", end="")
    _console.print(msg, markup=False, highlight=False)

def error(msg: str) -> None:
    """显示错误消息"""
    _console.print(f"  [{COLORS['error']}]{ICONS['error']}[/] ", end="")
    _console.print(msg, markup=False, highlight=False)

def warning(msg: str) -> None:
    """显示警告消息"""
    _console.print(f"  [{COLORS['warning']}]{ICONS['warning']}[/] ", end="")
    _console.print(msg, markup=False, highlight=False)

def info(msg: str) -> None:
    """显示信息消息"""
    _console.print(f"  [{COLORS['info']}]ℹ[/] ", end="")
    _console.print(msg, markup=False, highlight=False)

def dim(msg: str) -> None:
    """显示暗色消息"""
    _console.print(f"  ", end="")
    _console.print(msg, markup=False, highlight=False, style="dim")

# ============================================================
# 内容渲染
# ============================================================

def markdown(text: str) -> None:
    """渲染 Markdown 内容"""
    if not text:
        return
    try:
        md = Markdown(text, code_theme="monokai")
        content = Padding(md, (0, 0, 0, 2))
        _console.print(content)
    except Exception:
        _console.print(text)

def code(content: str, language: str = "python") -> None:
    """渲染代码块"""
    if not content:
        return
    try:
        syntax = Syntax(
            content,
            language,
            theme="monokai",
            line_numbers=True,
            background_color="#0F0F0F",
            padding=(1, 1),
        )
        _console.print(Padding(syntax, (0, 0, 0, 2)))
    except Exception:
        _console.print(content)

# ============================================================
# 布局元素
# ============================================================

def rule(style: str = None) -> None:
    """显示分割线"""
    _console.print(Rule(style=style or COLORS['border']))

def blank(count: int = 1) -> None:
    """显示空行"""
    for _ in range(count):
        _console.print()

def clear() -> None:
    """清屏"""
    _console.clear()

# ============================================================
# 原始输出
# ============================================================

def print(msg: str = "", **kwargs) -> None:
    """原始打印（支持 Rich 标记）"""
    _console.print(msg, **kwargs)

def print_raw(msg: str) -> None:
    """原始打印（不解析标记）"""
    _console.print(msg, markup=False, highlight=False)