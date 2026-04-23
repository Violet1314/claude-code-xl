"""UI 组件 - Logo、状态栏、选择器 (Refactored for Elegance)"""
import os
import random
import shutil
from typing import List, Dict, Optional
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule
from rich.box import ROUNDED, SIMPLE
from claude_code.ui.theme import COLORS, ICONS, PROGRAMMING_QUOTES
from claude_code.ui import console
from claude_code.config.defaults import VERSION

# ============================================================
# Logo
# ============================================================
CLAUDE_LOGO = [
    r"                                                          ",
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
    r"                                        "
]

def show_logo() -> None:
    """显示 Claude 官方 Logo (优雅渐变效果)"""
    con = console.get_console()
    CLAUDE_COLOR = COLORS['primary']
    
    # 渲染 CLAUDE
    for line in CLAUDE_LOGO:
        con.print(f"[bold {CLAUDE_COLOR}]{line}[/]")
    
    # 渲染 CODE (稍微缩进，形成层级)
    con.print() # 增加一点垂直呼吸感
    for line in CODE_LOGO:
        con.print(f"[bold {CLAUDE_COLOR}]{line}[/]")

def show_welcome(model_name: str = "Claude") -> None:
    """显示欢迎界面 (卡片式布局)"""
    console.clear()
    show_logo()
    
    con = console.get_console()
    
    # 版本与模型信息 (紧凑行)
    header_text = Text.assemble(
        ("Claude Code Terminal ", "dim"),
        (f"v{VERSION}", "cyan bold"),
        ("  │  ", "dim"),
        (model_name, "white bold")
    )
    con.print(header_text)
    
    # 分隔线
    con.print(Rule(style=COLORS['border_subtle']))
    
    # 随机编程名言 (居中或左对齐，增加艺术感)
    quote = random.choice(PROGRAMMING_QUOTES)
    con.print(f"\n  [italic {COLORS['text_muted']}]{quote}[/]\n")
    
    # 快捷键提示 (使用 Columns 布局，更整齐)
    hints = [
        f"[{COLORS['primary']}]/help[/] [dim]帮助[/]",
        f"[{COLORS['primary']}]/model[/] [dim]切换模型[/]",
        f"[{COLORS['primary']}]/quit[/] [dim]退出[/]",
    ]
    # 简单打印，保持极简
    con.print("   " + "  ".join(hints))
    con.print()

