"""响应渲染器"""
from claude_code.ui import console
from claude_code.ui.theme import COLORS, ICONS


def render_response(content: str, model_name: str, duration: float, tokens: dict = None) -> None:
    """
    渲染 AI 响应

    Args:
        content: 响应内容
        model_name: 模型名称
        duration: 耗时（秒）
        tokens: token 使用量 {"input": int, "output": int}
    """
    con = console.get_console()

    # 头部信息行
    header_parts = [f"[bold {COLORS['primary']}]{ICONS['claude']}[/]", model_name]

    # 耗时
    if duration:
        header_parts.append(f"[dim]{duration:.1f}s[/]")

    # Token 信息
    if tokens and tokens.get('output'):
        output_tokens = tokens['output']
        if output_tokens >= 1000:
            token_str = f"{output_tokens / 1000:.1f}K"
        else:
            token_str = str(output_tokens)
        header_parts.append(f"[dim]{token_str} tokens[/]")

    header = " ─ ".join(header_parts)

    # 顶部边框
    con.print(f"\n  [dim {COLORS['border_subtle']}]╭─[/] {header}")

    # 内容区域
    if content.strip():
        # 使用 markdown 渲染
        console.markdown(content)

    # 底部边框
    con.print(f"  [dim {COLORS['border_subtle']}]╰{'─' * 50}[/]")


def render_response_simple(content: str, model_name: str, duration: float) -> None:
    """
    简洁版响应渲染（兼容旧调用）

    Args:
        content: 响应内容
        model_name: 模型名称
        duration: 耗时（秒）
    """
    con = console.get_console()

    con.print(f"\n  [bold {COLORS['primary']}]{ICONS['claude']} Response[/]")
    con.print(f"  [dim]{'─' * 60}[/]")

    console.markdown(content)

    con.print(f"  [dim]{'─' * 60}[/]")
    con.print(f"  [dim]🕒 耗时: {duration:.2f}s | 模型: {model_name}[/]\n")