"""路径工具模块测试"""
import os
import pytest
import tempfile
from pathlib import Path

from claude_code.utils.paths import (
    resolve_path,
    is_hidden,
    is_supported_extension,
    get_extension,
    expand_glob,
    get_relative_display,
    SUPPORTED_EXTENSIONS,
)

class TestResolvePath:
    """resolve_path 函数测试"""
    
    def test_empty_string(self):
        assert resolve_path("") == ""
    
    def test_strip_quotes(self):
        result = resolve_path('"some/path"')
        assert '"' not in result
    
    def test_relative_to_absolute(self):
        result = resolve_path("./test.py")
        assert os.path.isabs(result)
    
    def test_normalize_path(self):
        result = resolve_path("./foo/../bar")
        assert ".." not in result

class TestIsHidden:
    """is_hidden 函数测试"""
    
    def test_hidden_file(self):
        assert is_hidden(".gitignore") is True
        assert is_hidden("/path/to/.env") is True
    
    def test_normal_file(self):
        assert is_hidden("main.py") is False
        assert is_hidden("/path/to/config.json") is False
    
    def test_empty_path(self):
        assert is_hidden("") is False

class TestIsSupportedExtension:
    """is_supported_extension 函数测试"""
    
    def test_python_file(self):
        assert is_supported_extension("main.py") is True
    
    def test_javascript_file(self):
        assert is_supported_extension("app.js") is True
        assert is_supported_extension("component.tsx") is True
    
    def test_unsupported_file(self):
        assert is_supported_extension("image.png") is False
        assert is_supported_extension("video.mp4") is False
    
    def test_case_insensitive(self):
        assert is_supported_extension("README.MD") is True
        assert is_supported_extension("config.JSON") is True
    
    def test_empty_path(self):
        assert is_supported_extension("") is False

class TestGetExtension:
    """get_extension 函数测试"""
    
    def test_normal_extension(self):
        assert get_extension("main.py") == "py"
        assert get_extension("config.json") == "json"
    
    def test_uppercase_extension(self):
        assert get_extension("README.MD") == "md"
    
    def test_no_extension(self):
        assert get_extension("Makefile") == ""
    
    def test_empty_path(self):
        assert get_extension("") == ""

class TestExpandGlob:
    """expand_glob 函数测试"""
    
    def test_empty_pattern(self):
        assert expand_glob("") == []
    
    def test_single_file(self):
        # 创建临时文件测试
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            temp_path = f.name
        
        try:
            result = expand_glob(temp_path)
            assert len(result) == 1
            assert result[0] == os.path.normpath(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_nonexistent_file(self):
        result = expand_glob("/nonexistent/path/file.py")
        assert result == []
    
    def test_glob_pattern(self):
        # 创建临时目录和文件
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试文件
            Path(tmpdir, "a.py").touch()
            Path(tmpdir, "b.py").touch()
            Path(tmpdir, "c.txt").touch()
            
            pattern = os.path.join(tmpdir, "*.py")
            result = expand_glob(pattern)
            
            assert len(result) == 2
            assert all(p.endswith(".py") for p in result)

class TestGetRelativeDisplay:
    """get_relative_display 函数测试"""
    
    def test_empty_path(self):
        assert get_relative_display("") == ""
    
    def test_same_directory(self):
        cwd = os.getcwd()
        full_path = os.path.join(cwd, "test.py")
        result = get_relative_display(full_path, cwd)
        assert result == "test.py"
    
    def test_subdirectory(self):
        cwd = os.getcwd()
        full_path = os.path.join(cwd, "src", "main.py")
        result = get_relative_display(full_path, cwd)
        assert "src" in result
        assert "main.py" in result