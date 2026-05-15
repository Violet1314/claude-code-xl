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
from rich.box import ROUNDED, SIMPLE, HORIZONTALS
from claude_code.ui.theme import COLORS, ICONS, PROGRAMMING_QUOTES, PANEL_STYLES
from claude_code.ui import console
from claude_code.config.defaults import VERSION

# ============================================================
# 响应式布局工具
# ============================================================
def _terminal_width() -> int:
    """获取当前终端宽度"""
    return shutil.get_terminal_size().columns

def _responsive_panel_width(min_w: int = 60, max_w: int = 120) -> int:
    """根据终端宽度计算 Panel 最佳宽度"""
    tw = _terminal_width()
    # 终端宽度的 90%，限制在 min_w ~ max_w 之间
    return max(min_w, min(int(tw * 0.9), max_w))

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
    """显示 Claude 官方 Logo (优雅渐变效果 + 终端自适应)"""
    con = console.get_console()
    width = shutil.get_terminal_size().columns
    CLAUDE_COLOR = COLORS['primary']
    
    # 窄终端（<80列）使用紧凑 Logo
    if width < 80:
        con.print(f"[bold {CLAUDE_COLOR}]  {ICONS['claude']} Claude Code[/]")
        con.print(f"[dim {CLAUDE_COLOR}]  Terminal v{VERSION}[/]")
        return
    
    # 宽终端：渲染完整 ASCII Logo（启用渐变效果）
    from claude_code.ui.theme import LOGO_GRADIENT
    
    # 渲染 CLAUDE（应用 6 级渐变）
    for i, line in enumerate(CLAUDE_LOGO):
        color = LOGO_GRADIENT[min(i, len(LOGO_GRADIENT)-1)]
        con.print(f"[bold {color}]{line}[/]")
    
    # 渲染 CODE（稍微缩进，形成层级，继续渐变）
    con.print()  # 增加一点垂直呼吸感
    for i, line in enumerate(CODE_LOGO):
        # CODE_LOGO 有 7 行，从渐变中间开始
        color = LOGO_GRADIENT[min(i + 2, len(LOGO_GRADIENT)-1)]
        con.print(f"[bold {color}]{line}[/]")

def _show_easter_egg(con) -> None:
    """🎲 随机彩蛋（1% 概率触发）"""
    easter_eggs = [
        (f"[{COLORS['warning']}]✨ 彩蛋！[/] [dim]你触发了隐藏成就：天选之子[/]", f"[{COLORS['primary']}]{ICONS['star']} 幸运星照耀着你[/]"),
        (f"[{COLORS['info']}]🎲 彩蛋！[/] [dim]你触发了隐藏成就：概率学家[/]", f"[dim]1% 的概率，你抓住了它[/]"),
        (f"[{COLORS['success']}]🍀 彩蛋！[/] [dim]你触发了隐藏成就：四叶草[/]", f"[dim]今天代码一定会一次通过！[/]"),
    ]
    egg_title, egg_text = random.choice(easter_eggs)
    con.print(f"\n  {egg_title}")
    con.print(f"  {egg_text}\n")

