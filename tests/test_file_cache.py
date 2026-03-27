"""文件缓存管理器测试"""
import pytest
import sys
import os
import tempfile
import time

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from claude_code.tools.file_cache import (
    FileCacheManager,
    CachedFile,
    FilePatch,
    file_cache,
)


class TestFilePatch:
    """FilePatch 数据类测试"""

    def test_create_patch(self):
        """测试创建修改记录"""
        patch = FilePatch(
            type="edit",
            old="old text",
            new="new text",
            line=10
        )

        assert patch.type == "edit"
        assert patch.old == "old text"
        assert patch.new == "new text"
        assert patch.line == 10

    def test_patch_timestamp(self):
        """测试时间戳自动生成"""
        before = time.time()
        patch = FilePatch(type="edit")
        after = time.time()

        assert before <= patch.timestamp <= after


class TestCachedFile:
    """CachedFile 数据类测试"""

    def test_create_cached_file(self):
        """测试创建缓存文件"""
        cached = CachedFile(
            base_content="Hello World",
            base_hash="abc123",
        )

        assert cached.base_content == "Hello World"
        assert cached.base_hash == "abc123"
        assert cached.patches == []
        assert cached.version == 0

    def test_get_current_content_no_patches(self):
        """测试无修改时获取当前内容"""
        cached = CachedFile(
            base_content="Original content",
            base_hash="hash123",
        )

        assert cached.get_current_content() == "Original content"

    def test_get_current_content_with_edit_patch(self):
        """测试应用编辑修改"""
        cached = CachedFile(
            base_content="Hello World",
            base_hash="hash123",
        )

        # 添加编辑修改
        cached.patches.append(FilePatch(
            type="edit",
            old="World",
            new="Python"
        ))

        assert cached.get_current_content() == "Hello Python"

    def test_get_current_content_with_write_patch(self):
        """测试应用写入修改"""
        cached = CachedFile(
            base_content="Old content",
            base_hash="hash123",
        )

        # 写入会完全覆盖
        cached.patches.append(FilePatch(
            type="write",
            new="Completely new content"
        ))

        assert cached.get_current_content() == "Completely new content"

    def test_get_content_hash(self):
        """测试获取内容 hash"""
        cached = CachedFile(
            base_content="Test content",
            base_hash="initial",
        )

        hash1 = cached.get_content_hash()
        assert len(hash1) == 16  # MD5 截断到 16 位

        # 内容不变，hash 不变
        hash2 = cached.get_content_hash()
        assert hash1 == hash2

        # 应用修改后 hash 变化
        cached.patches.append(FilePatch(type="write", new="New content"))
        hash3 = cached.get_current_content()
        assert hash3 != cached.base_content


class TestFileCacheManagerInit:
    """初始化测试"""

    def test_init_empty(self):
        """测试空初始化"""
        cache = FileCacheManager()

        assert cache.get_stats()["cached_files"] == 0
        assert cache.get_stats()["cache_hits"] == 0

    def test_init_with_cache_file(self):
        """测试带缓存文件初始化"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"files": {}}')
            temp_path = f.name

        try:
            cache = FileCacheManager(cache_file=temp_path)
            assert cache.get_stats()["cached_files"] == 0
        finally:
            os.unlink(temp_path)


class TestFileCacheManagerRead:
    """读取操作测试"""

    def test_read_file_cache_miss(self):
        """测试缓存未命中"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("print('hello')")
            temp_path = f.name

        try:
            cache = FileCacheManager()

            result = cache.read_file(temp_path)

            assert result["cached"] is False
            assert result["version"] == 0
            assert result["changed"] is False
            assert "print('hello')" in result["content"]
            assert "[file:" in result["reference"]
        finally:
            os.unlink(temp_path)

    def test_read_file_cache_hit(self):
        """测试缓存命中"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            cache = FileCacheManager()

            # 第一次读取
            result1 = cache.read_file(temp_path)
            assert result1["cached"] is False

            # 第二次读取应该命中缓存
            result2 = cache.read_file(temp_path)
            assert result2["cached"] is True
            assert result2["version"] == 0

            # 统计
            stats = cache.get_stats()
            assert stats["cache_hits"] == 1
            assert stats["cache_misses"] == 1
        finally:
            os.unlink(temp_path)

    def test_read_file_with_content_provided(self):
        """测试提供内容时读取"""
        cache = FileCacheManager()

        # 直接提供内容，不实际读取文件
        result = cache.read_file(
            "/fake/path.py",
            content="provided content"
        )

        assert result["cached"] is False
        assert result["content"] == "provided content"

    def test_read_file_force_refresh(self):
        """测试强制刷新"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("original")
            temp_path = f.name

        try:
            cache = FileCacheManager()

            # 第一次读取
            cache.read_file(temp_path)

            # 强制刷新
            result = cache.read_file(temp_path, force_refresh=True)

            assert result["cached"] is False
        finally:
            os.unlink(temp_path)

    def test_read_file_detect_external_change(self):
        """测试检测外部修改"""
        cache = FileCacheManager()

        # 先缓存一个版本
        cache.read_file("/test.py", content="version 1")

        # 模拟外部修改：提供不同内容
        result = cache.read_file("/test.py", content="version 2")

        assert result["changed"] is True
        assert result["version"] == 1  # 版本号增加


