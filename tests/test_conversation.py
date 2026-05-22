"""会话管理测试"""
import pytest
import sys
import os

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from claude_code.core.conversation import Conversation, Message


class TestMessage:
    """Message 数据类测试"""

    def test_create_message(self):
        """测试创建消息"""
        msg = Message(role="user", content="Hello")

        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_to_dict(self):
        """测试转换为字典"""
        msg = Message(role="assistant", content="Hi there")

        result = msg.to_dict()

        assert result == {"role": "assistant", "content": "Hi there"}

    def test_from_dict(self):
        """测试从字典创建"""
        data = {"role": "system", "content": "You are helpful."}

        msg = Message.from_dict(data)

        assert msg.role == "system"
        assert msg.content == "You are helpful."

    def test_empty_content(self):
        """测试空内容"""
        msg = Message(role="user", content="")

        assert msg.content == ""
        assert msg.to_dict() == {"role": "user", "content": ""}
    def test_metadata_serialization(self):
        """测试 metadata 序列化/反序列化"""
        msg = Message(role="assistant", content="Hi", metadata={"model_name": "Test", "duration": 1.2})

        data = msg.to_dict()
        loaded = Message.from_dict(data)

        assert data["metadata"]["model_name"] == "Test"
        assert loaded.metadata == {"model_name": "Test", "duration": 1.2}

    def test_from_dict_without_metadata(self):
        """测试旧消息无 metadata 时兼容"""
        msg = Message.from_dict({"role": "assistant", "content": "Hi"})

        assert msg.metadata is None


class TestConversationInit:
    """Conversation 初始化测试"""

    def test_empty_conversation(self):
        """测试空会话"""
        conv = Conversation()

        assert conv.message_count == 0
        assert conv.is_empty is True

    def test_with_system_prompt(self):
        """测试带系统提示词初始化"""
        conv = Conversation(system_prompt="You are helpful.")

        assert conv.system_prompt == "You are helpful."
        # system 消息不计入 message_count
        assert conv.message_count == 0


class TestConversationMessages:
    """消息操作测试"""

    def test_add_user_message(self):
        """测试添加用户消息"""
        conv = Conversation()

        conv.add_user_message("Hello")

        assert conv.message_count == 1
        assert conv.is_empty is False

    def test_add_assistant_message(self):
        """测试添加助手消息"""
        conv = Conversation()

        conv.add_assistant_message("Hi there!")

        assert conv.message_count == 1

    def test_add_assistant_message_with_metadata(self):
        """测试添加带 metadata 的助手消息"""
        conv = Conversation()

        conv.add_assistant_message("Hi", metadata={"model_name": "Test", "duration": 0.5})

        messages = conv.get_messages()
        assert messages[0]["metadata"] == {"model_name": "Test", "duration": 0.5}


        """测试添加多条消息"""
        conv = Conversation()

        conv.add_user_message("Hello")
        conv.add_assistant_message("Hi!")
        conv.add_user_message("How are you?")

        assert conv.message_count == 3

    def test_get_messages(self):
        """测试获取消息列表"""
        conv = Conversation()
        conv.set_system_prompt("Be helpful.")
        conv.add_user_message("Hi")

        messages = conv.get_messages()

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


class TestConversationSystemPrompt:
    """系统提示词测试"""

    def test_set_system_prompt(self):
        """测试设置系统提示词"""
        conv = Conversation()

        conv.set_system_prompt("New prompt")

        assert conv.system_prompt == "New prompt"

    def test_update_system_prompt(self):
        """测试更新系统提示词"""
        conv = Conversation(system_prompt="Old prompt")

        conv.set_system_prompt("New prompt")

        assert conv.system_prompt == "New prompt"
        # 应该只有一条 system 消息
        messages = conv.get_messages()
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 1

    def test_system_prompt_in_messages(self):
        """测试系统提示词在消息列表中"""
        conv = Conversation()
        conv.set_system_prompt("Be helpful.")
        conv.add_user_message("Hi")

        messages = conv.get_messages()

        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "Be helpful."


class TestConversationReset:
    """重置测试"""

    def test_reset_clears_messages(self):
        """测试重置清空消息"""
        conv = Conversation()
        conv.add_user_message("Hello")
        conv.add_assistant_message("Hi!")

        conv.reset()

        assert conv.message_count == 0
        assert conv.is_empty is True

    def test_reset_preserves_system_prompt(self):
        """测试重置保留系统提示词"""
        conv = Conversation(system_prompt="Be helpful.")
        conv.add_user_message("Hello")

        conv.reset()

        assert conv.system_prompt == "Be helpful."
        messages = conv.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "system"


