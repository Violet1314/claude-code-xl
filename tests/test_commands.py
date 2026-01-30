"""命令系统测试"""
import pytest
from typing import List

from claude_code.commands.base import Command
from claude_code.commands.registry import CommandRegistry
from claude_code.commands.handlers import (
    HelpCommand,
    QuitCommand,
    BUILTIN_COMMANDS,
)

class MockCommand(Command):
    """测试用命令"""
    name = "mock"
    description = "Mock command for testing"
    aliases = ["m", "test"]
    
    def __init__(self, app=None):
        super().__init__(app)
        self.executed = False
        self.last_args = []
    
    def execute(self, args: List[str]) -> None:
        self.executed = True
        self.last_args = args

class TestCommand:
    """Command 基类测试"""
    
    def test_command_attributes(self):
        cmd = MockCommand()
        assert cmd.name == "mock"
        assert cmd.description == "Mock command for testing"
        assert "m" in cmd.aliases
    
    def test_command_with_app(self):
        mock_app = object()
        cmd = MockCommand(app=mock_app)
        assert cmd.app is mock_app
    
    def test_get_help(self):
        cmd = MockCommand()
        assert cmd.get_help() == cmd.description

class TestCommandRegistry:
    """CommandRegistry 测试"""
    
    def test_register_command(self):
        registry = CommandRegistry()
        registry.register(MockCommand)
        
        assert registry.has("mock")
    
    def test_get_by_name(self):
        registry = CommandRegistry()
        registry.register(MockCommand)
        
        cmd = registry.get("mock")
        assert cmd is not None
        assert cmd.name == "mock"
    
    def test_get_by_alias(self):
        registry = CommandRegistry()
        registry.register(MockCommand)
        
        cmd = registry.get("m")
        assert cmd is not None
        assert cmd.name == "mock"
    
    def test_get_with_slash(self):
        registry = CommandRegistry()
        registry.register(MockCommand)
        
        cmd = registry.get("/mock")
        assert cmd is not None
    
    def test_get_case_insensitive(self):
        registry = CommandRegistry()
        registry.register(MockCommand)
        
        assert registry.get("MOCK") is not None
        assert registry.get("Mock") is not None
    
    def test_get_nonexistent(self):
        registry = CommandRegistry()
        assert registry.get("nonexistent") is None
    
    def test_has_command(self):
        registry = CommandRegistry()
        registry.register(MockCommand)
        
        assert registry.has("mock") is True
        assert registry.has("m") is True  # alias
        assert registry.has("nonexistent") is False
    
    def test_execute_command(self):
        registry = CommandRegistry()
        registry.register(MockCommand)
        
        registry.execute("/mock arg1 arg2")
        
        cmd = registry.get("mock")
        assert cmd.executed is True
        assert cmd.last_args == ["arg1", "arg2"]
    
    def test_execute_nonexistent(self):
        registry = CommandRegistry()
        result = registry.execute("/nonexistent")
        assert result is None
    
    def test_list_commands(self):
        registry = CommandRegistry()
        registry.register(MockCommand)
        
        commands = registry.list_commands()
        
        assert len(commands) == 1
        assert commands[0]["name"] == "mock"
        assert commands[0]["description"] == "Mock command for testing"
    
    def test_command_names(self):
        registry = CommandRegistry()
        registry.register(MockCommand)
        
        names = registry.command_names
        assert "/mock" in names

class TestBuiltinCommands:
    """内置命令测试"""
    
    def test_all_commands_have_name(self):
        for cmd_class in BUILTIN_COMMANDS:
            assert cmd_class.name != "", f"{cmd_class} missing name"
    
    def test_all_commands_have_description(self):
        for cmd_class in BUILTIN_COMMANDS:
            assert cmd_class.description != "", f"{cmd_class} missing description"
    
    def test_quit_returns_true(self):
        cmd = QuitCommand()
        result = cmd.execute([])
        assert result is True
    
    def test_help_executes_without_error(self):
        cmd = HelpCommand()
        try:
            cmd.execute([])
        except Exception as e:
            pytest.fail(f"HelpCommand raised: {e}")
    
    def test_register_all_builtin(self):
        registry = CommandRegistry()
        for cmd_class in BUILTIN_COMMANDS:
            registry.register(cmd_class)
        
        assert registry.has("help")
        assert registry.has("quit")
        assert registry.has("model")
        assert registry.has("add")