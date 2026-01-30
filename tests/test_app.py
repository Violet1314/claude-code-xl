"""主应用类测试"""
import os
import pytest
import tempfile
import json
from pathlib import Path

from claude_code.app import Application

@pytest.fixture
def temp_config_dir():
    """创建临时配置目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建配置文件
        api_config = {
            "base_url": "http://test.example.com",
            "api_key": "test-key",
            "models": [
                {"id": "model-1", "name": "Test Model", "context_limit": 100000}
            ],
            "default_model": "model-1",
        }
        prompts = {"expert": "You are helpful."}
        
        with open(os.path.join(tmpdir, "api-config.json"), 'w') as f:
            json.dump(api_config, f)
        
        with open(os.path.join(tmpdir, "system-prompts.json"), 'w') as f:
            json.dump(prompts, f)
        
        yield tmpdir

class TestApplicationInit:
    """应用初始化测试"""
    
    def test_init_with_config(self, temp_config_dir):
        app = Application(config_dir=temp_config_dir)
        
        assert app.settings is not None
        assert app.client is not None
        assert app.conversation is not None
        assert app.files is not None
        assert app.stats is not None
        assert app.commands is not None
        
        app.client.close()
    
    def test_init_loads_model(self, temp_config_dir):
        app = Application(config_dir=temp_config_dir)
        
        assert app.current_model is not None
        assert app.current_model.name == "Test Model"
        
        app.client.close()
    
    def test_init_registers_commands(self, temp_config_dir):
        app = Application(config_dir=temp_config_dir)
        
        assert app.commands.has("help")
        assert app.commands.has("quit")
        assert app.commands.has("model")
        
        app.client.close()

class TestApplicationConversation:
    """对话功能测试"""
    
    def test_reset_conversation(self, temp_config_dir):
        app = Application(config_dir=temp_config_dir)
        
        # 添加一些消息
        app.conversation.add_user_message("Hello")
        app.conversation.add_assistant_message("Hi")
        
        assert not app.conversation.is_empty
        
        # 重置（不调用 reset_conversation 因为会清屏）
        app.conversation.reset()
        
        assert app.conversation.is_empty
        
        app.client.close()

class TestApplicationFiles:
    """文件管理测试"""
    
    def test_add_and_drop_files(self, temp_config_dir):
        app = Application(config_dir=temp_config_dir)
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write("print('test')")
            temp_path = f.name
        
        try:
            # 添加文件
            app.add_files([temp_path])
            assert app.files.count == 1
            
            # 移除文件
            app.drop_files(["all"])
            assert app.files.count == 0
            
        finally:
            os.unlink(temp_path)
            app.client.close()

class TestApplicationState:
    """状态管理测试"""
    
    def test_update_input_state(self, temp_config_dir):
        app = Application(config_dir=temp_config_dir)
        
        app._update_input_state()
        
        assert app.input_handler.model_name == "Test Model"
        assert app.input_handler.file_count == 0
        
        app.client.close()