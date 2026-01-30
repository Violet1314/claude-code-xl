"""命令基类 - 可扩展的命令接口"""
from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from claude_code.app import Application

class Command(ABC):
    """命令基类"""
    
    # 命令名称（如 /help）
    name: str = ""
    
    # 命令描述
    description: str = ""
    
    # 命令别名
    aliases: List[str] = []
    
    def __init__(self, app: "Application" = None):
        """
        初始化命令
        
        Args:
            app: 应用实例引用
        """
        self.app = app
    
    @abstractmethod
    def execute(self, args: List[str]) -> Optional[bool]:
        """
        执行命令
        
        Args:
            args: 命令参数列表
            
        Returns:
            None 或 bool（用于特殊控制流）
        """
        pass
    
    def get_help(self) -> str:
        """获取命令帮助信息"""
        return self.description