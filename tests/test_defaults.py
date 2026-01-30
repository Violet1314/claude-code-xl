"""默认配置模块测试"""
import pytest
from claude_code.config.defaults import (
    FILE, API, CONVERSATION, UI,
    FileDefaults, APIDefaults,
    VERSION, APP_NAME,
)

class TestFileDefaults:
    """文件配置测试"""
    
    def test_max_file_size(self):
        assert FILE.MAX_FILE_SIZE == 100 * 1024
    
    def test_max_file_count(self):
        assert FILE.MAX_FILE_COUNT == 30
    
    def test_max_total_chars(self):
        assert FILE.MAX_TOTAL_CHARS == 500_000
    
    def test_immutable(self):
        """确保配置不可修改"""
        with pytest.raises(Exception):  # frozen=True 会抛出 FrozenInstanceError
            FILE.MAX_FILE_SIZE = 999

class TestAPIDefaults:
    """API 配置测试"""
    
    def test_max_tokens(self):
        assert API.MAX_TOKENS == 4096
    
    def test_temperature_range(self):
        assert 0.0 <= API.TEMPERATURE <= 2.0
    
    def test_max_retries(self):
        assert API.MAX_RETRIES >= 1
    
    def test_timeouts_positive(self):
        assert API.CONNECT_TIMEOUT > 0
        assert API.READ_TIMEOUT > 0
        assert API.WRITE_TIMEOUT > 0
        assert API.POOL_TIMEOUT > 0
    
    def test_read_timeout_longest(self):
        """读取超时应该最长（流式响应需要）"""
        assert API.READ_TIMEOUT >= API.CONNECT_TIMEOUT
        assert API.READ_TIMEOUT >= API.WRITE_TIMEOUT

class TestConversationDefaults:
    """对话配置测试"""
    
    def test_context_limit(self):
        assert CONVERSATION.DEFAULT_CONTEXT_LIMIT > 0
    
    def test_summary_tokens(self):
        assert CONVERSATION.SUMMARY_MAX_TOKENS > 0
        assert CONVERSATION.SUMMARY_MAX_TOKENS < API.MAX_TOKENS

class TestUIDefaults:
    """UI 配置测试"""
    
    def test_width_range(self):
        assert UI.MIN_WIDTH < UI.MAX_WIDTH
        assert UI.MIN_WIDTH > 0

class TestAppInfo:
    """应用信息测试"""
    
    def test_version_format(self):
        """版本号应为 x.y.z 格式"""
        parts = VERSION.split('.')
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)
    
    def test_app_name(self):
        assert len(APP_NAME) > 0