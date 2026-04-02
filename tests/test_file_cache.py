"""文件缓存管理器测试"""
import os
import tempfile
import pytest
from pathlib import Path

from claude_code.tools.file_cache import (
    FileCacheManager,
    CachedFile,
    file_cache,
)

class TestCachedFile:
    """CachedFile 数据类测试"""

    def test_create(self):
        """测试创建缓存文件"""
        cached = CachedFile(
            base_content="Hello World",
            base_hash="abc123",
        )
        assert cached.base_content == "Hello World"
        assert cached.base_hash == "abc123"
        assert cached.version == 0

    def test_get_content_hash(self):
        """测试获取内容 hash"""
        cached = CachedFile(
            base_content="Hello",
            base_hash="abc123",
        )
        hash1 = cached.get_content_hash()
        assert isinstance(hash1, str)
        assert len(hash1) == 16

class TestFileCacheManager:
    """FileCacheManager 测试"""

    def test_init(self):
        """测试初始化"""
        cache = FileCacheManager()
        assert cache._cache == {}

    def test_read_file_first_time(self):
        """测试首次读取"""
        cache = FileCacheManager()
        result = cache.read_file("/test.py", "Hello World")

        assert result["cached"] is False
        assert result["content"] == "Hello World"
        assert result["version"] == 0
        assert result["changed"] is False
        assert "[file:test.py:v0]" in result["reference"]

    def test_read_file_cached(self):
        """测试缓存命中"""
        cache = FileCacheManager()
        cache.read_file("/test.py", "Hello World")

        result = cache.read_file("/test.py", "Hello World")
        assert result["cached"] is True
        assert result["content"] == "Hello World"
        assert result["version"] == 0

    def test_read_file_external_change(self):
        """测试检测外部修改"""
        cache = FileCacheManager()
        cache.read_file("/test.py", "Original")

        result = cache.read_file("/test.py", "Modified externally")
        assert result["cached"] is False
        assert result["changed"] is True
        assert result["version"] == 1
        assert result["content"] == "Modified externally"

    def test_read_file_no_content(self):
        """测试从磁盘读取"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("disk content")
            f.flush()
            temp_path = f.name

        try:
            cache = FileCacheManager()
            result = cache.read_file(temp_path)
            assert result["content"] == "disk content"
            assert result["cached"] is False
        finally:
            os.unlink(temp_path)

    def test_read_file_force_refresh(self):
        """测试强制刷新"""
        cache = FileCacheManager()
        cache.read_file("/test.py", "Version 1")

        result = cache.read_file("/test.py", "Version 2", force_refresh=True)
        assert result["cached"] is False
        assert result["content"] == "Version 2"

    def test_apply_write_new_file(self):
        """测试写入新文件"""
        cache = FileCacheManager()
        result = cache.apply_write("/new.py", "New content")

        assert result["success"] is True
        assert result["version"] == 1
        assert "[file:new.py:v1]" in result["reference"]

    def test_apply_write_existing_file(self):
        """测试覆盖已有文件"""
        cache = FileCacheManager()
        cache.read_file("/test.py", "Original")

        result = cache.apply_write("/test.py", "Overwritten")
        assert result["success"] is True
        assert result["version"] == 1

        # 验证缓存已更新
        read_result = cache.read_file("/test.py", "Overwritten")
        assert read_result["cached"] is True
        assert read_result["content"] == "Overwritten"

    def test_apply_write_version_increment(self):
        """测试版本递增"""
        cache = FileCacheManager()
        cache.read_file("/test.py", "V0")

        r1 = cache.apply_write("/test.py", "V1")
        assert r1["version"] == 1

        r2 = cache.apply_write("/test.py", "V2")
        assert r2["version"] == 2

        r3 = cache.apply_write("/test.py", "V3")
        assert r3["version"] == 3

    def test_clear(self):
        """测试清空缓存"""
        cache = FileCacheManager()
        cache.read_file("/a.py", "A")
        cache.read_file("/b.py", "B")

        cache.clear()
        assert cache._cache == {}

        # 清空后重新读取应该是未缓存
        result = cache.read_file("/a.py", "A")
        assert result["cached"] is False

    def test_multiple_files(self):
        """测试多文件缓存"""
        cache = FileCacheManager()
        cache.read_file("/a.py", "File A")
        cache.read_file("/b.py", "File B")
        cache.read_file("/c.py", "File C")

        assert len(cache._cache) == 3

        r_a = cache.read_file("/a.py", "File A")
        r_b = cache.read_file("/b.py", "File B")
        assert r_a["cached"] is True
        assert r_b["cached"] is True

    def test_reference_format(self):
        """测试引用格式"""
        cache = FileCacheManager()
        result = cache.read_file("/path/to/app.py", "content")
        assert result["reference"] == "[file:app.py:v0]"

        cache.apply_write("/path/to/app.py", "new content")
        result2 = cache.read_file("/path/to/app.py", "new content")
        assert result2["reference"] == "[file:app.py:v1]"

    def test_global_instance(self):
        """测试全局实例"""
        assert file_cache is not None
        assert isinstance(file_cache, FileCacheManager)