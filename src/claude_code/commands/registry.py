"""命令注册表 - 管理所有命令"""
from typing import Dict, List, Optional, Type, TYPE_CHECKING

from claude_code.commands.base import Command

if TYPE_CHECKING:
    from claude_code.app import Application

class CommandRegistry:
    """命令注册表"""
    
    def __init__(self):
        self._commands: Dict[str, Command] = {}
        self._aliases: Dict[str, str] = {}
    
    def register(self, command_class: Type[Command], app: "Application" = None) -> None:
        """
        注册命令
        
        Args:
            command_class: 命令类
            app: 应用实例
        """
        instance = command_class(app)
        name = instance.name.lower()
        
        self._commands[name] = instance
        
        # 注册别名
        for alias in instance.aliases:
            self._aliases[alias.lower()] = name
    
    def get(self, name: str) -> Optional[Command]:
        """
        获取命令实例
        
        Args:
            name: 命令名称或别名
            
        Returns:
            命令实例或 None
        """
        name = name.lower().lstrip('/')
        
        # 直接匹配
        if name in self._commands:
            return self._commands[name]
        
        # 别名匹配
        if name in self._aliases:
            return self._commands[self._aliases[name]]
        
        return None
    
    def execute(self, command_str: str) -> Optional[bool]:
        """
        解析并执行命令
        
        Args:
            command_str: 完整命令字符串（如 "/help" 或 "/add file.py"）
            
        Returns:
            命令执行结果
        """
        parts = command_str.strip().split()
        if not parts:
            return None
        
        name = parts[0]
        args = parts[1:]
        
        command = self.get(name)
        if command:
            return command.execute(args)
        
        return None
    
    def has(self, name: str) -> bool:
        """
        检查命令是否存在
        
        Args:
            name: 命令名称
            
        Returns:
            是否存在
        """
        return self.get(name) is not None
    
    def list_commands(self) -> List[Dict[str, str]]:
        """
        列出所有命令
        
        Returns:
            命令信息列表
        """
        return [
            {"name": cmd.name, "description": cmd.description, "aliases": cmd.aliases}
            for cmd in self._commands.values()
            if not cmd.hidden
        ]
    
    @property
    def command_names(self) -> List[str]:
        """获取所有命令名称"""
        return [f"/{name}" for name in self._commands.keys()]