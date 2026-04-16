"""PathManager 路径管理器测试"""
import os
import sys
import tempfile
import pytest

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from claude_code.core.path_manager import PathManager, get_path_manager, reset_path_manager


class TestPathManagerInit:
    """初始化测试"""

    def test_default_init_uses_workplace(self):
        """默认初始化使用 workplace"""
        pm = PathManager()
        assert pm.is_workplace_mode is True
        assert os.path.isabs(pm.active_path)

    def test_init_with_absolute_path(self):
        """使用绝对路径初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager(project_root=tmpdir)
            assert pm.active_path == os.path.normpath(tmpdir)
            assert pm.is_workplace_mode is False

    def test_init_rejects_relative_path(self):
        """相对路径被忽略，回退到 workplace"""
        pm = PathManager(project_root="relative/path")
        assert pm.is_workplace_mode is True


class TestPathManagerResolve:
    """路径解析测试"""

    def test_resolve_absolute_within_root(self):
        """根目录内的绝对路径正常解析"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager(project_root=tmpdir)
            result = pm.resolve(os.path.join(tmpdir, "src", "file.py"))
            expected = os.path.normpath(os.path.join(tmpdir, "src", "file.py"))
            assert result == expected

    def test_resolve_relative_path(self):
        """相对路径基于 active_path 解析"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager(project_root=tmpdir)
            result = pm.resolve("src/file.py")
            expected = os.path.normpath(os.path.join(tmpdir, "src", "file.py"))
            assert result == expected

    def test_resolve_empty_path(self):
        """空路径返回 active_path"""
        pm = PathManager()
        result = pm.resolve("")
        assert result == pm.active_path

    def test_resolve_workplace_relative(self):
        """workplace 模式下相对路径基于 workplace 解析"""
        pm = PathManager()
        result = pm.resolve("test.py")
        expected = os.path.normpath(os.path.join(pm.workplace, "test.py"))
        assert result == expected


class TestPathManagerSecurity:
    """安全边界测试"""

    def test_is_within_boundary_within_root(self):
        """根目录下的路径在边界内"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager(project_root=tmpdir)
            assert pm.is_within_boundary(os.path.join(tmpdir, "src", "file.py")) is True

    def test_is_within_boundary_outside_root(self):
        """根目录外的路径不在边界内"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager(project_root=tmpdir)
            outside = os.path.join(os.path.dirname(tmpdir), "outside_file.py")
            assert pm.is_within_boundary(outside) is False

    def test_is_within_boundary_root_itself(self):
        """根目录本身在边界内"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager(project_root=tmpdir)
            assert pm.is_within_boundary(tmpdir) is True


class TestPathManagerSetPath:
    """路径切换测试"""

    def test_set_absolute_path(self):
        """设置绝对路径成功"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager()
            result = pm.set_active_path(tmpdir)
            assert result is True
            assert pm.active_path == os.path.normpath(tmpdir)
            assert pm.is_workplace_mode is False

    def test_set_relative_path_rejected(self):
        """设置相对路径被拒绝"""
        pm = PathManager()
        result = pm.set_active_path("relative/path")
        assert result is False

    def test_set_nonexistent_path(self):
        """设置不存在的路径也成功（模型可能要创建项目）"""
        pm = PathManager()
        # 使用一个合法但不存在的路径
        fake_path = os.path.join(tempfile.gettempdir(), "_pathmanager_test_nonexist_12345")
        result = pm.set_active_path(fake_path)
        assert result is True
        # 清理
        if os.path.exists(fake_path):
            os.rmdir(fake_path)


class TestPathManagerEnvironmentText:
    """路径环境文本测试"""

    def test_env_text_contains_paths(self):
        """环境文本包含路径信息"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager(project_root=tmpdir)
            text = pm.get_environment_text()
            assert tmpdir in text or os.path.normpath(tmpdir) in text
            assert "操作根目录" in text
            assert "路径规则" in text

    def test_env_text_not_empty(self):
        """环境文本不为空"""
        pm = PathManager()
        text = pm.get_environment_text()
        assert len(text) > 0

    def test_env_text_workplace_mode(self):
        """workplace 模式下环境文本包含提示"""
        pm = PathManager()
        text = pm.get_environment_text()
        assert "安全隔离" in text or "workplace" in text.lower()


class TestPathManagerWorkplaceIsolation:
    """Workplace 安全隔离测试"""

    def test_workplace_is_absolute(self):
        """workplace 路径是绝对路径"""
        pm = PathManager()
        assert os.path.isabs(pm.workplace)

    def test_workplace_dir_exists(self):
        """workplace 目录存在"""
        pm = PathManager()
        assert os.path.isdir(pm.workplace)

    def test_default_active_path_is_workplace(self):
        """默认 active_path 等于 workplace"""
        pm = PathManager()
        assert pm.active_path == pm.workplace


class TestPathManagerNormalize:
    """路径规范化测试"""

    def test_normalize_removes_trailing_slash(self):
        """去除尾部斜杠"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager(project_root=tmpdir)
            # resolve 内部会自动 normpath
            result = pm.resolve(tmpdir + os.sep)
            assert not result.endswith(os.sep) or result == os.path.normpath(tmpdir + os.sep)

    def test_normalize_handles_double_sep(self):
        """处理双分隔符"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager(project_root=tmpdir)
            result = pm.resolve(os.path.join(tmpdir, "src", "file.py"))
            # 不应包含连续分隔符
            assert os.sep + os.sep not in result


class TestPathManagerGlobalSingleton:
    """全局单例测试"""

    def setup_method(self):
        reset_path_manager()

    def test_get_path_manager(self):
        """获取全局实例"""
        pm = get_path_manager()
        assert isinstance(pm, PathManager)

    def test_singleton_same_instance(self):
        """多次获取返回同一实例"""
        pm1 = get_path_manager()
        pm2 = get_path_manager()
        assert pm1 is pm2

    def test_reset_returns_new_instance(self):
        """重置后返回新实例"""
        pm1 = get_path_manager()
        pm2 = reset_path_manager()
        assert pm1 is not pm2


class TestPathManagerRelativePath:
    """相对路径显示测试"""

    def test_get_relative_path(self):
        """绝对路径转相对路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager(project_root=tmpdir)
            abs_path = os.path.join(tmpdir, "src", "app.py")
            rel = pm.get_relative_path(abs_path)
            assert rel == os.path.join("src", "app.py")

    def test_get_relative_path_outside_root(self):
        """根目录外的路径返回原路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PathManager(project_root=tmpdir)
            outside = os.path.join(os.path.dirname(tmpdir), "other.py")
            rel = pm.get_relative_path(outside)
            assert rel == outside


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
