"""TodoList 数据模型测试"""
import pytest
import sys
import os

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from claude_code.core.todo import TodoItem, TodoList
from claude_code.config.defaults import PLAN


class TestTodoItem:
    """TodoItem 数据类测试"""

    def test_create_default(self):
        """测试默认创建"""
        item = TodoItem(id="t1", content="测试任务")
        assert item.id == "t1"
        assert item.content == "测试任务"
        assert item.status == "pending"
        assert item.priority == "medium"

    def test_create_with_all_fields(self):
        """测试完整参数创建"""
        item = TodoItem(id="t2", content="高优任务", status="in_progress", priority="high")
        assert item.status == "in_progress"
        assert item.priority == "high"

    def test_invalid_status(self):
        """测试无效状态抛异常"""
        with pytest.raises(ValueError, match="无效状态"):
            TodoItem(id="t1", content="test", status="running")

    def test_invalid_priority(self):
        """测试无效优先级抛异常"""
        with pytest.raises(ValueError, match="无效优先级"):
            TodoItem(id="t1", content="test", priority="urgent")

    def test_is_done_pending(self):
        """pending 状态不是完成"""
        item = TodoItem(id="t1", content="test")
        assert item.is_done is False

    def test_is_done_in_progress(self):
        """in_progress 状态不是完成"""
        item = TodoItem(id="t1", content="test", status="in_progress")
        assert item.is_done is False

    def test_is_done_completed(self):
        """completed 状态是完成"""
        item = TodoItem(id="t1", content="test", status="completed")
        assert item.is_done is True

    def test_is_done_failed(self):
        """failed 状态也是结束"""
        item = TodoItem(id="t1", content="test", status="failed")
        assert item.is_done is True

    def test_icons(self):
        """测试各状态图标"""
        assert TodoItem(id="t1", content="", status="pending").icon == "○"
        assert TodoItem(id="t1", content="", status="in_progress").icon == "●"
        assert TodoItem(id="t1", content="", status="completed").icon == "✓"
        assert TodoItem(id="t1", content="", status="failed").icon == "✗"


