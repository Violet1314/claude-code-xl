"""UI 组件 - Logo、状态栏、选择器"""
import os
import shutil
from typing import List, Dict, Optional

from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule

from claude_code.ui.theme import COLORS, ICONS, LOGO_GRADIENT
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

# def show_logo() -> None:
#     """显示渐变色 Logo"""
#     con = console.get_console() 
#     # 渲染 CLAUDE
#     for i, line in enumerate(CLAUDE_LOGO):
#         color = LOGO_GRADIENT[i % len(LOGO_GRADIENT)]
#         con.print(f"[bold {color}]{line}[/]")
#     # 渲染 CODE
#     for i, line in enumerate(CODE_LOGO):
#         color = LOGO_GRADIENT[i % len(LOGO_GRADIENT)]
#         con.print(f"[bold {color}]{line}[/]")

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
    con.print(f"\n  [dim]Claude Code Terminal[/] [cyan]v{VERSION}[/] [dim]│[/] [bold white]{model_name}[/]")
    con.print(Rule(style=COLORS['border']))
    con.print(f"  {ICONS['success']} [italic {COLORS['system']}]System ready. Type /help for commands.[/]\n")

# ============================================================
# 状态栏
# ============================================================
def show_status_bar(
    model_name: str,
    total_tokens: int,
    file_count: int = 0,
    price_short: str = "",
) -> None:
    """
    显示 Powerline 风格状态栏
    
    Args:
        model_name: 模型名称
        total_tokens: 总 token 数
        file_count: 挂载文件数
        price_short: 价格简写 (如 "5/25")
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
    
    # Powerline 分隔符
    sep = ""
    
    # 构建 Powerline 段
    segments = []
    
    # 段1: 模型名称 (橙色背景)
    segments.append(f"[bold #000000 on {COLORS['primary']}] {ICONS['claude']} {model_short} [/]")
    segments.append(f"[{COLORS['primary']}]{sep}[/]")
    
    # 段2: 价格 (如果有)
    if price_short:
        segments.append(f"[grey30] [dim]💰[/] [grey30]{price_short}[/] [grey30]$/M[/] [/]")
        segments.append(f"[grey30]{sep}[/]")
    
    # 段3: 文件数 (如果有)
    if file_count > 0:
        segments.append(f"[on dodger_blue3] [dim]{ICONS['file']}[/] [black]{file_count}[/] [/]")
        segments.append(f"[dodger_blue3]{sep}[/]")
    
    # 段4: Token 统计
    segments.append(f"[on grey23] [dim]Σ[/] [black]{total_tokens:,}[/] [/]")
    segments.append(f"[grey23]{sep}[/]")
    
    # 输出
    console.blank()
    con.print("".join(segments))
    console.blank()

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
        border_style=COLORS['border'],
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
        border_style=COLORS['border'],
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
        border_style=COLORS['border'],
        expand=False,
    ))

def show_files_list(files: List[Dict], total_tokens: int = 0) -> None:
    """
    显示挂载文件列表
    
    Args:
        files: 文件列表 [{"path": ..., "tokens": ...}]
        total_tokens: 总 token 数
    """
    table = Table(box=None, padding=(0, 2))
    table.add_column("#", style=COLORS['primary'], width=3)
    table.add_column("路径", style=COLORS['info'])
    table.add_column("Tokens", style="dim", justify="right", width=10)
    
    for idx, file in enumerate(files, 1):
        table.add_row(
            str(idx),
            file.get('path', ''),
            f"{file.get('tokens', 0):,}",
        )
    
    console.get_console().print(Panel(
        table,
        title=f"[bold white]Attached Files ({len(files)})[/]",
        border_style=COLORS['border'],
        expand=False,
    ))
    
    console.dim(f"  Total Tokens: {total_tokens:,}")
    console.blank()

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