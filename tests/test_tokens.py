"""Token 估算模块测试"""
import pytest
from claude_code.utils.tokens import estimate_tokens, estimate_messages_tokens

class TestEstimateTokens:
    """estimate_tokens 函数测试"""
    
    def test_empty_string(self):
        assert estimate_tokens("") == 0
    
    def test_none_input(self):
        assert estimate_tokens(None) == 0
    
    def test_english_only(self):
        text = "Hello World"  # 11 chars
        result = estimate_tokens(text)
        assert 2 <= result <= 5  # 约 11 * 0.25 ≈ 2.75
    
    def test_chinese_only(self):
        text = "你好世界"  # 4 chars
        result = estimate_tokens(text)
        assert 5 <= result <= 7  # 约 4 * 1.5 = 6
    
    def test_mixed_content(self):
        text = "Hello 你好"  # 6 ASCII + 2 中文
        result = estimate_tokens(text)
        assert result > 0
    
    def test_code_block(self):
        code = """def hello():
    print("Hello World")
"""
        result = estimate_tokens(code)
        assert result > 0

class TestEstimateMessagesTokens:
    """estimate_messages_tokens 函数测试"""
    
    def test_empty_list(self):
        assert estimate_messages_tokens([]) == 0
    
    def test_single_message(self):
        messages = [{"role": "user", "content": "Hello"}]
        result = estimate_messages_tokens(messages)
        # CONV_OVERHEAD(3) + content_tokens + MSG_OVERHEAD(4)
        assert result >= 7
    
    def test_multiple_messages(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        result = estimate_messages_tokens(messages)
        assert result > estimate_messages_tokens(messages[:1])
    
    def test_missing_content(self):
        messages = [{"role": "user"}]  # 无 content 字段
        result = estimate_messages_tokens(messages)
        assert result == 3 + 4  # CONV + MSG overhead