"""响应渲染器 - 优雅卡片风格 (Elegant Card Style)"""
import re
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from claude_code.ui import console
from claude_code.ui.theme import COLORS, ICONS, PANEL_STYLES


def _add_code_block_labels(content: str) -> str:
    """预处理 Markdown：在代码块首行注入语言标签
    
    将 ```python 转换为 ```python\n# ── PYTHON ──
    让 Rich Markdown 渲染时自动显示语言标签
    """
    def _replace_code_block(match):
        backticks = match.group(1)
        lang = match.group(2) or ""
        code = match.group(3)
        
        if lang:
            # 构建语言标签行
            label = f"# ── {lang.upper()} ──"
            # 对于不同语言使用不同注释符号
            if lang.lower() in ("html", "xml", "svg"):
                label = f"<!-- ── {lang.upper()} ── -->"
            elif lang.lower() in ("css", "scss", "less"):
                label = f"/* ── {lang.upper()} ── */"
            elif lang.lower() in ("sql",):
                label = f"-- ── {lang.upper()} ──"
            elif lang.lower() in ("lua",):
                label = f"-- ── {lang.upper()} ──"
            elif lang.lower() in ("r",):
                label = f"# ── {lang.upper()} ──"
            
            return f"{backticks}{lang}\n{label}\n{code}"
        return match.group(0)
    
    # 匹配 ```lang\n...\n``` 代码块
    pattern = r"(```)(\w+)?\n([\s\S]*?)```"
    return re.sub(pattern, _replace_code_block, content)


def render_response(content: str, model_name: str, duration: float, tokens: dict = None, has_tools: bool = False) -> None:
    """
    渲染 AI 响应 (使用统一 Panel 风格)
    
    Args:
        content: 响应内容 (Markdown)
        model_name: 模型名称
        duration: 耗时（秒）
        tokens: token 使用量 { "input": int, "output": int}
        has_tools: 是否有工具调用（有则不打后空行，由分组打印控制间距）
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
    
    # 2. 预处理 Markdown：注入代码块语言标签
    labeled_content = _add_code_block_labels(content)
    
    # 3. 渲染 Markdown 内容
    md_content = Markdown(labeled_content, code_theme="github-dark")
    
    # 4. 创建 Panel（重要面板使用圆角）
    panel = Panel(
        md_content,
        title=header_text,
        title_align="left",
        border_style=COLORS['border'],
        box=PANEL_STYLES['primary'],
        padding=(1, 2),  # 上下1行，左右2列留白
    )
    
    if not has_tools:
        con.print() # 顶部空行（无工具时增加呼吸感；有工具时紧贴工具摘要）
    con.print(panel)
    if not has_tools:
        con.print() # 底部空行（无工具时由 Panel 自带间距；有工具时由分组打印控制）

def render_response_simple(content: str, model_name: str, duration: float) -> None:
    """
    简洁版响应渲染（兼容旧调用，保持风格一致）
    """
    con = console.get_console()
    
    header_text = f"[bold]{model_name}[/] [dim]({duration:.1f}s)[/]"
    
    labeled_content = _add_code_block_labels(content)
    md_content = Markdown(labeled_content, code_theme="github-dark")
    
    panel = Panel(
        md_content,
        title=header_text,
        title_align="left",
        border_style=COLORS['border'],
        box=PANEL_STYLES['primary'],
        padding=(1, 2),
    )
    
    con.print()
    con.print(panel)
    con.print()
