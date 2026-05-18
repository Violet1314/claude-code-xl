"""项目记忆文件功能测试"""
import pytest
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestProjectMemory:
    """项目记忆文件测试"""

    def _create_mock_app(self, active_path: str) -> MagicMock:
        """创建一个带有 _load_project_memory 方法的 mock app"""
        from claude_code.app import Application
        app = MagicMock(spec=Application)
        app.path_manager = MagicMock()
        app.path_manager.active_path = active_path
        # 绑定真实方法
        app._load_project_memory = Application._load_project_memory.__get__(app, Application)
        return app

    def test_load_project_memory_exists(self):
        """测试项目记忆文件存在时加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建 .claude/CLAUDE.md
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            memory_file = claude_dir / "CLAUDE.md"
            memory_file.write_text("# 项目说明\n这是一个测试项目", encoding='utf-8')

            app = self._create_mock_app(tmpdir)
            result = app._load_project_memory()

            assert result is not None
            assert "项目说明" in result
            assert "项目记忆" in result

    def test_load_project_memory_not_exists(self):
        """测试项目记忆文件不存在时返回 None"""
        with tempfile.TemporaryDirectory() as tmpdir:
            app = self._create_mock_app(tmpdir)
            result = app._load_project_memory()

            assert result is None

    def test_load_project_memory_empty_file(self):
        """测试空的项目记忆文件返回 None"""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            memory_file = claude_dir / "CLAUDE.md"
            memory_file.write_text("   \n  \n", encoding='utf-8')

            app = self._create_mock_app(tmpdir)
            result = app._load_project_memory()

            assert result is None

    def test_load_project_memory_truncation(self):
        """测试过长的项目记忆文件被截断"""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            claude_dir.mkdir()
            memory_file = claude_dir / "CLAUDE.md"
            # 创建超长内容
            long_content = "x" * 5000
            memory_file.write_text(long_content, encoding='utf-8')

            app = self._create_mock_app(tmpdir)
            result = app._load_project_memory()

            assert result is not None
            assert "截断" in result
            assert len(result) < len(long_content) + 500  # 加上标题等额外文本
