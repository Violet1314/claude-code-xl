"""控制台输出 - 统一的 Rich 封装 (Refactored for Elegance)"""
import sys
from rich.console import Console as RichConsole
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.padding import Padding
from rich.rule import Rule
from rich.panel import Panel
from rich.box import ROUNDED
from claude_code.ui.theme import COLORS, ICONS, PANEL_STYLES

# ============================================================
# Windows 终端编码修复
# ============================================================
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ============================================================
# 全局 Console 实例 + Markup 安全防护
# ============================================================
_console = RichConsole()

# 保存原始 print 方法
_original_console_print = _console.print

def _safe_console_print(*args, **kwargs):
    """安全版 Console.print — Markup 解析失败时自动修复而非回退纯文本
    
    策略：
    1. 正常 Markup → 直接打印（最快路径）
    2. MarkupError → 用 safe_markup() 自动修复后重试（保留样式）
    3. 修复后仍失败 → 回退为纯文本（最后防线）
    """
    markup = kwargs.get('markup', True)
    if markup and args and isinstance(args[0], str):
        try:
            _original_console_print(*args, **kwargs)
        except Exception:
            # MarkupError → 尝试用 safe_markup 修复后重试
            try:
                from claude_code.ui.safe_markup import safe_markup
                fixed_args = (safe_markup(args[0]),) + args[1:]
                _original_console_print(*fixed_args, **kwargs)
            except Exception:
                # 修复也失败 → 纯文本回退（最后防线）
                kwargs['markup'] = False
                kwargs.setdefault('highlight', False)
                _original_console_print(*args, **kwargs)
    else:
        _original_console_print(*args, **kwargs)

# 猴子补丁：替换 _console.print 为安全版本
_console.print = _safe_console_print

def get_console() -> RichConsole:
    """获取全局 Console 实例"""
    return _console

# ============================================================
# 状态消息 (简化版 - 单行)
# ============================================================
def success(msg: str) -> None:
    """显示成功消息 (单行)"""
    _console.print(f"  [{COLORS['success']}]{ICONS['success']}[/] {msg}", markup=True)

def error(msg: str) -> None:
    """显示错误消息 (单行)"""
    _console.print(f"  [{COLORS['error']}]{ICONS['error']}[/] {msg}", markup=True)

def warning(msg: str) -> None:
    """显示警告消息 (单行)"""
    _console.print(f"  [{COLORS['warning']}]{ICONS['warning']}[/] {msg}", markup=True)

def info(msg: str) -> None:
    """显示信息消息 (单行)"""
    _console.print(f"  [{COLORS['info']}]{ICONS['info']}[/] {msg}", markup=True)

def dim(msg: str) -> None:
    """显示暗色消息"""
    _console.print(f"  [dim]{msg}[/]", markup=True)

# ============================================================
# 消息框组件 (Panel 风格 - 统一视觉)
# ============================================================
def _show_panel_box(
    title: str,
    content: str = None,
    level: str = "info",
    suggestion: str = None
) -> None:
    """
    内部辅助函数：显示统一风格的 Panel 消息框
    
    Args:
        title: 标题文本
        content: 主要内容
        level: 级别 (success/warning/error/info)
        suggestion: 建议文本 (仅 error 常用)
    """
    color_map = {
        "success": COLORS['success'],
        "warning": COLORS['warning'],
        "error": COLORS['error'],
        "info": COLORS['info'],
    }
    icon_map = {
        "success": ICONS['success'],
        "warning": ICONS['warning'],
        "error": ICONS['error'],
        "info": ICONS['info'],
    }

    color = color_map.get(level, COLORS['info'])
    icon = icon_map.get(level, ICONS['info'])
    
    # 构建标题
    panel_title = f"{icon} {title}"
    
    # 构建内容
    lines = []
    if content:
        lines.append(content)
    
    if suggestion:
        # 视觉引导：建议区块使用 info 色边框包裹，与错误内容区分
        lines.append("")
        lines.append(f"[{COLORS['info']}]━ 解决建议 ━[/]")
        lines.append(f"[{COLORS['info']}]{ICONS['info']} {suggestion}[/]")
        
    final_content = "\n".join(lines) if lines else ""

    panel = Panel(
        final_content,
        title=panel_title,
        title_align="left",
        border_style=color,
        box=PANEL_STYLES.get(level, PANEL_STYLES['primary']),
        padding=(1, 2),
    )
    
    _console.print()
    _console.print(panel)
    _console.print()

def success_box(title: str, content: str = None) -> None:
    """显示成功消息框"""
    _show_panel_box(title, content, level="success")

def error_box(title: str, content: str = None, suggestion: str = None, error_code: int = None) -> None:
    """显示错误消息框（支持错误码徽章）"""
    if error_code is not None:
        # 在标题中注入错误码徽章
        title = f"{title}  ┌─{error_code}─┐"
    _show_panel_box(title, content, level="error", suggestion=suggestion)

def warning_box(title: str, content: str = None) -> None:
    """显示警告消息框"""
    _show_panel_box(title, content, level="warning")

def info_box(title: str, content: str = None) -> None:
    """显示信息消息框"""
    _show_panel_box(title, content, level="info")

# ============================================================
# 内容渲染
# ============================================================
def markdown(text: str) -> None:
    """渲染 Markdown 内容 (增加左侧缩进以创造层级感)"""
    if not text:
        return
    try:
        md = Markdown(text, code_theme="github-dark")
        # 左侧缩进 2 个字符，避免贴边
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
            theme="github-dark",
            line_numbers=True,
            background_color="#0F0F0F",
            padding=(1, 1),
        )
        # 左侧缩进 2 个字符
        _console.print(Padding(syntax, (0, 0, 0, 2)))
    except Exception:
        _console.print(content)

# ============================================================
# 布局元素
# ============================================================
def rule(style: str = None) -> None:
    """显示分割线"""
    _console.print(Rule(style=style or COLORS['border']))

def brand_rule() -> None:
    """显示品牌分隔线（纯线条）"""
    _console.print(Rule(style=COLORS['border']))

def blank(count: int = 1) -> None:
    """显示空行"""
    for _ in range(count):
        _console.print()

def clear() -> None:
    """清屏"""
    _console.clear()

# ============================================================
# 原始输出 (兼容旧代码 + Markup 安全防护)
# ============================================================
def print(msg: str = "", **kwargs) -> None:
    """安全打印 — Markup 解析失败时自动修复而非回退纯文本
    
    策略同猴子补丁：正常 → 修复 → 纯文本回退
    """
    markup = kwargs.pop('markup', True)
    kwargs['markup'] = markup
    _console.print(msg, **kwargs)

def print_raw(msg: str) -> None:
    """原始打印 (不解析标记，用于文件内容等)"""
    _console.print(msg, markup=False, highlight=False)