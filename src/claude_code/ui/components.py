"""UI 组件 - Logo、状态栏、选择器"""
import os
import random
import shutil
from typing import List, Dict, Optional

from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule

from claude_code.ui.theme import COLORS, ICONS, POWERLINE, LOGO_GRADIENT, PROGRAMMING_QUOTES
from claude_code.ui import console
from claude_code.config.defaults import VERSION

# ============================================================
# Logo
# ============================================================

CLAUDE_LOGO = [
    r"     ██████╗ ██╗       █████╗  ██╗   ██╗ ██████╗  ███████╗",
    r"    ██╔════╝ ██║      ██╔══██╗ ██║   ██║ ██╔══██╗ ██╔════╝",
    r"    ██║      ██║      ███████║ ██║   ██║ ██║  ██║ █████╗  ",
    r"    ██║      ██║      ██╔══██║ ██║   ██║ ██║  ██║ ██╔══╝  ",
    r"    ╚██████╗ ███████╗ ██║  ██║ ╚██████╔╝ ██████╔╝ ███████╗",
    r"     ╚═════╝ ╚══════╝ ╚═╝  ╚═╝  ╚═════╝  ╚═════╝  ╚══════╝",
]

CODE_LOGO = [
    r"     ██████╗  ██████╗  ██████╗  ███████╗",
    r"    ██╔════╝ ██╔═══██╗ ██╔══██╗ ██╔════╝",
    r"    ██║      ██║   ██║ ██║  ██║ █████╗  ",
    r"    ██║      ██║   ██║ ██║  ██║ ██╔══╝  ",
    r"    ╚██████╗ ╚██████╔╝ ██████╔╝ ███████╗",
    r"     ╚═════╝  ╚═════╝  ╚═════╝  ╚══════╝",
]


def show_logo() -> None:
    """显示 Claude 官方土橙色 Logo"""
    con = console.get_console()
    # Claude 官方标志性的土橙色 (Terracotta/Earthy Orange)
    CLAUDE_COLOR = "#D97757"
    # 渲染 CLAUDE
    for line in CLAUDE_LOGO:
        con.print(f"[bold {CLAUDE_COLOR}]{line}[/]")
    # 渲染 CODE
    for line in CODE_LOGO:
        con.print(f"[bold {CLAUDE_COLOR}]{line}[/]")


def show_welcome(model_name: str = "Claude") -> None:
    """
    显示欢迎界面

    Args:
        model_name: 当前模型名称
    """
    console.clear()
    show_logo()

    con = console.get_console()

    # 版本信息行
    con.print(f"\n  [dim]Claude Code Terminal[/] [cyan]v{VERSION}[/] [dim]│[/] [bold white]{model_name}[/]")

    # 分隔线
    con.print(Rule(style=COLORS['border_default']))

    # 随机编程名言
    quote = random.choice(PROGRAMMING_QUOTES)
    con.print(f"  [italic {COLORS['text_muted']}]{quote}[/]")

    # 快捷键提示
    con.print()
    hints = [
        f"[{COLORS['primary']}]/help[/] [dim]查看命令[/]",
        f"[dim]│[/]",
        f"[{COLORS['primary']}]Tab[/] [dim]自动补全[/]",
        f"[dim]│[/]",
        f"[{COLORS['primary']}]Esc+Enter[/] [dim]发送[/]",
    ]
    con.print("  " + "  ".join(hints))
    con.print()


# ============================================================
# 状态栏 (简化 Powerline 风格)
# ============================================================

def show_status_bar(
    model_name: str,
    total_tokens: int,
    file_count: int = 0,
    price_short: str = "",
    total_cost: float = 0.0,
) -> None:
    """
    显示状态栏

    Args:
        model_name: 模型名称
        total_tokens: 总 token 数
        file_count: 挂载文件数
        price_short: 价格简写 (如 "5/25")
        total_cost: 累计费用（美元）
    """
    con = console.get_console()

    # 模型名称处理
    if len(model_name) <= 20:
        model_short = model_name.upper()
    elif '-' in model_name:
        model_short = model_name.split('-')[-1].upper()
    else:
        parts = model_name.split()
        model_short = ' '.join(parts[:2]).upper() if len(parts) > 1 else model_name[:15].upper()

    # 分隔符
    sep = POWERLINE.get('separator', '│')

    # 构建状态栏（使用简单的背景色块）
    segments = []

    # 段1: 模型名称 (橙色背景，黑色文字)
    segments.append(f"[bold #000000 on {COLORS['primary']}] {ICONS['claude']} {model_short} [/]")

    # 段2: 价格 (如果有)
    if price_short:
        segments.append(f" [dim]{sep}[/] ")
        segments.append(f"[{COLORS['text_muted']}]${price_short} $/M[/]")

    # 段3: 文件数 (如果有)
    if file_count > 0:
        segments.append(f" [dim]{sep}[/] ")
        segments.append(f"[{COLORS['text_muted']}]{ICONS.get('folder', '📁')} {file_count}[/]")

    # 段4: Token 统计
    token_display = _format_token_count(total_tokens)
    segments.append(f" [dim]{sep}[/] ")
    segments.append(f"[{COLORS['text_muted']}]{ICONS.get('token', '◆')} {token_display}[/]")

    # 段5: 累计费用
    if total_cost > 0:
        cost_display = _format_cost(total_cost)
        segments.append(f" [dim]{sep}[/] ")
        segments.append(f"[{COLORS['text_muted']}]≈${cost_display}[/]")

    # 输出
    console.blank()
    con.print("".join(segments))
    console.blank()


def _format_token_count(count: int) -> str:
    """格式化 token 数量显示"""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    else:
        return str(count)