class TestFileCacheManagerEdit:
    """编辑操作测试"""

    def test_apply_edit_success(self):
        """测试成功编辑"""
        cache = FileCacheManager()

        # 先缓存文件
        cache.read_file("/test.py", content="Hello World")

        # 应用编辑
        result = cache.apply_edit("/test.py", "World", "Python")

        assert result["success"] is True
        assert result["version"] == 1
        assert "reference" in result
        assert "diff_summary" in result

    def test_apply_edit_not_in_cache(self):
        """测试编辑未缓存的文件"""
        cache = FileCacheManager()

        result = cache.apply_edit("/nonexistent.py", "old", "new")

        assert result["success"] is False
        assert "未在缓存中" in result["error"]

    def test_apply_edit_string_not_found(self):
        """测试找不到要替换的内容"""
        cache = FileCacheManager()

        cache.read_file("/test.py", content="Hello World")

        result = cache.apply_edit("/test.py", "nonexistent", "replacement")

        assert result["success"] is False
        assert "未找到" in result["error"]

    def test_apply_multiple_edits(self):
        """测试多次编辑"""
        cache = FileCacheManager()

        cache.read_file("/test.py", content="Line 1\nLine 2\nLine 3")

        # 第一次编辑
        result1 = cache.apply_edit("/test.py", "Line 1", "Modified 1")
        assert result1["success"] is True
        assert result1["version"] == 1

        # 第二次编辑
        result2 = cache.apply_edit("/test.py", "Line 2", "Modified 2")
        assert result2["success"] is True
        assert result2["version"] == 2


class TestFileCacheManagerWrite:
    """写入操作测试"""

    def test_apply_write_new_file(self):
        """测试写入新文件"""
        cache = FileCacheManager()

        result = cache.apply_write("/new.py", "new content")

        assert result["success"] is True
        assert result["version"] == 1  # 新文件版本从 1 开始（因为 old_version=0）

    def test_apply_write_overwrite(self):
        """测试覆盖已有文件"""
        cache = FileCacheManager()

        # 先缓存
        cache.read_file("/test.py", content="old content")

        # 写入覆盖
        result = cache.apply_write("/test.py", "brand new content")

        assert result["success"] is True
        assert result["version"] == 1


