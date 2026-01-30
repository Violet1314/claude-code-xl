"""响应渲染器"""
from claude_code.ui import console
from claude_code.ui.theme import COLORS, ICONS

def render_response(content: str, model_name: str, duration: float) -> None:
    """
    渲染 AI 响应
    
    Args:
        content: 响应内容
        model_name: 模型名称
        duration: 耗时（秒）
    """
    console.print(f"\n  [bold {COLORS['primary']}]{ICONS['claude']} Response[/]")
    console.print(f"  [dim]{'─' * 60}[/]")
    
    console.markdown(content)
    
    console.print(f"  [dim]{'─' * 60}[/]")
    console.print(f"  [dim]🕒 耗时: {duration:.2f}s | 模型: {model_name}[/]\n")