# ============================================================
# 状态栏 (重构为紧凑信息块)
# ============================================================
def show_status_bar(
    model_name: str,
    total_tokens: int,
    file_count: int = 0,
    price_short: str = "",
    total_cost: float = 0.0,
) -> None:
    """
    显示紧凑状态信息 (使用完整 Panel 边框)
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

    # 构建状态文本
    status_parts = []

    # 1. 模型
    status_parts.append(f"[bold {COLORS['primary']}]{ICONS['claude']} {model_short}[/]")

    # 2. Token (添加含义说明)
    token_display = _format_token_count(total_tokens)
    status_parts.append(f"[dim]{ICONS['token']} {token_display} tokens[/]")

    # 3. 费用
    if total_cost > 0:
        cost_display = _format_cost(total_cost)
        status_parts.append(f"[dim]$ {cost_display}[/]")

    # 4. 文件数
    if file_count > 0:
        status_parts.append(f"[dim]{ICONS['folder']} {file_count} files[/]")

    # 输出为一行
    status_line = " │ ".join(status_parts)
    con.print(status_line)
    con.print()  # 状态栏后空行，与输入分隔

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
# 选择器 (统一表格样式)
# ============================================================
def _create_base_table() -> Table:
    """创建基础表格样式"""
    return Table(
        box=SIMPLE,  # 使用简单线条，更现代
        padding=(0, 2),
        header_style=f"bold {COLORS['primary']}",
        row_styles=[None, f"dim {COLORS['surface_1']}"],  # 斑马纹
    )

def show_model_list(models: List[Dict], current_id: str = None) -> None:
    """显示模型列表"""
    table = _create_base_table()
    table.add_column("ID", style=COLORS['primary'], justify="center", width=4)
    table.add_column("模型名称", style="bold white")
    table.add_column("Context", style="dim", justify="right")
    table.add_column(" ", style="cyan", width=8)

    for idx, model in enumerate(models, 1):
        context = f"{model.get('context_limit', 0) // 1000}K"
        status = f"[{COLORS['success']}]● 当前[/]" if model.get('id') == current_id else ""
        table.add_row(str(idx), model.get('name', ''), context, status)

    console.get_console().print(Panel(
        table,
        title="[bold white]Available Models[/]",
        border_style=COLORS['border_default'],
        expand=False,
        box=ROUNDED, # 列表容器使用圆角
    ))

def show_style_list(styles: List[Dict], current_id: str = None) -> None:
    """显示风格列表"""
    table = _create_base_table()
    table.add_column("ID", style=COLORS['primary'], justify="center", width=4)
    table.add_column("风格", style="bold white", width=12)
    table.add_column("简介", style="dim italic")
    table.add_column(" ", style="cyan", width=8)

    for idx, style in enumerate(styles, 1):
        status = f"[{COLORS['success']}]● 当前[/]" if style.get('id') == current_id else ""
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
        box=ROUNDED,
    ))

def show_history_list(history: List[Dict]) -> None:
    """显示历史会话列表"""
    table = _create_base_table()
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
        box=ROUNDED,
    ))

# ============================================================
# 输入边框 (简化)
# ============================================================
def get_input_border(width: int = None) -> tuple:
    """
    获取输入框边框 (极简直线)
    """
    if width is None:
        cols = shutil.get_terminal_size().columns
        width = min(max(cols - 2, 40), 120)

    # 使用更细的线条或仅保留心理边界
    top = '─' * width
    bottom = '─' * width

    return top, bottom

# ============================================================
# 消息框组件 (统一 Panel 风格)
# ============================================================
def show_message_box(
    title: str,
    content: str,
    level: str = "info",
    icon: str = None
) -> None:
    """显示美化的消息框 (使用 Rich Panel)"""
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
    
    # 构建标题
    title_text = f"{display_icon} {title}"
    
    # 使用 Panel 包裹内容
    panel = Panel(
        content,
        title=title_text,
        title_align="left",
        border_style=color,
        box=ROUNDED,
        padding=(1, 2),
    )
    con.print(panel)

def show_tool_result_box(
    tool_name: str,
    success: bool,
    output: str,
    duration: float = None
) -> None:
    """显示工具执行结果框 (使用 Rich Panel)"""
    color = COLORS['success'] if success else COLORS['error']
    icon = ICONS['success'] if success else ICONS['error']
    status = "完成" if success else "失败"
    
    duration_str = f" {duration:.1f}s" if duration else ""
    title = f"{icon} {tool_name} ({status}{duration_str})"

    con = console.get_console()
    
    # 截断长输出
    lines = output.split('\n')
    max_lines = 15
    if len(lines) > max_lines:
        display_lines = lines[:max_lines]
        omitted = len(lines) - max_lines
        display_output = "\n".join(display_lines) + f"\n[dim]... 省略 {omitted} 行[/]"
    else:
        display_output = output

    # 限制每行长度
    truncated_lines = []
    for line in display_output.split('\n'):
        if len(line) > 100:
            truncated_lines.append(line[:97] + "...")
        else:
            truncated_lines.append(line)
    
    final_output = "\n".join(truncated_lines)

    panel = Panel(
        final_output,
        title=title,
        title_align="left",
        border_style=color,
        box=ROUNDED,
        padding=(1, 2),
    )
    con.print(panel)


# ============================================================
# Todo 计划面板
# ============================================================

def show_todo_panel(todo_list) -> None:
    """显示 TodoList 进度面板

    Args:
        todo_list: TodoList 实例
    """
    if not todo_list.items:
        return

    con = console.get_console()

    # 全部完成时边框变绿
    border_color = COLORS['success'] if todo_list.is_all_done else COLORS['primary']
    # 进度条填充色随状态变化
    bar_color = COLORS['success'] if todo_list.is_all_done else COLORS['primary']

    # 构建面板内容
    content_lines = []
    # ID 对齐宽度：根据总任务数计算数字位数
    max_id_width = len(str(todo_list.total_count))

    for item in todo_list.items:
        # 状态标记 - Unicode 符号，与主题系统统一
        if item.status == "completed":
            status_icon = "✓"
            style = "[dim]"
            end_style = "[/]"
        elif item.status == "in_progress":
            status_icon = "●"
            style = f"[bold {COLORS['primary']}]"
            end_style = "[/]"
        elif item.status == "failed":
            status_icon = "✗"
            style = f"[{COLORS['error']}]"
            end_style = "[/]"
        else:  # pending
            status_icon = "○"
            style = ""
            end_style = ""

        # ID 数字右对齐，保持内容列整齐
        id_num = item.id.lstrip("t")
        aligned_id = id_num.rjust(max_id_width)

        content_lines.append(
            f"  {status_icon} {aligned_id}  {style}{item.content}{end_style}"
        )

    content = "\n".join(content_lines)

    # 极简进度条
    total = todo_list.total_count
    done = todo_list.done_count
    bar_width = 20
    filled = int(bar_width * done / total) if total > 0 else 0
    bar = f"[{bar_color}]{'█' * filled}[/][dim]{'░' * (bar_width - filled)}[/]"

    # 图标化统计行
    stats_line = (
        f"[dim]✓{todo_list.completed_count}  "
        f"✗{todo_list.failed_count}  "
        f"○{todo_list.pending_count}[/]"
    )

    # 标题
    title = f"执行计划 [{todo_list.progress_text}]"

    panel = Panel(
        f"{content}\n\n{bar}  {stats_line}",
        title=title,
        title_align="left",
        border_style=border_color,
        box=ROUNDED,
        padding=(0, 2),
    )
    con.print(panel)


def show_plan_complete(todo_list) -> None:
    """显示计划完成仪式

    Args:
        todo_list: TodoList 实例
    """
    con = console.get_console()

    # 分隔线
    con.print(Rule(style=COLORS['success']))

    # 完成面板
    completed = todo_list.completed_count
    failed = todo_list.failed_count
    total = todo_list.total_count

    summary_parts = [f"✓ {completed} 完成"]
    if failed > 0:
        summary_parts.append(f"✗ {failed} 失败")
    summary = "  ".join(summary_parts)

    panel = Panel(
        f"[{COLORS['success']}]{summary}[/]  [dim]{completed}/{total}[/]",
        title=f"[{COLORS['success']}]✓ 执行完成[/]",
        title_align="left",
        border_style=COLORS['success'],
        box=ROUNDED,
        padding=(0, 2),
    )
    con.print(panel)