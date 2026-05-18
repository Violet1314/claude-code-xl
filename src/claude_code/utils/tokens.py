"""Token 估算工具 - 精确估算 + 回退方案

优先使用 tiktoken 精确计算（支持 cl100k_base / o200k_base 等编码），
tiktoken 不可用时自动回退到基于字符的快速估算。
"""
import re
from typing import List, Dict, Optional

# ── 回退估算系数（基于 Claude tokenizer 经验值）──
_ZH_RATIO = 1.5      # 中文字符
_EN_RATIO = 0.25     # 英文/ASCII
_MSG_OVERHEAD = 4    # 每条消息的格式开销
_CONV_OVERHEAD = 3   # 对话整体开销

# ── tiktoken 懒加载 ──
_tiktoken_available: Optional[bool] = None
_default_encoding = None


def _init_tiktoken():
    """懒加载 tiktoken，仅首次调用时初始化"""
    global _tiktoken_available, _default_encoding
    if _tiktoken_available is not None:
        return

    try:
        import tiktoken
        # o200k_base 是 GPT-4o / Claude 3.5+ 使用的编码，对代码和中英文混合文本更准确
        # 如果不可用则回退到 cl100k_base
        try:
            _default_encoding = tiktoken.get_encoding("o200k_base")
        except Exception:
            _default_encoding = tiktoken.get_encoding("cl100k_base")
        _tiktoken_available = True
    except Exception:
        _tiktoken_available = False
        _default_encoding = None


def _count_tokens_tiktoken(text: str) -> int:
    """使用 tiktoken 精确计算 token 数"""
    _init_tiktoken()
    if _default_encoding is None:
        return -1  # 不可用，调用方应回退
    return len(_default_encoding.encode(text))


def _count_tokens_fallback(text: str) -> int:
    """基于字符的快速估算（回退方案）"""
    if not text:
        return 0
    non_ascii = len(re.findall(r'[^\x00-\x7f]', text))
    ascii_chars = len(text) - non_ascii
    return int(non_ascii * _ZH_RATIO + ascii_chars * _EN_RATIO)


def estimate_tokens(text: str, precise: bool = True) -> int:
    """
    估算文本 token 数量

    Args:
        text: 输入文本
        precise: 是否尝试使用 tiktoken 精确计算（默认 True）

    Returns:
        估算的 token 数量
    """
    if not text:
        return 0

    if precise:
        count = _count_tokens_tiktoken(text)
        if count >= 0:
            return count

    return _count_tokens_fallback(text)


def estimate_messages_tokens(messages: List[Dict[str, str]], precise: bool = True) -> int:
    """
    估算消息列表的总 token 数量

    Args:
        messages: 消息列表，每条包含 role 和 content
        precise: 是否尝试使用 tiktoken 精确计算（默认 True）

    Returns:
        估算的总 token 数量
    """
    if not messages:
        return 0

    total = _CONV_OVERHEAD
    for msg in messages:
        content = msg.get("content", "")
        total += estimate_tokens(content, precise=precise) + _MSG_OVERHEAD

    return total


def is_tiktoken_available() -> bool:
    """检查 tiktoken 是否可用"""
    _init_tiktoken()
    return _tiktoken_available is True
