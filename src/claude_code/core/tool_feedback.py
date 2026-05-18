"""工具反馈构建 - 将工具执行结果转换为模型可理解的消息格式

从 app.py 拆分出的模块，职责：
1. 构建 XML 格式的工具反馈消息
2. 压缩过大的工具输出（减少历史 Token 膨胀）
"""
from typing import Optional, List


def build_tool_feedback(report) -> Optional[str]:
    """
    构建工具执行反馈消息

    Args:
        report: ExecutionReport 执行报告

    Returns:
        反馈消息文本，无结果时返回 None
    """
    if report.total == 0:
        return None

    lines = ["<tool_results>"]

    # 如果有用户中断，添加特殊标记
    if report.has_interrupted:
        lines.append("<system_message type=\"user_interrupt\">")
        lines.append("用户按下 CTRL+C 中断了正在执行的操作。")
        lines.append("这表示用户希望停止当前任务，不要再继续尝试。")
        lines.append("请向用户确认是否需要继续其他工作，或者直接等待用户的新指令。")
        lines.append("</system_message>")

    for result in report.results:
        if result.skipped:
            lines.append(f"<result tool=\"{result.tool_call.name}\" status=\"skipped\">")
            if result.permission_denied:
                lines.append("权限被拒绝，此操作需要用户明确授权")
            else:
                lines.append("用户主动取消执行")
        elif result.interrupted:
            # 用户中断：使用特殊状态，让模型理解这不是"失败"
            lines.append(f"<result tool=\"{result.tool_call.name}\" status=\"interrupted\">")
            lines.append("用户按下 CTRL+C 中断了此操作")
        elif result.success:
            lines.append(f"<result tool=\"{result.tool_call.name}\" status=\"success\">")
            # 压缩大结果
            output = compress_tool_output(
                result.output,
                result.tool_call.name,
                result.tool_call.parameters
            )
            lines.append(output)
        else:
            lines.append(f"<result tool=\"{result.tool_call.name}\" status=\"error\">")
            lines.append(result.error or "执行失败")
        lines.append("</result>")

    lines.append("</tool_results>")

    return "\n".join(lines)


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
