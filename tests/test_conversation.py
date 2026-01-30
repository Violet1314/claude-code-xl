"""会话管理模块测试"""
import pytest
from claude_code.core.conversation import Conversation, Message

class TestMessage:
    """Message 数据类测试"""
    
    def test_to_dict(self):
        msg = Message(role="user", content="Hello")
        assert msg.to_dict() == {"role": "user", "content": "Hello"}
    
    def test_from_dict(self):
        data = {"role": "assistant", "content": "Hi there"}
        msg = Message.from_dict(data)
        assert msg.role == "assistant"
        assert msg.content == "Hi there"
    
    def test_from_dict_missing_fields(self):
        msg = Message.from_dict({})
        assert msg.role == ""
        assert msg.content == ""

class TestConversationInit:
    """Conversation 初始化测试"""
    
    def test_empty_init(self):
        conv = Conversation()
        assert conv.is_empty
        assert conv.message_count == 0
    
    def test_init_with_system_prompt(self):
        conv = Conversation(system_prompt="You are helpful.")
        assert conv.system_prompt == "You are helpful."
        assert conv.message_count == 0  # system 不计入
    
    def test_is_empty_property(self):
        conv = Conversation("System")
        assert conv.is_empty
        conv.add_user_message("Hi")
        assert not conv.is_empty

class TestConversationMessages:
    """消息操作测试"""
    
    def test_add_user_message(self):
        conv = Conversation()
        conv.add_user_message("Hello")
        assert conv.message_count == 1
    
    def test_add_assistant_message(self):
        conv = Conversation()
        conv.add_assistant_message("Hi there")
        assert conv.message_count == 1
    
    def test_message_order(self):
        conv = Conversation("System")
        conv.add_user_message("Q1")
        conv.add_assistant_message("A1")
        conv.add_user_message("Q2")
        
        messages = conv.get_messages()
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"
        assert messages[3]["role"] == "user"

class TestSystemPrompt:
    """系统提示词测试"""
    
    def test_set_system_prompt_empty_conv(self):
        conv = Conversation()
        conv.set_system_prompt("New prompt")
        assert conv.system_prompt == "New prompt"
        assert conv.get_messages()[0]["content"] == "New prompt"
    
    def test_update_system_prompt(self):
        conv = Conversation("Old prompt")
        conv.set_system_prompt("New prompt")
        assert conv.system_prompt == "New prompt"
        # 应该只有一条 system 消息
        system_msgs = [m for m in conv.get_messages() if m["role"] == "system"]
        assert len(system_msgs) == 1

class TestOptimizedMessages:
    """上下文优化测试"""
    
    def test_empty_conversation(self):
        conv = Conversation()
        assert conv.get_optimized_messages() == []
    
    def test_only_system(self):
        conv = Conversation("System prompt")
        result = conv.get_optimized_messages()
        assert len(result) == 1
        assert result[0]["role"] == "system"
    
    def test_preserves_last_message(self):
        conv = Conversation("System")
        conv.add_user_message("First")
        conv.add_assistant_message("Response")
        conv.add_user_message("Last question")
        
        # 使用很小的 token 限制
        result = conv.get_optimized_messages(max_tokens=50)
        
        # 应该至少包含 system 和最后一条
        assert result[0]["role"] == "system"
        assert result[-1]["content"] == "Last question"
    
    def test_reverse_priority(self):
        """验证倒序优先级：新消息优先保留"""
        conv = Conversation("S")
        for i in range(10):
            conv.add_user_message(f"Message {i}")
            conv.add_assistant_message(f"Response {i}")
        
        result = conv.get_optimized_messages(max_tokens=200)
        
        # 最后一条必须存在
        assert result[-1]["content"] == "Response 9"

class TestReset:
    """重置功能测试"""
    
    def test_reset_clears_messages(self):
        conv = Conversation("System")
        conv.add_user_message("Hello")
        conv.add_assistant_message("Hi")
        
        conv.reset()
        
        assert conv.message_count == 0
        assert conv.system_prompt == "System"
    
    def test_reset_preserves_system_prompt(self):
        conv = Conversation("Keep this")
        conv.add_user_message("Test")
        conv.reset()
        
        messages = conv.get_messages()
        assert len(messages) == 1
        assert messages[0]["content"] == "Keep this"

class TestLoadMessages:
    """加载历史测试"""
    
    def test_load_messages(self):
        conv = Conversation()
        history = [
            {"role": "system", "content": "Loaded system"},
            {"role": "user", "content": "Q"},
            {"role": "assistant", "content": "A"},
        ]
        
        conv.load_messages(history)
        
        assert conv.message_count == 2
        assert conv.system_prompt == "Loaded system"
    
    def test_load_overwrites(self):
        conv = Conversation("Old")
        conv.add_user_message("Old message")
        
        conv.load_messages([{"role": "user", "content": "New"}])
        
        assert conv.message_count == 1
        messages = conv.get_messages()
        assert messages[0]["content"] == "New"

class TestEstimateTokens:
    """Token 估算测试"""
    
    def test_empty_conversation(self):
        conv = Conversation()
        assert conv.estimate_tokens() == 0
    
    def test_with_messages(self):
        conv = Conversation("System")
        conv.add_user_message("Hello")
        
        tokens = conv.estimate_tokens()
        assert tokens > 0