def show_welcome(model_name: str = "Claude") -> None:
    """显示欢迎界面 (卡片式布局 + 随机彩蛋)"""
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
    
    # 品牌分隔线
    console.brand_rule()
    
    # 🎲 随机彩蛋（1% 概率）
    if random.random() < 0.01:
        _show_easter_egg(con)
    
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
    context_limit: int = 0,
) -> None:
    """
    显示状态信息 (分层：模型名突出，次要信息 dim，Token 预算可视化)
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

    # 主行：模型名（突出）
    con.print(f"[bold {COLORS['primary']}]{ICONS['claude']} {model_short}[/]", end="")

    # 次要信息：dim，同行右对齐
    secondary_parts = []
    token_display = _format_token_count(total_tokens)
    
    # Token 预算可视化：用量百分比 + 剩余空间
    if context_limit > 0:
        usage_pct = min(total_tokens / context_limit, 1.0)
        remaining = max(context_limit - total_tokens, 0)
        remaining_display = _format_token_count(remaining)
        
        # 根据用量选择颜色
        if usage_pct >= 0.9:
            pct_color = COLORS['error']
        elif usage_pct >= 0.7:
            pct_color = COLORS['warning']
        else:
            pct_color = COLORS['success']
        
        # 迷你进度条（8宽）
        bar_width = 8
        filled = int(bar_width * usage_pct)
        mini_bar = f"[{pct_color}]{'█' * filled}[/][dim]{'░' * (bar_width - filled)}[/]"
        
        token_info = f"{token_display}/{_format_token_count(context_limit)} {mini_bar} [{pct_color}]{usage_pct:.0%}[/]"
        secondary_parts.append(token_info)
    else:
        secondary_parts.append(f"{token_display} tok")
    
    if total_cost > 0:
        secondary_parts.append(f"{ICONS['price']}{_format_cost(total_cost)}")
    if file_count > 0:
        secondary_parts.append(f"{ICONS['folder']}{file_count}")

    if secondary_parts:
        con.print(f"  [dim]{' │ '.join(secondary_parts)}[/]")
    else:
        con.print()

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
        row_styles=[None, "dim"],  # 斑马纹
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
        border_style=COLORS['border'],
        expand=False,
        width=_responsive_panel_width(),
        box=PANEL_STYLES['secondary'], # 列表容器使用简洁边框
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
        border_style=COLORS['border'],
        expand=False,
        width=_responsive_panel_width(),
        box=PANEL_STYLES['secondary'],
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
        border_style=COLORS['border'],
        expand=False,
        width=_responsive_panel_width(),
        box=PANEL_STYLES['secondary'], # 列表容器使用简洁边框
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
    
    # 使用 Panel 包裹内容（按层级选择边框风格）
    panel = Panel(
        content,
        title=title_text,
        title_align="left",
        border_style=color,
        box=PANEL_STYLES.get(level, PANEL_STYLES['info']),
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
        box=PANEL_STYLES['secondary'],
        padding=(1, 2),
    )
    con.print(panel)


# ============================================================
# Todo 计划面板
# ============================================================

def show_todo_panel(todo_list, flash_ids: list = None) -> None:
    """显示 TodoList 进度面板

    Args:
        todo_list: TodoList 实例
        flash_ids: 需要闪烁高亮的任务 ID 列表（刚完成的任务）
    """
    if not todo_list.items:
        return

    con = console.get_console()
    flash_ids = flash_ids or []

    # 全部完成时边框变绿
    border_color = COLORS['success'] if todo_list.is_all_done else COLORS['primary']
    # 进度条填充色随状态变化
    bar_color = COLORS['success'] if todo_list.is_all_done else COLORS['primary']

    # 构建面板内容
    content_lines = []
    # ID 对齐宽度：根据总任务数计算数字位数
    max_id_width = len(str(todo_list.total_count))

    for item in todo_list.items:
        # 优先级色彩标记（三种颜色实心圆，统一格式）
        priority = getattr(item, 'priority', 'medium')
        if priority == 'high':
            priority_dot = f"[{COLORS['error']}]●[/]"
        elif priority == 'low':
            priority_dot = f"[{COLORS['text_muted']}]●[/]"
        else:  # medium
            priority_dot = f"[{COLORS['primary']}]●[/]"

        # 状态标记 - Unicode 符号，与主题系统统一
        if item.status == "completed":
            status_icon = "✓"
            # 闪烁效果：刚完成的任务使用高亮绿色 + 粗体
            if item.id in flash_ids:
                style = f"[bold {COLORS['success']}]"
                end_style = "[/]"
            else:
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
            f"  {priority_dot} {status_icon} {aligned_id}  {style}{item.content}{end_style}"
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
        box=PANEL_STYLES['primary'],
        padding=(0, 2),
    )
    con.print(panel)


def _format_plan_stats(todo_list) -> str:
    """格式化计划统计行。"""
    return (
        f"总任务：{todo_list.total_count}  "
        f"✓ 完成：{todo_list.completed_count}  "
        f"✗ 失败：{todo_list.failed_count}  "
        f"● 进行中：{todo_list.in_progress_count}  "
        f"○ 待处理：{todo_list.pending_count}"
    )


def show_plan_complete(todo_list) -> None:
    """显示计划完成仪式

    Args:
        todo_list: TodoList 实例
    """
    con = console.get_console()
    con.print(Rule(style=COLORS['success']))

    failed_items = [item for item in todo_list.items if item.status == "failed"]
    lines = [
        f"[{COLORS['success']}]计划已结束[/]  [dim]{todo_list.progress_text}[/]",
        f"[dim]{_format_plan_stats(todo_list)}[/]",
    ]
    if failed_items:
        lines.append("")
        lines.append(f"[{COLORS['error']}]失败任务[/]")
        for item in failed_items:
            lines.append(f"  ✗ {item.id}  {item.content}")

    panel = Panel(
        "\n".join(lines),
        title=f"[{COLORS['success']}]✓ 执行完成[/]",
        title_align="left",
        border_style=COLORS['success'],
        box=PANEL_STYLES['primary'],
        padding=(0, 2),
    )
    con.print(panel)


def show_plan_status(todo_list, active: bool = False) -> None:
    """显示当前计划状态。"""
    if not todo_list.items:
        show_message_box("计划状态", "当前没有执行计划。用法: /plan <任务描述>", level="info")
        return

    show_todo_panel(todo_list)
    # 简洁操作提示（不再重复统计行，todo_panel 已包含进度条和统计）
    con = console.get_console()
    mode_icon = "●" if active else "○"
    mode_text = "运行中" if active else "未运行"
    hint = "/plan stop 退出计划模式" if active else "/plan <任务描述> 开始新计划"
    con.print(f"  {mode_icon} [{COLORS['info']}]{mode_text}[/]  [dim]{hint}[/]")


def show_plan_stopped(todo_list) -> None:
    """显示主动退出计划模式摘要。"""
    con = console.get_console()
    con.print(Rule(style=COLORS['warning']))

    if not todo_list.items:
        panel = Panel(
            "当前没有执行计划。",
            title=f"[{COLORS['warning']}]■ 已退出计划模式[/]",
            title_align="left",
            border_style=COLORS['warning'],
            box=PANEL_STYLES['warning'],
            padding=(0, 2),
        )
        con.print(panel)
        return

    unfinished = [item for item in todo_list.items if not item.is_done]
    lines = [
        f"[{COLORS['warning']}]计划已中断[/]  [dim]{todo_list.progress_text}[/]",
        f"[dim]{_format_plan_stats(todo_list)}[/]",
    ]
    if unfinished:
        lines.append("")
        lines.append(f"[{COLORS['text_muted']}]未完成任务[/]")
        for item in unfinished:
            lines.append(f"  {item.icon} {item.id}  {item.content}")
    else:
        lines.append("所有任务均已结束。")

    panel = Panel(
        "\n".join(lines),
        title=f"[{COLORS['warning']}]■ 已退出计划模式[/]",
        title_align="left",
        border_style=COLORS['warning'],
        box=PANEL_STYLES['warning'],
        padding=(0, 2),
    )
    con.print(panel)


def show_plan_aborted(reason: str, todo_list=None) -> None:
    """显示计划模式自动退出原因。"""
    con = console.get_console()
    con.print(Rule(style=COLORS['error']))

    lines = [f"[{COLORS['error']}]原因[/]  {reason}"]
    if todo_list is not None and todo_list.items:
        lines.append(f"[{COLORS['warning']}]进度[/]  {todo_list.progress_text}")
        lines.append(f"[dim]{_format_plan_stats(todo_list)}[/]")
    lines.append("")
    lines.append(f"[dim]建议：重新执行 /plan <任务>，或手动继续当前任务。[/]")

    panel = Panel(
        "\n".join(lines),
        title=f"[{COLORS['error']}]⚠ 计划模式已自动退出[/]",
        title_align="left",
        border_style=COLORS['error'],
        box=PANEL_STYLES['error'],
        padding=(0, 2),
    )
    con.print(panel)