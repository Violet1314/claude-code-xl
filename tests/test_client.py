"""API 客户端模块测试"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import httpx

from claude_code.core.client import APIClient
from claude_code.config.defaults import API

class TestAPIClientInit:
    """客户端初始化测试"""
    
    def test_init_with_defaults(self):
        client = APIClient(
            base_url="https://api.example.com/v1",
            api_key="test-key",
        )
        assert client.base_url == "https://api.example.com/v1"
        assert client.api_key == "test-key"
        assert client.max_retries == API.MAX_RETRIES
        client.close()
    
    def test_init_strips_url(self):
        client = APIClient(
            base_url="  https://api.example.com/v1/  ",
            api_key="test-key",
        )
        assert client.base_url == "https://api.example.com/v1"
        client.close()
    
    def test_init_custom_retries(self):
        client = APIClient(
            base_url="https://api.example.com",
            api_key="test-key",
            max_retries=5,
        )
        assert client.max_retries == 5
        client.close()
    
    def test_endpoint_construction(self):
        client = APIClient(
            base_url="https://api.example.com/v1",
            api_key="test-key",
        )
        assert client.endpoint == "https://api.example.com/v1/chat/completions"
        client.close()

class TestAPIClientContextManager:
    """上下文管理器测试"""
    
    def test_context_manager(self):
        with APIClient("https://api.example.com", "key") as client:
            assert client._client is not None
        # 退出后应关闭
        assert client._client is None

class TestExtractContent:
    """extract_content 静态方法测试"""
    
    def test_normal_chunk(self):
        chunk = {
            "choices": [
                {"delta": {"content": "Hello"}}
            ]
        }
        assert APIClient.extract_content(chunk) == "Hello"
    
    def test_empty_choices(self):
        chunk = {"choices": []}
        assert APIClient.extract_content(chunk) == ""
    
    def test_no_choices(self):
        chunk = {}
        assert APIClient.extract_content(chunk) == ""
    
    def test_text_field(self):
        """兼容 text 字段"""
        chunk = {
            "choices": [
                {"delta": {"text": "World"}}
            ]
        }
        assert APIClient.extract_content(chunk) == "World"
    
    def test_empty_delta(self):
        chunk = {
            "choices": [
                {"delta": {}}
            ]
        }
        assert APIClient.extract_content(chunk) == ""

class TestExtractUsage:
    """extract_usage 静态方法测试"""
    
    def test_normal_usage(self):
        chunk = {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            }
        }
        result = APIClient.extract_usage(chunk)
        assert result == {"input": 100, "output": 50, "total": 150}
    
    def test_no_usage(self):
        chunk = {}
        assert APIClient.extract_usage(chunk) is None
    
    def test_partial_usage(self):
        chunk = {
            "usage": {
                "prompt_tokens": 100,
            }
        }
        result = APIClient.extract_usage(chunk)
        assert result["input"] == 100
        assert result["output"] == 0
        assert result["total"] == 0

class TestAPIClientClose:
    """关闭功能测试"""
    
    def test_close_cleans_up(self):
        client = APIClient("https://api.example.com", "key")
        assert client._client is not None
        client.close()
        assert client._client is None
    
    def test_double_close_safe(self):
        """多次关闭不应报错"""
        client = APIClient("https://api.example.com", "key")
        client.close()
        client.close()  # 不应抛出异常