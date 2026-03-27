"""
连接恢复能力测试

测试目标：验证失败后连接是否能正常恢复

测试场景：
1. 连续多次请求，观察是否有"立即失败"现象
2. 故意触发超时，看后续请求是否正常
3. 混合快慢模型，观察交叉影响
"""

import os
import sys
import time
import json

# Windows 终端编码修复
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import httpx

# API 配置
BASE_URL = "https://yunwu.ai/v1"
API_KEY = "sk-hwvRPhrBz0OEMa6u4wSzdAKs2yEYsvHzA3FvFmCeT25HdI8B"
ENDPOINT = f"{BASE_URL}/chat/completions"

# 测试模型 - 选一个容易出问题的
TEST_MODEL = "gemini-3-flash-preview"


def make_streaming_request(client: httpx.Client, timeout: float = 30.0, debug: bool = False) -> dict:
    """发起流式请求"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": TEST_MODEL,
        "messages": [{"role": "user", "content": "说一个数字"}],
        "max_tokens": 20,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    start_time = time.time()
    chunks = 0
    content = ""
    error = None
    raw_chunks = []  # 用于调试

    try:
        with client.stream("POST", ENDPOINT, headers=headers, json=payload, timeout=timeout) as resp:
            if resp.status_code != 200:
                error = f"HTTP {resp.status_code}: {resp.read().decode('utf-8', errors='replace')[:100]}"
            else:
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                        chunks += 1
                        if debug and chunks <= 3:
                            raw_chunks.append(chunk)
                        # 安全处理空 choices
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content += delta.get("content", "")
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:80]}"

    elapsed = time.time() - start_time
    result = {
        "success": error is None and chunks > 0,
        "elapsed": elapsed,
        "chunks": chunks,
        "content": content[:30] if content else None,
        "error": error,
    }
    if debug:
        result["raw_chunks"] = raw_chunks
    return result


def make_non_streaming_request(client: httpx.Client, timeout: float = 30.0) -> dict:
    """发起非流式请求"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": TEST_MODEL,
        "messages": [{"role": "user", "content": "说一个数字"}],
        "max_tokens": 20,
        "stream": False,
    }

    start_time = time.time()
    error = None
    content = None

    try:
        resp = client.post(ENDPOINT, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        else:
            error = f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:80]}"

    elapsed = time.time() - start_time
    return {
        "success": error is None,
        "elapsed": elapsed,
        "content": content[:30] if content else None,
        "error": error,
    }


def test_consecutive_requests():
    """测试1: 连续请求稳定性"""
    print("=" * 70)
    print("测试1: 连续请求稳定性（流式）")
    print(f"模型: {TEST_MODEL}")
    print("=" * 70)

    client = httpx.Client(timeout=60.0)
    results = []

    for i in range(5):
        print(f"\n第 {i+1}/5 次请求...", end=" ", flush=True)
        debug = (i == 0)  # 第一次请求打印调试信息
        result = make_streaming_request(client, timeout=45.0, debug=debug)
        results.append(result)

        if result["success"]:
            print(f"OK {result['elapsed']:.2f}s, {result['chunks']} chunks, 内容: {result['content']}")
        else:
            print(f"FAIL {result['elapsed']:.2f}s")
            if result["error"]:
                print(f"      错误: {result['error']}")
            if result.get("chunks", 0) == 0 and not result["error"]:
                print(f"      原因: 收到 0 个 chunk（可能 API 返回空响应）")
            if result.get("raw_chunks"):
                print(f"      原始响应: {result['raw_chunks']}")

        # 短暂间隔
        time.sleep(0.5)

    client.close()

    # 统计
    success_count = sum(1 for r in results if r["success"])
    print(f"\n统计: {success_count}/5 成功")

    # 检查是否有"立即失败"现象（elapsed < 1s 且失败）
    immediate_failures = [r for r in results if not r["success"] and r["elapsed"] < 1.0]
    if immediate_failures:
        print(f"⚠️ 发现 {len(immediate_failures)} 次「立即失败」！")
    else:
        print("✓ 无立即失败现象")

    return results


