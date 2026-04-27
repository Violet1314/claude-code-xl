"""TodoList 数据模型 - 计划模式的核心数据结构"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from claude_code.config.defaults import PLAN


@dataclass
class TodoItem:
    """单个任务项"""
    id: str                          # 唯一ID，如 "t1"
    content: str                     # 任务描述
    status: str = "pending"          # pending | in_progress | completed | failed
    priority: str = "medium"         # high | medium | low

    # 合法状态值
    VALID_STATUSES = ("pending", "in_progress", "completed", "failed")
    VALID_PRIORITIES = ("high", "medium", "low")

    # 合法状态转换规则（状态机）
    # pending → in_progress ✓ 开始任务
    # in_progress → completed ✓ 完成任务
    # in_progress → failed ✓ 任务失败
    # 其他转换 ✗ 禁止
    VALID_TRANSITIONS = {
        "pending": ("in_progress",),           # pending 只能转到 in_progress
        "in_progress": ("completed", "failed"), # in_progress 可以完成或失败
        "completed": (),                        # 已完成不可变更
        "failed": (),                           # 已失败不可变更
    }

    def __post_init__(self):
        """校验参数"""
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"无效状态: {self.status}，合法值: {self.VALID_STATUSES}")
        if self.priority not in self.VALID_PRIORITIES:
            raise ValueError(f"无效优先级: {self.priority}，合法值: {self.VALID_PRIORITIES}")

    @property
    def is_done(self) -> bool:
        """是否已结束（完成或失败）"""
        return self.status in ("completed", "failed")

    @property
    def icon(self) -> str:
        """状态图标"""
        icons = {
            "pending": "○",
            "in_progress": "●",
            "completed": "✓",
            "failed": "✗",
        }
        return icons.get(self.status, "⏳")


@dataclass
class TodoList:
    """任务清单 - 计划模式的核心数据结构"""
    items: List[TodoItem] = field(default_factory=list)

    # ============================================================
    # 增删改
    # ============================================================

    def add_item(self, content: str, priority: str = "medium") -> Optional[TodoItem]:
        """
        添加任务项

        Args:
            content: 任务描述
            priority: 优先级

        Returns:
            新建的 TodoItem，超出限制或内容为空时返回 None
        """
        # 校验：空内容
        if not content or not content.strip():
            return None

        # 校验：超出最大数量
        if len(self.items) >= PLAN.MAX_ITEMS:
            return None

        # 生成 ID
        next_num = len(self.items) + 1
        item_id = f"t{next_num}"

        item = TodoItem(id=item_id, content=content.strip(), priority=priority)
        self.items.append(item)
        return item

    def update_status(self, item_id: str, status: str) -> tuple[bool, str]:
        """
        更新任务状态（带状态机验证）

        Args:
            item_id: 任务ID
            status: 新状态

        Returns:
            (成功与否, 错误信息) 元组
            成功返回 (True, "")，失败返回 (False, "错误原因")
        """
        if status not in TodoItem.VALID_STATUSES:
            return False, f"无效状态: {status}，合法值: {TodoItem.VALID_STATUSES}"

        for item in self.items:
            if item.id == item_id:
                # 状态机验证：检查转换是否合法
                if status not in TodoItem.VALID_TRANSITIONS.get(item.status, ()):
                    if item.status == "completed":
                        return False, f"任务 {item_id} 已完成，不可变更状态"
                    elif item.status == "failed":
                        return False, f"任务 {item_id} 已失败，不可变更状态"
                    elif item.status == "pending" and status in ("completed", "failed"):
                        return False, f"任务 {item_id} 尚未开始（pending），请先调用 TodoUpdate(id, 'in_progress') 标记为进行中，完成实际工作后再标记为 {status}"
                    else:
                        return False, f"任务 {item_id} 不允许从 [{item.status}] 转换到 [{status}]"

                item.status = status
                return True, ""
        return False, f"未找到任务: {item_id}"

    def get_item(self, item_id: str) -> Optional[TodoItem]:
        """根据 ID 获取任务项"""
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def get_next_pending(self) -> Optional[TodoItem]:
        """获取下一个待执行的任务"""
        for item in self.items:
            if item.status == "pending":
                return item
        return None

    # ============================================================
    # 批量创建
    # ============================================================

    @classmethod
    def create_from_dicts(
        cls,
        items_data: List[Dict[str, str]],
        max_items: int = None,
    ) -> "TodoList":
        """
        从字典列表批量创建 TodoList

        Args:
            items_data: 字典列表，每个字典包含 content 和可选的 priority
            max_items: 最大任务数，默认使用配置值

        Returns:
            新的 TodoList 实例
        """
        todo = cls()
        limit = max_items or PLAN.MAX_ITEMS

        for data in items_data:
            if len(todo.items) >= limit:
                break
            content = data.get("content", "").strip()
            if not content:
                continue  # 跳过空内容
            priority = data.get("priority", "medium")
            todo.add_item(content=content, priority=priority)

        return todo

    # ============================================================
    # 统计属性
    # ============================================================

    @property
    def pending_count(self) -> int:
        """待执行数量"""
        return sum(1 for item in self.items if item.status == "pending")

    @property
    def in_progress_count(self) -> int:
        """进行中数量"""
        return sum(1 for item in self.items if item.status == "in_progress")

    @property
    def completed_count(self) -> int:
        """已完成数量"""
        return sum(1 for item in self.items if item.status == "completed")

    @property
    def failed_count(self) -> int:
        """失败数量"""
        return sum(1 for item in self.items if item.status == "failed")

    @property
    def done_count(self) -> int:
        """已结束数量（完成+失败）"""
        return sum(1 for item in self.items if item.is_done)

    @property
    def total_count(self) -> int:
        """总数量"""
        return len(self.items)

    @property
    def is_all_done(self) -> bool:
        """是否全部结束"""
        return len(self.items) > 0 and all(item.is_done for item in self.items)

    @property
    def progress_text(self) -> str:
        """进度文本，如 '3/7'"""
        return f"{self.done_count}/{self.total_count}"

    # ============================================================
    # 文本输出
    # ============================================================

    def to_prompt_text(self) -> str:
        """
        生成注入给模型的文本

        Returns:
            格式化的任务清单文本
        """
        if not self.items:
            return "（无任务）"

        lines = []
        for item in self.items:
            lines.append(f"  {item.icon} {item.id}  {item.content}  [{item.status}]")
        return "\n".join(lines)

    def clear(self) -> None:
        """清空所有任务"""
        self.items.clear()
