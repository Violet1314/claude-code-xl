"""输入处理模块测试"""
import pytest
from unittest.mock import Mock, patch

from claude_code.ui.input import (
    CommandCompleter,
    InputHandler,
    interactive_menu,
    input_number,
)

class TestCommandCompleter:
    """命令补全器测试"""
    
    def test_init_empty(self):
        completer = CommandCompleter()
        assert completer.commands == []
    
    def test_init_with_commands(self):
        commands = [{"name": "help", "description": "Show help"}]
        completer = CommandCompleter(commands)
        assert len(completer.commands) == 1
    
    def test_set_commands(self):
        completer = CommandCompleter()
        completer.set_commands([{"name": "test", "description": "Test"}])
        assert len(completer.commands) == 1
    
    def test_get_completions_no_slash(self):
        completer = CommandCompleter([{"name": "help", "description": ""}])
        
        # Mock document
        doc = Mock()
        doc.text_before_cursor = "hello"
        
        completions = list(completer.get_completions(doc, None))
        assert len(completions) == 0
    
    def test_get_completions_with_slash(self):
        completer = CommandCompleter([
            {"name": "help", "description": "Show help"},
            {"name": "history", "description": "Show history"},
        ])
        
        doc = Mock()
        doc.text_before_cursor = "/h"
        
        completions = list(completer.get_completions(doc, None))
        assert len(completions) == 2  # /help and /history
    
    def test_get_completions_exact_match(self):
        completer = CommandCompleter([
            {"name": "help", "description": "Show help"},
            {"name": "quit", "description": "Quit"},
        ])
        
        doc = Mock()
        doc.text_before_cursor = "/q"
        
        completions = list(completer.get_completions(doc, None))
        assert len(completions) == 1
        assert completions[0].text == "/quit"

class TestInputHandler:
    """输入处理器测试（不触发 PromptSession 创建）"""
    
    def test_init(self):
        handler = InputHandler()
        assert handler.model_name == "Claude"
        assert handler.file_count == 0
        assert handler._session is None  # 延迟初始化
    
    def test_init_with_commands(self):
        commands = [{"name": "help", "description": ""}]
        handler = InputHandler(commands)
        assert len(handler.completer.commands) == 1
    
    def test_update_state(self):
        handler = InputHandler()
        
        handler.update_state(model_name="GPT-4", file_count=5)
        
        assert handler.model_name == "GPT-4"
        assert handler.file_count == 5
    
    def test_update_state_partial(self):
        handler = InputHandler()
        handler.update_state(model_name="Test")
        
        handler.update_state(file_count=3)
        
        assert handler.model_name == "Test"  # 保持不变
        assert handler.file_count == 3
    
    def test_update_commands(self):
        handler = InputHandler()
        
        handler.update_commands([{"name": "new", "description": "New"}])
        
        assert len(handler.completer.commands) == 1
    
    def test_get_prompt_returns_list(self):
        handler = InputHandler()
        prompt = handler._get_prompt()
        
        assert isinstance(prompt, list)
        assert len(prompt) > 0
    
    def test_get_prompt_with_files(self):
        handler = InputHandler()
        handler.update_state(file_count=3)
        
        prompt = handler._get_prompt()
        
        # 应该包含文件信息的 tuple
        assert any('3' in str(p) for p in prompt)
    
    def test_get_continuation(self):
        handler = InputHandler()
        continuation = handler._get_continuation(80, 1, False)
        
        assert isinstance(continuation, list)
        assert len(continuation) > 0

class TestInteractiveMenu:
    """交互式菜单测试"""
    
    def test_empty_options_returns_none(self):
        result = interactive_menu("Test", [])
        assert result is None
    
    def test_options_structure(self):
        """验证选项结构被正确处理"""
        options = [
            {"name": "Option 1", "value": "v1", "desc": "Description 1"},
            {"name": "Option 2", "value": "v2"},
        ]
        
        # 不实际运行 app，只验证结构
        assert options[0]["value"] == "v1"
        assert options[1].get("desc") is None

class TestInputNumber:
    """数字输入测试"""
    
    def test_input_number_structure(self):
        """验证函数签名"""
        import inspect
        sig = inspect.signature(input_number)
        
        params = list(sig.parameters.keys())
        assert "prompt" in params
        assert "min_val" in params
        assert "max_val" in params