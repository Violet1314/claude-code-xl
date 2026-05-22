"""历史保存/加载回放测试"""
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from claude_code.app import Application
from claude_code.core.conversation import Conversation
from claude_code.config.settings import ModelConfig, ProviderConfig


class DummySettings:
    def __init__(self):
        self.active_profile = "deepseek"
        self.profiles = {"deepseek": object()}
        self.style_ids = ["expert"]
        self.model = ModelConfig(id="m1", name="Model One")
        self.provider = ProviderConfig(id="p1", profile="official")

    def get_provider(self, model=None):
        return self.provider

    def get_model(self, model_id=None):
        if model_id in (None, "m1"):
            return self.model
        return None


def make_app(tmp_path):
    app = Application.__new__(Application)
    app.history_dir = str(tmp_path)
    app.settings = DummySettings()
    app.current_model = app.settings.model
    app.current_style_id = "expert"
    app.conversation = Conversation()
    app.files = SimpleNamespace(list_files=lambda: [], count=0)
    app.path_manager = SimpleNamespace(active_path=str(tmp_path), workplace=str(tmp_path), is_workplace_mode=True)
    app.stats = SimpleNamespace(session=SimpleNamespace(total_tokens=0, accumulated_input=0, accumulated_output=0, cost=0.0))
    app.tool_executor = SimpleNamespace(get_history=lambda limit=100: [], execution_history=[])
    app._plan_mode = False
    app._plan_task = ""
    return app


