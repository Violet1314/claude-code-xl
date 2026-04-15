"""统计管理 - Token 使用量跟踪与持久化"""
import os
import json
import tempfile
import shutil
from typing import Dict, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

from claude_code.utils.tokens import estimate_tokens, estimate_messages_tokens

@dataclass
class SessionStats:
    """会话统计"""
    input_tokens: int = 0      # 最新一次 prompt_tokens（显示用，不累加）
    output_tokens: int = 0     # 最新一次 completion_tokens（显示用，不累加）
    cost: float = 0.0          # 累计费用（美元）

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> Dict[str, int]:
        return {
            "input": self.input_tokens,
            "output": self.output_tokens,
            "total": self.total_tokens,
            "cost": self.cost,
        }

class StatsManager:
    """统计管理器"""

    def __init__(self, stats_dir: str = "data/stats"):
        """
        初始化统计管理器

        Args:
            stats_dir: 统计数据存储目录
        """
        self.stats_dir = stats_dir
        self.stats_file = os.path.join(stats_dir, "total_stats.json")

        # 确保目录存在
        os.makedirs(stats_dir, exist_ok=True)

        # 当前会话统计
        self._session = SessionStats()
        self._last_saved = SessionStats()
    
    @property
    def session(self) -> SessionStats:
        """获取当前会话统计"""
        return self._session
    
    def update_input(self, messages: list) -> None:
        """
        更新输入 token 统计
        
        Args:
            messages: 消息列表
        """
        self._session.input_tokens = estimate_messages_tokens(messages)
    
    def update_output(self, text: str) -> None:
        """
        更新输出 token 统计（估算值，作为后备）

        Args:
            text: 输出文本
        """
        self._session.output_tokens += estimate_tokens(text)

    def set_real_usage(self, input_tokens: int, output_tokens: int) -> tuple:
        """
        更新 token 使用量，返回本次消耗用于费用计算

        Token 显示：最新一次的真实消耗（不累加）
        费用显示：累计总费用（每次费用累加）

        Args:
            input_tokens: 本次请求的 prompt_tokens
            output_tokens: 本次请求的 completion_tokens

        Returns:
            (input_tokens, output_tokens) 用于计算本次费用
        """
        # Token 只记录最新一次（显示用）
        if input_tokens > 0:
            self._session.input_tokens = input_tokens
        if output_tokens > 0:
            self._session.output_tokens = output_tokens

        # 返回本次消耗用于费用计算
        return input_tokens, output_tokens

    def add_cost(self, cost: float) -> None:
        """
        累加费用

        Args:
            cost: 本次请求费用（美元）
        """
        self._session.cost += cost

    def reset_session(self) -> None:
        """重置会话统计"""
        self._session = SessionStats()
        self._last_saved = SessionStats()
    
    def load_total(self) -> Dict:
        """
        加载总统计数据
        
        Returns:
            统计数据字典
        """
        default = {
            "total": {"input": 0, "output": 0, "total": 0},
            "sessions": [],
        }
        
        if not os.path.exists(self.stats_file):
            return default
        
        if os.path.getsize(self.stats_file) == 0:
            return default
        
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default
    
    def _atomic_write(self, data: Dict) -> bool:
        """
        原子写入统计文件
        
        Args:
            data: 要写入的数据
            
        Returns:
            是否成功
        """
        try:
            # 写入临时文件
            fd, tmp_path = tempfile.mkstemp(
                dir=self.stats_dir,
                suffix='.tmp',
            )
            
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # 原子替换
            shutil.move(tmp_path, self.stats_file)
            return True
            
        except Exception:
            # 清理临时文件
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            return False
    
    def save_session(
        self,
        model_id: str,
        message_count: int,
        finalize: bool = False,
    ) -> bool:
        """
        保存会话统计到总统计
        
        Args:
            model_id: 模型 ID
            message_count: 消息数量
            finalize: 是否结束会话
            
        Returns:
            是否成功
        """
        if message_count <= 0:
            return False
        
        data = self.load_total()
        
        # 创建或更新会话记录
        if not data["sessions"] or data["sessions"][-1].get("finalized", False):
            # 新建会话
            session_record = {
                "id": f"session_{len(data['sessions']) + 1:03d}",
                "model": model_id,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "messages": 0,
                "tokens": {"input": 0, "output": 0, "total": 0},
                "finalized": False,
            }
            data["sessions"].append(session_record)
            self._last_saved = SessionStats()
        
        # 更新最后一个会话
        last_session = data["sessions"][-1]
        last_session["messages"] = message_count
        last_session["tokens"] = self._session.to_dict()
        last_session["finalized"] = finalize
        
        # 计算增量（确保非负）
        input_diff = max(0, self._session.input_tokens - self._last_saved.input_tokens)
        output_diff = max(0, self._session.output_tokens - self._last_saved.output_tokens)
        
        # 更新总计
        data["total"]["input"] += input_diff
        data["total"]["output"] += output_diff
        data["total"]["total"] = data["total"]["input"] + data["total"]["output"]
        
        # 记录已保存值
        self._last_saved = SessionStats(
            input_tokens=self._session.input_tokens,
            output_tokens=self._session.output_tokens,
        )
        
        return self._atomic_write(data)
    
    def get_total_stats(self) -> Dict[str, int]:
        """
        获取总统计
        
        Returns:
            总统计字典
        """
        data = self.load_total()
        return data.get("total", {"input": 0, "output": 0, "total": 0})