class TestFileCacheManagerReference:
    """引用生成测试"""

    def test_make_reference(self):
        """测试生成引用"""
        cache = FileCacheManager()

        ref = cache._make_reference("/path/to/app.py", 0)

        assert ref == "[file:app.py:v0]"

    def test_make_reference_version_increment(self):
        """测试版本号递增"""
        cache = FileCacheManager()

        ref0 = cache._make_reference("/test.py", 0)
        ref1 = cache._make_reference("/test.py", 1)
        ref2 = cache._make_reference("/test.py", 2)

        assert "v0" in ref0
        assert "v1" in ref1
        assert "v2" in ref2

    def test_make_diff_summary_single_line(self):
        """测试单行 diff 摘要"""
        cache = FileCacheManager()

        summary = cache._make_diff_summary("old", "new")

        assert "old" in summary
        assert "new" in summary

    def test_make_diff_summary_multi_line(self):
        """测试多行 diff 摘要"""
        cache = FileCacheManager()

        old = "line1\nline2\nline3"
        new = "line1\nmodified\nline3"

        summary = cache._make_diff_summary(old, new)

        assert "3行" in summary


class TestFileCacheManagerResultGeneration:
    """结果生成测试"""

    def test_make_read_result(self):
        """测试生成读取结果"""
        cache = FileCacheManager()

        result = cache.make_read_result(
            "/test.py",
            content="print('hello')\nprint('world')",
            show_content=True
        )

        assert "test.py" in result
        assert "[file:" in result
        assert "缓存引用" in result

    def test_make_read_result_with_limit(self):
        """测试带限制的读取结果"""
        cache = FileCacheManager()

        content = "\n".join([f"line {i}" for i in range(100)])
        result = cache.make_read_result(
            "/test.py",
            content=content,
            limit=10
        )

        assert "省略" in result

    def test_make_edit_result_success(self):
        """测试成功编辑结果"""
        cache = FileCacheManager()

        cache.read_file("/test.py", content="Hello World")

        result = cache.make_edit_result(
            "/test.py",
            "World",
            "Python",
            success=True
        )

        assert "编辑成功" in result
        assert "[file:" in result

    def test_make_edit_result_failure(self):
        """测试失败编辑结果"""
        cache = FileCacheManager()

        result = cache.make_edit_result(
            "/test.py",
            "old",
            "new",
            success=False,
            error="测试错误"
        )

        assert "编辑失败" in result
        assert "测试错误" in result


class TestFileCacheManagerStats:
    """统计信息测试"""

    def test_get_stats(self):
        """测试获取统计"""
        cache = FileCacheManager()

        stats = cache.get_stats()

        assert "cache_hits" in stats
        assert "cache_misses" in stats
        assert "cached_files" in stats

    def test_get_cached_files(self):
        """测试获取缓存文件列表"""
        cache = FileCacheManager()

        cache.read_file("/file1.py", content="content1")
        cache.read_file("/file2.py", content="content2")

        files = cache.get_cached_files()

        assert len(files) == 2
        assert all("path" in f and "version" in f for f in files)

    def test_clear(self):
        """测试清空缓存"""
        cache = FileCacheManager()

        cache.read_file("/test.py", content="content")
        cache.read_file("/test.py")  # 命中缓存

        cache.clear()

        assert cache.get_stats()["cached_files"] == 0
        assert cache.get_stats()["cache_hits"] == 0


class TestFileCacheManagerPersistence:
    """持久化测试"""

    def test_save_and_load_cache(self):
        """测试保存和加载缓存"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"files": {}}')
            temp_path = f.name

        try:
            # 创建缓存并添加文件
            cache1 = FileCacheManager(cache_file=temp_path)
            cache1.read_file("/test.py", content="original content")
            cache1.apply_edit("/test.py", "original", "modified")

            # 保存
            cache1.save_cache()

            # 新建缓存管理器加载
            cache2 = FileCacheManager(cache_file=temp_path)
            files = cache2.get_cached_files()

            assert len(files) == 1
            assert files[0]["version"] == 1  # 编辑后版本

        finally:
            os.unlink(temp_path)


class TestFileCacheManagerThreadSafety:
    """线程安全测试"""

    def test_concurrent_reads(self):
        """测试并发读取"""
        import threading

        cache = FileCacheManager()
        results = []

        def read_file(i):
            result = cache.read_file(f"/test{i}.py", content=f"content {i}")
            results.append(result)

        threads = [threading.Thread(target=read_file, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])