def test_save_conversation_saves_profile_and_title_meta(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    app.conversation.add_user_message("帮我修复历史保存")
    monkeypatch.setattr(app, "_generate_history_title", lambda messages: ("标题", {
        "title_model": "deepseek-v4-flash",
        "title_profile": "deepseek",
        "title_generated": True,
    }))

    app.save_conversation()

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["title"] == "标题"
    assert data["title_model"] == "deepseek-v4-flash"
    assert data["title_profile"] == "deepseek"
    assert data["title_generated"] is True
    assert data["active_profile"] == "deepseek"
    assert data["provider_profile"] == "official"


def test_load_history_restores_profile_before_model(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    data = {
        "title": "旧历史",
        "active_profile": "deepseek",
        "model": "m1",
        "messages": [{"role": "user", "content": "hi"}],
        "tool_history": [],
        "mounted_files": [],
        "path_state": {},
        "stats": {},
        "plan_state": {},
    }
    (tmp_path / "history.json").write_text(json.dumps(data), encoding="utf-8")
    calls = []
    monkeypatch.setattr(app, "switch_provider_profile", lambda profile, persist=True: calls.append((profile, persist)) or True)
    monkeypatch.setattr(app, "_setup_system_prompt", lambda: None)
    monkeypatch.setattr(app, "_update_input_state", lambda: None)
    monkeypatch.setattr(app, "_replay_messages", lambda messages, replay_mode="recent": None)
    monkeypatch.setattr(app, "_estimate_context_usage", lambda: 0)

    app._load_history_file("history.json")

    assert calls == [("deepseek", False)]
    assert app.current_model.id == "m1"


def test_replay_messages_uses_assistant_metadata(monkeypatch, tmp_path):
    app = make_app(tmp_path)
    rendered = []
    import claude_code.ui.renderer as renderer
    monkeypatch.setattr(renderer, "render_response", lambda content, model_name, duration, tokens, has_tools=False: rendered.append((content, model_name, duration, tokens, has_tools)))

    app._replay_messages([{
        "role": "assistant",
        "content": "answer",
        "metadata": {"model_name": "Old Model", "duration": 2.5, "tokens": {"input": 1, "output": 2}, "has_tools": True},
    }], replay_mode="full")

    assert rendered == [("answer", "Old Model", 2.5, {"input": 1, "output": 2}, True)]


def test_replay_messages_limits_recent_not_full(monkeypatch, tmp_path):
    app = make_app(tmp_path)
    printed = []
    import claude_code.app as app_module
    monkeypatch.setattr(app_module.console, "print", lambda *args, **kwargs: printed.append(args[0] if args else ""))
    messages = [{"role": "user", "content": f"m{i}"} for i in range(55)]

    app._replay_messages(messages, replay_mode="recent")
    recent_count = sum(1 for item in printed if "YOU" in str(item))
    assert recent_count == 50
    assert any("/history full" in str(item) for item in printed)

    printed.clear()
    app._replay_messages(messages, replay_mode="full")
    full_count = sum(1 for item in printed if "YOU" in str(item))
    assert full_count == 55


def test_replay_tool_uses_tool_history(monkeypatch, tmp_path):
    app = make_app(tmp_path)
    app.tool_executor.execution_history = [{
        "tool_call_id": "call-1",
        "tool": "Read",
        "parameters": {"file_path": "a.py"},
        "success": True,
        "output": "file content",
        "duration_ms": 12,
    }]
    printed = []
    import claude_code.app as app_module
    monkeypatch.setattr(app_module.console, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    app._replay_messages([{"role": "tool", "tool_call_id": "call-1", "content": "raw"}], replay_mode="full")

    output = "\n".join(printed)
    assert "Read" in output
    assert "file_path=a.py" in output
    assert "file content" in output


def test_generate_history_title_uses_clean_deepseek_config(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    provider = ProviderConfig(id="deepseek", base_url="https://api.deepseek.com", api_key="test", profile="deepseek_official")
    model = ModelConfig(
        id="deepseek-v4-flash",
        name="DeepSeek V4 Flash",
        capabilities={"tools": True, "thinking": True, "reasoning_effort": True, "stream_usage": True},
        thinking={"type": "enabled"},
        reasoning_effort="max",
        max_output_tokens=393216,
    )
    app.settings.profiles = {
        "deepseek": SimpleNamespace(
            id="deepseek",
            models=[model],
            default_model="deepseek-v4-flash",
            primary_provider=provider,
        )
    }
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        def send_message(self, **kwargs):
            captured.update(kwargs)
            return [{"choices": [{"delta": {"content": "代码重构进度"}}]}]

        @staticmethod
        def extract_content(chunk):
            return chunk["choices"][0]["delta"]["content"]

        def close(self):
            captured["closed"] = True

    import claude_code.app as app_module
    monkeypatch.setattr(app_module, "APIClient", FakeClient)

    title, meta = app._generate_history_title([{"role": "user", "content": "请总结当前重构进度"}])

    title_model = captured["model_config"]
    assert title == "代码重构进度"
    assert meta["title_generated"] is True
    assert meta["title_error"] == ""
    assert title_model.id == "deepseek-v4-flash"
    assert title_model.capabilities["tools"] is False
    assert title_model.capabilities["thinking"] is True
    assert title_model.capabilities["reasoning_effort"] is False
    assert title_model.capabilities["stream_usage"] is False
    assert title_model.thinking == {"type": "disabled"}
    assert title_model.reasoning_effort is None
    assert title_model.max_output_tokens == 64
    assert captured["max_tokens"] == 64
    assert captured["closed"] is True


def test_generate_history_title_records_error_on_failure(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    provider = ProviderConfig(id="deepseek", base_url="https://api.deepseek.com", api_key="test")
    model = ModelConfig(id="deepseek-v4-flash", name="DeepSeek V4 Flash")
    app.settings.profiles = {
        "deepseek": SimpleNamespace(
            id="deepseek",
            models=[model],
            default_model="deepseek-v4-flash",
            primary_provider=provider,
        )
    }

    class FailingClient:
        def __init__(self, **kwargs):
            pass

        def send_message(self, **kwargs):
            raise RuntimeError("bad request")

        def close(self):
            pass

    import claude_code.app as app_module
    monkeypatch.setattr(app_module, "APIClient", FailingClient)

    title, meta = app._generate_history_title([{"role": "user", "content": "这是首条用户消息用于回退"}])

    assert title == "这是首条用户消息用于回退"
    assert meta["title_generated"] is False
    assert "RuntimeError: bad request" in meta["title_error"]
