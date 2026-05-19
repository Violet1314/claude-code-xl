"""TodoList 数据模型 - 计划模式的核心数据结构"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple

from claude_code.config.defaults import PLAN


@dataclass
class TodoItem:
    """单个任务项"""
    id: str                          # 唯一ID，如 "t1"
    content: str                     # 任务描述
    status: str = "pending"          # pending | in_progress | completed | failed
    priority: str = "medium"         # high | medium | low
    depends_on: List[str] = field(default_factory=list)  # 依赖的任务ID列表，如 ["t1", "t2"]

    # 合法状态值
    VALID_STATUSES = ("pending", "in_progress", "completed", "failed")
    VALID_PRIORITIES = ("high", "medium", "low")

    # 合法状态转换规则（状态机）
    # pending → in_progress ✓ 开始任务
    # in_progress → completed ✓ 完成任务
    # in_progress → failed ✓ 任务失败
    # in_progress → pending ✓ 任务暂停（暂无法推进，释放进行中名额）
    # 其他转换 ✗ 禁止
    VALID_TRANSITIONS = {
        "pending": ("in_progress",),                          # pending 只能转到 in_progress
        "in_progress": ("completed", "failed", "pending"),    # in_progress 可以完成、失败或暂停
        "completed": (),                                      # 已完成不可变更
        "failed": (),                                         # 已失败不可变更
    }

    def __post_init__(self):
        """校验参数"""
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"无效状态: {self.status}，合法值: {self.VALID_STATUSES}")
        if self.priority not in self.VALID_PRIORITIES:
            raise ValueError(f"无效优先级: {self.priority}，合法值: {self.VALID_PRIORITIES}")
        # 确保 depends_on 是 list
        if self.depends_on is None:
            self.depends_on = []

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

    def add_item(self, content: str, priority: str = "medium", depends_on: List[str] = None) -> Optional[TodoItem]:
        """
        添加任务项

        Args:
            content: 任务描述
            priority: 优先级
            depends_on: 依赖的任务ID列表

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

        # 校验依赖：引用的 ID 必须在当前列表中已存在
        deps = depends_on or []
        if deps:
            valid_ids = {item.id for item in self.items}
            deps = [d for d in deps if d in valid_ids]  # 忽略无效依赖

        item = TodoItem(id=item_id, content=content.strip(), priority=priority, depends_on=deps)
        self.items.append(item)
        return item

    def check_dependencies(self, item_id: str) -> Tuple[bool, str]:
        """
        检查任务的前置依赖是否已全部完成

        Args:
            item_id: 任务ID

        Returns:
            (依赖满足与否, 未完成的依赖任务列表描述)
        """
        target = self.get_item(item_id)
        if target is None or not target.depends_on:
            return True, ""

        incomplete_deps = []
        for dep_id in target.depends_on:
            dep_item = self.get_item(dep_id)
            if dep_item is None:
                continue  # 不存在的依赖忽略
            if not dep_item.is_done:
                incomplete_deps.append(dep_item)

        if incomplete_deps:
            dep_str = ", ".join(f"{d.id}({d.status})" for d in incomplete_deps)
            return False, (
                f"任务 {item_id} 的前置依赖未完成：{dep_str}。"
                f"请先完成依赖任务再开始此任务。"
            )
        return True, ""

    def update_status(self, item_id: str, status: str) -> tuple[bool, str]:
        """
        更新任务状态（带状态机验证 + 依赖检查）

        Args:
            item_id: 任务ID
            status: 新状态

        Returns:
            (成功与否, 错误信息) 元组
            成功返回 (True, "")，失败返回 (False, "错误原因")
        """
        if status not in TodoItem.VALID_STATUSES:
            return False, f"无效状态: {status}，合法值: {TodoItem.VALID_STATUSES}"

        target = self.get_item(item_id)
        if target is None:
            return False, f"未找到任务: {item_id}"

        # 同一时间只允许一个任务处于 in_progress，避免计划模式并行漂移。
        if status == "in_progress":
            active = self.get_in_progress_item()
            if active is not None and active.id != item_id:
                return False, (
                    f"已有任务 {active.id} 正在进行中，请先结束当前任务："
                    f"TodoUpdate(id=\"{active.id}\", status=\"completed\") 或 "
                    f"TodoUpdate(id=\"{active.id}\", status=\"failed\") 或 "
                    f"TodoUpdate(id=\"{active.id}\", status=\"pending\") 暂停后换任务"
                )

            # 依赖检查：开始任务前，前置依赖必须全部完成
            deps_ok, deps_msg = self.check_dependencies(item_id)
            if not deps_ok:
                return False, deps_msg

        # 状态机验证：检查转换是否合法
        if status not in TodoItem.VALID_TRANSITIONS.get(target.status, ()):
            if target.status == "completed":
                return False, f"任务 {item_id} 已完成，不可变更状态"
            elif target.status == "failed":
                return False, f"任务 {item_id} 已失败，不可变更状态"
            elif target.status == "pending" and status in ("completed", "failed"):
                return False, (
                    f"任务 {item_id} 尚未开始（pending），不能直接标记为 {status}。"
                    f"下一步：请先调用 TodoUpdate(id=\"{item_id}\", status=\"in_progress\")，"
                    f"完成实际工作后再标记为 {status}"
                )
            else:
                return False, f"任务 {item_id} 不允许从 [{target.status}] 转换到 [{status}]"

        target.status = status
        return True, ""

    def get_item(self, item_id: str) -> Optional[TodoItem]:
        """根据 ID 获取任务项"""
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def get_in_progress_item(self) -> Optional[TodoItem]:
        """获取当前进行中的任务（计划模式约束：最多一个）"""
        for item in self.items:
            if item.status == "in_progress":
                return item
        return None
    def get_next_pending(self) -> Optional[TodoItem]:
        """获取下一个待执行的任务（优先返回无依赖或依赖已满足的）"""
        for item in self.items:
            if item.status == "pending":
                deps_ok, _ = self.check_dependencies(item.id)
                if deps_ok:
                    return item
        # 没有依赖满足的，返回第一个 pending（兼容旧行为）
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
            items_data: 字典列表，每个字典包含 content 和可选的 priority、depends_on
            max_items: 最大任务数，默认使用配置值

        Returns:
            新的 TodoList 实例
        """
        todo = cls()
        limit = max_items or PLAN.MAX_ITEMS

        # 先收集所有合法 ID（按顺序 t1, t2, ...）
        valid_ids = set()
        for i, data in enumerate(items_data[:limit]):
            content = data.get("content", "").strip()
            if content:
                valid_ids.add(f"t{i + 1}")

        for data in items_data:
            if len(todo.items) >= limit:
                break
            content = data.get("content", "").strip()
            if not content:
                continue  # 跳过空内容
            priority = data.get("priority", "medium")
            depends_on = data.get("depends_on", [])
            # 过滤无效依赖ID（引用不存在的任务）
            if depends_on:
                depends_on = [d for d in depends_on if d in valid_ids]
            todo.add_item(content=content, priority=priority, depends_on=depends_on)

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
            dep_str = f" ← {', '.join(item.depends_on)}" if item.depends_on else ""
            lines.append(f"  {item.icon} {item.id}  {item.content}  [{item.status}]{dep_str}")
        return "\n".join(lines)

    def clear(self) -> None:
        """清空所有任务"""
        self.items.clear()
