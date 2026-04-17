"""工具上下文容器 — 统一管理工具层的全局单例生命周期

解决问题：
  - file_cache / registry / command_safety_checker 等模块级单例分散各处
  - 测试时难以替换
  - 生命周期不受 App 控制

使用方式：
  from claude_code.tools.context import tool_context

  # 获取单例
  cache = tool_context.file_cache
  reg = tool_context.registry

  # 测试时替换
  tool_context.file_cache = MockFileCache()

  # 重置（测试 teardown）
  tool_context.reset()
"""

from typing import Optional

from .base import ToolRegistry
from .file_cache import FileCacheManager
from .command_safety import CommandSafetyChecker


class ToolContext:
    """工具层全局单例容器

    所有工具层组件通过此容器获取依赖，而非直接 import 模块级变量。
    这使得：
    1. 生命周期由 App 控制（初始化/重置）
    2. 测试时可以替换为 mock
    3. 单例来源唯一，不会出现多实例问题
    """

    def __init__(self):
        self._registry: Optional[ToolRegistry] = None
        self._file_cache: Optional[FileCacheManager] = None
        self._safety_checker: Optional[CommandSafetyChecker] = None
        self._permission_manager = None
        self._tool_executor = None
        self._path_manager = None

    @property
    def registry(self) -> ToolRegistry:
        """全局工具注册表"""
        if self._registry is None:
            self._registry = ToolRegistry()
        return self._registry

    @registry.setter
    def registry(self, value: ToolRegistry) -> None:
        self._registry = value

    @property
    def file_cache(self) -> FileCacheManager:
        """全局文件缓存管理器"""
        if self._file_cache is None:
            self._file_cache = FileCacheManager()
        return self._file_cache

    @file_cache.setter
    def file_cache(self, value: FileCacheManager) -> None:
        self._file_cache = value

    @property
    def safety_checker(self) -> CommandSafetyChecker:
        """全局命令安全检查器"""
        if self._safety_checker is None:
            self._safety_checker = CommandSafetyChecker()
        return self._safety_checker

    @safety_checker.setter
    def safety_checker(self, value: CommandSafetyChecker) -> None:
        self._safety_checker = value

    def register(self, name: str, instance: object) -> None:
        """注册单例到上下文（用于 App 初始化时统一注册）"""
        if name == "registry":
            self._registry = instance
        elif name == "file_cache":
            self._file_cache = instance
        elif name == "safety_checker":
            self._safety_checker = instance
        elif name == "permission_manager":
            self._permission_manager = instance
        elif name == "tool_executor":
            self._tool_executor = instance
        elif name == "path_manager":
            self._path_manager = instance
        else:
            setattr(self, f"_{name}", instance)

    def clear(self) -> None:
        """清理所有单例（用于 App 退出时统一清理）"""
        if self._file_cache is not None:
            self._file_cache.clear()
        self._registry = None
        self._file_cache = None
        self._safety_checker = None
        self._permission_manager = None
        self._tool_executor = None
        self._path_manager = None

    def reset(self) -> None:
        """重置所有单例（用于测试 teardown 或 App 重启）"""
        self.clear()


# 全局唯一上下文实例
tool_context = ToolContext()
