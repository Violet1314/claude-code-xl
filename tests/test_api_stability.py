"""
API 调用稳定性测试脚本

测试项目：
1. 基本文本生成
2. 工具调用（native 模式）
3. 响应时间、成功率统计
"""

import os
import sys

# Windows 终端编码修复
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import httpx
import json
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# API 配置
BASE_URL = "https://yunwu.ai/v1"
API_KEY = "sk-hwvRPhrBz0OEMa6u4wSzdAKs2yEYsvHzA3FvFmCeT25HdI8B"

# 测试模型列表
TEST_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gpt-5.4",
    "gpt-5.3-codex-high",
    "qwen3.5-plus",
    "deepseek-v3.2",
]

# 工具定义（用于测试 native tool calling）
TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称"
                    }
                },
                "required": ["city"]
            }
        }
    }
]


def test_basic_completion(client: httpx.Client, model_id: str) -> dict:
    """测试基本文本生成"""
    endpoint = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": "请用一句话回答：1+1等于几？"}
        ],
        "max_tokens": 100,
        "stream": False,
    }

    start_time = time.time()
    try:
        response = client.post(endpoint, headers=headers, json=payload, timeout=30.0)
        elapsed = time.time() - start_time

        if response.status_code == 200:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {
                "success": True,
                "elapsed": elapsed,
                "content": content[:50] + "..." if len(content) > 50 else content,
                "status_code": response.status_code,
            }
        else:
            return {
                "success": False,
                "elapsed": elapsed,
                "error": response.text[:100],
                "status_code": response.status_code,
            }
    except Exception as e:
        return {
            "success": False,
            "elapsed": time.time() - start_time,
            "error": str(e)[:100],
            "status_code": None,
        }


def test_tool_calling(client: httpx.Client, model_id: str) -> dict:
    """测试工具调用（native 模式）"""
    endpoint = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": "北京今天的天气怎么样？"}
        ],
        "tools": TOOLS_DEFINITION,
        "max_tokens": 200,
        "stream": False,
    }

    start_time = time.time()
    try:
        response = client.post(endpoint, headers=headers, json=payload, timeout=30.0)
        elapsed = time.time() - start_time

        if response.status_code == 200:
            data = response.json()
            message = data.get("choices", [{}])[0].get("message", {})

            # 检查是否有工具调用
            tool_calls = message.get("tool_calls", [])
            has_tool_call = len(tool_calls) > 0

            if has_tool_call:
                tool_name = tool_calls[0].get("function", {}).get("name", "")
                tool_args = tool_calls[0].get("function", {}).get("arguments", "")
            else:
                tool_name = None
                tool_args = None
                # 可能模型直接回答了而不是调用工具
                content = message.get("content", "")

            return {
                "success": True,
                "elapsed": elapsed,
                "has_tool_call": has_tool_call,
                "tool_name": tool_name,
                "tool_args": tool_args[:50] if tool_args else None,
                "status_code": response.status_code,
            }
        else:
            return {
                "success": False,
                "elapsed": elapsed,
                "error": response.text[:100],
                "status_code": response.status_code,
            }
    except Exception as e:
        return {
            "success": False,
            "elapsed": time.time() - start_time,
            "error": str(e)[:100],
            "status_code": None,
        }


def test_streaming(client: httpx.Client, model_id: str) -> dict:
    """测试流式输出"""
    endpoint = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": "从1数到5"}
        ],
        "max_tokens": 50,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    start_time = time.time()
    chunks_received = 0
    total_content = ""
    usage = None

    try:
        with client.stream("POST", endpoint, headers=headers, json=payload, timeout=30.0) as response:
            if response.status_code != 200:
                return {
                    "success": False,
                    "elapsed": time.time() - start_time,
                    "error": f"HTTP {response.status_code}",
                    "status_code": response.status_code,
                }

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw = line[6:].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                    chunks_received += 1

                    # 提取内容
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            total_content += content

                    # 提取 usage
                    if "usage" in chunk:
                        usage = chunk["usage"]
                except json.JSONDecodeError:
                    continue

        elapsed = time.time() - start_time

        return {
            "success": True,
            "elapsed": elapsed,
            "chunks": chunks_received,
            "content_length": len(total_content),
            "has_usage": usage is not None,
            "status_code": 200,
        }

    except Exception as e:
        return {
            "success": False,
            "elapsed": time.time() - start_time,
            "error": str(e)[:100],
            "status_code": None,
        }


def main():
    print("=" * 70)
    print("API 调用稳定性测试")
    print(f"Base URL: {BASE_URL}")
    print("=" * 70)

    # 创建 HTTP 客户端
    client = httpx.Client(timeout=60.0)

    results = {}

    for model_id in TEST_MODELS:
        print(f"\n测试模型: {model_id}")
        print("-" * 50)

        model_results = {
            "basic": None,
            "tool_call": None,
            "streaming": None,
        }

        # 1. 基本文本生成
        print("  [1/3] 基本文本生成...", end=" ", flush=True)
        result = test_basic_completion(client, model_id)
        model_results["basic"] = result

        if result["success"]:
            print(f"✓ {result['elapsed']:.2f}s")
            print(f"        响应: {result['content']}")
        else:
            print(f"✗ {result.get('error', 'Unknown error')}")

        # 2. 工具调用
        print("  [2/3] 工具调用 (native)...", end=" ", flush=True)
        result = test_tool_calling(client, model_id)
        model_results["tool_call"] = result

        if result["success"]:
            if result["has_tool_call"]:
                print(f"✓ {result['elapsed']:.2f}s, 工具: {result['tool_name']}")
            else:
                print(f"⚠ {result['elapsed']:.2f}s, 未调用工具（直接回答）")
        else:
            print(f"✗ {result.get('error', 'Unknown error')}")

        # 3. 流式输出
        print("  [3/3] 流式输出...", end=" ", flush=True)
        result = test_streaming(client, model_id)
        model_results["streaming"] = result

        if result["success"]:
            usage_str = "有 usage" if result["has_usage"] else "无 usage"
            print(f"✓ {result['elapsed']:.2f}s, {result['chunks']} chunks, {usage_str}")
        else:
            print(f"✗ {result.get('error', 'Unknown error')}")

        results[model_id] = model_results

    client.close()

    # 打印汇总
    print("\n" + "=" * 70)
    print("测试汇总")
    print("=" * 70)

    print(f"\n{'模型':<25} {'基本':<10} {'工具调用':<12} {'流式':<10} {'平均耗时'}")
    print("-" * 70)

    for model_id, data in results.items():
        basic_ok = "✓" if data["basic"]["success"] else "✗"
        tool_ok = "✓" if data["tool_call"]["success"] else "✗"
        tool_note = "" if data["tool_call"].get("has_tool_call") else " (无调用)"
        stream_ok = "✓" if data["streaming"]["success"] else "✗"

        # 计算平均耗时
        times = []
        for test in ["basic", "tool_call", "streaming"]:
            if data[test]["success"]:
                times.append(data[test]["elapsed"])
        avg_time = sum(times) / len(times) if times else 0

        print(f"{model_id:<25} {basic_ok:<10} {tool_ok + tool_note:<12} {stream_ok:<10} {avg_time:.2f}s")

    print("\n" + "=" * 70)
    print("测试完成")


if __name__ == "__main__":
    main()