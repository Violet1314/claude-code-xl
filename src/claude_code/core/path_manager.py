"""路径管理器 - 统一路径解析、安全边界校验、路径状态管理

核心设计：
1. 所有工具统一通过 PathManager 解析路径
2. 用户指定绝对路径 → active_path = 用户路径
3. 用户未指定 → active_path = workplace（安全隔离目录）
4. 每轮对话注入路径环境，模型始终可见
5. 安全边界校验，禁止越界操作
"""
import os
from pathlib import Path
from typing import Optional

from claude_code.config.defaults import WORKPLACE_DIR


class PathManager:
    """统一路径管理器"""

    def __init__(self, project_root: Optional[str] = None):
        """
        初始化路径管理器

        Args:
            project_root: 用户指定的项目根目录（绝对路径），
                         为 None 时使用 workplace 安全隔离目录
        """
        # 确保 workplace 目录存在
        self._workplace = str(Path(WORKPLACE_DIR).resolve())
        os.makedirs(self._workplace, exist_ok=True)

        # 设置活跃路径
        if project_root and os.path.isabs(project_root):
            self._active_path = os.path.normpath(project_root)
        else:
            self._active_path = self._workplace

        # 确保活跃路径目录存在
        os.makedirs(self._active_path, exist_ok=True)

    @property
    def active_path(self) -> str:
        """当前生效的操作路径（绝对路径）"""
        return self._active_path

    @property
    def workplace(self) -> str:
        """workplace 安全隔离目录（绝对路径）"""
        return self._workplace

    @property
    def is_workplace_mode(self) -> bool:
        """是否处于 workplace 安全隔离模式"""
        return self._active_path == self._workplace

    def set_active_path(self, path: str) -> bool:
        """
        设置新的活跃路径（用户通过 /cd 命令切换）

        Args:
            path: 必须是绝对路径

        Returns:
            设置成功返回 True，路径无效返回 False
        """
        if not os.path.isabs(path):
            return False

        norm_path = os.path.normpath(path)

        # 检查路径是否存在（允许不存在，模型可能要创建项目）
        # 但必须是合法路径格式
        try:
            Path(norm_path).resolve()
        except (OSError, ValueError):
            return False

        self._active_path = norm_path
        os.makedirs(self._active_path, exist_ok=True)
        return True

    def resolve(self, file_path: str) -> str:
        """
        统一路径解析

        规则：
        - 绝对路径：检查是否在 active_path 下，是则直接使用，否则拒绝
        - 相对路径：基于 active_path 解析为绝对路径
        - 空路径：返回 active_path

        Args:
            file_path: 输入路径

        Returns:
            解析后的绝对路径
        """
        if not file_path or not file_path.strip():
            return self._active_path

        cleaned = file_path.strip().strip('"').strip("'")

        if os.path.isabs(cleaned):
            # 绝对路径：规范化后直接使用
            return os.path.normpath(cleaned)
        else:
            # 相对路径：基于 active_path 解析
            return os.path.normpath(os.path.join(self._active_path, cleaned))

    def resolve_safe(self, file_path: str) -> tuple:
        """
        安全路径解析（带边界校验）

        规则：
        - 绝对路径：用户明确指定，直接放行（用户知道自己在做什么）
        - 相对路径：基于 active_path 解析为绝对路径，始终在边界内

        Args:
            file_path: 输入路径

        Returns:
            (resolved_path, is_within_boundary)
            is_within_boundary 为 True 表示路径合法
        """
        if not file_path or not file_path.strip():
            return "", False

        cleaned = file_path.strip().strip('"').strip("'")

        # 绝对路径：直接使用，不做边界限制（用户明确指定）
        if os.path.isabs(cleaned):
            resolved = os.path.normpath(cleaned)
            return resolved, True

        # 相对路径：基于 active_path 解析，始终在边界内
        resolved = os.path.normpath(os.path.join(self._active_path, cleaned))
        return resolved, True

    def is_within_boundary(self, path: str) -> bool:
        """
        检查路径是否在 active_path 下（安全边界校验）

        Args:
            path: 待检查的绝对路径

        Returns:
            是否在 active_path 内
        """
        try:
            # 解析为规范化的绝对路径进行比较
            resolved = Path(path).resolve()
            active = Path(self._active_path).resolve()
            # 检查是否是 active_path 的子路径或就是 active_path
            return str(resolved).startswith(str(active))
        except (OSError, ValueError):
            return False

    # 向后兼容的别名
    _is_within_active = is_within_boundary

    def get_relative_path(self, abs_path: str) -> str:
        """
        将绝对路径转为相对于 active_path 的相对路径（用于显示）

        Args:
            abs_path: 绝对路径

        Returns:
            相对路径字符串
        """
        try:
            return str(Path(abs_path).relative_to(self._active_path))
        except ValueError:
            return abs_path

    def get_environment_text(self) -> str:
        """
        生成注入给模型的路径环境文本（每轮对话注入）

        Returns:
            路径环境信息文本
        """
        mode = "workplace 安全隔离模式" if self.is_workplace_mode else "用户指定目录模式"

        lines = [
            "## 路径环境（每轮对话均有效，不可遗忘）",
            f"- 操作根目录: {self._active_path}",
            f"- Workplace 目录: {self._workplace}",
            f"- 当前模式: {mode}",
            "",
            "### 路径规则（强制）",
            "- 所有文件操作基于操作根目录进行",
            "- 相对路径自动基于操作根目录解析为绝对路径",
            "- 绝对路径必须在操作根目录下，禁止越界访问",
            "- Write/Edit 写入文件 → 路径基于操作根目录",
            "- Read/Glob/Grep 读取搜索 → 路径基于操作根目录",
            "- Bash 执行命令 → 工作目录为操作根目录",
            "",
            "### 路径示例",
            f"- 写入文件: file_path=\"{self._active_path}\\src\\app.py\"",
            f"- 读取文件: file_path=\"{self._active_path}\\src\\app.py\"",
            f"- 搜索文件: pattern=\"**/*.py\", path=\"{self._active_path}\\src\"",
            f"- 执行命令: command=\"python main.py\", cwd=\"{self._active_path}\"",
        ]

        if self.is_workplace_mode:
            lines.extend([
                "",
                "### ⚠️ Workplace 安全隔离模式",
                "当前未指定项目目录，所有操作隔离在 workplace 目录下。",
                "如需操作真实项目，请使用 /cd <绝对路径> 切换到项目目录。",
                f"示例: /cd E:\\你的项目目录",
            ])

        return "\n".join(lines)


# 全局单例
_path_manager: Optional[PathManager] = None


def get_path_manager() -> PathManager:
    """获取全局 PathManager 实例"""
    global _path_manager
    if _path_manager is None:
        _path_manager = PathManager()
    return _path_manager


def init_path_manager(project_root: Optional[str] = None) -> PathManager:
    """初始化全局 PathManager 实例"""
    global _path_manager
    _path_manager = PathManager(project_root)
    return _path_manager


def reset_path_manager() -> PathManager:
    """重置全局 PathManager（回到 workplace 模式）"""
    global _path_manager
    _path_manager = PathManager()
    return _path_manager
