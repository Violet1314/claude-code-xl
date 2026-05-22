"""TodoList 数据模型 - 计划模式的核心数据结构"""
from dataclasses import dataclass, field
from datetime import datetime
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
    notes: str = ""                   # 执行备注/完成说明
    evidence: str = ""                # 完成证据摘要
    files: List[str] = field(default_factory=list)        # 相关文件
    tests: List[str] = field(default_factory=list)        # 相关测试/验证命令
    error: str = ""                   # 最近失败原因
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    last_failure_tool: str = ""
    last_error_signature: str = ""
    retry_count: int = 0

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
        # 确保 depends_on/files/tests 是 list
        if self.depends_on is None:
            self.depends_on = []
        if self.files is None:
            self.files = []
        if self.tests is None:
            self.tests = []

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

        # 幂等更新：模型重复标记同一状态时视为成功 no-op，避免计划模式无意义失败
        if target.status == status:
            return True, ""

        # 同一时间最多 PLAN.MAX_IN_PROGRESS 个任务处于 in_progress（支持并行推进）
        if status == "in_progress":
            # 如果该任务当前已是 in_progress，不重复计数（允许重复标记）
            if target.status != "in_progress":
                active_count = self.in_progress_count
                if active_count >= PLAN.MAX_IN_PROGRESS:
                    active_items = [item for item in self.items if item.status == "in_progress"]
                    active_ids = ", ".join(item.id for item in active_items)
                    return False, (
                        f"已有 {active_count} 个任务正在进行中（上限 {PLAN.MAX_IN_PROGRESS}）：{active_ids}。"
                        f"请先结束某个进行中的任务后再开始新任务。"
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

        now = datetime.now().isoformat(timespec="seconds")
        if status == "in_progress" and not target.started_at:
            target.started_at = now
        if status in ("completed", "failed"):
            target.completed_at = now
        if status == "completed":
            target.error = ""
            target.last_failure_tool = ""
            target.last_error_signature = ""

        target.status = status
        return True, ""

    def apply_evidence(
        self,
        item_id: str,
        notes: str = "",
        evidence: str = "",
        files: List[str] = None,
        tests: List[str] = None,
        error: str = "",
    ) -> tuple[bool, str]:
        """为任务记录执行证据/备注。"""
        target = self.get_item(item_id)
        if target is None:
            return False, f"未找到任务: {item_id}"
        if notes:
            target.notes = notes.strip()
        if evidence:
            target.evidence = evidence.strip()
        if files is not None:
            target.files = [str(f) for f in files if str(f).strip()]
        if tests is not None:
            target.tests = [str(t) for t in tests if str(t).strip()]
        if error:
            target.error = error.strip()
        return True, ""

    def record_failure(self, item_id: str, tool_name: str, error: str, signature: str = "") -> tuple[bool, str]:
        """记录任务执行失败信息，供计划模式换策略/恢复使用。"""
        target = self.get_item(item_id)
        if target is None:
            return False, f"未找到任务: {item_id}"
        target.error = (error or "").strip()
        target.last_failure_tool = tool_name or ""
        target.last_error_signature = signature or tool_name or ""
        target.retry_count += 1
        return True, ""

    def record_current_failure(self, tool_name: str, error: str, signature: str = "") -> Optional[TodoItem]:
        """记录当前 in_progress 任务的失败；没有进行中任务时返回 None。"""
        item = self.get_in_progress_item()
        if not item:
            return None
        self.record_failure(item.id, tool_name, error, signature)
        return item

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

    @staticmethod
    def _format_prompt_item(item: TodoItem) -> str:
        dep_str = f" ← {', '.join(item.depends_on)}" if item.depends_on else ""
        detail_parts = []
        if item.evidence:
            detail_parts.append(f"证据:{item.evidence[:80]}")
        if item.files:
            detail_parts.append(f"文件:{', '.join(item.files[:3])}")
        if item.tests:
            detail_parts.append(f"测试:{', '.join(item.tests[:2])}")
        if item.error:
            retry = f" 重试:{item.retry_count}" if item.retry_count else ""
            tool = f" 工具:{item.last_failure_tool}" if item.last_failure_tool else ""
            detail_parts.append(f"错误:{item.error[:80]}{tool}{retry}")
        details = f"  {{{'; '.join(detail_parts)}}}" if detail_parts else ""
        return f"  {item.icon} {item.id}  {item.content}  [{item.status}]{dep_str}{details}"

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
            lines.append(self._format_prompt_item(item))
        return "\n".join(lines)

    def to_prompt_diff(self, previous_statuses: dict) -> str:
        """
        生成增量任务状态文本（仅包含状态变化的任务项）

        相比 to_prompt_text() 全量输出，此方法只返回状态发生变化的任务行，
        配合进度文本使用，大幅减少每轮重复注入的 token。

        Args:
            previous_statuses: 上一轮的任务状态快照 {id: status}

        Returns:
            增量格式文本，无变化时返回简洁状态行
        """
        if not self.items:
            return "（无任务）"

        changes = []
        for item in self.items:
            prev = previous_statuses.get(item.id)
            if prev != item.status:
                changes.append(self._format_prompt_item(item))

        if not changes:
            # 无变化：返回简洁状态行
            return (
                f"[计划模式] 进度:{self.progress_text}（无变化）\n"
                f"（任务状态未变，请继续推进当前任务）"
            )

        # 有变化：列出变化项 + 进度
        return f"[计划模式] 进度:{self.progress_text}\n" + "\n".join(changes)

    def get_status_snapshot(self) -> dict:
        """获取当前所有任务的状态快照 {id: status}，供增量对比使用"""
        return {
            item.id: (
                item.status,
                item.retry_count,
                item.error,
                item.evidence,
                tuple(item.files),
                tuple(item.tests),
            )
            for item in self.items
        }

    def clear(self) -> None:
        """清空所有任务"""
        self.items.clear()
