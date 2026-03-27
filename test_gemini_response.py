"""
Gemini 流式响应格式分析
"""

import os
import sys
import json

if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import httpx

BASE_URL = "https://yunwu.ai/v1"
API_KEY = "sk-hwvRPhrBz0OEMa6u4wSzdAKs2yEYsvHzA3FvFmCeT25HdI8B"
ENDPOINT = f"{BASE_URL}/chat/completions"

def analyze_response():
    """分析 Gemini 流式响应的实际格式"""

    models = [
        "gemini-3-flash-preview",
        "gpt-5.4",  # 对比
    ]

    for model in models:
        print("=" * 70)
        print(f"模型: {model}")
        print("=" * 70)

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "说数字123"}],
            "max_tokens": 30,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        client = httpx.Client(timeout=60.0)

        try:
            with client.stream("POST", ENDPOINT, headers=headers, json=payload, timeout=60.0) as resp:
                print(f"HTTP 状态: {resp.status_code}")
                print(f"\n原始响应行:\n")

                chunk_count = 0
                for line in resp.iter_lines():
                    if not line:
                        continue

                    print(f"[{chunk_count}] {line[:100]}{'...' if len(line) > 100 else ''}")

                    if line.startswith("data: "):
                        raw = line[6:].strip()
                        if raw == "[DONE]":
                            print("      → [DONE] 标记")
                            break
                        try:
                            chunk = json.loads(raw)
                            chunk_count += 1

                            # 详细分析
                            print(f"      解析后: {json.dumps(chunk, ensure_ascii=False, indent=8)[:300]}")

                            # 提取内容的方式
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                print(f"      → content: '{content}'")
                            else:
                                print(f"      → 无 choices")
                        except json.JSONDecodeError as e:
                            print(f"      → JSON 解析失败: {e}")

                    if chunk_count >= 10:  # 只看前 10 个
                        print("... (截断)")
                        break

        except Exception as e:
            print(f"错误: {type(e).__name__}: {e}")

        client.close()
        print()

if __name__ == "__main__":
    analyze_response()