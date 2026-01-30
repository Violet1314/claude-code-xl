"""统计管理模块测试"""
import os
import json
import pytest
import tempfile
from pathlib import Path

from claude_code.core.stats import StatsManager, SessionStats

class TestSessionStats:
    """SessionStats 数据类测试"""
    
    def test_default_values(self):
        stats = SessionStats()
        assert stats.input_tokens == 0
        assert stats.output_tokens == 0
        assert stats.total_tokens == 0
    
    def test_total_calculation(self):
        stats = SessionStats(input_tokens=100, output_tokens=50)
        assert stats.total_tokens == 150
    
    def test_to_dict(self):
        stats = SessionStats(input_tokens=100, output_tokens=50)
        result = stats.to_dict()
        
        assert result["input"] == 100
        assert result["output"] == 50
        assert result["total"] == 150

class TestStatsManagerInit:
    """初始化测试"""
    
    def test_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_dir = os.path.join(tmpdir, "stats")
            sm = StatsManager(stats_dir=stats_dir)
            
            assert os.path.isdir(stats_dir)
    
    def test_initial_session_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StatsManager(stats_dir=tmpdir)
            
            assert sm.session.input_tokens == 0
            assert sm.session.output_tokens == 0

class TestStatsManagerUpdate:
    """更新统计测试"""
    
    def test_update_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StatsManager(stats_dir=tmpdir)
            
            messages = [
                {"role": "user", "content": "Hello World"},
            ]
            sm.update_input(messages)
            
            assert sm.session.input_tokens > 0
    
    def test_update_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StatsManager(stats_dir=tmpdir)
            
            sm.update_output("This is a response")
            
            assert sm.session.output_tokens > 0
    
    def test_update_output_accumulates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StatsManager(stats_dir=tmpdir)
            
            sm.update_output("First")
            first_count = sm.session.output_tokens
            
            sm.update_output("Second")
            
            assert sm.session.output_tokens > first_count

class TestStatsManagerReset:
    """重置测试"""
    
    def test_reset_clears_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StatsManager(stats_dir=tmpdir)
            
            sm.update_output("Some text")
            assert sm.session.output_tokens > 0
            
            sm.reset_session()
            
            assert sm.session.input_tokens == 0
            assert sm.session.output_tokens == 0

class TestStatsManagerLoadTotal:
    """加载总统计测试"""
    
    def test_load_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StatsManager(stats_dir=tmpdir)
            
            result = sm.load_total()
            
            assert result["total"]["input"] == 0
            assert result["sessions"] == []
    
    def test_load_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 预先写入数据
            stats_file = os.path.join(tmpdir, "total_stats.json")
            data = {
                "total": {"input": 100, "output": 50, "total": 150},
                "sessions": [],
            }
            with open(stats_file, 'w') as f:
                json.dump(data, f)
            
            sm = StatsManager(stats_dir=tmpdir)
            result = sm.load_total()
            
            assert result["total"]["input"] == 100
    
    def test_load_corrupted_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_file = os.path.join(tmpdir, "total_stats.json")
            with open(stats_file, 'w') as f:
                f.write("invalid json {{{")
            
            sm = StatsManager(stats_dir=tmpdir)
            result = sm.load_total()
            
            # 应返回默认值
            assert result["total"]["input"] == 0

class TestStatsManagerSaveSession:
    """保存会话测试"""
    
    def test_save_creates_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StatsManager(stats_dir=tmpdir)
            
            sm.update_output("Response text")
            result = sm.save_session("model-1", message_count=2)
            
            assert result is True
            
            data = sm.load_total()
            assert len(data["sessions"]) == 1
            assert data["sessions"][0]["model"] == "model-1"
    
    def test_save_zero_messages_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StatsManager(stats_dir=tmpdir)
            
            result = sm.save_session("model-1", message_count=0)
            
            assert result is False
    
    def test_save_accumulates_total(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StatsManager(stats_dir=tmpdir)
            
            sm.update_output("First response")
            sm.save_session("model-1", message_count=2)
            
            sm.update_output("Second response")
            sm.save_session("model-1", message_count=4)
            
            data = sm.load_total()
            assert data["total"]["output"] > 0
    
    def test_finalize_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StatsManager(stats_dir=tmpdir)
            
            sm.update_output("Response")
            sm.save_session("model-1", message_count=2, finalize=True)
            
            data = sm.load_total()
            assert data["sessions"][-1]["finalized"] is True

class TestStatsManagerGetTotal:
    """获取总统计测试"""
    
    def test_get_total_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StatsManager(stats_dir=tmpdir)
            
            result = sm.get_total_stats()
            
            assert result["input"] == 0
            assert result["output"] == 0
            assert result["total"] == 0