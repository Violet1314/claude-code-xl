"""文件管理模块测试"""
import os
import pytest
import tempfile
from pathlib import Path

from claude_code.core.files import FileManager, AttachedFile

class TestFileManagerInit:
    """初始化测试"""
    
    def test_default_init(self):
        fm = FileManager()
        assert fm.count == 0
        assert fm.is_empty
    
    def test_custom_limits(self):
        fm = FileManager(
            max_file_size=1024,
            max_file_count=5,
            max_total_chars=10000,
        )
        assert fm.max_file_size == 1024
        assert fm.max_file_count == 5
        assert fm.max_total_chars == 10000

class TestFileManagerProperties:
    """属性测试"""
    
    def test_count_and_is_empty(self):
        fm = FileManager()
        assert fm.count == 0
        assert fm.is_empty
    
    def test_total_chars_and_tokens(self):
        fm = FileManager()
        assert fm.total_chars == 0
        assert fm.total_tokens == 0

class TestFileManagerAdd:
    """添加文件测试"""
    
    def test_add_single_file(self):
        fm = FileManager()
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write("print('hello')")
            temp_path = f.name
        
        try:
            added, skipped = fm.add([temp_path])
            assert len(added) == 1
            assert len(skipped) == 0
            assert fm.count == 1
        finally:
            os.unlink(temp_path)
    
    def test_add_nonexistent_file(self):
        fm = FileManager()
        added, skipped = fm.add(["/nonexistent/file.py"])
        
        assert len(added) == 0
        assert len(skipped) == 1
        assert "不存在" in skipped[0][1]
    
    def test_add_unsupported_extension(self):
        fm = FileManager()
        
        with tempfile.NamedTemporaryFile(suffix='.xyz', delete=False) as f:
            temp_path = f.name
        
        try:
            added, skipped = fm.add([temp_path])
            assert len(added) == 0
            assert "不支持" in skipped[0][1]
        finally:
            os.unlink(temp_path)
    
    def test_add_duplicate(self):
        fm = FileManager()
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write("code")
            temp_path = f.name
        
        try:
            fm.add([temp_path])
            added, skipped = fm.add([temp_path])
            
            assert len(added) == 0
            assert "已挂载" in skipped[0][1]
        finally:
            os.unlink(temp_path)
    
    def test_add_hidden_file(self):
        fm = FileManager()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            hidden_path = os.path.join(tmpdir, ".hidden.py")
            Path(hidden_path).write_text("secret")
            
            added, skipped = fm.add([hidden_path])
            assert len(added) == 0
            assert "隐藏" in skipped[0][1]
    
    def test_add_glob_pattern(self):
        fm = FileManager()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建多个 .py 文件
            for name in ["a.py", "b.py", "c.txt"]:
                Path(tmpdir, name).write_text(f"# {name}")
            
            pattern = os.path.join(tmpdir, "*.py")
            added, skipped = fm.add([pattern])
            
            assert len(added) == 2
            assert fm.count == 2
    
    def test_add_max_count_limit(self):
        fm = FileManager(max_file_count=2)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = []
            for i in range(5):
                p = Path(tmpdir, f"file{i}.py")
                p.write_text(f"# file {i}")
                paths.append(str(p))
            
            added, skipped = fm.add(paths)
            
            assert len(added) == 2
            assert fm.count == 2

class TestFileManagerDrop:
    """移除文件测试"""
    
    def test_drop_single_file(self):
        fm = FileManager()
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write("code")
            temp_path = f.name
        
        try:
            fm.add([temp_path])
            assert fm.count == 1
            
            removed = fm.drop([temp_path])
            assert len(removed) == 1
            assert fm.count == 0
        finally:
            os.unlink(temp_path)
    
    def test_drop_all(self):
        fm = FileManager()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["a.py", "b.py"]:
                Path(tmpdir, name).write_text("code")
            
            fm.add([os.path.join(tmpdir, "*.py")])
            assert fm.count == 2
            
            removed = fm.drop(["all"])
            assert len(removed) == 2
            assert fm.is_empty
    
    def test_drop_by_basename(self):
        fm = FileManager()
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write("code")
            temp_path = f.name
            basename = os.path.basename(temp_path)
        
        try:
            fm.add([temp_path])
            removed = fm.drop([basename])
            assert len(removed) == 1
        finally:
            os.unlink(temp_path)

class TestFileManagerRefresh:
    """刷新测试"""
    
    def test_refresh_updated_file(self):
        fm = FileManager()
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write("original")
            temp_path = f.name
        
        try:
            fm.add([temp_path])
            
            # 修改文件
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write("updated content")
            
            refreshed, removed = fm.refresh()
            
            assert len(refreshed) == 1
            assert len(removed) == 0
            assert "updated" in fm.get_files()[temp_path].content
        finally:
            os.unlink(temp_path)
    
    def test_refresh_deleted_file(self):
        fm = FileManager()
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write("code")
            temp_path = f.name
        
        fm.add([temp_path])
        os.unlink(temp_path)  # 删除文件
        
        refreshed, removed = fm.refresh()
        
        assert len(refreshed) == 0
        assert len(removed) == 1
        assert fm.is_empty

class TestFileManagerBuildContext:
    """构建上下文测试"""
    
    def test_empty_context(self):
        fm = FileManager()
        assert fm.build_context() is None
    
    def test_context_format(self):
        fm = FileManager()
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write("print('test')")
            temp_path = f.name
        
        try:
            fm.add([temp_path])
            context = fm.build_context()
            
            assert context is not None
            assert "📎" in context
            assert "```py" in context
            assert "print('test')" in context
        finally:
            os.unlink(temp_path)

class TestFileManagerClear:
    """清空测试"""
    
    def test_clear(self):
        fm = FileManager()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["a.py", "b.py"]:
                Path(tmpdir, name).write_text("code")
            
            fm.add([os.path.join(tmpdir, "*.py")])
            
            count = fm.clear()
            assert count == 2
            assert fm.is_empty