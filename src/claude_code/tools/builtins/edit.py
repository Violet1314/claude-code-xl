"""Edit 工具 - 编辑文件（双模式：精确匹配 + 行号范围，集成缓存，语法检查）

v2.8.21 重构要点：
1. 新增行号范围模式（start_line/end_line）— 替换指定行范围，无需精确复制原文
2. 保留精确匹配模式（old_string/new_string）— 短文本精确替换
3. 行号模式返回被替换的原始内容，供 AI 确认
4. 两种模式互斥，根据参数自动选择
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
from ..base import Tool, ToolResult
from ..file_cache import file_cache
from ..syntax_checker import check_syntax
from claude_code.core.path_manager import get_path_manager
from claude_code.ui.theme import COLORS, ICONS
from rich.markup import escape


class EditTool(Tool):
    """编辑文件工具（双模式：精确匹配 + 行号范围）

    核心设计原则：
    - 精确匹配模式：old_string 必须完全匹配，适合短文本替换
    - 行号范围模式：指定 start_line/end_line，适合大块替换，无需复制原文
    - 行号模式返回被替换的原始内容，供 AI 确认替换正确
    - 两种模式互斥，根据参数自动选择
    """
    name = "Edit"
    description = (
        "替换文件内容。支持两种模式（互斥，根据参数自动选择）：\n"
        "\n"
        "模式 1 — 精确匹配（默认）：\n"
        "  提供 old_string + new_string，old_string 必须完全精确匹配文件内容。\n"
        "  适合短文本替换（1-5行）。长文本建议用行号模式。\n"
        "  精确匹配失败时，会自动尝试容错匹配（空白/缩进/换行差异），匹配成功会标注 [fuzzy]。\n"
        "\n"
        "模式 2 — 行号范围：\n"
        "  提供 start_line + end_line + new_string，替换指定行范围的内容。\n"
        "  适合大块替换（5行以上），无需精确复制原文，直接用 Read 返回的行号定位。\n"
        "  替换结果会返回被替换的原始内容，供确认是否正确。"
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径",
                    "example": "E:\\项目目录\\src\\file.py"
                },
                "old_string": {
                    "type": "string",
                    "description": "要替换的原文（精确匹配模式）。从 Read 结果中精确复制，包括缩进、空格、换行",
                    "example": "print('hello')"
                },
                "new_string": {
                    "type": "string",
                    "description": "替换后的新内容",
                    "example": "print('world')"
                },
                "start_line": {
                    "type": "integer",
                    "description": "行号范围模式：起始行号（从 1 开始，含）。与 end_line 一起使用，替代 old_string",
                    "example": 10
                },
                "end_line": {
                    "type": "integer",
                    "description": "行号范围模式：结束行号（含）。与 start_line 一起使用，替代 old_string",
                    "example": 15
                }
            },
            "required": ["file_path", "new_string"],
            "errorMessage": {
                "file_path": "必须提供 file_path，如 file_path=\"E:\\项目目录\\src\\file.py\"",
                "new_string": "必须提供 new_string（替换后的新内容，可为空字符串表示删除）"
            }
        }

    def execute(
        self,
        parameters: Dict[str, Any],
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> ToolResult:
        """执行编辑操作（自动选择精确匹配模式或行号范围模式）"""
        # 参数验证
        validation_error = self.validate_parameters(parameters)
        if validation_error:
            return ToolResult(success=False, output="", error=validation_error)

        file_path = parameters.get("file_path", "")
        new_string = parameters.get("new_string", "")

        # 使用 PathManager 统一路径解析（含安全边界校验）
        pm = get_path_manager()
        file_path, boundary_ok = pm.resolve_safe(file_path)
        if not boundary_ok:
            return ToolResult(
                success=False, output="",
                error=f"路径越界: {file_path} 不在操作根目录 {pm.active_path} 下，禁止访问"
            )
        # v2.8.36：缓存新鲜度校验
        freshness_hint = ""
        if not file_cache.is_cached(file_path):
            freshness_hint = (
                "\n[提示] 此文件尚未被 Read 缓存。"
                "建议先调用 Read 确认文件当前内容，再执行 Edit，避免匹配失败。"
            )
        else:
            read_count = file_cache.get_read_count(file_path)
            if read_count == 0:
                freshness_hint = (
                    "\n[提示] 此文件自上次修改后未被重新读取。"
                    "建议先调用 Read 获取最新内容，再执行 Edit，避免匹配失败。"
                )

        # 判断模式：有 start_line/end_line → 行号范围模式，否则 → 精确匹配模式
        start_line = parameters.get("start_line")
        end_line = parameters.get("end_line")

        if start_line is not None and end_line is not None:
            return self._execute_line_range_mode(file_path, start_line, end_line, new_string, pm, freshness_hint)
        else:
            old_string = parameters.get("old_string", "")
            return self._execute_exact_match_mode(file_path, old_string, new_string, pm, freshness_hint)

    # ============================================================
    # 模式 1：精确匹配
    # ============================================================

    def _execute_exact_match_mode(
        self, file_path: str, old_string: str, new_string: str, pm, freshness_hint: str = ""
    ) -> ToolResult:
        """精确匹配模式执行"""
        try:
            path = Path(file_path)
            if not path.exists():
                # 文件不存在时，自动搜索同名文件
                return self._handle_file_not_found(file_path, pm)

            with open(path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            # ============================================================
            # 精确匹配 → 模糊匹配容错
            # ============================================================
            positions = self._find_exact_matches(original_content, old_string)
            fuzzy_matched = False  # 标记是否使用了模糊匹配

            if not positions:
                # 精确匹配失败，尝试模糊匹配容错
                fuzzy_results = self._find_fuzzy_matches(original_content, old_string)
                if len(fuzzy_results) == 1:
                    # 模糊匹配唯一，使用该结果
                    start_char, end_char = fuzzy_results[0]
                    # 用匹配到的原始内容替换 old_string，确保替换区域正确
                    old_string = original_content[start_char:end_char]
                    positions = [start_char]
                    fuzzy_matched = True
                elif len(fuzzy_results) > 1:
                    # 模糊匹配多处，仍报错
                    return self._build_no_match_error(original_content, old_string, file_path, freshness_hint)
                else:
                    # 模糊匹配也失败，尝试行级归一化匹配降级到行号模式
                    line_match = self._try_line_normalized_match(original_content, old_string)
                    if line_match:
                        # 找到唯一行级匹配，自动降级为行号范围模式执行
                        start_line, end_line = line_match
                        return self._execute_line_range_mode(
                            file_path, start_line, end_line, new_string, pm, freshness_hint
                        )
                    return self._build_no_match_error(original_content, old_string, file_path, freshness_hint)

            match_count = len(positions)

            if match_count > 1:
                # 多处匹配，要求添加上下文
                return self._build_multiple_matches_error(
                    original_content, old_string, positions
                )

            # ============================================================
            # 执行替换
            # ============================================================
            start_pos = positions[0]
            new_content = original_content[:start_pos] + new_string + original_content[start_pos + len(old_string):]

            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # 更新缓存
            cache_result = file_cache.apply_write(file_path, new_content)
            version = cache_result["version"]
            reference = cache_result["reference"]

            # 计算起始行号
            start_line = original_content[:start_pos].count('\n') + 1

            # 语法检查（仅警告，不阻止）
            is_valid, syntax_warning = check_syntax(new_content, file_path)

            output = self._build_model_output(
                path, old_string, new_string, start_line, version, reference, syntax_warning,
                fuzzy_matched=fuzzy_matched, new_content=new_content
            )
            # v2.8.36：附加缓存新鲜度提示
            if freshness_hint:
                output = output + freshness_hint

            display_output = self._build_terminal_display(
                path, old_string, new_string, original_content, new_content,
                start_line, version, reference, syntax_warning, fuzzy_matched=fuzzy_matched
            )

            return ToolResult(
                success=True,
                output=output,
                display_output=display_output,
                summary=f"Edit {path.name}" + (" (fuzzy)" if fuzzy_matched else ""),
                metadata={
                    "file_path": str(path.absolute()),
                    "old_length": len(old_string),
                    "new_length": len(new_string),
                    "start_line": start_line,
                    "cache_version": version,
                    "cache_reference": reference,
                    "syntax_valid": is_valid,
                    "fuzzy_matched": fuzzy_matched,
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足，无法写入: {file_path}")
        except FileNotFoundError:
            return self._handle_file_not_found(file_path, pm)
        except OSError as e:
            return ToolResult(success=False, output="", error=f"系统错误: {e.strerror or str(e)} ({file_path})")
        except UnicodeDecodeError as e:
            return ToolResult(success=False, output="", error=f"编码错误: 文件包含无法解码的字符 ({e})")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"编辑失败: {type(e).__name__}: {str(e)}")

    # ============================================================
    # 模式 2：行号范围
    # ============================================================

    def _execute_line_range_mode(
        self, file_path: str, start_line: int, end_line: int, new_string: str, pm, freshness_hint: str = ""
    ) -> ToolResult:
        """行号范围模式执行"""
        try:
            path = Path(file_path)
            if not path.exists():
                return self._handle_file_not_found(file_path, pm)

            with open(path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            original_lines = original_content.splitlines()
            total_lines = len(original_lines)

            # 行号范围校验
            if start_line < 1:
                return ToolResult(
                    success=False, output="",
                    error=f"start_line 必须 >= 1，当前值: {start_line}"
                )
            if end_line < start_line:
                return ToolResult(
                    success=False, output="",
                    error=f"end_line 必须 >= start_line，当前: start_line={start_line}, end_line={end_line}"
                )
            if start_line > total_lines:
                return ToolResult(
                    success=False, output="",
                    error=f"start_line={start_line} 超出文件总行数 {total_lines}"
                )

            # 实际结束行（不超过文件末尾）
            actual_end = min(end_line, total_lines)

            # 提取被替换的原始内容（供 AI 确认）
            replaced_lines = original_lines[start_line - 1 : actual_end]
            old_string = '\n'.join(replaced_lines)

            # 执行替换
            new_lines = new_string.splitlines()
            result_lines = (
                original_lines[: start_line - 1]   # 替换范围之前
                + new_lines                         # 新内容
                + original_lines[actual_end:]       # 替换范围之后
            )
            new_content = '\n'.join(result_lines)

            # 如果原文件末尾有换行，保留
            if original_content.endswith('\n') and not new_content.endswith('\n'):
                new_content += '\n'

            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # 更新缓存
            cache_result = file_cache.apply_write(file_path, new_content)
            version = cache_result["version"]
            reference = cache_result["reference"]

            # 语法检查
            is_valid, syntax_warning = check_syntax(new_content, file_path)

            # 构建输出：包含被替换的原始内容，供 AI 确认
            output = self._build_line_range_model_output(
                path, start_line, actual_end, old_string, new_string,
                version, reference, syntax_warning
            )
            # v2.8.36：附加缓存新鲜度提示
            if freshness_hint:
                output = output + freshness_hint

            display_output = self._build_line_range_terminal_display(
                path, start_line, actual_end, old_string, new_string,
                version, reference, syntax_warning
            )

            return ToolResult(
                success=True,
                output=output,
                display_output=display_output,
                summary=f"Edit {path.name} (lines {start_line}-{actual_end})",
                metadata={
                    "file_path": str(path.absolute()),
                    "start_line": start_line,
                    "end_line": actual_end,
                    "old_length": len(old_string),
                    "new_length": len(new_string),
                    "replaced_lines": len(replaced_lines),
                    "cache_version": version,
                    "cache_reference": reference,
                    "syntax_valid": is_valid,
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足，无法写入: {file_path}")
        except FileNotFoundError:
            return self._handle_file_not_found(file_path, pm)
        except OSError as e:
            return ToolResult(success=False, output="", error=f"系统错误: {e.strerror or str(e)} ({file_path})")
        except UnicodeDecodeError as e:
            return ToolResult(success=False, output="", error=f"编码错误: 文件包含无法解码的字符 ({e})")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"编辑失败: {type(e).__name__}: {str(e)}")

    # ============================================================
    # 精确匹配辅助
    # ============================================================

    def _find_exact_matches(self, content: str, old_string: str) -> List[int]:
        """精确匹配：查找所有完全匹配的位置

        Returns:
            匹配起始位置的字符索引列表
        """
        positions = []
        start = 0
        while True:
            pos = content.find(old_string, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        return positions

    def _normalize_for_fuzzy_match(self, text: str) -> str:
        """归一化文本用于模糊匹配（不改变原始内容，仅用于比较）

        归一化规则：
        1. \r\n → \n（换行符统一）
        2. 每行行尾空白去除
        3. Tab → 4空格（缩进对齐）
        4. 首尾空行去除
        """
        # 1. 换行符统一
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # 2. 按行处理：行尾空白去除 + tab→空格
        lines = text.split('\n')
        lines = [line.expandtabs(4).rstrip() for line in lines]
        # 3. 去除首尾空行
        while lines and lines[0] == '':
            lines.pop(0)
        while lines and lines[-1] == '':
            lines.pop()
        return '\n'.join(lines)

    def _find_fuzzy_matches(self, content: str, old_string: str) -> List[Tuple[int, int]]:
        """模糊匹配：在精确匹配失败时尝试容错匹配

        归一化后按行比较，返回原始内容中的 (起始字符位置, 结束字符位置) 列表。
        只在精确匹配失败时调用，匹配结果必须唯一才使用。

        策略：将 old_string 和 content 都按行归一化后，逐行滑动窗口匹配。
        匹配成功后，将匹配的行号范围映射回原始内容的字符位置。

        Returns:
            匹配的 (start_char_index, end_char_index) 列表（基于原始内容）
        """
        # 归一化行列表
        norm_old_lines = self._normalize_for_fuzzy_match(old_string).split('\n')
        orig_content_lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        norm_content_lines = [line.expandtabs(4).rstrip() for line in orig_content_lines]

        if not norm_old_lines or not norm_content_lines:
            return []

        # 去除 old_string 归一化后的首尾空行（已在 _normalize 中处理，但确保安全）
        while norm_old_lines and norm_old_lines[0] == '':
            norm_old_lines.pop(0)
        while norm_old_lines and norm_old_lines[-1] == '':
            norm_old_lines.pop()
        if not norm_old_lines:
            return []

        old_len = len(norm_old_lines)
        content_len = len(norm_content_lines)

        if old_len > content_len:
            return []

        # 滑动窗口：在归一化内容行中查找连续匹配的行序列
        results = []
        for i in range(content_len - old_len + 1):
            match = True
            for j in range(old_len):
                if norm_content_lines[i + j] != norm_old_lines[j]:
                    match = False
                    break
            if match:
                # 计算原始内容中的字符位置
                # 匹配的行范围：[i, i + old_len - 1]
                start_line = i
                end_line = i + old_len - 1

                # 计算起始字符位置
                start_char = sum(len(orig_content_lines[k]) + 1 for k in range(start_line))
                # 计算结束字符位置（end_line 行尾）
                end_char = sum(len(orig_content_lines[k]) + 1 for k in range(end_line)) + len(orig_content_lines[end_line])

                results.append((start_char, end_char))

        return results

    def _try_line_normalized_match(self, content: str, old_string: str) -> Optional[Tuple[int, int]]:
        """
        行级归一化匹配：精确匹配和字符级模糊匹配都失败后的第三道防线

        策略：按行 strip 后匹配首行，如果唯一匹配则返回行号范围，
        由调用方自动降级为行号范围模式执行替换。

        Returns:
            (start_line, end_line) 元组，无法定位时返回 None
        """
        old_lines = [l.strip() for l in old_string.split('\n') if l.strip()]
        if not old_lines:
            return None

        content_lines = content.split('\n')
        first_old_line = old_lines[0]
        matches = []

        for i, line in enumerate(content_lines, 1):
            stripped = line.strip()
            if stripped and first_old_line in stripped:
                # 首行匹配，验证后续行是否也匹配
                match_len = len(old_lines)
                all_match = True
                for j in range(1, match_len):
                    if i - 1 + j >= len(content_lines):
                        all_match = False
                        break
                    if old_lines[j] not in content_lines[i - 1 + j].strip():
                        all_match = False
                        break
                if all_match:
                    end_line = min(i + match_len - 1, len(content_lines))
                    matches.append((i, end_line))

        # 唯一匹配才自动降级，多处匹配仍返回 None 让错误提示处理
        if len(matches) == 1:
            return matches[0]
        return None

    def _build_no_match_error(self, content: str, old_string: str, file_path: str, freshness_hint: str = "") -> ToolResult:
        """精确匹配失败时的错误反馈（含最接近匹配定位）"""
        # 提供行号模式建议
        line_count = old_string.count('\n') + 1
        mode_hint = ""
        if line_count > 5:
            mode_hint = (
                "\n\nℹ 提示：old_string 超过 5 行，建议改用行号范围模式：\n"
                "  提供 start_line 和 end_line 参数替代 old_string，无需精确复制原文。\n"
                "  例如: start_line=10, end_line=20, new_string=\"新内容\""
            )

        total_lines = content.count('\n') + 1

        # 策略 1：用 old_string 的第一行在文件中搜索（子串匹配）
        first_line = old_string.split('\n')[0].strip()
        if first_line and len(first_line) >= 5:
            content_lines = content.split('\n')
            matches = []
            for i, line in enumerate(content_lines, 1):
                if first_line in line:
                    matches.append((i, line.strip()))
            if matches:
                # 找到部分匹配，给出定位信息（最多 3 处）
                if len(matches) == 1:
                    loc_str = f"第 {matches[0][0]} 行"
                    loc_detail = f"  {matches[0][0]:5d} | {matches[0][1][:100]}"
                elif len(matches) <= 3:
                    loc_str = " / ".join(f"第 {m[0]} 行" for m in matches)
                    loc_detail = "\n".join(f"  {m[0]:5d} | {m[1][:100]}" for m in matches)
                else:
                    loc_str = f"第 {matches[0][0]} 行 / 第 {matches[1][0]} 行 等 {len(matches)} 处"
                    loc_detail = "\n".join(f"  {m[0]:5d} | {m[1][:100]}" for m in matches[:3])
                    loc_detail += f"\n  ... 等 {len(matches)} 处"
                return ToolResult(
                    success=False, output="",
                    error=(
                        f"精确匹配失败: old_string 在文件中未找到完全匹配（文件共 {total_lines} 行）。\n"
                        f"但第一行「{first_line[:60]}」出现在: {loc_str}\n\n"
                        f"文件中对应内容:\n{loc_detail}\n\n"
                        f"可能原因：缩进/空白/换行差异，或复制时遗漏了部分内容。\n\n"
                        f"建议：\n"
                        f"1. 重新 Read 文件，从上述位置精确复制原文（包括缩进）\n"
                        f"2. 或缩小 old_string 范围，只匹配最关键的一两行\n"
                        f"3. 或使用行号范围模式直接指定行号"
                        f"{mode_hint}"
                        f"{freshness_hint}"
                    )
                )

        # 策略 2：尝试按行做归一化模糊匹配（忽略首尾空白）
        old_lines = [l.strip() for l in old_string.split('\n') if l.strip()]
        if old_lines:
            content_lines = content.split('\n')
            best_line = None
            for i, line in enumerate(content_lines, 1):
                stripped = line.strip()
                if stripped and old_lines[0] in stripped:
                    best_line = (i, line.strip()[:120])
                    break
            if best_line:
                return ToolResult(
                    success=False, output="",
                    error=(
                        f"精确匹配失败: old_string 在文件中未找到完全匹配（文件共 {total_lines} 行）。\n"
                        f"最接近的第 {best_line[0]} 行（去空白后匹配）:\n"
                        f"  {best_line[0]:5d} | {best_line[1]}\n\n"
                        f"建议：\n"
                        f"1. 重新 Read 文件，从第 {best_line[0]} 行附近精确复制原文（包括缩进、空白）\n"
                        f"2. 或缩小 old_string 范围，只匹配最关键的一两行\n"
                        f"3. 或使用行号范围模式: start_line={best_line[0]}, end_line={best_line[0] + line_count - 1}"
                        f"{mode_hint}"
                        f"{freshness_hint}"
                    )
                )

        # 策略 3：无法定位，尝试从首行关键词给出具体行号建议
        # 即使完全无法匹配，也尝试从 old_string 首行提取关键词定位
        first_line_hint = ""
        if old_lines:
            keyword = old_lines[0][:60]
            for i, line in enumerate(content_lines, 1):
                if keyword in line.strip():
                    first_line_hint = (
                        f"\n\n💡 可能的位置: 第 {i} 行包含相似内容 \"{line.strip()[:60]}\"\n"
                        f"可使用行号范围模式: Edit(file_path=\"{file_path}\", start_line={i}, end_line={i + line_count - 1}, new_string=...)"
                    )
                    break

        return ToolResult(
            success=False, output="",
            error=(
                f"精确匹配失败: old_string 在文件中未找到（文件共 {total_lines} 行）。\n\n"
                f"建议：\n"
                f"1. 重新 Read 文件，精确复制要替换的原文（包括缩进）\n"
                f"2. 或缩小 old_string 范围，只匹配最关键的一两行\n"
                f"3. 或使用行号范围模式直接指定行号"
                f"{mode_hint}"
                f"{first_line_hint}"
                f"{freshness_hint}"
            )
        )

    def _build_multiple_matches_error(
        self, content: str, old_string: str, positions: List[int]
    ) -> ToolResult:
        """多处匹配时的错误反馈"""
        # 计算每个匹配的行号
        match_lines = []
        for pos in positions[:5]:  # 最多显示 5 个
            line_num = content[:pos].count('\n') + 1
            match_lines.append(line_num)

        lines_info = ', '.join(str(l) for l in match_lines)
        if len(positions) > 5:
            lines_info += f' 等 {len(positions)} 处'

        # 提供行号模式建议
        first_line = match_lines[0]
        line_count = old_string.count('\n') + 1

        return ToolResult(
            success=False, output="",
            error=(
                f"多处匹配: old_string 在文件中匹配到 {len(positions)} 处（第 {lines_info} 行）。\n"
                f"必须添加更多上下文使匹配唯一。\n\n"
                f"建议：\n"
                f"1. 扩大 old_string 范围，包含更多上下文行使其唯一\n"
                f"2. 或使用行号范围模式: start_line={first_line}, end_line={first_line + line_count - 1}"
            )
        )

    # ============================================================
    # 模型输出（精确匹配模式）
    # ============================================================

    def _build_model_output(
        self, path, old_string, new_string, start_line, version, reference, syntax_warning=None, fuzzy_matched=False, new_content=None
    ) -> str:
        """构建给模型的纯文本输出（精确匹配模式），包含修改后上下文确认"""
        parts = []
        parts.append(f"File: {path.name}")
        parts.append(f"Path: {path}")
        parts.append(f"Cache: [{reference}]")
        parts.append(f"Mode: exact_match")
        if fuzzy_matched:
            parts.append(f"Match: fuzzy (whitespace/indent normalized)")
        parts.append(f"Start line: {start_line}")
        parts.append("")

        # 简洁 diff
        for line in old_string.splitlines():
            parts.append(f"- {line}")
        for line in new_string.splitlines():
            parts.append(f"+ {line}")

        # 修改后上下文确认（前后各3行，让模型无需额外 Read 即可确认结果）
        if new_content:
            new_lines = new_content.splitlines()
            new_line_count = len(new_string.splitlines())
            end_line = start_line + new_line_count - 1
            context_before = 3
            context_after = 3
            ctx_start = max(1, start_line - context_before)
            ctx_end = min(len(new_lines), end_line + context_after)
            if ctx_end > ctx_start:
                parts.append("")
                parts.append(f"▼ 修改后上下文（行 {ctx_start}-{ctx_end}）:")
                for i in range(ctx_start - 1, ctx_end):
                    marker = " →" if start_line <= i + 1 <= end_line else "  "
                    line_display = new_lines[i][:120] if len(new_lines[i]) > 120 else new_lines[i]
                    parts.append(f"  {i + 1:5d}{marker} {line_display}")

        if syntax_warning:
            parts.append("")
            parts.append(f"⚠️ 语法警告: {syntax_warning}")

        return '\n'.join(parts)

    # ============================================================
    # 模型输出（行号范围模式）
    # ============================================================

    def _build_line_range_model_output(
        self, path, start_line, end_line, old_string, new_string,
        version, reference, syntax_warning=None
    ) -> str:
        """构建给模型的纯文本输出（行号范围模式）

        关键：返回被替换的原始内容，供 AI 确认替换正确
        """
        parts = []
        parts.append(f"File: {path.name}")
        parts.append(f"Path: {path}")
        parts.append(f"Cache: [{reference}]")
        parts.append(f"Mode: line_range")
        parts.append(f"Replaced lines: {start_line}-{end_line}")
        parts.append("")

        # 被替换的原始内容（供 AI 确认）
        parts.append("▼ 被替换的原始内容:")
        for i, line in enumerate(old_string.splitlines(), start_line):
            parts.append(f"  {i:5d} | {line}")
        parts.append("")

        # 新内容
        parts.append("▼ 替换后的新内容:")
        for i, line in enumerate(new_string.splitlines(), start_line):
            parts.append(f"  {i:5d} | {line}")

        if syntax_warning:
            parts.append("")
            parts.append(f"⚠️ 语法警告: {syntax_warning}")

        return '\n'.join(parts)

    # ============================================================
    # 终端显示（精确匹配模式）
    # ============================================================

    def _build_terminal_display(
        self, path, old_string, new_string, original_content, new_content,
        start_line, version, reference, syntax_warning=None, fuzzy_matched=False
    ) -> str:
        """给终端的统一格式 diff 显示（精确匹配模式）"""
        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()
        original_lines = original_content.splitlines()

        context_lines = 2
        added_count = len(new_lines) - len(old_lines)

        result = []
        result.append("")
        line_change = f"-{len(old_lines)} lines, +{len(new_lines)} lines"
        fuzzy_tag = " [dim]\\[fuzzy][/]" if fuzzy_matched else ""
        result.append(f"[bold]{ICONS.get('edit', '✎')} Edit:[/] [cyan]{escape(str(path.name))}[/] [dim]\\[{reference}] ({line_change})[/]{fuzzy_tag}")

        # 上文（2空格缩进）
        for i in range(context_lines):
            line_num = start_line - context_lines + i
            if 0 <= line_num - 1 < len(original_lines):
                content = self._truncate_line(original_lines[line_num - 1])
                result.append(f"  [dim]{line_num:4d}[/]  [dim]{escape(content)}[/]")

        # 删除的行
        for i, line in enumerate(old_lines):
            line_num = start_line + i
            content = self._truncate_line(line)
            result.append(f"  [red]{line_num:4d}[/]  [red]{escape(content)}[/]")

        # 添加的行
        for i, line in enumerate(new_lines):
            line_num = start_line + i
            content = self._truncate_line(line)
            result.append(f"  [green]{line_num:4d}[/]  [green]{escape(content)}[/]")

        # 下文
        after_start_new = start_line + added_count
        for i in range(context_lines):
            line_num = after_start_new + i
            new_file_lines = new_content.splitlines()
            if line_num < len(new_file_lines):
                content = self._truncate_line(new_file_lines[line_num])
                result.append(f"  [dim]{line_num + 1:4d}[/]  [dim]{escape(content)}[/]")

        if syntax_warning:
            result.append("")
            result.append(f"  [yellow]⚠ 语法警告:[/] {escape(syntax_warning[:100])}")

        return '\n'.join(result)

    # ============================================================
    # 终端显示（行号范围模式）
    # ============================================================

    def _build_line_range_terminal_display(
        self, path, start_line, end_line, old_string, new_string,
        version, reference, syntax_warning=None
    ) -> str:
        """给终端的 diff 显示（行号范围模式）"""
        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()

        result = []
        result.append("")
        line_change = f"-{len(old_lines)} lines, +{len(new_lines)} lines"
        result.append(
            f"[bold]{ICONS.get('edit', '✎')} Edit:[/] [cyan]{escape(str(path.name))}[/] "
            f"[dim]\\[{reference}] lines {start_line}-{end_line} ({line_change})[/]"
        )

        # 删除的行（红色，2空格缩进）
        for i, line in enumerate(old_lines):
            line_num = start_line + i
            content = self._truncate_line(line)
            result.append(f"  [red]{line_num:4d}[/]  [red]{escape(content)}[/]")

        # 添加的行（绿色）
        for i, line in enumerate(new_lines):
            line_num = start_line + i
            content = self._truncate_line(line)
            result.append(f"  [green]{line_num:4d}[/]  [green]{escape(content)}[/]")

        if syntax_warning:
            result.append("")
            result.append(f"  [yellow]⚠ 语法警告:[/] {escape(syntax_warning[:100])}")

        return '\n'.join(result)

    def _truncate_line(self, line: str, max_len: int = 60) -> str:
        """截断过长的行"""
        if len(line) > max_len:
            return line[:max_len] + "..."
        return line

    # ============================================================
    # 文件不存在时的自动搜索回退
    # ============================================================

    def _handle_file_not_found(self, file_path: str, pm) -> ToolResult:
        """文件不存在时的处理：自动搜索同名文件并给出精确路径建议"""
        from claude_code.utils.paths import format_file_not_found_error
        error_msg = format_file_not_found_error(file_path, pm.active_path)
        return ToolResult(success=False, output="", error=error_msg)

    # ============================================================
    # 工具属性
    # ============================================================

    def is_read_only(self) -> bool:
        return False

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数（支持两种模式）"""
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"

        new_string = parameters.get("new_string")
        if new_string is None:
            return "缺少 new_string 参数"

        # 判断模式
        start_line = parameters.get("start_line")
        end_line = parameters.get("end_line")
        old_string = parameters.get("old_string")

        has_line_range = start_line is not None or end_line is not None
        has_old_string = old_string is not None

        if has_line_range:
            # 行号范围模式：start_line 和 end_line 必须同时提供
            if start_line is None or end_line is None:
                return "行号范围模式需要同时提供 start_line 和 end_line"
            try:
                sl = int(start_line)
                el = int(end_line)
            except (ValueError, TypeError):
                return "start_line 和 end_line 必须是整数"
            if sl < 1:
                return "start_line 必须 >= 1"
            if el < sl:
                return "end_line 必须 >= start_line"
            # 行号范围模式不需要 old_string（如果提供了则忽略）
        else:
            # 精确匹配模式：old_string 必填
            if not old_string:
                return "缺少 old_string 参数（或改用行号范围模式：提供 start_line 和 end_line）"

        return None

    def get_security_context(self) -> Dict[str, Any]:
        """返回安全上下文"""
        return {
            "is_sensitive": True,
            "paths": [self.parameters.get("file_path", "")],
            "command_preview": ""
        }
