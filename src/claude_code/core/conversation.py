"""会话管理 - 对话历史与上下文优化

v2.8.17 优化要点：
1. 需求锚定：始终保留前 N 条用户消息（防止长对话遗忘最初需求）
2. 滑动窗口：保留最近 K 轮对话（工作上下文）
3. 中间压缩：对中间轮次的大输出进行摘要化，节省 token
4. 工具输出摘要化：历史轮次的工具大输出替换为摘要
"""
import re
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
    
    # 上下文优化参数
    ANCHOR_USER_MSGS = 3        # 锚定前 N 条用户消息（需求锚点）
    RECENT_WINDOW = 10          # 保留最近 K 条消息（滑动窗口）
    TOOL_SUMMARY_THRESHOLD = 1500  # 工具输出超过此长度则摘要化
    TOOL_SUMMARY_MAX = 200      # 摘要化后保留的最大字符数
    ASSISTANT_SUMMARY_MAX = 500 # assistant 消息截断后保留的最大字符数
    
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
        """消息数量（不含 system prompt）"""
        if self._messages and self._messages[0].role == "system":
            return len(self._messages) - 1
        return len(self._messages)
    
    @property
    def is_empty(self) -> bool:
        """是否为空"""
        return len(self._messages) == 0
    
    def set_system_prompt(self, prompt: str) -> None:
        """设置系统提示词"""
        self._system_prompt = prompt
        
        if self._messages and self._messages[0].role == "system":
            self._messages[0] = Message(role="system", content=prompt)
        else:
            self._messages.insert(0, Message(role="system", content=prompt))
    
    def add_user_message(self, content: str) -> None:
        """添加用户消息"""
        self._messages.append(Message(role="user", content=content))
    
    def add_assistant_message(self, content: str) -> None:
        """添加助手消息"""
        self._messages.append(Message(role="assistant", content=content))
    
    def get_messages(self) -> List[Dict[str, str]]:
        """获取所有消息"""
        return [msg.to_dict() for msg in self._messages]
    
    def get_optimized_messages(self, max_tokens: int = None) -> List[Dict[str, str]]:
        """
        获取优化后的消息列表（需求锚定 + 滑动窗口 + 中间压缩）
        
        策略：
        1. 始终保留 system prompt
        2. 锚定前 N 条用户消息（需求锚点，防止遗忘最初目标）
        3. 保留最近 K 条消息（滑动窗口，工作上下文）
        4. 中间轮次：对工具大输出摘要化，节省 token
        5. 仍超限则从中间继续丢弃
        
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
        
        # 快速判断：总 token 量远低于限制时，无需优化直接返回
        total_chat_tokens = sum(estimate_tokens(m.content) + 4 for m in chat_msgs)
        if current_tokens + total_chat_tokens < max_tokens * 0.7:
            return system_msgs + [m.to_dict() for m in chat_msgs]
        
        # === 阶段 1：需求锚定 — 保留前 N 条用户消息 ===
        anchor_msgs = []
        user_count = 0
        for msg in chat_msgs:
            if msg.role == "user":
                user_count += 1
                if user_count <= self.ANCHOR_USER_MSGS:
                    anchor_msgs.append(msg)
                else:
                    break
            elif user_count > 0 and user_count <= self.ANCHOR_USER_MSGS:
                # 锚定用户消息后的助手回复也保留（保持对话连贯性）
                # 对 tool 大输出进行摘要化，防止锚定区域占用过多 token
                if msg.role == "tool" and len(msg.content) > self.TOOL_SUMMARY_THRESHOLD:
                    anchor_msgs.append(Message(role=msg.role, content=self._compress_history_content(msg.content)))
                else:
                    anchor_msgs.append(msg)
            if user_count > self.ANCHOR_USER_MSGS:
                break
        
        anchor_tokens = sum(estimate_tokens(m.content) + 4 for m in anchor_msgs)
        current_tokens += anchor_tokens
        
        # === 阶段 2：滑动窗口 — 保留最近 K 条消息 ===
        recent_msgs = chat_msgs[-self.RECENT_WINDOW:] if len(chat_msgs) > self.RECENT_WINDOW else []
        # 去掉与锚定重叠的部分
        if anchor_msgs and recent_msgs:
            anchor_end_idx = len(anchor_msgs) - 1  # 锚定区域在 chat_msgs 中的结束索引
            recent_start_idx = len(chat_msgs) - len(recent_msgs)
            if recent_start_idx <= anchor_end_idx:
                # 锚定和窗口重叠，窗口从锚定后开始
                recent_msgs = chat_msgs[anchor_end_idx + 1:]
        
        recent_tokens = sum(estimate_tokens(m.content) + 4 for m in recent_msgs)
        current_tokens += recent_tokens
        
        # === 阶段 3：中间轮次 — 摘要化工具大输出 ===
        # 确定中间范围（锚定之后、窗口之前）
        anchor_end = len(anchor_msgs) - 1  # 锚定区域在 chat_msgs 中的结束索引
        
        recent_start = len(chat_msgs) - len(recent_msgs) if recent_msgs else len(chat_msgs)
        
        middle_msgs = chat_msgs[anchor_end + 1:recent_start] if anchor_end + 1 < recent_start else []
        
        # 对中间消息的工具大输出进行摘要化
        middle_compressed = []
        for msg in middle_msgs:
            compressed_content = self._compress_history_content(msg.content, msg.role)
            middle_compressed.append(Message(role=msg.role, content=compressed_content))
        
        middle_tokens = sum(estimate_tokens(m.content) + 4 for m in middle_compressed)
        
        # 如果中间轮次加入后超限，从中间前面开始丢弃
        if current_tokens + middle_tokens > max_tokens:
            # 从中间消息前面开始丢弃，保留靠近窗口的部分
            remaining_budget = max_tokens - current_tokens
            kept_middle = []
            for msg in reversed(middle_compressed):
                msg_tokens = estimate_tokens(msg.content) + 4
                if remaining_budget - msg_tokens < 0:
                    break
                kept_middle.insert(0, msg)
                remaining_budget -= msg_tokens
            middle_compressed = kept_middle
        
        # === 组装最终消息列表 ===
        result = system_msgs
        result.extend(m.to_dict() for m in anchor_msgs)
        result.extend(m.to_dict() for m in middle_compressed)
        result.extend(m.to_dict() for m in recent_msgs)
        
        # Debug: 校验消息总数不超过原始消息数（防止重复）
        original_count = len(system_msgs) + len(chat_msgs)
        if len(result) > original_count:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"上下文优化后消息数({len(result)})超过原始({original_count})，"
                f"可能存在重复。anchor={len(anchor_msgs)}, middle={len(middle_compressed)}, recent={len(recent_msgs)}"
            )
        
        return result
    
    def _compress_history_content(self, content: str, role: str = "") -> str:
        """
        对历史消息中的工具大输出进行摘要化
        
        规则：
        - 包含 <tool_results> 的大输出 → 摘要化
        - 包含 <result> 的大输出 → 摘要化
        - assistant 超长消息 → 保留首尾（比工具结果更宽松）
        - 普通超长消息 → 保留首尾
        
        Args:
            content: 消息内容
            role: 消息角色（用于区分压缩策略）
            
        Returns:
            压缩后的内容
        """
        if len(content) <= self.TOOL_SUMMARY_THRESHOLD:
            return content
        
        # 工具结果消息：摘要化
        if "<tool_results>" in content or "<result" in content:
            return self._summarize_tool_results(content)
        
        # 路径提醒消息：极简化
        if "[系统提醒]" in content:
            return ""  # 历史路径提醒不需要保留
        
        # 计划模式提示：极简化
        if "计划模式" in content and "任务清单" in content:
            return "[计划模式提示已压缩]"
        
        # 超长消息：保留首尾（assistant 消息使用更宽松的截断长度）
        summary_max = self.ASSISTANT_SUMMARY_MAX if role == "assistant" else self.TOOL_SUMMARY_MAX
        if len(content) > self.TOOL_SUMMARY_THRESHOLD * 2:
            head = content[:summary_max]
            tail_len = summary_max // 2
            tail = content[-tail_len:]
            omitted = len(content) - len(head) - tail_len
            return f"{head}\n\n... (省略 {omitted} 字符) ...\n\n{tail}"
        
        return content
    
    def _summarize_tool_results(self, content: str) -> str:
        """
        将工具结果摘要化
        
        提取每个 <result> 的工具名、状态、简要信息，
        丢弃大块输出内容。
        
        Args:
            content: 包含 <tool_results> 的消息内容
            
        Returns:
            摘要化后的内容
        """
        # 提取中断信息
        interrupt_note = ""
        if "user_interrupt" in content:
            interrupt_note = "\n[用户中断了部分操作]"
        
        # 提取每个工具结果的状态
        summaries = []
        # 匹配 <result tool="xxx" status="yyy">
        pattern = r'<result\s+tool="([^"]+)"\s+status="([^"]+)">'
        matches = re.findall(pattern, content)
        
        for tool_name, status in matches:
            if status == "success":
                summaries.append(f"✅ {tool_name}")
            elif status == "error":
                summaries.append(f"❌ {tool_name}")
            elif status == "skipped":
                summaries.append(f"⏭️ {tool_name}")
            elif status == "interrupted":
                summaries.append(f"⚡ {tool_name}")
            else:
                summaries.append(f"❓ {tool_name}({status})")
        
        if summaries:
            summary_text = ", ".join(summaries)
            return f"<tool_results_summary>{interrupt_note}\n执行结果: {summary_text}\n(详细输出已压缩，如需查看请重新调用工具)</tool_results_summary>"
        
        # 无法解析的兜底：截断
        return content[:self.TOOL_SUMMARY_MAX] + f"\n... (省略 {len(content) - self.TOOL_SUMMARY_MAX} 字符) ..."
    
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