class TestTodoList:
    """TodoList 测试"""

    def _make_list(self, count=3):
        """创建测试用 TodoList"""
        items = [
            TodoItem(id=f"t{i+1}", content=f"任务{i+1}", priority="medium")
            for i in range(count)
        ]
        return TodoList(items=items)

    def test_create_empty(self):
        """测试创建空列表"""
        todo = TodoList()
        assert todo.total_count == 0
        assert todo.items == []

    def test_create_with_items(self):
        """测试创建带任务的列表"""
        todo = self._make_list(3)
        assert todo.total_count == 3

    def test_add_item(self):
        """测试添加任务"""
        todo = TodoList()
        item = todo.add_item("新增任务", priority="high")
        assert todo.total_count == 1
        assert item.id == "t1"
        assert item.content == "新增任务"
        assert item.priority == "high"
        assert item.status == "pending"

    def test_add_item_auto_increment_id(self):
        """测试自动递增 ID"""
        todo = self._make_list(3)
        item = todo.add_item("第四个任务")
        assert item.id == "t4"

    def test_add_item_respects_max_items(self):
        """测试最大任务数限制"""
        todo = self._make_list(PLAN.MAX_ITEMS)
        result = todo.add_item("超出任务")
        assert result is None  # 超出限制返回 None
        assert todo.total_count == PLAN.MAX_ITEMS

    def test_add_item_empty_content(self):
        """测试空内容返回 None"""
        todo = TodoList()
        result = todo.add_item("")
        assert result is None
        result = todo.add_item("   ")
        assert result is None

    def test_update_status(self):
        """测试更新任务状态（合法转换: pending → in_progress）"""
        todo = self._make_list(3)
        result, error = todo.update_status("t2", "in_progress")
        assert result is True
        assert error == ""
        assert todo.get_item("t2").status == "in_progress"

    def test_update_status_not_found(self):
        """测试更新不存在的任务"""
        todo = self._make_list(3)
        result, error = todo.update_status("t99", "in_progress")
        assert result is False
        assert "未找到任务" in error

    def test_update_status_invalid(self):
        """测试更新为无效状态"""
        todo = self._make_list(3)
        result, error = todo.update_status("t1", "running")
        assert result is False
        assert "无效状态" in error

    def test_update_status_invalid_transition(self):
        """测试非法状态转换"""
        todo = self._make_list(3)
        # pending → completed 被禁止
        result, error = todo.update_status("t1", "completed")
        assert result is False
        assert "尚未开始" in error or "pending" in error

        # pending → failed 被禁止
        result, error = todo.update_status("t2", "failed")
        assert result is False

        # 正确流程: pending → in_progress → completed
        result, error = todo.update_status("t1", "in_progress")
        assert result is True
        result, error = todo.update_status("t1", "completed")
        assert result is True

        # 已完成不可变更
        result, error = todo.update_status("t1", "in_progress")
        assert result is False
        assert "已完成" in error

    def test_get_item(self):
        """测试按 ID 获取任务"""
        todo = self._make_list(3)
        item = todo.get_item("t2")
        assert item is not None
        assert item.content == "任务2"
    def test_get_item_not_found(self):
        """测试获取不存在的任务"""
        todo = self._make_list(3)
        item = todo.get_item("t99")
        assert item is None

    def test_get_next_pending(self):
        """测试获取下一个待执行任务"""
        todo = self._make_list(3)
        next_item = todo.get_next_pending()
        assert next_item is not None
        assert next_item.id == "t1"

    def test_get_next_pending_skip_done(self):
        """测试跳过已完成的任务"""
        todo = self._make_list(3)
        todo.update_status("t1", "in_progress")
        todo.update_status("t1", "completed")
        next_item = todo.get_next_pending()
        assert next_item.id == "t2"

    def test_get_next_pending_all_done(self):
        """测试全部完成时返回 None"""
        todo = self._make_list(2)
        todo.update_status("t1", "in_progress")
        todo.update_status("t1", "completed")
        todo.update_status("t2", "in_progress")
        todo.update_status("t2", "completed")
        assert todo.get_next_pending() is None

    def test_get_next_pending_skip_in_progress(self):
        """测试跳过 in_progress 的任务"""
        todo = self._make_list(3)
        todo.update_status("t1", "in_progress")
        next_item = todo.get_next_pending()
        assert next_item.id == "t2"

    def test_counts(self):
        """测试各种计数"""
        todo = self._make_list(4)
        todo.update_status("t1", "in_progress")
        todo.update_status("t1", "completed")
        todo.update_status("t2", "in_progress")
        todo.update_status("t2", "failed")
        todo.update_status("t3", "in_progress")
        # t1=completed, t2=failed, t3=in_progress, t4=pending
        assert todo.completed_count == 1
        assert todo.failed_count == 1
        assert todo.pending_count == 1
        assert todo.in_progress_count == 1
        assert todo.done_count == 2  # completed + failed
        assert todo.total_count == 4

    def test_is_all_done(self):
        """测试全部完成判定"""
        todo = self._make_list(2)
        assert todo.is_all_done is False
        todo.update_status("t1", "in_progress")
        todo.update_status("t1", "completed")
        assert todo.is_all_done is False
        todo.update_status("t2", "in_progress")
        todo.update_status("t2", "failed")
        assert todo.is_all_done is True  # failed 也算结束

    def test_is_all_done_empty(self):
        """空列表不是全部完成"""
        todo = TodoList()
        assert todo.is_all_done is False

    def test_progress_text(self):
        """测试进度文本"""
        todo = self._make_list(3)
        assert todo.progress_text == "0/3"
        todo.update_status("t1", "in_progress")
        todo.update_status("t1", "completed")
        assert todo.progress_text == "1/3"

    def test_to_prompt_text_empty(self):
        """空列表的提示文本"""
        todo = TodoList()
        assert todo.to_prompt_text() == "（无任务）"

    def test_to_prompt_text_with_items(self):
        """有任务的提示文本"""
        todo = self._make_list(2)
        text = todo.to_prompt_text()
        assert "t1" in text
        assert "t2" in text
        assert "任务1" in text
        assert "任务2" in text

    def test_clear(self):
        """测试清空"""
        todo = self._make_list(3)
        todo.clear()
        assert todo.total_count == 0
        assert todo.items == []

    def test_create_from_dicts(self):
        """测试从字典列表创建"""
        items_data = [
            {"content": "任务A", "priority": "high"},
            {"content": "任务B", "priority": "low"},
        ]
        todo = TodoList.create_from_dicts(items_data)
        assert todo.total_count == 2
        assert todo.items[0].id == "t1"
        assert todo.items[0].priority == "high"
        assert todo.items[1].id == "t2"
        assert todo.items[1].priority == "low"

    def test_create_from_dicts_respects_max(self):
        """测试从字典创建时也受最大数限制"""
        items_data = [{"content": f"任务{i}"} for i in range(PLAN.MAX_ITEMS + 5)]
        todo = TodoList.create_from_dicts(items_data)
        assert todo.total_count == PLAN.MAX_ITEMS

    def test_create_from_dicts_empty_content_skipped(self):
        """测试空内容被跳过"""
        items_data = [
            {"content": "有效任务"},
            {"content": ""},
            {"content": "   "},
            {"content": "另一个有效任务"},
        ]
        todo = TodoList.create_from_dicts(items_data)
        assert todo.total_count == 2


