"""会话管理 - 对话历史与上下文优化"""
from typing import List, Dict, Optional
from dataclasses import dataclass, field

from claude_code.utils.tokens import estimate_tokens, estimate_messages_tokens
from claude_code.config.defaults import CONVERSATION

@dataclass
class Message:
    """单条消息"""
    role: str
    content: str
    
    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Message":
        return cls(role=data.get("role", ""), content=data.get("content", ""))

class Conversation:
    """会话管理器"""
    
    def __init__(self, system_prompt: str = ""):
        """
        初始化会话
        
        Args:
            system_prompt: 系统提示词
        """
        self._messages: List[Message] = []
        self._system_prompt: str = ""
        
        if system_prompt:
            self.set_system_prompt(system_prompt)
    
    @property
    def system_prompt(self) -> str:
        """获取系统提示词"""
        return self._system_prompt
    
    @property
    def message_count(self) -> int:
        """获取用户/助手消息数量（不含 system）"""
        return sum(1 for m in self._messages if m.role != "system")
    
    @property
    def is_empty(self) -> bool:
        """会话是否为空（无用户消息）"""
        return self.message_count == 0
    
    def set_system_prompt(self, prompt: str) -> None:
        """
        设置系统提示词
        
        Args:
            prompt: 系统提示词内容
        """
        self._system_prompt = prompt
        
        # 更新或插入 system 消息
        if self._messages and self._messages[0].role == "system":
            self._messages[0].content = prompt
        else:
            self._messages.insert(0, Message(role="system", content=prompt))
    
    def add_user_message(self, content: str) -> None:
        """添加用户消息"""
        self._messages.append(Message(role="user", content=content))
    
    def add_assistant_message(self, content: str) -> None:
        """添加助手消息"""
        self._messages.append(Message(role="assistant", content=content))
    
    def get_messages(self) -> List[Dict[str, str]]:
        """获取所有消息（字典格式）"""
        return [m.to_dict() for m in self._messages]
    
    def get_optimized_messages(
        self,
        max_tokens: int = None,
    ) -> List[Dict[str, str]]:
        """
        获取优化后的消息列表（倒序优先级修剪）
        
        保证：
        1. 始终保留 system 消息
        2. 始终保留最后一条消息（当前用户输入）
        3. 从最新到最旧填充历史
        
        Args:
            max_tokens: 最大 token 限制
            
        Returns:
            优化后的消息列表
        """
        max_tokens = max_tokens or CONVERSATION.DEFAULT_CONTEXT_LIMIT
        
        if not self._messages:
            return []
        
        # 分离 system 消息
        if self._messages[0].role == "system":
            system_msgs = [self._messages[0].to_dict()]
            chat_msgs = self._messages[1:]
        else:
            system_msgs = []
            chat_msgs = self._messages
        
        if not chat_msgs:
            return system_msgs
        
        # 计算 system 消息的 token
        current_tokens = estimate_messages_tokens(system_msgs)
        
        # 必须包含最后一条消息
        last_msg = chat_msgs[-1]
        optimized = [last_msg.to_dict()]
        current_tokens += estimate_tokens(last_msg.content) + 4
        
        # 逆序填充历史消息
        for msg in reversed(chat_msgs[:-1]):
            msg_tokens = estimate_tokens(msg.content) + 4
            
            if current_tokens + msg_tokens > max_tokens:
                break
            
            optimized.insert(0, msg.to_dict())
            current_tokens += msg_tokens
        
        return system_msgs + optimized
    
    def reset(self) -> None:
        """重置会话（保留 system prompt）"""
        self._messages.clear()
        
        if self._system_prompt:
            self._messages.append(Message(role="system", content=self._system_prompt))
    
    def load_messages(self, messages: List[Dict[str, str]]) -> None:
        """
        加载消息历史
        
        Args:
            messages: 消息列表
        """
        self._messages = [Message.from_dict(m) for m in messages]
        
        # 更新 system prompt
        if self._messages and self._messages[0].role == "system":
            self._system_prompt = self._messages[0].content
    
    def estimate_tokens(self) -> int:
        """估算当前会话总 token 数"""
        return estimate_messages_tokens(self.get_messages())