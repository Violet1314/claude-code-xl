"""Token 估算工具 - 单一数据源"""
import re
from typing import List, Dict

# 估算系数（基于 Claude tokenizer 经验值）
ZH_RATIO = 1.5      # 中文字符
EN_RATIO = 0.25     # 英文/ASCII
MSG_OVERHEAD = 4    # 每条消息的格式开销
CONV_OVERHEAD = 3   # 对话整体开销

def estimate_tokens(text: str) -> int:
    """
    估算文本 token 数量
    
    Args:
        text: 输入文本
        
    Returns:
        估算的 token 数量
    """
    if not text:
        return 0
    
    # 统计非 ASCII 字符（中文等）
    non_ascii = len(re.findall(r'[^\x00-\x7f]', text))
    ascii_chars = len(text) - non_ascii
    
    return int(non_ascii * ZH_RATIO + ascii_chars * EN_RATIO)

def estimate_messages_tokens(messages: List[Dict[str, str]]) -> int:
    """
    估算消息列表的总 token 数量
    
    Args:
        messages: 消息列表，每条包含 role 和 content
        
    Returns:
        估算的总 token 数量
    """
    if not messages:
        return 0
    
    total = CONV_OVERHEAD
    for msg in messages:
        content = msg.get("content", "")
        total += estimate_tokens(content) + MSG_OVERHEAD
    
    return total