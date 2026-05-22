"""配置加载 - API 配置与系统提示词"""
import os
import json
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field


@dataclass
class ProviderConfig:
    """Provider 配置"""
    id: str
    name: str = ""
    base_url: str = ""
    api_key: str = ""
    api_style: str = "openai_compatible"
    profile: str = "generic_openai_compatible"

    @classmethod
    def from_dict(cls, data: Dict) -> "ProviderConfig":
        provider_id = data.get("id", "")
        return cls(
            id=provider_id,
            name=data.get("name", provider_id),
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
            api_style=data.get("api_style", "openai_compatible"),
            profile=data.get("profile", "generic_openai_compatible"),
        )


@dataclass
class ModelConfig:
    """模型配置"""
    id: str
    name: str
    desc: str = ""
    context_limit: int = 100_000
    price: str = ""
    provider: str = "default"
    tool_mode: str = "native"
    capabilities: Dict[str, bool] = field(default_factory=dict)
    max_output_tokens: Optional[int] = None
    reasoning_effort: Optional[str] = None
    thinking: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "ModelConfig":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            desc=data.get("desc", ""),
            context_limit=data.get("context_limit", 100_000),
            price=data.get("price", ""),
            provider=data.get("provider", "default"),
            tool_mode=data.get("tool_mode", "native"),
            capabilities=data.get("capabilities", {}) or {},
            max_output_tokens=data.get("max_output_tokens"),
            reasoning_effort=data.get("reasoning_effort"),
            thinking=data.get("thinking"),
        )

    def get_price_short(self) -> str:
        """
        解析价格为简短格式
        'Input: $0.96/1M Output: $1.91/1M' -> '0.96/1.91'
        """
        if not self.price:
            return ""

        import re
        numbers = re.findall(r'\$(\d+(?:\.\d+)?)', self.price)
        if len(numbers) >= 2:
            return f"{numbers[0]}/{numbers[1]}"
        return ""

    def get_prices(self) -> tuple:
        """
        解析价格为数值
        'Input: $0.96/1M Output: $1.91/1M' -> (0.96, 1.91)
        """
        if not self.price:
            return (0.0, 0.0)

        import re
        numbers = re.findall(r'\$(\d+(?:\.\d+)?)', self.price)
        if len(numbers) >= 2:
            return (float(numbers[0]), float(numbers[1]))
        return (0.0, 0.0)


@dataclass
class ProviderProfileConfig:
    """Provider profile 配置"""
    id: str
    name: str
    providers: Dict[str, ProviderConfig]
    models: List[ModelConfig]
    default_model: str
    task_models: Dict[str, str] = field(default_factory=dict)

    @property
    def primary_provider(self) -> Optional[ProviderConfig]:
        return self.providers.get(self.id) or self.providers.get("default") or next(iter(self.providers.values()), None)


@dataclass
class Settings:
    """应用配置"""
    base_url: str
    api_key: str
    models: List[ModelConfig]
    default_model: str
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    task_models: Dict[str, str] = field(default_factory=dict)
    system_prompts: Dict[str, str] = field(default_factory=dict)
    active_profile: str = "default"
    profiles: Dict[str, ProviderProfileConfig] = field(default_factory=dict)
    config_file: str = ""

    def switch_profile(self, profile_id: str) -> bool:
        """切换当前 active profile 的运行时视图"""
        profile = self.profiles.get(profile_id)
        if not profile:
            return False

        provider = profile.primary_provider
        self.active_profile = profile_id
        self.providers = profile.providers
        self.models = profile.models
        self.default_model = profile.default_model
        self.task_models = profile.task_models
        self.base_url = provider.base_url if provider else ""
        self.api_key = provider.api_key if provider else ""
        return True

    def persist_active_profile(self) -> bool:
        """将 active_profile 写回配置文件"""
        if not self.config_file:
            return False
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if "profiles" not in data:
                return False
            data["active_profile"] = self.active_profile
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            return True
        except (OSError, json.JSONDecodeError):
            return False

    def get_model(self, model_id: str = None) -> Optional[ModelConfig]:
        """获取模型配置"""
        target_id = model_id or self.default_model

        for model in self.models:
            if model.id == target_id:
                return model

        return self.models[0] if self.models else None

    def get_provider(self, model_or_id: Union[ModelConfig, str, None] = None) -> Optional[ProviderConfig]:
        """获取模型绑定的 provider 配置"""
        if isinstance(model_or_id, ModelConfig):
            provider_id = model_or_id.provider
        else:
            model = self.get_model(model_or_id)
            provider_id = model.provider if model else "default"

        if provider_id in self.providers:
            return self.providers[provider_id]
        return self.providers.get("default") or next(iter(self.providers.values()), None)

    def get_prompt(self, style_id: str) -> str:
        """获取系统提示词"""
        if style_id in self.system_prompts:
            return self.system_prompts[style_id]

        if self.system_prompts:
            return next(iter(self.system_prompts.values()))

        return "You are a helpful assistant."

    @property
    def style_ids(self) -> List[str]:
        """获取所有风格 ID"""
        return list(self.system_prompts.keys())


