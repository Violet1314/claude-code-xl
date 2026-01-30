"""配置加载模块测试"""
import os
import json
import pytest
import tempfile
from pathlib import Path

from claude_code.config.settings import (
    ModelConfig,
    Settings,
    SettingsLoader,
    load_settings,
)

class TestModelConfig:
    """ModelConfig 测试"""
    
    def test_from_dict(self):
        data = {
            "id": "model-1",
            "name": "Test Model",
            "desc": "A test model",
            "context_limit": 50000,
        }
        model = ModelConfig.from_dict(data)
        
        assert model.id == "model-1"
        assert model.name == "Test Model"
        assert model.context_limit == 50000
    
    def test_from_dict_defaults(self):
        model = ModelConfig.from_dict({})
        
        assert model.id == ""
        assert model.context_limit == 100_000

class TestSettings:
    """Settings 测试"""
    
    def test_get_model_by_id(self):
        models = [
            ModelConfig(id="m1", name="Model 1"),
            ModelConfig(id="m2", name="Model 2"),
        ]
        settings = Settings(
            base_url="http://test",
            api_key="key",
            models=models,
            default_model="m1",
        )
        
        model = settings.get_model("m2")
        assert model.id == "m2"
    
    def test_get_model_default(self):
        models = [
            ModelConfig(id="m1", name="Model 1"),
            ModelConfig(id="m2", name="Model 2"),
        ]
        settings = Settings(
            base_url="http://test",
            api_key="key",
            models=models,
            default_model="m1",
        )
        
        model = settings.get_model()
        assert model.id == "m1"
    
    def test_get_model_not_found(self):
        models = [ModelConfig(id="m1", name="Model 1")]
        settings = Settings(
            base_url="http://test",
            api_key="key",
            models=models,
            default_model="m1",
        )
        
        model = settings.get_model("nonexistent")
        assert model.id == "m1"  # 返回第一个
    
    def test_get_prompt(self):
        settings = Settings(
            base_url="http://test",
            api_key="key",
            models=[],
            default_model="",
            system_prompts={"expert": "Be expert", "casual": "Be casual"},
        )
        
        assert settings.get_prompt("expert") == "Be expert"
        assert settings.get_prompt("casual") == "Be casual"
    
    def test_get_prompt_fallback(self):
        settings = Settings(
            base_url="http://test",
            api_key="key",
            models=[],
            default_model="",
            system_prompts={"expert": "Be expert"},
        )
        
        # 不存在的 style 返回第一个
        result = settings.get_prompt("nonexistent")
        assert result == "Be expert"
    
    def test_get_prompt_empty(self):
        settings = Settings(
            base_url="http://test",
            api_key="key",
            models=[],
            default_model="",
            system_prompts={},
        )
        
        result = settings.get_prompt("any")
        assert "helpful" in result.lower()
    
    def test_style_ids(self):
        settings = Settings(
            base_url="http://test",
            api_key="key",
            models=[],
            default_model="",
            system_prompts={"a": "A", "b": "B", "c": "C"},
        )
        
        assert settings.style_ids == ["a", "b", "c"]

class TestSettingsLoader:
    """SettingsLoader 测试"""
    
    def test_load_from_config_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建配置文件
            api_config = {
                "base_url": "http://test.com",
                "api_key": "test-key",
                "models": [{"id": "m1", "name": "Model"}],
                "default_model": "m1",
            }
            prompts = {"style1": "Prompt 1"}
            
            with open(os.path.join(tmpdir, "api-config.json"), 'w') as f:
                json.dump(api_config, f)
            
            with open(os.path.join(tmpdir, "system-prompts.json"), 'w') as f:
                json.dump(prompts, f)
            
            loader = SettingsLoader(config_dir=tmpdir)
            settings = loader.load()
            
            assert settings.base_url == "http://test.com"
            assert settings.api_key == "test-key"
            assert len(settings.models) == 1
            assert "style1" in settings.system_prompts
    
    def test_load_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 空目录，应使用兜底配置
            loader = SettingsLoader(config_dir=tmpdir)
            settings = loader.load()
            
            assert settings.base_url != ""
            assert len(settings.models) > 0
    
    def test_invalid_json_uses_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 写入无效 JSON
            with open(os.path.join(tmpdir, "api-config.json"), 'w') as f:
                f.write("invalid json {{{")
            
            loader = SettingsLoader(config_dir=tmpdir)
            settings = loader.load()
            
            # 应使用兜底配置
            assert settings.base_url != ""

class TestLoadSettings:
    """load_settings 便捷函数测试"""
    
    def test_load_settings_function(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = load_settings(config_dir=tmpdir)
            
            assert isinstance(settings, Settings)
            assert settings.base_url != ""