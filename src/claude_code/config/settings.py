"""配置加载 - API 配置与系统提示词"""
import os
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from claude_code.config.defaults import VERSION

@dataclass
class ModelConfig:
    """模型配置"""
    id: str
    name: str
    desc: str = ""
    context_limit: int = 100_000
    price: str = ""

    @classmethod
    def from_dict(cls, data: Dict) -> "ModelConfig":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            desc=data.get("desc", ""),
            context_limit=data.get("context_limit", 100_000),
            price=data.get("price", ""),
        )
    
    def get_price_short(self) -> str:
        """
        解析价格为简短格式
        'Input: 5$/1M Output: 25$/1M' -> '5/25'
        """
        if not self.price:
            return ""
        
        import re
        # 匹配数字（包括小数）
        numbers = re.findall(r'(\d+(?:\.\d+)?)\$', self.price)
        if len(numbers) >= 2:
            return f"{numbers[0]}/{numbers[1]}"
        return ""
    
@dataclass
class Settings:
    """应用配置"""
    base_url: str
    api_key: str
    models: List[ModelConfig]
    default_model: str
    task_models: Dict[str, str] = field(default_factory=dict)
    system_prompts: Dict[str, str] = field(default_factory=dict)
    
    def get_model(self, model_id: str = None) -> Optional[ModelConfig]:
        """
        获取模型配置
        
        Args:
            model_id: 模型 ID，为空则返回默认模型
            
        Returns:
            模型配置或 None
        """
        target_id = model_id or self.default_model
        
        for model in self.models:
            if model.id == target_id:
                return model
        
        return self.models[0] if self.models else None
    
    def get_prompt(self, style_id: str) -> str:
        """
        获取系统提示词
        
        Args:
            style_id: 风格 ID
            
        Returns:
            提示词内容
        """
        if style_id in self.system_prompts:
            return self.system_prompts[style_id]
        
        # 返回第一个可用的
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
        """
        初始化加载器
        
        Args:
            config_dir: 配置目录路径
        """
        self.config_dir = config_dir
        
        # 主配置文件路径
        self.api_config_file = os.path.join(config_dir, "api-config.json")
        self.prompts_file = os.path.join(config_dir, "system-prompts.json")
    
    def _read_json(self, path: str) -> Optional[Dict]:
        """
        安全读取 JSON 文件
        
        Args:
            path: 文件路径
            
        Returns:
            解析后的字典或 None
        """
        if not os.path.exists(path):
            print(f"[DEBUG] 配置文件不存在: {path}")
            return None
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                #print(f"[DEBUG] 成功加载: {path}")
                return data
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
        """
        加载完整配置
        
        Returns:
            Settings 实例
        """
        api_config = self._load_api_config()
        prompts = self._load_prompts()
        
        models = [
            ModelConfig.from_dict(m)
            for m in api_config.get("models", [])
        ]
        
        return Settings(
            base_url=api_config.get("base_url", ""),
            api_key=api_config.get("api_key", ""),
            models=models,
            default_model=api_config.get("default_model", ""),
            task_models=api_config.get("task_models", {}),
            system_prompts=prompts,
        )

def load_settings(config_dir: str = "data/config") -> Settings:
    """
    便捷函数：加载配置
    
    Args:
        config_dir: 配置目录
        
    Returns:
        Settings 实例
    """
    loader = SettingsLoader(config_dir)
    return loader.load()