class TestTodoCreateTool:
    """TodoCreate 工具测试"""

    def setup_method(self):
        """每个测试前重置全局 TodoList"""
        from claude_code.tools.builtins.todo import reset_todo_list
        reset_todo_list()

    def test_create_plan(self):
        """测试创建计划"""
        from claude_code.tools.builtins.todo import TodoCreateTool
        tool = TodoCreateTool()
        result = tool.execute({
            "items": [
                {"content": "分析代码", "priority": "high"},
                {"content": "编写测试", "priority": "medium"},
            ]
        })
        assert result.success is True
        assert "2" in result.output
        assert "分析代码" in result.output

    def test_create_empty_items(self):
        """测试空任务列表"""
        from claude_code.tools.builtins.todo import TodoCreateTool
        tool = TodoCreateTool()
        result = tool.execute({"items": []})
        assert result.success is False

    def test_create_overwrites_existing(self):
        """测试创建新计划会覆盖旧计划"""
        from claude_code.tools.builtins.todo import TodoCreateTool, get_todo_list
        tool = TodoCreateTool()
        # 第一次创建
        tool.execute({"items": [{"content": "旧任务"}]})
        # 第二次创建
        tool.execute({"items": [{"content": "新任务1"}, {"content": "新任务2"}]})
        todo = get_todo_list()
        assert todo.total_count == 2
        assert todo.items[0].content == "新任务1"

    def test_is_read_only(self):
        """测试不是只读"""
        from claude_code.tools.builtins.todo import TodoCreateTool
        tool = TodoCreateTool()
        assert tool.is_read_only() is False


class TestTodoUpdateTool:
    """TodoUpdate 工具测试"""

    def setup_method(self):
        from claude_code.tools.builtins.todo import reset_todo_list, TodoCreateTool
        reset_todo_list()
        # 预创建一个计划
        tool = TodoCreateTool()
        tool.execute({
            "items": [
                {"content": "任务1"},
                {"content": "任务2"},
            ]
        })

    def test_update_to_in_progress(self):
        """测试更新为进行中"""
        from claude_code.tools.builtins.todo import TodoUpdateTool, get_todo_list
        tool = TodoUpdateTool()
        result = tool.execute({"id": "t1", "status": "in_progress"})
        assert result.success is True
        todo = get_todo_list()
        assert todo.items[0].status == "in_progress"

    def test_update_to_completed(self):
        """测试更新为完成（需要先 in_progress）"""
        from claude_code.tools.builtins.todo import TodoUpdateTool, get_todo_list
        tool = TodoUpdateTool()
        # 直接 pending → completed 会被拒绝
        result = tool.execute({"id": "t1", "status": "completed"})
        assert result.success is False

        # 正确流程：pending → in_progress → completed
        result = tool.execute({"id": "t1", "status": "in_progress"})
        assert result.success is True
        result = tool.execute({"id": "t1", "status": "completed"})
        assert result.success is True
        todo = get_todo_list()
        assert todo.items[0].status == "completed"

    def test_update_not_found(self):
        """测试更新不存在的任务"""
        from claude_code.tools.builtins.todo import TodoUpdateTool
        tool = TodoUpdateTool()
        result = tool.execute({"id": "t99", "status": "in_progress"})
        assert result.success is False

    def test_update_invalid_status(self):
        """测试更新为无效状态"""
        from claude_code.tools.builtins.todo import TodoUpdateTool
        tool = TodoUpdateTool()
        result = tool.execute({"id": "t1", "status": "running"})
        assert result.success is False

    def test_is_read_only(self):
        """测试不是只读"""
        from claude_code.tools.builtins.todo import TodoUpdateTool
        tool = TodoUpdateTool()
        assert tool.is_read_only() is False


