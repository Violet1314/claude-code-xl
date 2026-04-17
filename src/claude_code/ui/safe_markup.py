"""Rich Markup 安全防护层 — 彻底根治 MarkupError 导致程序崩溃的问题

问题根因：
    Rich 的 console.print(markup=True) 会将字符串当作 Rich Markup 解析，
    当内容中包含不匹配的 [/] 或类似 Markup 标签时，Rich 解析失败导致 MarkupError 崩溃。

解决方案：
    1. safe_print() — 安全打印，先尝试 markup=True，失败则自动转义后重试
    2. 猴子补丁 — 让 _console.print 默认安全，MarkupError 自动修复
    3. escape_markup() — 完全转义所有 Markup 标签（用于纯文本显示）

关键设计原则：
    - 不用白名单过滤（白名单无法覆盖 [cyan]、[dim #6A6A6A]、[bold green] 等组合样式）
    - 让 Rich 自己验证 Markup 是否合法
    - Markup 合法 → 正常渲染（标签隐藏，样式生效）
    - Markup 非法 → 自动转义所有标签后以纯文本显示
"""
import re
from rich.markup import escape as rich_escape


# Markup 标签正则：匹配 [tag] 和 [/tag] 形式
_MARKUP_TAG_RE = re.compile(r'\[(/?)([^\]]*)\]')


def escape_markup(text: str) -> str:
    """完全转义所有 Rich Markup 标签，使文本作为纯文本安全显示
    
    使用 Rich 内置的 escape() 函数，将 [ 转为 [[，] 转为 ]]。
    """
    return rich_escape(text)


def _try_render_markup(text: str) -> bool:
    """测试 Rich Markup 是否能合法解析
    
    通过 Rich 内部的 _parse() 方法验证，不产生任何输出。
    """
    try:
        from rich.console import Console
        # 用一个不输出到终端的 Console 来验证
        test_console = Console(file=open('NUL', 'w') if __import__('sys').platform == 'win32' else open('/dev/null', 'w'), legacy_windows=False)
        test_console.print(text, markup=True, highlight=False, no_wrap=True)
        # 关闭文件句柄
        try:
            test_console.file.close()
        except Exception:
            pass
        return True
    except Exception:
        return False


def safe_markup(text: str) -> str:
    """自动修复不合法的 Rich Markup，使其可以安全渲染

    策略：
    1. 先用 Rich 验证 Markup 是否合法
    2. 如果合法 → 原样返回（保留样式）
    3. 如果非法 → 转义所有标签为纯文本（[[...]]），确保不崩溃

    这样：
    - 工具生成的合法 Markup（如 [cyan]...[/]）能正常渲染，标签隐藏
    - AI 输出中的非法 Markup（如不匹配的 [/]）自动转义，程序不崩溃
    """
    if _try_render_markup(text):
        return text
    # Markup 非法 → 转义所有标签
    return escape_markup(text)


def safe_print(console, content: str, *, markup: bool = True, highlight: bool = False, **kwargs) -> None:
    """安全打印 — 自动处理 MarkupError，确保程序永不崩溃

    策略：
    1. 如果 markup=False，直接打印纯文本
    2. 如果 markup=True，先尝试让 Rich 正常解析
    3. 如果 Rich 解析失败（MarkupError），转义所有标签后以纯文本打印
    
    这样：
    - 工具生成的合法 Markup（如 [cyan]...[/]）能正常渲染
    - AI 输出中的非法 Markup（如不匹配的 [/]）不会崩溃
    """
    if not markup or not isinstance(content, str):
        console.print(content, markup=markup, highlight=highlight, **kwargs)
        return

    try:
        # 先尝试正常 Markup 渲染
        console.print(content, markup=True, highlight=highlight, **kwargs)
    except Exception:
        # MarkupError → 用 safe_markup 自动修复后重试
        fixed = safe_markup(content)
        if fixed != content:
            try:
                console.print(fixed, markup=True, highlight=highlight, **kwargs)
            except Exception:
                # 修复后仍失败 → 转义所有标签纯文本显示
                console.print(escape_markup(content), markup=True, highlight=False, **kwargs)
        else:
            # safe_markup 没有修改（理论上不应到达），纯文本回退
            console.print(escape_markup(content), markup=True, highlight=False, **kwargs)


def validate_markup(text: str) -> list[str]:
    """验证文本中的 Rich Markup 标签是否配对

    Returns:
        错误列表，空列表表示无错误
    """
    errors = []
    stack = []

    for match in _MARKUP_TAG_RE.finditer(text):
        close_slash = match.group(1)
        tag = match.group(2)

        if close_slash:
            # 关闭标签 [/tag]
            if not stack or stack[-1] != tag:
                errors.append(f"关闭标签 [/{tag}] 没有匹配的开启标签")
            else:
                stack.pop()
        else:
            # 开启标签 [tag]
            stack.append(tag)

    for tag in stack:
        errors.append(f"开启标签 [{tag}] 没有匹配的关闭标签")

    return errors
