"""内置工具"""
from .read import ReadTool
from .glob import GlobTool
from .grep import GrepTool
from .write import WriteTool
from .edit import EditTool
from .bash import BashTool
from .ask_user import AskUserQuestionTool

# 导出所有工具类
__all__ = [
    "ReadTool",
    "GlobTool",
    "GrepTool",
    "WriteTool",
    "EditTool",
    "BashTool",
    "AskUserQuestionTool",
]


def register_all_tools(registry):
    """注册所有内置工具"""
    registry.register(ReadTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(BashTool())
    registry.register(AskUserQuestionTool())