def test_timeout_recovery():
    """测试2: 超时后恢复能力"""
    print("\n" + "=" * 70)
    print("测试2: 超时后恢复能力")
    print("=" * 70)

    client = httpx.Client(timeout=60.0)

    # 第一次：故意设置很短的超时，预期会失败
    print("\n[步骤1] 故意设置 2 秒超时（预期失败）...", end=" ", flush=True)
    result1 = make_streaming_request(client, timeout=2.0)
    if result1["success"]:
        print(f"意外成功 {result1['elapsed']:.2f}s")
    else:
        print(f"预期失败 {result1['elapsed']:.2f}s")
        print(f"      错误: {result1['error']}")

    # 立即尝试第二次：正常超时
    print("\n[步骤2] 立即用正常超时（45秒）重试...", end=" ", flush=True)
    result2 = make_streaming_request(client, timeout=45.0)
    if result2["success"]:
        print(f"OK {result2['elapsed']:.2f}s, {result2['chunks']} chunks")
    else:
        print(f"FAIL {result2['elapsed']:.2f}s")
        print(f"      错误: {result2['error']}")

    # 第三次：再次验证
    print("\n[步骤3] 再次验证...", end=" ", flush=True)
    result3 = make_streaming_request(client, timeout=45.0)
    if result3["success"]:
        print(f"OK {result3['elapsed']:.2f}s, {result3['chunks']} chunks")
    else:
        print(f"FAIL {result3['elapsed']:.2f}s")
        print(f"      错误: {result3['error']}")

    client.close()

    # 判断
    if not result1["success"] and result2["success"] and result3["success"]:
        print("\n✓ 超时后恢复正常")
    elif not result1["success"] and not result2["success"]:
        print("\n✗ 超时后连接可能损坏！后续请求也失败！")
    else:
        print("\n⚠ 其他情况，需人工判断")


def test_mixed_mode():
    """测试3: 混合流式/非流式"""
    print("\n" + "=" * 70)
    print("测试3: 混合流式/非流式请求")
    print("=" * 70)

    client = httpx.Client(timeout=60.0)

    for i in range(4):
        mode = "非流式" if i % 2 == 0 else "流式"
        print(f"\n第 {i+1}/4 次 ({mode})...", end=" ", flush=True)

        if i % 2 == 0:
            result = make_non_streaming_request(client, timeout=30.0)
        else:
            result = make_streaming_request(client, timeout=45.0)

        if result["success"]:
            content_info = result.get("content") or f"{result.get('chunks', 0)} chunks"
            print(f"OK {result['elapsed']:.2f}s, {content_info}")
        else:
            print(f"FAIL {result['elapsed']:.2f}s")
            print(f"      错误: {result['error']}")

        time.sleep(0.5)

    client.close()


def test_connection_reset():
    """测试4: 模拟连接重置"""
    print("\n" + "=" * 70)
    print("测试4: 模拟连接重置（关闭重建）")
    print("=" * 70)

    # 第一轮
    print("\n[第一轮] 创建新连接...")
    client1 = httpx.Client(timeout=60.0)

    print("  请求1...", end=" ", flush=True)
    r1 = make_streaming_request(client1, timeout=45.0)
    print(f"{'OK' if r1['success'] else 'FAIL'} {r1['elapsed']:.2f}s")

    print("  请求2...", end=" ", flush=True)
    r2 = make_streaming_request(client1, timeout=45.0)
    print(f"{'OK' if r2['success'] else 'FAIL'} {r2['elapsed']:.2f}s")

    # 关闭连接
    print("\n[关闭连接]")
    client1.close()
    time.sleep(1)

    # 新连接
    print("\n[第二轮] 创建新连接...")
    client2 = httpx.Client(timeout=60.0)

    print("  请求3...", end=" ", flush=True)
    r3 = make_streaming_request(client2, timeout=45.0)
    print(f"{'OK' if r3['success'] else 'FAIL'} {r3['elapsed']:.2f}s")

    print("  请求4...", end=" ", flush=True)
    r4 = make_streaming_request(client2, timeout=45.0)
    print(f"{'OK' if r4['success'] else 'FAIL'} {r4['elapsed']:.2f}s")

    client2.close()

    # 判断
    all_ok = all(r['success'] for r in [r1, r2, r3, r4])
    if all_ok:
        print("\n✓ 连接重置正常")
    else:
        print("\n⚠ 有失败的请求")


def main():
    print("=" * 70)
    print("gemini-3-flash-preview 连接恢复能力测试")
    print(f"API: {BASE_URL}")
    print("=" * 70)

    # 运行所有测试
    test_consecutive_requests()
    test_timeout_recovery()
    test_mixed_mode()
    test_connection_reset()

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()