"""计划模式状态机测试"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from claude_code.app import Application
from claude_code.config.settings import ModelConfig, ProviderConfig
from claude_code.core.conversation import Conversation, Message
from claude_code.core.todo import TodoList
from claude_code.tools.base import ToolCall, ToolResult
from claude_code.tools.executor import ExecutionReport, ExecutionResult
from claude_code.tools.builtins.todo import reset_todo_list, get_todo_list


def make_app():
    app = Application.__new__(Application)
    app._plan_mode = True
    app._plan_task = "测试计划"
    app._plan_reminder_count = 0
    app._plan_prev_statuses = {}
    return app


def test_record_plan_tool_failures_updates_current_task():
    reset_todo_list()
    todo = get_todo_list()
    todo.add_item("执行失败恢复测试")
    todo.update_status("t1", "in_progress")
    app = make_app()
    report = ExecutionReport(results=[
        ExecutionResult(
            tool_call=ToolCall(name="Bash", parameters={"command": "pytest"}, id="call-1"),
            tool_result=ToolResult(success=False, output="", error="pytest failed"),
        )
    ])

    app._record_plan_tool_failures(report)

    item = todo.get_item("t1")
    assert item.error == "pytest failed"
    assert item.last_failure_tool == "Bash"
    assert item.last_error_signature.startswith("Bash:pytest failed")
    assert item.retry_count == 1
    assert "pytest failed" in todo.to_prompt_text()


def test_record_plan_tool_failures_ignores_non_plan_mode():
    reset_todo_list()
    todo = get_todo_list()
    todo.add_item("任务")
    todo.update_status("t1", "in_progress")
    app = make_app()
    app._plan_mode = False
    report = ExecutionReport(results=[
        ExecutionResult(
            tool_call=ToolCall(name="Bash", parameters={}),
            tool_result=ToolResult(success=False, output="", error="failed"),
        )
    ])

    app._record_plan_tool_failures(report)

    assert todo.get_item("t1").error == ""


def test_plan_snapshot_changes_when_failure_recorded():
    todo = TodoList()
    todo.add_item("任务")
    before = todo.get_status_snapshot()
    todo.update_status("t1", "in_progress")
    todo.record_current_failure("Read", "missing file", "Read:missing file")
    after = todo.get_status_snapshot()

    assert before != after
    assert after["t1"][2] == "missing file"


def test_build_autosave_data_includes_extended_plan_state(tmp_path):
    reset_todo_list()
    todo = get_todo_list()
    todo.add_item("任务")
    todo.update_status("t1", "in_progress")
    todo.apply_evidence("t1", evidence="已验证", files=["a.py"], tests=["pytest"])
    app = make_app()
    app.conversation = Conversation()
    app.conversation.add_user_message("hello")
    app.current_model = ModelConfig(id="m1", name="Model")
    app.current_style_id = "expert"
    provider = ProviderConfig(id="p1", profile="official")
    app.settings = SimpleNamespace(
        active_profile="deepseek",
        get_provider=lambda model=None: provider,
    )
    app.path_manager = SimpleNamespace(
        active_path=str(tmp_path),
        workplace=str(tmp_path),
        is_workplace_mode=True,
    )
    app.tool_executor = SimpleNamespace(get_history=lambda limit=100: [{"tool": "Read"}])
    app._plan_started_at = "2026-01-01T00:00:00"
    app._plan_completed_at = ""
    app._plan_final_summary = ""
    app._plan_prev_statuses = todo.get_status_snapshot()

    data = app._build_autosave_data()

    assert data["active_profile"] == "deepseek"
    assert data["provider_profile"] == "official"
    assert data["path_state"]["active_path"] == str(tmp_path)
    assert data["tool_history"] == [{"tool": "Read"}]
    assert data["plan_started_at"] == "2026-01-01T00:00:00"
    assert data["plan_prev_statuses"]
    assert data["todos"][0]["evidence"] == "已验证"
    assert data["todos"][0]["files"] == ["a.py"]
    assert data["todos"][0]["tests"] == ["pytest"]


def test_build_plan_prompt_is_compact():
    reset_todo_list()
    todo = get_todo_list()
    todo.add_item("分析代码")
    app = make_app()

    prompt = app._build_plan_prompt(todo, first_injection=True)

    assert prompt.startswith("[PLAN]")
    assert "预估>2步时先TodoCreate" in prompt
    assert len(prompt) < 300


def test_build_plan_reminder_is_compact():
    reset_todo_list()
    todo = get_todo_list()
    todo.add_item("分析代码")
    app = make_app()
    app._plan_reminder_count = 2

    reminder = app._build_plan_reminder(todo, "调用 TodoUpdate")

    assert reminder.startswith("[PLAN_REMINDER]")
    assert "NEXT:" in reminder
    assert "WARN:" in reminder


def test_generate_plan_summary_messages_preserves_plan_context():
    reset_todo_list()
    todo = get_todo_list()
    todo.add_item("修复功能")
    todo.update_status("t1", "in_progress")
    todo.record_current_failure("Bash", "pytest failed", "Bash:pytest failed")
    todo.apply_evidence("t1", evidence="定位到失败", files=["src/app.py"], tests=["pytest"])
    app = make_app()
    app.conversation = Conversation()
    app.conversation._messages.append(Message(role="user", content="用户目标"))
    app.conversation._messages.append(Message(role="tool", content="很长工具输出" * 50))

    messages = app._generate_plan_summary_messages()

    content = messages[0]["content"]
    assert "目标: 测试计划" in content
    assert "t1 in_progress 修复功能" in content
    assert "证据:定位到失败" in content
    assert "文件:src/app.py" in content
    assert "失败:pytest failed" in content