class TestTodoListTool:
    """TodoList 工具测试"""

    def setup_method(self):
        from claude_code.tools.builtins.todo import reset_todo_list
        reset_todo_list()

    def test_list_empty(self):
        """测试空计划"""
        from claude_code.tools.builtins.todo import TodoListTool
        tool = TodoListTool()
        result = tool.execute({})
        assert result.success is True
        assert "没有" in result.output or "无" in result.output

    def test_list_with_items(self):
        """测试有任务的计划"""
        from claude_code.tools.builtins.todo import TodoListTool, TodoCreateTool
        # 先创建
        create_tool = TodoCreateTool()
        create_tool.execute({
            "items": [
                {"content": "任务A"},
                {"content": "任务B"},
            ]
        })
        # 再查看
        list_tool = TodoListTool()
        result = list_tool.execute({})
        assert result.success is True
        assert "任务A" in result.output
        assert "任务B" in result.output
        assert "2/2" in result.output or "0/2" in result.output

    def test_is_read_only(self):
        """测试是只读"""
        from claude_code.tools.builtins.todo import TodoListTool
        tool = TodoListTool()
        assert tool.is_read_only() is True


class TestTodoIntegration:
    """Todo 工具集成测试 - 端到端流程"""

    def setup_method(self):
        from claude_code.tools.builtins.todo import reset_todo_list
        reset_todo_list()

    def test_full_workflow(self):
        """测试完整流程：创建 → 更新 → 查看 → 完成"""
        from claude_code.tools.builtins.todo import (
            TodoCreateTool, TodoUpdateTool, TodoListTool, get_todo_list
        )

        # 1. 创建计划
        create_tool = TodoCreateTool()
        result = create_tool.execute({
            "items": [
                {"content": "分析代码", "priority": "high"},
                {"content": "编写测试", "priority": "medium"},
                {"content": "提交代码", "priority": "low"},
            ]
        })
        assert result.success is True

        # 2. 开始第一个任务
        update_tool = TodoUpdateTool()
        result = update_tool.execute({"id": "t1", "status": "in_progress"})
        assert result.success is True

        # 3. 完成第一个任务
        result = update_tool.execute({"id": "t1", "status": "completed"})
        assert result.success is True

        # 4. 开始并完成第二个任务
        update_tool.execute({"id": "t2", "status": "in_progress"})
        update_tool.execute({"id": "t2", "status": "completed"})

        # 5. 第三个任务失败
        update_tool.execute({"id": "t3", "status": "in_progress"})
        update_tool.execute({"id": "t3", "status": "failed"})

        # 6. 查看最终状态
        list_tool = TodoListTool()
        result = list_tool.execute({})
        assert result.success is True
        assert "3/3" in result.output  # 全部结束

        # 7. 验证 TodoList 状态
        todo = get_todo_list()
        assert todo.is_all_done is True
        assert todo.completed_count == 2
        assert todo.failed_count == 1

    def test_create_overwrites_previous(self):
        """测试新计划覆盖旧计划"""
        from claude_code.tools.builtins.todo import (
            TodoCreateTool, TodoUpdateTool, get_todo_list
        )

        create_tool = TodoCreateTool()
        update_tool = TodoUpdateTool()

        # 第一轮
        create_tool.execute({"items": [{"content": "旧任务1"}, {"content": "旧任务2"}]})
        update_tool.execute({"id": "t1", "status": "in_progress"})
        update_tool.execute({"id": "t1", "status": "completed"})

        # 第二轮（覆盖）
        create_tool.execute({"items": [{"content": "新任务1"}]})
        todo = get_todo_list()
        assert todo.total_count == 1
        assert todo.items[0].content == "新任务1"
        assert todo.items[0].status == "pending"  # 新任务默认 pending

    def test_status_transitions(self):
        """测试状态转换：pending → in_progress → completed/failed"""
        from claude_code.tools.builtins.todo import (
            TodoCreateTool, TodoUpdateTool, get_todo_list
        )

        create_tool = TodoCreateTool()
        update_tool = TodoUpdateTool()

        create_tool.execute({"items": [{"content": "任务"}]})

        # pending → in_progress
        result = update_tool.execute({"id": "t1", "status": "in_progress"})
        assert result.success is True
        todo = get_todo_list()
        assert todo.items[0].status == "in_progress"

        # in_progress → completed
        result = update_tool.execute({"id": "t1", "status": "completed"})
        assert result.success is True
        assert todo.items[0].status == "completed"
        assert todo.items[0].is_done is True

    def test_empty_plan_list(self):
        """测试空计划的查看"""
        from claude_code.tools.builtins.todo import TodoListTool

        list_tool = TodoListTool()
        result = list_tool.execute({})
        assert result.success is True
        assert "没有" in result.output or "无" in result.output

    def test_todo_list_prompt_text(self):
        """测试 to_prompt_text 输出格式"""
        from claude_code.tools.builtins.todo import (
            TodoCreateTool, TodoUpdateTool, get_todo_list
        )

        create_tool = TodoCreateTool()
        update_tool = TodoUpdateTool()

        create_tool.execute({"items": [
            {"content": "已完成任务"},
            {"content": "进行中任务"},
            {"content": "待处理任务"},
        ]})
        update_tool.execute({"id": "t1", "status": "in_progress"})
        update_tool.execute({"id": "t1", "status": "completed"})
        update_tool.execute({"id": "t2", "status": "in_progress"})

        todo = get_todo_list()
        text = todo.to_prompt_text()
        assert "✓" in text
        assert "●" in text
        assert "○" in text

    def test_reset_clears_everything(self):
        """测试重置清空所有状态"""
        from claude_code.tools.builtins.todo import (
            TodoCreateTool, reset_todo_list, get_todo_list
        )

        create_tool = TodoCreateTool()
        create_tool.execute({"items": [{"content": "任务1"}, {"content": "任务2"}]})

        todo = get_todo_list()
        assert todo.total_count == 2

        reset_todo_list()
        todo = get_todo_list()
        assert todo.total_count == 0
        assert todo.items == []



