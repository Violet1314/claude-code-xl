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
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list] = None
    reasoning_content: Optional[str] = None  # 新增

    def to_dict(self) -> Dict[str, str]:
        result = {"role": self.role, "content": self.content}
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.reasoning_content:              # 新增
            result["reasoning_content"] = self.reasoning_content
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Message":
        return cls(
            role=data.get("role", ""),
            content=data.get("content", ""),
            tool_call_id=data.get("tool_call_id"),
            tool_calls=data.get("tool_calls"),
            reasoning_content=data.get("reasoning_content"),  # 新增
        )

class Conversation:
    """会话管理器"""
    
    # 上下文优化参数（基准值，自适应会在此基础上调整）
    ANCHOR_USER_MSGS_BASE = 3        # 锚定前 N 条用户消息（需求锚点）基准值
    ANCHOR_USER_MSGS_MIN = 2         # 锚定最小值（极限压缩时仍保留2条，防止需求丢失）
    RECENT_WINDOW_BASE = 10          # 保留最近 K 条消息（滑动窗口）基准值
    RECENT_WINDOW_MIN = 6            # 窗口最小值（极限压缩时保留6条，避免上下文断裂）
    RECENT_WINDOW_MAX = 20           # 窗口最大值（空间充足时放宽）
    TOOL_SUMMARY_THRESHOLD = 1500    # 工具输出超过此长度则摘要化
    TOOL_SUMMARY_MAX = 200           # 摘要化后保留的最大字符数
    ASSISTANT_SUMMARY_MAX = 500      # assistant 消息截断后保留的最大字符数
    RECENT_TOOL_COMPRESS_THRESHOLD = 1000  # 近期窗口 tool 消息轻量压缩阈值
    
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
    
    def add_assistant_message(self, content: str, tool_calls: Optional[list] = None, reasoning_content: Optional[str] = None) -> None:
        """添加助手消息（可附带原生 tool_calls 和 reasoning_content）"""
        self._messages.append(Message(role="assistant", content=content, tool_calls=tool_calls, reasoning_content=reasoning_content))

    def add_tool_message(self, tool_call_id: str, content: str) -> None:
        """添加工具结果消息（原生 tool role）"""
        self._messages.append(Message(role="tool", content=content, tool_call_id=tool_call_id))
    
    def add_tool_messages(self, tool_results: List[Dict[str, str]]) -> None:
        """批量添加工具结果消息
        
        Args:
            tool_results: 列表，每项包含 tool_call_id 和 content
        """
        for tr in tool_results:
            self._messages.append(Message(
                role="tool",
                content=tr.get("content", ""),
                tool_call_id=tr.get("tool_call_id", ""),
            ))
    
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
        usage_ratio = (current_tokens + total_chat_tokens) / max_tokens if max_tokens > 0 else 0
        
        if usage_ratio < 0.7:
            return system_msgs + [m.to_dict() for m in chat_msgs]
        
        # === 自适应调参：根据上下文使用率动态调整锚定和窗口 ===
        anchor_n, window_k = self._adaptive_params(usage_ratio)
        
        # === 阶段 1：需求锚定 — 保留前 N 条用户消息 ===
        anchor_msgs = []
        user_count = 0
        for msg in chat_msgs:
            if msg.role == "user":
                user_count += 1
                if user_count <= anchor_n:
                    anchor_msgs.append(msg)
                else:
                    break
            elif user_count > 0 and user_count <= anchor_n:
                # 锚定用户消息后的助手回复也保留（保持对话连贯性）
                # 对 tool 大输出进行摘要化，防止锚定区域占用过多 token
                if msg.role == "tool" and len(msg.content) > self.TOOL_SUMMARY_THRESHOLD:
                    anchor_msgs.append(Message(
                        role=msg.role,
                        content=self._compress_history_content(msg.content, msg.role),
                        tool_call_id=msg.tool_call_id,
                    ))
                else:
                    # 锚定消息中的 assistant 消息也压缩推理内容
                    if msg.role == "assistant" and getattr(msg, 'reasoning_content', None):
                        anchor_msgs.append(Message(
                            role=msg.role,
                            content=msg.content,
                            tool_call_id=msg.tool_call_id,
                            tool_calls=msg.tool_calls,
                            reasoning_content=self._compress_reasoning_content(
                                getattr(msg, 'reasoning_content', None)
                            ),
                        ))
                    else:
                        anchor_msgs.append(msg)
            if user_count > anchor_n:
                break
        
        anchor_tokens = sum(estimate_tokens(m.content) + 4 for m in anchor_msgs)
        current_tokens += anchor_tokens
        
        # === 阶段 2：滑动窗口 — 保留最近 K 条消息 ===
        recent_msgs = chat_msgs[-window_k:] if len(chat_msgs) > window_k else []
        # 去掉与锚定重叠的部分
        if anchor_msgs and recent_msgs:
            anchor_end_idx = len(anchor_msgs) - 1  # 锚定区域在 chat_msgs 中的结束索引
            recent_start_idx = len(chat_msgs) - len(recent_msgs)
            if recent_start_idx <= anchor_end_idx:
                # 锚定和窗口重叠，窗口从锚定后开始
                recent_msgs = chat_msgs[anchor_end_idx + 1:]
        
        # 近期窗口 tool 消息轻量压缩：保留首尾摘要，节省近期窗口占用
        # 这是近期窗口完全不压缩的最大盲区，tool 消息可能占窗口 50%+ 体积
        recent_compressed = []
        for msg in recent_msgs:
            if msg.role == "tool" and len(msg.content) > self.RECENT_TOOL_COMPRESS_THRESHOLD:
                head = msg.content[:300]
                tail = msg.content[-200:]
                omitted = len(msg.content) - 500
                compressed_content = f"{head}\n\n... (省略 {omitted} 字符) ...\n\n{tail}"
                recent_compressed.append(Message(
                    role=msg.role,
                    content=compressed_content,
                    tool_call_id=msg.tool_call_id,
                    tool_calls=msg.tool_calls,
                    reasoning_content=msg.reasoning_content,
                ))
            else:
                recent_compressed.append(msg)
        recent_msgs = recent_compressed
        
        recent_tokens = sum(estimate_tokens(m.content) + 4 for m in recent_msgs)
        current_tokens += recent_tokens
        
        # === 阶段 3：中间轮次 — 摘要化工具大输出 ===
        # 确定中间范围（锚定之后、窗口之前）
        anchor_end = len(anchor_msgs) - 1  # 锚定区域在 chat_msgs 中的结束索引
        
        recent_start = len(chat_msgs) - len(recent_msgs) if recent_msgs else len(chat_msgs)
        
        middle_msgs = chat_msgs[anchor_end + 1:recent_start] if anchor_end + 1 < recent_start else []
        
        # 对中间消息的工具大输出进行摘要化
        # v2.8.42+: 先尝试生成操作摘要链，将连续工具操作压缩为因果链
        middle_compressed = self._build_operation_chain(middle_msgs)
        if middle_compressed is None:
            # 回退：逐条压缩（原逻辑）
            middle_compressed = []
            for msg in middle_msgs:
                compressed_content = self._compress_history_content(msg.content, msg.role)
                compressed_tool_calls = self._compress_tool_calls(msg.tool_calls) if msg.tool_calls else None
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
    
    def _adaptive_params(self, usage_ratio: float) -> tuple:
        """根据上下文使用率动态调整锚定数量和窗口大小
        
        策略（v2.8.38+ 四档自适应）：
        - 使用率 < 50%：空间充足，放宽窗口（最大20），保持基准锚定
        - 使用率 50-70%：轻度压缩，基准锚定，中等窗口（12）
        - 使用率 70-90%：中高压缩，锚定2，窗口8
        - 使用率 ≥ 90%：极限压缩，最小锚定（2）+最小窗口（6）
        
        Args:
            usage_ratio: 当前上下文使用率（0.0 ~ 1.0+）
        
        Returns:
            (anchor_n, window_k) 锚定消息数和窗口大小
        """
        if usage_ratio >= 0.9:
            # 极限压缩：最小锚定+最小窗口
            anchor_n = self.ANCHOR_USER_MSGS_MIN
            window_k = self.RECENT_WINDOW_MIN
        elif usage_ratio >= 0.7:
            # 中高压缩：适度缩减锚定和窗口
            anchor_n = 2
            window_k = 8
        elif usage_ratio >= 0.5:
            # 轻度压缩：基准锚定，中等窗口
            anchor_n = self.ANCHOR_USER_MSGS_BASE
            window_k = 12
        else:
            # 空间充足：放宽窗口，保持基准锚定
            anchor_n = self.ANCHOR_USER_MSGS_BASE
            window_k = self.RECENT_WINDOW_MAX
        
        return anchor_n, window_k
    
    def _compress_history_content(self, content: str, role: str = "") -> str:
        """
        对历史消息中的大输出进行摘要化
        
        规则：
        - tool 角色消息（原生格式）→ 保留首尾摘要
        - 包含 <tool_results> 的旧格式消息 → 摘要化（向后兼容）
        - assistant 超长消息 → 保留首尾（比工具结果更宽松）
        - 路径提醒消息 → 极简化
        - 计划模式提示 → 极简化
        - 普通超长消息 → 保留首尾
        
        Args:
            content: 消息内容
            role: 消息角色（用于区分压缩策略）
            
        Returns:
            压缩后的内容
        """
        if len(content) <= self.TOOL_SUMMARY_THRESHOLD:
            return content
        
        # tool 角色消息（原生格式）：保留首尾
        if role == "tool":
            head = content[:self.TOOL_SUMMARY_MAX]
            tail_len = self.TOOL_SUMMARY_MAX // 2
            tail = content[-tail_len:]
            omitted = len(content) - len(head) - tail_len
            return f"{head}\n\n... (省略 {omitted} 字符) ...\n\n{tail}"
        
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
    
    def _compress_reasoning_content(self, reasoning: Optional[str]) -> Optional[str]:
        """
        压缩历史轮次的 reasoning_content（思考模型 Token 膨胀的主要来源）

        策略：
        - None/空字符串 → 原样返回（普通模型无此字段）
        - 短推理（≤300字符）→ 保留原文（足够短，无需压缩）
        - 长推理 → 保留前 150 字符 + 省略标记

        重要：绝不返回空字符串。o1 系列 API 要求 reasoning_content
        非空时必须回传，返回空值可能导致 API 报错。

        Args:
            reasoning: 原始推理内容

        Returns:
            压缩后的推理内容，None 保持不变
        """
        if not reasoning:
            return reasoning  # None 或空字符串，不处理

        MAX_REASONING_LEN = 300
        if len(reasoning) <= MAX_REASONING_LEN:
            return reasoning  # 短推理保留完整

        # 长推理：保留头部 + 省略标记（API 仍能收到非空值）
        head = reasoning[:150]
        omitted = len(reasoning) - 150
        return f"{head}\n\n... [推理过程已压缩，省略 {omitted} 字符] ..."
    @staticmethod
    def _compress_tool_calls(tool_calls: list) -> list:
        """
        压缩历史轮次 assistant 消息的 tool_calls：保留工具名/id/关键参数，丢弃冗长参数

        保留的关键参数（帮助模型回溯操作，每条仅数十字节）：
        - file_path: Read/Write/Edit/Glob 的文件路径
        - pattern: Grep/Glob 的搜索模式
        - command: Bash 的命令（截断至 80 字符）
        """
        KEEP_KEYS = {"file_path", "pattern", "command"}
        import json as _json

        compressed = []
        for tc in tool_calls:
            if isinstance(tc, dict) and tc.get("type") == "function":
                name = tc.get("function", {}).get("name", "")
                args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = _json.loads(args_str)
                    keep = {k: v for k, v in args.items() if k in KEEP_KEYS}
                    # command 截断至 80 字符（通常只需知道是什么命令即可）
                    if "command" in keep and len(keep["command"]) > 80:
                        keep["command"] = keep["command"][:80] + "..."
                except Exception:
                    keep = {}
                compressed.append({
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": _json.dumps(keep, ensure_ascii=False),
                    },
                })
            else:
                compressed.append(tc)  # 非标准格式原样保留
        return compressed
    
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
    
    def generate_summary_messages(self) -> List[Dict[str, str]]:
        """
        生成用于摘要API调用的消息列表
        
        从中间轮次（锚定之后、窗口之前）提取需要摘要的内容，
        构造一条请求消息，让模型对中间轮次生成摘要。
        
        Returns:
            包含摘要请求的消息列表（用于发送给API）
            如果中间轮次为空或内容太少，返回空列表
        """
        if not self._messages:
            return []
        
        # 分离 system 和 chat
        chat_msgs = self._messages
        if self._messages[0].role == "system":
            chat_msgs = self._messages[1:]
        
        if len(chat_msgs) < 10:
            return []  # 消息太少，不需要摘要
        
        # 动态计算 skip_head/skip_tail（与 apply_summary 保持一致）
        skip_head = min(30, max(6, len(chat_msgs) // 10))
        skip_tail = min(15, max(4, len(chat_msgs) // 15))
        if len(chat_msgs) <= skip_head + skip_tail:
            return []
        
        middle = chat_msgs[skip_head:-skip_tail]
        
        # 提取中间轮次的对话内容（压缩过长的工具输出）
        middle_text_parts = []
        for msg in middle:
            if msg.role == "tool":
                # 工具结果：只保留前100字符摘要
                snippet = msg.content[:100] + ("..." if len(msg.content) > 100 else "")
                middle_text_parts.append(f"[工具结果] {snippet}")
            elif msg.role == "assistant":
                # 助手消息：只保留前200字符
                snippet = msg.content[:200] + ("..." if len(msg.content) > 200 else "")
                middle_text_parts.append(f"[助手] {snippet}")
            elif msg.role == "user" and not msg.content.startswith("[计划模式") and not msg.content.startswith("[计划提醒") and not msg.content.startswith("[系统提醒"):
                # 用户消息（排除计划提醒等系统消息）
                snippet = msg.content[:200] + ("..." if len(msg.content) > 200 else "")
                middle_text_parts.append(f"[用户] {snippet}")
        
        if not middle_text_parts:
            return []
        
        middle_text = "\n".join(middle_text_parts)
        if len(middle_text) < 200:
            return []  # 内容太少不值得摘要
        
        # 构建摘要请求
        summary_prompt = (
            "请用简洁的中文总结以下对话片段的关键信息（包括：完成了什么操作、遇到了什么问题、做了什么决策）。"
            "只输出摘要内容，不要输出其他解释。摘要控制在200字以内。\n\n"
            f"--- 对话片段 ---\n{middle_text}"
        )
        
        return [
            {"role": "user", "content": summary_prompt}
        ]
    
    @staticmethod
    def _extract_entities_from_messages(messages: list) -> str:
        """
        从消息列表中提取文件路径和代码位置实体，供摘要回溯使用
        
        从被摘要替换的中间消息中提取涉及文件路径和代码位置引用，
        让模型在需要细节时知道去哪查找，而非盲猜。
        
        Args:
            messages: 被摘要替换的中间消息列表
        
        Returns:
            回溯线索文本，无实体时返回空字符串
        """
        file_refs = set()
        # 匹配 Read/Edit/Write 工具输出中的文件路径（如 "File: xxx.py" 或 "Path: xxx.py"）
        _file_path_pattern = re.compile(
            r'(?:file_path|path|File|Path)["\s:=]+["\']?'
            r'([^\s"\'<>\n]+\.\w+)',  # 匹配 xxx.yyy 形式的文件路径
        )
        # 匹配代码位置引用（如 app.py:120-180 或 conversation.py:50）
        _location_pattern = re.compile(r'(\w[\w.-]+\.\w+:\d+(?:-\d+)?)')
        
        for msg in messages:
            content = msg.content or ""
            for m in _file_path_pattern.finditer(content):
                file_refs.add(m.group(1))
            for m in _location_pattern.finditer(content):
                file_refs.add(m.group(1))
        
        if not file_refs:
            return ""
        # 最多保留8个引用，控制 token
        refs_str = ", ".join(sorted(file_refs)[:8])
        return f"\n[回溯线索] 涉及: {refs_str} — 如需细节请 Read 对应文件"
    
    def apply_summary(self, summary_text: str) -> None:
        """
        将生成的摘要应用到中间轮次
        
        将锚定区域和窗口之间的中间消息替换为一条摘要消息，
        并附带回溯线索（文件路径/代码位置），让模型知道去哪找回细节。
        
        Args:
            summary_text: 模型生成的摘要文本
        """
        if not self._messages or not summary_text.strip():
            return
        
        chat_msgs = self._messages
        system_msg = None
        if self._messages[0].role == "system":
            system_msg = self._messages[0]
            chat_msgs = self._messages[1:]
        
        # 动态计算 skip_head/skip_tail（长对话保留更多头部上下文）
        skip_head = min(30, max(6, len(chat_msgs) // 10))
        skip_tail = min(15, max(4, len(chat_msgs) // 15))
        
        if len(chat_msgs) <= skip_head + skip_tail:
            return
        
        # 提取中间消息的回溯线索（文件路径/代码位置）
        middle = chat_msgs[skip_head:-skip_tail]
        trace_hint = self._extract_entities_from_messages(middle)
        
        # 重组：system + 前段 + 摘要 + 后段
        head = chat_msgs[:skip_head]
        tail = chat_msgs[-skip_tail:]
        
        summary_content = f"[对话摘要] 以下是对之前对话的摘要：{summary_text.strip()}{trace_hint}"
        
        summary_msg = Message(
            role="user",
            content=summary_content
        )
        
        self._messages = []
        if system_msg:
            self._messages.append(system_msg)
        self._messages.extend(head)
        self._messages.append(summary_msg)
        self._messages.extend(tail)

    # ============================================================
    # 操作摘要链
    # ============================================================

    def _build_operation_chain(self, middle_msgs: list) -> Optional[list]:
        """
        将中间轮次的工具操作压缩为轻量操作摘要链

        策略：扫描连续的 tool + assistant 消息组，提取每步操作的因果摘要：
        Read app.py → Edit app.py L42-45 → Bash pytest ✓ → Write test.py

        比逐条压缩更节省 token，且保留操作因果关系，避免长对话中信息衰减。

        Returns:
            压缩后的消息列表，消息太少不值得压缩时返回 None
        """
        if len(middle_msgs) < 6:
            return None  # 太少不值得

        # 提取操作链
        chain_items = []
        for msg in middle_msgs:
            if msg.role == "tool" and msg.content:
                # 从 tool 消息中提取操作摘要
                summary = self._extract_tool_summary(msg.content)
                if summary:
                    chain_items.append(summary)
            elif msg.role == "assistant" and msg.tool_calls:
                # 从 assistant 的 tool_calls 中提取操作名
                for tc in msg.tool_calls:
                    if hasattr(tc, 'function'):
                        name = tc.function.get('name', '')
                        args = tc.function.get('arguments', {})
                        if name:
                            arg_hint = self._extract_key_arg(name, args)
                            chain_items.append(f"{name}({arg_hint})" if arg_hint else name)

        if len(chain_items) < 3:
            return None  # 操作太少，不值得压缩为链

        # 生成摘要链消息
        chain_text = " → ".join(chain_items)
        chain_msg = Message(
            role="user",
            content=f"[操作摘要链] 之前执行的操作: {chain_text}"
        )

        # 保留用户消息（非计划模式提醒），丢弃 tool/assistant 消息
        result = []
        for msg in middle_msgs:
            if msg.role == "user":
                content = msg.content or ""
                # 丢弃计划模式提醒和系统提醒
                if content.startswith("[计划模式]") or content.startswith("[系统提醒]"):
                    continue
                result.append(msg)

        # 插入摘要链到最前面
        result.insert(0, chain_msg)
        return result

    def _extract_tool_summary(self, content: str) -> str:
        """从 tool 输出中提取简短操作摘要"""
        if not content:
            return ""

        # 取第一行有意义的内容
        for line in content.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            # 截断到 60 字符
            if len(stripped) > 60:
                return stripped[:57] + "..."
            return stripped
        return ""

    @staticmethod
    def _extract_key_arg(tool_name: str, args: dict) -> str:
        """从工具参数中提取关键参数值，用于摘要链"""
        if not args:
            return ""

        # 按工具类型提取最关键的参数
        key_map = {
            "Read": "file_path",
            "Write": "file_path",
            "Edit": "file_path",
            "Bash": "command",
            "Grep": "pattern",
            "Glob": "pattern",
            "TodoCreate": "",
            "TodoUpdate": "id",
            "ProjectContext": "query",
        }
        key = key_map.get(tool_name)
        if key and key in args:
            val = str(args[key])
            if len(val) > 40:
                val = val[:37] + "..."
            return val
        return ""
