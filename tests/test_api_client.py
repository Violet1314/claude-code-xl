from claude_code.config.settings import ModelConfig, ProviderConfig
from claude_code.core.client import OpenAICompatibleAdapter


def test_payload_does_not_send_reasoning_effort_by_default_with_model_config():
    adapter = OpenAICompatibleAdapter("https://example.com/v1", "sk-test")
    model = ModelConfig(id="m", name="Model")

    payload = adapter.build_payload("m", [{"role": "user", "content": "hi"}], model_config=model)

    assert "reasoning_effort" not in payload


def test_payload_sends_stream_usage_and_reasoning_effort_only_when_enabled():
    adapter = OpenAICompatibleAdapter("https://example.com/v1", "sk-test")
    model = ModelConfig(
        id="m",
        name="Model",
        capabilities={"stream_usage": True, "reasoning_effort": True},
        reasoning_effort="high",
    )

    payload = adapter.build_payload(
        "m",
        [{"role": "user", "content": "hi"}],
        stream=True,
        model_config=model,
    )

    assert payload["stream_options"] == {"include_usage": True}
    assert payload["reasoning_effort"] == "high"


def test_payload_omits_stream_usage_when_capability_disabled():
    adapter = OpenAICompatibleAdapter("https://example.com/v1", "sk-test")
    model = ModelConfig(
        id="m",
        name="Model",
        capabilities={"stream_usage": False, "reasoning_effort": False},
    )

    payload = adapter.build_payload(
        "m",
        [{"role": "user", "content": "hi"}],
        stream=True,
        model_config=model,
    )

    assert "stream_options" not in payload
    assert "reasoning_effort" not in payload


def test_openai_compatible_endpoint_uses_chat_completions():
    adapter = OpenAICompatibleAdapter("https://example.com/v1/", "sk-test")

    assert adapter.endpoint == "https://example.com/v1/chat/completions"


def test_provider_overrides_client_base_url_and_key():
    provider = ProviderConfig(
        id="p",
        base_url="https://provider.example/v1",
        api_key="sk-provider",
    )

    adapter = OpenAICompatibleAdapter.from_provider(
        "https://fallback.example/v1",
        "sk-fallback",
        provider,
    )

    assert adapter.endpoint == "https://provider.example/v1/chat/completions"
    assert adapter.build_headers()["Authorization"] == "Bearer sk-provider"


def test_deepseek_official_payload_includes_thinking_and_max_reasoning():
    adapter = OpenAICompatibleAdapter("https://api.deepseek.com", "sk-test")
    model = ModelConfig(
        id="deepseek-v4-pro",
        name="DeepSeek V4 Pro",
        capabilities={
            "temperature": True,
            "max_tokens": True,
            "tools": True,
            "stream_usage": False,
            "reasoning_effort": True,
            "thinking": True,
        },
        thinking={"type": "enabled"},
        reasoning_effort="max",
    )

    payload = adapter.build_payload(
        "deepseek-v4-pro",
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "Read"}}],
        stream=True,
        model_config=model,
    )

    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "max"
    assert payload["tools"]
    assert "stream_options" not in payload


def test_company_generic_payload_omits_deepseek_specific_fields():
    adapter = OpenAICompatibleAdapter("https://company.example/v1", "sk-test")
    model = ModelConfig(
        id="deepseek-v4-pro",
        name="DeepSeek V4 Pro",
        capabilities={"stream_usage": True, "reasoning_effort": False},
    )

    payload = adapter.build_payload(
        "deepseek-v4-pro",
        [{"role": "user", "content": "hi"}],
        stream=True,
        model_config=model,
    )

    assert "thinking" not in payload
    assert "reasoning_effort" not in payload
    assert payload["stream_options"] == {"include_usage": True}