class TestTodoImprovements:
    """计划模式增强行为测试"""

    def setup_method(self):
        from claude_code.tools.builtins.todo import reset_todo_list
        reset_todo_list()

    def test_only_one_in_progress_allowed(self):
        """同一时间只允许一个任务处于 in_progress"""
        todo = TodoList.create_from_dicts([
            {"content": "任务1"},
            {"content": "任务2"},
        ])

        result, error = todo.update_status("t1", "in_progress")
        assert result is True
        assert error == ""

        result, error = todo.update_status("t2", "in_progress")
        assert result is False
        assert "已有任务 t1 正在进行中" in error
        assert "TodoUpdate" in error
        assert todo.get_item("t2").status == "pending"

    def test_get_in_progress_item(self):
        """可获取当前进行中任务"""
        todo = TodoList.create_from_dicts([
            {"content": "任务1"},
            {"content": "任务2"},
        ])
        assert todo.get_in_progress_item() is None

        todo.update_status("t2", "in_progress")
        active = todo.get_in_progress_item()
        assert active is not None
        assert active.id == "t2"

    def test_create_tool_reports_skipped_items(self):
        """TodoCreate 对超上限/空内容忽略项给出明确提示"""
        from claude_code.tools.builtins.todo import TodoCreateTool, get_todo_list

        tool = TodoCreateTool()
        items = [{"content": f"任务{i}"} for i in range(PLAN.MAX_ITEMS + 2)]
        items.append({"content": "   "})

        result = tool.execute({"items": items})

        assert result.success is True
        assert get_todo_list().total_count == PLAN.MAX_ITEMS
        assert "忽略" in result.output
        assert "上限" in result.output
        assert "忽略" in result.summary
        assert "忽略" in result.display_output


class TestPlanCommandImprovements:
    """/plan 命令增强行为测试"""

    class DummyApp:
        def __init__(self):
            self._plan_mode = False
            self._plan_task = ""
            self._plan_reminder_count = 0
            self.chat_called_with = None

        def chat(self, task_description):
            self.chat_called_with = task_description

        def _update_input_state(self):
            pass

    def setup_method(self):
        from claude_code.tools.builtins.todo import reset_todo_list
        reset_todo_list()

    def test_plan_status_does_not_start_chat(self, monkeypatch):
        """/plan status 只展示状态，不启动 chat"""
        from claude_code.commands.handlers import PlanCommand
        from claude_code.tools.builtins.todo import TodoCreateTool
        from claude_code.ui import components

        TodoCreateTool().execute({"items": [{"content": "任务1"}]})
        calls = []
        monkeypatch.setattr(components, "show_plan_status", lambda todo, active=False: calls.append((todo.total_count, active)))

        app = self.DummyApp()
        app._plan_mode = True
        PlanCommand(app).execute(["status"])

        assert app.chat_called_with is None
        assert calls == [(1, True)]

    def test_plan_stop_shows_summary_and_resets_state(self, monkeypatch):
        """/plan stop 主动退出并展示摘要"""
        from claude_code.commands.handlers import PlanCommand
        from claude_code.tools.builtins.todo import TodoCreateTool
        from claude_code.ui import components

        TodoCreateTool().execute({"items": [{"content": "任务1"}]})
        calls = []
        monkeypatch.setattr(components, "show_plan_stopped", lambda todo: calls.append(todo.total_count))

        app = self.DummyApp()
        app._plan_mode = True
        app._plan_task = "旧任务"
        app._plan_reminder_count = 2

        PlanCommand(app).execute(["stop"])

        assert app._plan_mode is False
        assert app._plan_task == ""
        assert app._plan_reminder_count == 0
        assert calls == [1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
