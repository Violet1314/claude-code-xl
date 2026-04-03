"""响应渲染器 - 优雅卡片风格 (Elegant Card Style)"""
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.box import ROUNDED
from claude_code.ui import console
from claude_code.ui.theme import COLORS, ICONS

def render_response(content: str, model_name: str, duration: float, tokens: dict = None) -> None:
    """
    渲染 AI 响应 (使用统一 Panel 风格)
    
    Args:
        content: 响应内容 (Markdown)
        model_name: 模型名称
        duration: 耗时（秒）
        tokens: token 使用量 { "input": int, "output": int}
    """
    con = console.get_console()
    
    # 1. 构建头部信息文本
    header_parts = [f"[bold]{model_name}[/]"]
    
    if duration:
        header_parts.append(f"[dim]{duration:.1f}s[/]")
        
    if tokens and tokens.get('output'):
        output_tokens = tokens['output']
        if output_tokens >= 1000:
            token_str = f"{output_tokens / 1000:.1f}K"
        else:
            token_str = str(output_tokens)
        header_parts.append(f"[dim]{token_str} tok[/]")
    
    # 使用 subtle 分隔符连接
    header_text = " [dim]•[/] ".join(header_parts)
    
    # 2. 渲染 Markdown 内容
    # 增加左侧 padding (2) 以创造视觉层级，避免文字贴边
    md_content = Markdown(content, code_theme="monokai")
    
    # 3. 创建 Panel
    panel = Panel(
        md_content,
        title=header_text,
        title_align="left",
        border_style=COLORS['border_default'],
        box=ROUNDED,
        padding=(1, 2),  # 上下1行，左右2列留白
    )
    
    con.print() # 顶部空行，增加呼吸感
    con.print(panel)
    con.print() # 底部空行

def render_response_simple(content: str, model_name: str, duration: float) -> None:
    """
    简洁版响应渲染（兼容旧调用，保持风格一致）
    """
    con = console.get_console()
    
    header_text = f"[bold]{model_name}[/] [dim]({duration:.1f}s)[/]"
    
    md_content = Markdown(content, code_theme="monokai")
    
    panel = Panel(
        md_content,
        title=header_text,
        title_align="left",
        border_style=COLORS['border_subtle'],
        box=ROUNDED,
        padding=(1, 2),
    )
    
    con.print()
    con.print(panel)
    con.print()