class SettingsLoader:
    """配置加载器"""

    def __init__(self, config_dir: str = "data/config"):
        self.config_dir = config_dir
        self.api_config_file = os.path.join(config_dir, "api-config.json")
        self.prompts_file = os.path.join(config_dir, "system-prompts.json")

    def _read_json(self, path: str) -> Optional[Dict]:
        """安全读取 JSON 文件"""
        if not os.path.exists(path):
            print(f"[DEBUG] 配置文件不存在: {path}")
            return None

        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[DEBUG] 加载失败: {path}, 错误: {e}")
            return None

    def _load_api_config(self) -> Dict:
        """加载 API 配置"""
        config = self._read_json(self.api_config_file)
        if config and self._validate_api_config(config):
            return config

        print("[DEBUG] 使用兜底配置")
        return self._get_fallback_config()

    def _validate_api_config(self, config: Dict) -> bool:
        """验证 API 配置有效性"""
        if "profiles" in config:
            return bool(config.get("profiles"))
        if "providers" in config:
            return all(key in config for key in ["providers", "models", "default_model"])
        required = ["base_url", "api_key", "models", "default_model"]
        return all(key in config for key in required)

    def _get_fallback_config(self) -> Dict:
        """获取兜底配置"""
        return {
            "base_url": "https://api.anthropic.com/v1",
            "api_key": "YOUR_API_KEY_HERE",
            "models": [
                {
                    "id": "claude-sonnet-4-20250514",
                    "name": "Claude Sonnet 4",
                    "desc": "Default model",
                    "context_limit": 200000,
                }
            ],
            "default_model": "claude-sonnet-4-20250514",
            "task_models": {},
        }

    def _load_prompts(self) -> Dict[str, str]:
        """加载系统提示词"""
        prompts = self._read_json(self.prompts_file)
        if prompts:
            return prompts

        return {
            "expert": "You are a helpful coding assistant. Always respond in Chinese.",
        }

    def load(self) -> Settings:
        """加载完整配置"""
        api_config = self._load_api_config()
        prompts = self._load_prompts()
        profiles = self._load_profiles(api_config)
        active_profile = api_config.get("active_profile") or next(iter(profiles.keys()), "default")
        if active_profile not in profiles:
            active_profile = next(iter(profiles.keys()), "default")

        active = profiles.get(active_profile)
        provider = active.primary_provider if active else None

        return Settings(
            base_url=provider.base_url if provider else "",
            api_key=provider.api_key if provider else "",
            models=active.models if active else [],
            default_model=active.default_model if active else "",
            providers=active.providers if active else {},
            task_models=active.task_models if active else {},
            system_prompts=prompts,
            active_profile=active_profile,
            profiles=profiles,
            config_file=self.api_config_file,
        )

    def _load_profiles(self, api_config: Dict) -> Dict[str, ProviderProfileConfig]:
        """加载 profiles；兼容旧格式和 P0 providers 格式"""
        raw_profiles = api_config.get("profiles")
        if raw_profiles:
            profiles = {}
            for profile_id, profile_data in raw_profiles.items():
                profiles[profile_id] = self._profile_from_dict(profile_id, profile_data or {})
            return profiles

        return {"default": self._profile_from_legacy("default", api_config)}

    def _profile_from_dict(self, profile_id: str, profile_data: Dict) -> ProviderProfileConfig:
        provider_data = profile_data.get("provider", {}) or {}
        provider_id = provider_data.get("id", profile_id)
        provider = ProviderConfig.from_dict({"id": provider_id, **provider_data})
        providers = {provider.id: provider}
        models = [
            ModelConfig.from_dict({"provider": provider.id, **(m or {})})
            for m in profile_data.get("models", [])
        ]
        return ProviderProfileConfig(
            id=profile_id,
            name=profile_data.get("name", profile_id),
            providers=providers,
            models=models,
            default_model=profile_data.get("default_model", models[0].id if models else ""),
            task_models=profile_data.get("task_models", {}) or {},
        )

    def _profile_from_legacy(self, profile_id: str, api_config: Dict) -> ProviderProfileConfig:
        providers = self._load_providers(api_config)
        default_provider = "default" if "default" in providers else next(iter(providers.keys()), profile_id)
        models = [
            ModelConfig.from_dict({"provider": default_provider, **(m or {})})
            for m in api_config.get("models", [])
        ]
        return ProviderProfileConfig(
            id=profile_id,
            name=api_config.get("name", profile_id),
            providers=providers,
            models=models,
            default_model=api_config.get("default_model", models[0].id if models else ""),
            task_models=api_config.get("task_models", {}) or {},
        )

    def _load_providers(self, api_config: Dict) -> Dict[str, ProviderConfig]:
        """加载 provider 配置，兼容旧格式全局 base_url/api_key"""
        raw_providers = api_config.get("providers")
        if raw_providers:
            providers = {}
            if isinstance(raw_providers, dict):
                for provider_id, provider_data in raw_providers.items():
                    data = {"id": provider_id, **(provider_data or {})}
                    providers[provider_id] = ProviderConfig.from_dict(data)
            elif isinstance(raw_providers, list):
                for provider_data in raw_providers:
                    provider = ProviderConfig.from_dict(provider_data or {})
                    if provider.id:
                        providers[provider.id] = provider
            return providers

        return {
            "default": ProviderConfig(
                id="default",
                name="Default",
                base_url=api_config.get("base_url", ""),
                api_key=api_config.get("api_key", ""),
                api_style=api_config.get("api_style", "openai_compatible"),
                profile=api_config.get("profile", "generic_openai_compatible"),
            )
        }


def load_settings(config_dir: str = "data/config") -> Settings:
    """便捷函数：加载配置"""
    loader = SettingsLoader(config_dir)
    return loader.load()