class TestConversationOptimizedMessages:
    """优化消息测试"""

    def test_get_optimized_messages_empty(self):
        """测试空会话的优化消息"""
        conv = Conversation()

        result = conv.get_optimized_messages(max_tokens=1000)

        assert result == []

    def test_get_optimized_messages_within_limit(self):
        """测试在限制内返回所有消息"""
        conv = Conversation()
        conv.set_system_prompt("Be helpful.")
        conv.add_user_message("Hello")

        result = conv.get_optimized_messages(max_tokens=100000)

        # system + user
        assert len(result) == 2

    def test_get_optimized_messages_preserves_system(self):
        """测试优化消息保留 system"""
        conv = Conversation()
        conv.set_system_prompt("System prompt here")
        conv.add_user_message("User message")

        result = conv.get_optimized_messages(max_tokens=100)

        assert result[0]["role"] == "system"

    def test_get_optimized_messages_preserves_last(self):
        """测试优化消息保留最后一条用户消息"""
        conv = Conversation()

        # 添加很多消息
        for i in range(10):
            conv.add_user_message(f"Message {i} - " + "x" * 1000)
            conv.add_assistant_message(f"Response {i} - " + "y" * 1000)

        # 最后一条
        conv.add_user_message("Important last message")

        # 非常小的限制
        result = conv.get_optimized_messages(max_tokens=500)

        # 最后一条应该在
        last_user_msgs = [m for m in result if m["role"] == "user"]
        assert len(last_user_msgs) >= 1
        assert "Important last message" in last_user_msgs[-1]["content"]

    def test_get_optimized_messages_no_system(self):
        """测试没有 system 消息时的优化"""
        conv = Conversation()
        # 不设置 system prompt
        conv.add_user_message("Hello")
        conv.add_assistant_message("Hi")

        result = conv.get_optimized_messages(max_tokens=100000)

        assert len(result) == 2
        # 没有 system 消息
        assert all(m["role"] != "system" for m in result)


class TestConversationLoadMessages:
    """加载消息测试"""

    def test_load_messages(self):
        """测试加载消息列表"""
        conv = Conversation()

        messages = [
            {"role": "system", "content": "Be helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        conv.load_messages(messages)

        assert conv.message_count == 2  # user + assistant
        assert conv.system_prompt == "Be helpful."

    def test_load_messages_empty(self):
        """测试加载空消息列表"""
        conv = Conversation()
        conv.add_user_message("Existing")

        conv.load_messages([])

        assert conv.message_count == 0

    def test_load_messages_overwrites(self):
        """测试加载消息会覆盖现有"""
        conv = Conversation()
        conv.add_user_message("Old message")

        conv.load_messages([
            {"role": "user", "content": "New message"}
        ])

        messages = conv.get_messages()
        assert len(messages) == 1
        assert messages[0]["content"] == "New message"


class TestConversationEstimateTokens:
    """Token 估算测试"""

    def test_estimate_tokens_empty(self):
        """测试空会话的 token 估算"""
        conv = Conversation()

        assert conv.estimate_tokens() == 0

    def test_estimate_tokens_with_messages(self):
        """测试有消息时的 token 估算"""
        conv = Conversation()
        conv.add_user_message("Hello, this is a test message.")
        conv.add_assistant_message("I understand. How can I help?")

        tokens = conv.estimate_tokens()

        assert tokens > 0

    def test_estimate_tokens_with_system(self):
        """测试带 system 消息的 token 估算"""
        conv = Conversation()
        conv.set_system_prompt("You are a helpful assistant.")
        conv.add_user_message("Hi")

        tokens = conv.estimate_tokens()

        assert tokens > 0


class TestConversationEdgeCases:
    """边界情况测试"""

    def test_empty_user_message(self):
        """测试空用户消息"""
        conv = Conversation()

        conv.add_user_message("")

        assert conv.message_count == 1
        messages = conv.get_messages()
        assert messages[-1]["content"] == ""

    def test_very_long_message(self):
        """测试超长消息"""
        conv = Conversation()

        long_content = "x" * 100000
        conv.add_user_message(long_content)

        assert conv.message_count == 1
        messages = conv.get_messages()
        assert len(messages[-1]["content"]) == 100000

    def test_special_characters_in_message(self):
        """测试消息中的特殊字符"""
        conv = Conversation()

        special_content = "Hello\nWorld\t<TAG>\"quotes\"'apostrophe'"
        conv.add_user_message(special_content)

        messages = conv.get_messages()
        assert messages[-1]["content"] == special_content

    def test_unicode_in_message(self):
        """测试消息中的 Unicode"""
        conv = Conversation()

        unicode_content = "你好世界 🌍 日本語 한글"
        conv.add_user_message(unicode_content)

        messages = conv.get_messages()
        assert messages[-1]["content"] == unicode_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])