def _format_cost(cost: float) -> str:
    """格式化费用显示"""
    if cost >= 1.0:
        return f"{cost:.2f}"
    elif cost >= 0.01:
        return f"{cost:.3f}"
    else:
        return f"{cost:.4f}"


# ============================================================
# 选择器
# ============================================================

def show_model_list(models: List[Dict], current_id: str = None) -> None:
    """
    显示模型列表

    Args:
        models: 模型列表 [{"id": ..., "name": ..., "context_limit": ...}]
        current_id: 当前模型 ID
    """
    table = Table(box=None, padding=(0, 2))
    table.add_column("ID", style=COLORS['primary'], justify="center", width=4)
    table.add_column("模型名称", style="bold white")
    table.add_column("Context", style="dim", justify="right")
    table.add_column("", style="cyan", width=8)

    for idx, model in enumerate(models, 1):
        context = f"{model.get('context_limit', 0) // 1000}K"
        status = "● 当前" if model.get('id') == current_id else ""
        table.add_row(str(idx), model.get('name', ''), context, status)

    console.get_console().print(Panel(
        table,
        title="[bold white]Available Models[/]",
        border_style=COLORS['border_default'],
        expand=False,
    ))


def show_style_list(styles: List[Dict], current_id: str = None) -> None:
    """
    显示风格列表

    Args:
        styles: 风格列表 [{"id": ..., "name": ..., "desc": ...}]
        current_id: 当前风格 ID
    """
    table = Table(box=None, padding=(0, 2))
    table.add_column("ID", style=COLORS['primary'], justify="center", width=4)
    table.add_column("风格", style="bold white", width=12)
    table.add_column("简介", style="dim italic")
    table.add_column("", style="cyan", width=8)

    for idx, style in enumerate(styles, 1):
        status = "● 当前" if style.get('id') == current_id else ""
        table.add_row(
            str(idx),
            style.get('name', '').upper(),
            style.get('desc', ''),
            status,
        )

    console.get_console().print(Panel(
        table,
        title="[bold white]AI Persona[/]",
        border_style=COLORS['border_default'],
        expand=False,
    ))


def show_history_list(history: List[Dict]) -> None:
    """
    显示历史会话列表

    Args:
        history: 历史列表 [{"id": ..., "title": ..., "time": ..., "count": ...}]
    """
    table = Table(box=None, padding=(0, 2))
    table.add_column("ID", style=COLORS['primary'], justify="center", width=4)
    table.add_column("时间", style="dim", width=16)
    table.add_column("主题", style="bold white")
    table.add_column("轮数", style="dim", justify="right", width=8)

    for idx, item in enumerate(history, 1):
        table.add_row(
            str(idx),
            item.get('time', ''),
            item.get('title', '未命名')[:20],
            f"{item.get('count', 0)} 轮",
        )

    console.get_console().print(Panel(
        table,
        title="[bold white]History Sessions[/]",
        border_style=COLORS['border_default'],
        expand=False,
    ))


# ============================================================
# 输入边框
# ============================================================

def get_input_border(width: int = None) -> tuple:
    """
    获取输入框边框（上下纯直线）

    Args:
        width: 边框宽度，默认自动计算

    Returns:
        (top_border, bottom_border)
    """
    if width is None:
        cols = shutil.get_terminal_size().columns
        width = min(max(cols - 2, 40), 120)

    top = '─' * width           # ───────────
    bottom = '─' * width        # ───────────

    return top, bottom


# ============================================================
# 消息框组件
# ============================================================

def show_message_box(
    title: str,
    content: str,
    level: str = "info",
    icon: str = None
) -> None:
    """
    显示美化的消息框

    Args:
        title: 标题
        content: 内容
        level: 级别 (success/warning/error/info)
        icon: 自定义图标
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
    display_icon = icon or icon_map.get(level, ICONS['info'])

    con = console.get_console()

    # 顶部边框
    con.print(f"  [dim {COLORS['border_subtle']}]╭─[/] [{color}]{display_icon}[/] [bold {color}]{title}[/] [dim {COLORS['border_subtle']}]{'─' * 40}[/]")

    # 内容
    for line in content.split('\n'):
        con.print(f"  [dim {COLORS['border_subtle']}]│[/] {line}")

    # 底部边框
    con.print(f"  [dim {COLORS['border_subtle']}]╰{'─' * 50}[/]")


def show_tool_result_box(
    tool_name: str,
    success: bool,
    output: str,
    duration: float = None
) -> None:
    """
    显示工具执行结果框

    Args:
        tool_name: 工具名称
        success: 是否成功
        output: 输出内容
        duration: 耗时（秒）
    """
    color = COLORS['success'] if success else COLORS['error']
    icon = ICONS['success'] if success else ICONS['error']
    status = "完成" if success else "失败"

    con = console.get_console()

    # 标题行
    duration_str = f" {duration:.1f}s" if duration else ""
    con.print(f"  [dim {COLORS['border_subtle']}]╭─[/] [{color}]{icon}[/] [bold]{tool_name}[/] [dim]{status}{duration_str}[/]")

    # 输出内容（截断处理）
    lines = output.split('\n')
    max_lines = 15
    if len(lines) > max_lines:
        display_lines = lines[:max_lines]
        omitted = len(lines) - max_lines
        truncated = True
    else:
        display_lines = lines
        truncated = False

    for line in display_lines:
        # 截断长行
        if len(line) > 80:
            line = line[:77] + "..."
        con.print(f"  [dim {COLORS['border_subtle']}]│[/] {line}")

    if truncated:
        con.print(f"  [dim {COLORS['border_subtle']}]│[/] [dim]... 省略 {omitted} 行[/]")

    # 底部边框
    con.print(f"  [dim {COLORS['border_subtle']}]╰{'─' * 50}[/]")