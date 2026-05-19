"""工具反馈构建 - 将工具执行结果转换为原生 tool role 消息

v2.8.35 重构：
- 改用原生 tool role 消息替代 user+XML 格式
- 每个工具结果独立一条 tool message，带 tool_call_id
- 模型可精确关联自己的 tool_call 与对应结果，多轮工具调用时不再混淆
"""
from typing import Optional, List, Dict


def build_tool_feedback(report) -> Optional[List[Dict[str, str]]]:
    """
    构建工具执行反馈消息（原生 tool role 格式）

    每个工具结果独立一条消息，通过 tool_call_id 与模型的 tool_call 关联。
    这让模型在多轮工具调用中能精确区分用户意图与工具反馈。

    Args:
        report: ExecutionReport 执行报告

    Returns:
        工具结果消息列表，每项包含 tool_call_id 和 content；
        无结果时返回 None
    """
    if report.total == 0:
        return None

    results = []
    has_interrupt = report.has_interrupted

    for result in report.results:
        # 获取 tool_call_id（API 原生返回的调用 ID）
        tool_call_id = result.tool_call.id if result.tool_call.id else f"tc_{id(result.tool_call)}"

        if result.skipped:
            if result.permission_denied:
                content = "权限被拒绝，此操作需要用户明确授权"
            else:
                content = "用户主动取消执行"
        elif result.interrupted:
            content = (
                "用户按下 CTRL+C 中断了此操作。"
                "这表示用户希望停止当前任务，不要再继续尝试。"
            )
        elif result.success:
            # 压缩大结果
            content = compress_tool_output(
                result.output,
                result.tool_call.name,
                result.tool_call.parameters
            )
        else:
            content = result.error or "执行失败"

        # 如果有全局中断且这是第一条结果，附加中断上下文
        if has_interrupt and not results:
            content = f"[系统提示：用户中断了部分操作，请确认是否继续]\n{content}"

        results.append({
            "tool_call_id": tool_call_id,
            "content": content,
        })

    return results if results else None


def compress_tool_output(
    output: str,
    tool_name: str,
    parameters: dict
) -> str:
    """
    压缩工具输出（减少历史 Token 膨胀）

    Args:
        output: 原始输出
        tool_name: 工具名称
        parameters: 工具参数

    Returns:
        压缩后的输出
    """
    MAX_OUTPUT_LEN = 3000  # 压缩阈值

    if len(output) <= MAX_OUTPUT_LEN:
        return output

    # Read 工具：已经是摘要模式，保留原文
    if tool_name == "Read":
        # 检查是否是摘要输出
        if "○" in output or "结构概览" in output:
            return output  # 摘要已经很精简
        # 非摘要的大输出，压缩
        return compress_large_output(output, MAX_OUTPUT_LEN)

    # Grep/Glob：保留结果但压缩
    if tool_name in ("Grep", "Glob"):
        return compress_large_output(output, MAX_OUTPUT_LEN)

    # Bash：保留前后部分
    if tool_name == "Bash":
        return compress_large_output(output, MAX_OUTPUT_LEN)

    # 其他工具：通用压缩
    return compress_large_output(output, MAX_OUTPUT_LEN)


def compress_large_output(output: str, max_len: int = 3000) -> str:
    """
    压缩大输出（保留前后部分）

    Args:
        output: 原始输出
        max_len: 最大长度

    Returns:
        压缩后的输出
    """
    if len(output) <= max_len:
        return output

    half = max_len // 2
    head = output[:half]
    tail = output[-half:]
    omitted = len(output) - max_len

    return f"{head}\n\n... (省略 {omitted} 字符) ...\n\n{tail}"
