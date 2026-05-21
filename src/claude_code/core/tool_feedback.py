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
    压缩工具输出（历史 Token 膨胀的核心防线）

    v2.8.37+ 增强：Read 输出在压缩前先提取语义摘要（函数/类签名），
    大幅减少历史中冗余代码内容的 Token 占用。

    Args:
        output: 原始输出
        tool_name: 工具名称
        parameters: 工具参数

    Returns:
        压缩后的输出
    """
    MAX_OUTPUT_LEN = 1000  # 压缩阈值（从 2000 收紧为 1000，大部分工具输出在此区间）

    if len(output) <= MAX_OUTPUT_LEN:
        return output

    # Read 工具：尝试语义摘要（提取关键符号），失败则回退到通用压缩
    if tool_name == "Read":
        # 检查是否是摘要输出（结构概览等已精简内容）
        if "○" in output or "结构概览" in output:
            return output  # 摘要已经很精简
        # 尝试语义提取：保留函数/类签名 + 行号映射，丢弃具体实现
        semantic = _extract_semantic_summary(output, parameters)
        if semantic and len(semantic) < len(output):
            return semantic
        # 语义提取失败，保留行号映射的头尾压缩
        return _compress_read_fallback(output, MAX_OUTPUT_LEN)

    # Grep：保留匹配摘要 + 关键匹配行
    if tool_name == "Grep":
        return _compress_grep(output, MAX_OUTPUT_LEN)

    # Glob：保留文件列表摘要
    if tool_name == "Glob":
        return _compress_glob(output, MAX_OUTPUT_LEN)

    # Edit：保留修改摘要（行号 + 修改前后对比）
    if tool_name == "Edit":
        return _compress_edit(output, MAX_OUTPUT_LEN)

    # Bash：保留 exit code + stderr + stdout 关键行
    if tool_name == "Bash":
        return _compress_bash(output, MAX_OUTPUT_LEN)

    # 其他工具：通用压缩
    return compress_large_output(output, MAX_OUTPUT_LEN)


def _extract_semantic_summary(output: str, parameters: dict) -> Optional[str]:
    """
    从 Read 输出中提取语义摘要（针对代码文件）

    策略：保留函数/类签名、import 语句等结构性信息，
    丢弃具体实现体，大幅压缩但保留导航能力。

    Args:
        output: Read 的原始输出
        parameters: Read 工具参数（含 file_path）

    Returns:
        语义摘要文本，无法提取时返回 None
    """
    import re
    file_path = parameters.get("file_path", "")

    # 仅处理代码文件
    code_extensions = (".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h")
    if not any(file_path.endswith(ext) for ext in code_extensions):
        return None

    lines = output.split("\n")
    if len(lines) < 20:
        return None  # 太短不值得摘要

    # 提取关键行：def/class/import/export/function/struct 等
    key_patterns = [
        r'^\s*(def\s+\w+|class\s+\w+|async\s+def\s+\w+)',  # Python
        r'^\s*(import\s+|from\s+\w+\s+import)',              # Python import
        r'^\s*(function\s+\w+|class\s+\w+|export\s+)',       # JS/TS
        r'^\s*(func\s+\w+|type\s+\w+|struct\s+\{)',          # Go
        r'^\s*(pub\s+)?(fn\s+\w+|struct\s+\w+|impl\s+\w+)',  # Rust
        r'^\s*(public\s+)?(class\s+\w+|interface\s+\w+)',     # Java
        r'^\s*(@\w+)',                                        # Decorators
    ]

    key_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        for pattern in key_patterns:
            if re.match(pattern, line):
                key_lines.append(line.rstrip())
                break

    if not key_lines:
        return None  # 没有可提取的结构

    # 头部：文件信息
    total_lines = len(lines)
    total_chars = len(output)
    header = f"[文件: {file_path} | {total_lines}行 | {total_chars}字符]"
    body = "\n".join(key_lines)
    omitted = total_lines - len(key_lines)

    return f"{header}\n{body}\n... (省略 {omitted} 行实现细节) ..."


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


# ============================================================
# 按工具类型定制的压缩策略
# ============================================================

def _compress_read_fallback(output: str, max_len: int) -> str:
    """
    Read 压缩回退：保留行号映射的头尾，确保 API 仍能定位符号位置

    策略：保留头部（文件元信息+结构概览）+ 尾部，中间只保留行号前缀
    """
    if len(output) <= max_len:
        return output

    lines = output.split('\n')
    # 头部：文件元信息 + 结构概览（通常前 5-20 行）
    head_lines = []
    for line in lines:
        head_lines.append(line)
        if line.startswith('Content') or line.startswith('[结构]'):
            # 保留到 Content 行或结构行之后几行
            break

    # 保留头部的行号映射区域
    head_section = '\n'.join(head_lines[:max(len(head_lines), 15)])
    tail_section = '\n'.join(lines[-(max_len // 80):])  # 估算尾部行数

    result = head_section + f"\n\n... (省略中间 {len(lines) - len(head_lines) - max_len // 80} 行) ...\n\n" + tail_section
    if len(result) > max_len * 1.5:
        # 仍然太长，回退到通用压缩
        return compress_large_output(output, max_len)
    return result


def _compress_grep(output: str, max_len: int) -> str:
    """
    Grep 压缩：保留匹配摘要 + 关键匹配行（含 ✎Edit 提示）

    策略：保留标题行 + 匹配行（▸开头），丢弃上下文行
    """
    if len(output) <= max_len:
        return output

    lines = output.split('\n')
    result_lines = []
    for line in lines:
        # 保留标题、文件分隔、匹配行（▸开头）
        if (line.startswith('Grep:') or line.startswith('---') or
            line.strip().startswith('▸') or not line.strip()):
            result_lines.append(line)

    result = '\n'.join(result_lines)
    if len(result) <= max_len:
        return result
    # 匹配行仍然太多，截断
    return compress_large_output(result, max_len)


def _compress_glob(output: str, max_len: int) -> str:
    """
    Glob 压缩：保留文件列表摘要

    策略：保留标题 + 前后各部分文件，中间省略
    """
    if len(output) <= max_len:
        return output

    lines = output.split('\n')
    # 保留标题行
    title = lines[0] if lines else ""
    file_lines = [l for l in lines[1:] if l.strip() and not l.startswith('Glob:')]

    if len(file_lines) <= 20:
        return output

    head = '\n'.join(file_lines[:10])
    tail = '\n'.join(file_lines[-5:])
    omitted = len(file_lines) - 15
    return f"{title}\n{head}\n... (省略 {omitted} 个文件) ...\n{tail}"


def _compress_edit(output: str, max_len: int) -> str:
    """
    Edit 压缩：保留修改摘要（行号 + 修改前后对比）

    策略：保留 File/Path 行 + 修改行范围 + 修改后上下文确认区域
    """
    if len(output) <= max_len:
        return output

    lines = output.split('\n')
    result_lines = []
    in_context = False

    for line in lines:
        # 保留元信息行
        if line.startswith('File:') or line.startswith('Path:') or line.startswith('Cache:'):
            result_lines.append(line)
        # 保留修改摘要行（L42-45: old → new）
        elif '→' in line or line.strip().startswith('▼'):
            result_lines.append(line)
            in_context = True
        # 保留修改后上下文区域（标记行）
        elif in_context and ('→' in line or line.strip().startswith('  ')):
            result_lines.append(line)
        elif line.strip() == '':
            in_context = False

    result = '\n'.join(result_lines)
    if len(result) <= max_len:
        return result
    return compress_large_output(output, max_len)


def _compress_bash(output: str, max_len: int) -> str:
    """
    Bash 压缩：保留 exit code + stderr 全文 + stdout 关键行

    策略：失败时 stderr 不截断，成功时提取关键行
    """
    if len(output) <= max_len:
        return output

    # 失败输出：[exit=N] + [STDERR] + [STDOUT] 结构
    if output.startswith('[exit='):
        # 保留 [exit=N] 行 + [STDERR] 全文 + [STDOUT] 关键行
        stderr_start = output.find('[STDERR]\n')
        stdout_start = output.find('[STDOUT]\n')

        exit_line = output[:output.find('\n')]

        if stderr_start >= 0 and stdout_start >= 0:
            stderr_text = output[stderr_start + 9:stdout_start].strip()
            stdout_text = output[stdout_start + 9:].strip()
            # 提取 stdout 关键行
            key_lines = _extract_bash_key_lines(stdout_text)
            key_section = '\n'.join(key_lines) if key_lines else stdout_text[:200]
            result = f"{exit_line}\n[STDERR]\n{stderr_text}\n[STDOUT 关键行]\n{key_section}"
            if len(result) <= max_len:
                return result
        elif stderr_start >= 0:
            stderr_text = output[stderr_start + 9:].strip()
            result = f"{exit_line}\n[STDERR]\n{stderr_text}"
            if len(result) <= max_len:
                return result

    # 成功输出：提取关键行 + 首尾保留
    key_lines = _extract_bash_key_lines(output)
    if key_lines:
        key_section = "[关键行]\n" + '\n'.join(key_lines) + "\n"
        remaining = max_len - len(key_section)
        if remaining > 200:
            head = output[:remaining // 2]
            tail = output[-(remaining // 2):]
            return f"{key_section}{head}\n... (省略中间) ...\n{tail}"

    return compress_large_output(output, max_len)


def _extract_bash_key_lines(text: str, max_lines: int = 8) -> list:
    """从 Bash 输出中提取语义关键行"""
    import re
    if not text:
        return []
    key_re = re.compile(
        r'FAILED|ERROR|PASSED|assert|Traceback|Exception:|Error:|Warning:|✗|✓',
        re.IGNORECASE
    )
    key_lines = []
    for line in text.split('\n'):
        if key_re.search(line):
            key_lines.append(line.strip())
            if len(key_lines) >= max_lines:
                break
    return key_lines
