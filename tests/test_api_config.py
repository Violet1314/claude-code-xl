import json

from claude_code.config.settings import ModelConfig, SettingsLoader


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_old_format_config_loads_with_default_provider(tmp_path):
    write_json(tmp_path / "api-config.json", {
        "base_url": "https://example.com/v1",
        "api_key": "sk-old",
        "models": [{"id": "old-model", "name": "Old Model"}],
        "default_model": "old-model",
    })

    settings = SettingsLoader(str(tmp_path)).load()

    assert settings.base_url == "https://example.com/v1"
    assert settings.api_key == "sk-old"
    assert "default" in settings.providers
    assert settings.models[0].provider == "default"
    assert settings.get_provider(settings.models[0]).base_url == "https://example.com/v1"


def test_new_format_config_loads_model_provider(tmp_path):
    write_json(tmp_path / "api-config.json", {
        "providers": {
            "gateway": {
                "name": "Gateway",
                "base_url": "https://gateway.example/v1",
                "api_key": "sk-new",
                "api_style": "openai_compatible",
            }
        },
        "models": [{"id": "new-model", "name": "New Model", "provider": "gateway"}],
        "default_model": "new-model",
    })

    settings = SettingsLoader(str(tmp_path)).load()
    model = settings.get_model("new-model")
    provider = settings.get_provider(model)

    assert settings.base_url == "https://gateway.example/v1"
    assert settings.api_key == "sk-new"
    assert model.provider == "gateway"
    assert provider.id == "gateway"


def test_model_config_reads_provider_capability_fields():
    model = ModelConfig.from_dict({
        "id": "m",
        "name": "Model",
        "provider": "p",
        "tool_mode": "native",
        "capabilities": {"stream_usage": True, "reasoning_effort": False},
        "max_output_tokens": 4096,
        "reasoning_effort": "high",
        "thinking": {"type": "enabled"},
    })

    assert model.provider == "p"
    assert model.tool_mode == "native"
    assert model.capabilities == {"stream_usage": True, "reasoning_effort": False}
    assert model.max_output_tokens == 4096
    assert model.reasoning_effort == "high"
    assert model.thinking == {"type": "enabled"}


def test_profiles_config_loads_active_profile_and_switches(tmp_path):
    write_json(tmp_path / "api-config.json", {
        "active_profile": "company",
        "profiles": {
            "company": {
                "name": "Company",
                "provider": {
                    "id": "company",
                    "base_url": "https://company.example/v1",
                    "api_key": "sk-company",
                    "profile": "generic_openai_compatible",
                },
                "models": [
                    {"id": "glm-5.1", "name": "GLM 5.1"},
                    {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro"},
                ],
                "default_model": "glm-5.1",
            },
            "deepseek": {
                "name": "DeepSeek Official",
                "provider": {
                    "id": "deepseek",
                    "base_url": "https://api.deepseek.com",
                    "api_key": "sk-deepseek",
                    "profile": "deepseek_official",
                },
                "models": [
                    {
                        "id": "deepseek-v4-flash",
                        "name": "DeepSeek V4 Flash",
                        "capabilities": {"thinking": True, "reasoning_effort": True},
                        "thinking": {"type": "enabled"},
                        "reasoning_effort": "max",
                    }
                ],
                "default_model": "deepseek-v4-flash",
            },
        },
    })

    settings = SettingsLoader(str(tmp_path)).load()

    assert settings.active_profile == "company"
    assert settings.base_url == "https://company.example/v1"
    assert len(settings.models) == 2
    assert settings.get_model().id == "glm-5.1"

    assert settings.switch_profile("deepseek") is True
    assert settings.active_profile == "deepseek"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.api_key == "sk-deepseek"
    assert len(settings.models) == 1
    assert settings.get_model().id == "deepseek-v4-flash"
    assert settings.get_provider(settings.get_model()).profile == "deepseek_official"


def test_persist_active_profile_updates_profiles_config(tmp_path):
    config_path = tmp_path / "api-config.json"
    write_json(config_path, {
        "active_profile": "company",
        "profiles": {
            "company": {
                "provider": {"id": "company", "base_url": "https://company.example", "api_key": "sk"},
                "models": [{"id": "m1", "name": "M1"}],
                "default_model": "m1",
            },
            "deepseek": {
                "provider": {"id": "deepseek", "base_url": "https://api.deepseek.com", "api_key": "sk"},
                "models": [{"id": "m2", "name": "M2"}],
                "default_model": "m2",
            },
        },
    })

    settings = SettingsLoader(str(tmp_path)).load()
    settings.switch_profile("deepseek")

    assert settings.persist_active_profile() is True
    assert json.loads(config_path.read_text(encoding="utf-8"))["active_profile"] == "deepseek"
