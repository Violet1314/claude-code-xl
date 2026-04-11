"""API 客户端 - 统一的流式请求处理"""
import json
import random
import time
from typing import Generator, Optional, Dict, List, Any

import httpx

from claude_code.config.defaults import API
from claude_code.ui import console


def _get_error_suggestion(error_type: str) -> str:
    """根据错误类型提供解决建议"""
    suggestions = {
        "ConnectError": "检查网络连接，确认 API 地址是否正确",
        "ConnectTimeout": "网络连接超时，请检查网络稳定性或尝试更换网络",
        "ReadTimeout": "服务器响应超时，可能是请求过大或服务器繁忙",
        "WriteTimeout": "发送请求超时，请检查网络上传速度",
        "PoolTimeout": "连接池耗尽，请减少并发请求",
        "SSLError": "SSL 证书验证失败，检查系统证书或代理设置",
    }
    return suggestions.get(error_type, "")


def _get_http_error_suggestion(status_code: int) -> str:
    """根据 HTTP 状态码提供解决建议"""
    suggestions = {
        400: "请求格式错误，检查参数是否正确",
        401: "API Key 无效或已过期，请检查配置",
        402: "账户余额不足，请充值或更换账户",
        403: "权限不足，检查 API Key 权限设置",
        404: "API 端点不存在，检查 base_url 配置",
        422: "请求参数验证失败，检查模型 ID 和参数",
    }
    return suggestions.get(status_code, "")

class APIClient:
    """统一 API 客户端"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        max_retries: int = None,
    ):
        """
        初始化客户端

        Args:
            base_url: API 基础 URL
            api_key: API 密钥
            max_retries: 最大重试次数，默认使用配置值
        """
        self.base_url = base_url.strip().rstrip('/')
        self.api_key = api_key.strip()
        self.endpoint = f"{self.base_url}/chat/completions"
        self.max_retries = max_retries or API.MAX_RETRIES
        self._client: Optional[httpx.Client] = None
        self._init_client()

    def _init_client(self) -> None:
        """初始化 httpx 客户端"""
        self._close_client()
        self._client = httpx.Client(
            trust_env=True,
            verify=True,
            timeout=httpx.Timeout(
                connect=API.CONNECT_TIMEOUT,
                read=API.READ_TIMEOUT,
                write=API.WRITE_TIMEOUT,
                pool=API.POOL_TIMEOUT,
            ),
        )

    def _close_client(self) -> None:
        """安全关闭客户端"""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _reset_client(self) -> None:
        """重置客户端连接"""
        console.warning("触发客户端重置，正在重建连接...")
        self._init_client()

    def send_message(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]] = None,
        stream: bool = True,
        temperature: float = None,
        max_tokens: int = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        发送消息并流式返回响应 (静默重试版)
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model_id,
            "messages": messages,
            "stream": stream,
            "temperature": temperature or API.TEMPERATURE,
            "max_tokens": max_tokens or API.MAX_TOKENS,
        }

        if tools:
            payload["tools"] = tools

        if stream:
            payload["stream_options"] = {"include_usage": True}

        last_error: Optional[str] = None

        for attempt in range(self.max_retries):
            try:
                yield from self._do_request(headers, payload)
                return  # 成功则退出

            except httpx.HTTPError as e:
                last_error = f"{type(e).__name__}: {e}"

                # 【优化】：静默处理前 N-1 次重试
                is_last_attempt = (attempt == self.max_retries - 1)

                if is_last_attempt:
                    # 提供更详细的解决建议
                    error_type = type(e).__name__
                    suggestion = _get_error_suggestion(error_type)
                    console.error(f"请求最终失败: {last_error}")
                    if suggestion:
                        console.info(f"建议: {suggestion}")

                self._reset_client()

                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt + random.uniform(0, 1)
                    # 【优化】：静默等待
                    time.sleep(wait)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    retry_after = e.response.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after else 60
                    
                    is_last_attempt = (attempt == self.max_retries - 1)
                    if is_last_attempt:
                        console.warning(f"API 限流，等待 {wait}s...")
                    
                    self._reset_client()

                    if attempt < self.max_retries - 1:
                        time.sleep(wait)
                    continue

                if 400 <= e.response.status_code < 500:
                    status_code = e.response.status_code
                    console.error(f"API 错误 [{status_code}]: {e.response.text[:200]}")
                    # 提供针对常见错误的建议
                    suggestion = _get_http_error_suggestion(status_code)
                    if suggestion:
                        console.info(f"建议: {suggestion}")
                    return

                last_error = f"HTTP {e.response.status_code}"
                is_last_attempt = (attempt == self.max_retries - 1)
                if is_last_attempt:
                    console.error(f"服务器错误: {last_error}")
                    console.info("建议: 服务端临时故障，稍后重试")
                
                self._reset_client()

                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt + random.uniform(0, 1)
                    time.sleep(wait)

        if last_error:
            console.error(f"请求最终失败，已重试 {self.max_retries} 次")

    def _do_request(
        self,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> Generator[Dict[str, Any], None, None]:
        """执行实际请求"""
        # 编码时使用 replace 处理非法字符
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8', errors='replace')

        with self._client.stream("POST", self.endpoint, headers=headers, content=body) as resp:
            if resp.status_code != 200:
                err_msg = resp.read().decode('utf-8', errors='replace')
                raise httpx.HTTPStatusError(
                    err_msg,
                    request=resp.request,
                    response=resp,
                )

            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue

                raw = line[6:].strip()
                if raw == "[DONE]":
                    return

                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    continue

    @staticmethod
    def extract_content(chunk: Dict[str, Any]) -> str:
        """
        从响应块中提取内容

        Args:
            chunk: 响应数据块

        Returns:
            提取的文本内容
        """
        choices = chunk.get("choices", [])
        if not choices:
            return ""

        delta = choices[0].get("delta", {})
        return delta.get("content") or delta.get("text") or ""

    @staticmethod
    def extract_tool_calls(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从响应块中提取工具调用（原生格式）

        Args:
            chunk: 响应数据块

        Returns:
            工具调用列表
        """
        choices = chunk.get("choices", [])
        if not choices:
            return []

        delta = choices[0].get("delta", {})
        tool_calls = delta.get("tool_calls", [])

        return tool_calls

    @staticmethod
    def extract_usage(chunk: Dict[str, Any]) -> Optional[Dict[str, int]]:
        """
        从响应块中提取 token 使用量

        Args:
            chunk: 响应数据块

        Returns:
            使用量字典或 None
        """
        usage = chunk.get("usage")
        if not usage:
            return None

        return {
            "input": usage.get("prompt_tokens", 0),
            "output": usage.get("completion_tokens", 0),
            "total": usage.get("total_tokens", 0),
        }

    def close(self) -> None:
        """关闭客户端"""
        self._close_client()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False