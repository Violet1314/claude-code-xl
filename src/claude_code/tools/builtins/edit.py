"""Edit 工具 - 编辑文件（多层匹配，集成缓存，语法检查）"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from difflib import SequenceMatcher
from ..base import Tool, ToolResult
from ..file_cache import file_cache
from ..syntax_checker import check_syntax, get_supported_extensions
from claude_code.utils.paths import resolve_workplace_path
from claude_code.ui.theme import COLORS, ICONS
from rich.markup import escape


class EditTool(Tool):
    """编辑文件工具（带缓存，支持多层匹配 + 行号模式）"""
    name = "Edit"
    description = (
        "编辑文件内容。支持两种模式：\n"
        "1. replace 模式（默认）：精确替换，需提供 old_string 和 new_string\n"
        "2. lines 模式：按行号替换，只需提供 start_line、end_line 和 new_content，无需复制原文\n"
        "编辑后文件缓存自动更新，无需重新读取。"
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "mode": {
                    "type": "string",
                    "enum": ["replace", "lines"],
                    "description": "编辑模式：replace（精确替换）或 lines（行号替换）",
                    "default": "replace"
                },
                "old_string": {
                    "type": "string",
                    "description": "[replace模式] 要替换的原始内容（必须完全匹配，包括缩进和换行）"
                },
                "new_string": {
                    "type": "string",
                    "description": "[replace模式] 替换后的新内容"
                },
                "start_line": {
                    "type": "integer",
                    "description": "[lines模式] 起始行号（从1开始，包含）"
                },
                "end_line": {
                    "type": "integer",
                    "description": "[lines模式] 结束行号（从1开始，包含）"
                },
                "new_content": {
                    "type": "string",
                    "description": "[lines模式] 替换后的新内容"
                }
            },
            # required 根据 mode 动态判断，这里不强制
            "required": ["file_path"]
        }

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行编辑操作（支持 replace 和 lines 两种模式）"""
        file_path = parameters.get("file_path", "")
        mode = parameters.get("mode", "replace")

        if not file_path:
            return ToolResult(success=False, output="", error="缺少 file_path 参数")
        file_path = resolve_workplace_path(file_path)

        # 根据 mode 分流
        if mode == "lines":
            return self._execute_lines_mode(parameters, file_path)
        else:
            return self._execute_replace_mode(parameters, file_path)

    def _execute_lines_mode(self, parameters: Dict[str, Any], file_path: str) -> ToolResult:
        """lines 模式：按行号替换"""
        start_line = parameters.get("start_line")
        end_line = parameters.get("end_line")
        new_content = parameters.get("new_content", "")

        # 参数验证
        if start_line is None:
            return ToolResult(success=False, output="", error="lines 模式缺少 start_line 参数")
        if end_line is None:
            return ToolResult(success=False, output="", error="lines 模式缺少 end_line 参数")

        try:
            start_line = int(start_line)
            end_line = int(end_line)
        except (ValueError, TypeError):
            return ToolResult(success=False, output="", error="start_line 和 end_line 必须是整数")

        if start_line < 1:
            return ToolResult(success=False, output="", error=f"start_line 必须 >= 1，当前: {start_line}")
        if end_line < start_line:
            return ToolResult(success=False, output="", error=f"end_line ({end_line}) 不能小于 start_line ({start_line})")

        try:
            path = Path(file_path)
            if not path.exists():
                return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")

            with open(path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            lines = original_content.splitlines(keepends=True)
            total_lines = len(lines)

            # 行号越界检查
            if start_line > total_lines:
                return ToolResult(success=False, output="", error=f"start_line ({start_line}) 超出文件行数 ({total_lines})")
            if end_line > total_lines:
                return ToolResult(success=False, output="", error=f"end_line ({end_line}) 超出文件行数 ({total_lines})")

            actual_end_line = end_line

            # 提取被替换的内容（用于显示 diff）
            replaced_lines = lines[start_line - 1:actual_end_line]
            old_content = ''.join(replaced_lines)

            # 构建新内容
            # 确保 new_content 以换行结尾（如果原文有换行）
            if new_content and not new_content.endswith('\n') and old_content.endswith('\n'):
                new_content = new_content + '\n'

            # 执行替换
            new_lines = lines[:start_line - 1] + [new_content] + lines[actual_end_line:]
            new_file_content = ''.join(new_lines)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_file_content)

            # 更新缓存
            cache_result = file_cache.apply_write(file_path, new_file_content)
            version = cache_result["version"]
            reference = cache_result["reference"]

            # 语法检查
            is_valid, syntax_warning = check_syntax(new_file_content, file_path)

            # 构建输出（使用 lines 模式专用方法）
            output = self._build_lines_model_output(
                path, start_line, actual_end_line, old_content, new_content,
                reference, version, syntax_warning
            )
            display_output = self._build_lines_terminal_display(
                path, start_line, actual_end_line, old_content, new_content,
                reference, version, syntax_warning
            )

            replaced_count = actual_end_line - start_line + 1
            return ToolResult(
                success=True,
                output=output,
                display_output=display_output,
                summary=f"Edit {path.name} (lines {start_line}-{actual_end_line})",
                metadata={
                    "file_path": str(path.absolute()),
                    "mode": "lines",
                    "start_line": start_line,
                    "end_line": actual_end_line,
                    "replaced_lines": replaced_count,
                    "new_lines": new_content.count('\n') + 1 if new_content else 0,
                    "cache_version": version,
                    "syntax_valid": is_valid,
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足，无法写入: {file_path}")
        except FileNotFoundError:
            return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")
        except OSError as e:
            return ToolResult(success=False, output="", error=f"系统错误: {e.strerror or str(e)} ({file_path})")
        except UnicodeDecodeError as e:
            return ToolResult(success=False, output="", error=f"编码错误: 文件包含无法解码的字符 ({e})")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"编辑失败: {type(e).__name__}: {str(e)}")

    def _execute_replace_mode(self, parameters: Dict[str, Any], file_path: str) -> ToolResult:
        """replace 模式：精确替换（原有逻辑）"""
        old_string = parameters.get("old_string", "")
        new_string = parameters.get("new_string", "")

        if not old_string:
            return ToolResult(success=False, output="", error="replace 模式缺少 old_string 参数")

        try:
            path = Path(file_path)
            if not path.exists():
                return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")

            with open(path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            # ============================================================
            # 多层匹配策略
            # ============================================================
            positions, match_type = self._find_all_matches(original_content, old_string)
            
            if not positions:
                # 完全没有匹配，返回模糊匹配候选
                return self._build_no_match_error(original_content, old_string)

            # 检查匹配数量
            match_count = len(positions)
            
            if match_count > 1:
                # 多处匹配，返回候选列表让模型选择
                return self._build_multiple_matches_error(
                    original_content, old_string, positions, match_type
                )

            # 单处匹配，执行替换
            start_pos = positions[0]
            end_pos = start_pos + len(old_string)
            new_content = original_content[:start_pos] + new_string + original_content[end_pos:]

            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # 更新缓存
            cache_result = file_cache.apply_write(file_path, new_content)
            version = cache_result["version"]
            reference = cache_result["reference"]

            # 计算起始行号
            start_line = original_content[:start_pos].count('\n') + 1

            # 语法检查
            is_valid, syntax_warning = check_syntax(new_content, file_path)

            output = self._build_model_output(
                path, old_string, new_string,
                original_content, new_content,
                reference, version, match_count, start_line, syntax_warning
            )
            display_output = self._build_terminal_display(
                path, old_string, new_string,
                original_content, new_content,
                reference, version, match_count, start_line, syntax_warning
            )

            return ToolResult(
                success=True,
                output=output,
                display_output=display_output,
                summary=f"Edit {path.name}",
                metadata={
                    "file_path": str(path.absolute()),
                    "old_length": len(old_string),
                    "new_length": len(new_string),
                    "match_count": match_count,
                    "match_type": match_type,
                    "cache_version": version,
                    "cache_reference": reference,
                    "syntax_valid": is_valid,
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足，无法读取或写入: {file_path}")
        except FileNotFoundError:
            return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")
        except OSError as e:
            return ToolResult(success=False, output="", error=f"系统错误: {e.strerror or str(e)} ({file_path})")
        except UnicodeDecodeError as e:
            return ToolResult(success=False, output="", error=f"编码错误: 文件包含无法解码的字符 ({e})")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"编辑失败: {type(e).__name__}: {str(e)}")

    def _build_no_match_error(self, content: str, old_string: str) -> ToolResult:
        """构建无匹配时的错误信息"""
        content_lines = content.splitlines()
        old_lines = old_string.splitlines()
        
        # 获取模糊匹配候选
        candidates, scores = self._fuzzy_match(content_lines, old_lines, threshold=0.6)
        
        error_parts = ["❌ 未找到匹配内容"]
        error_parts.append(f"匹配类型: 无匹配")
        error_parts.append(f"目标内容: {self._truncate_line(old_lines[0] if old_lines else '', 50)}...")
        error_parts.append("")
        
        if candidates:
            error_parts.append(f"🔍 发现 {len(candidates)} 个相似位置：")
            error_parts.append(self._build_candidates_report(content_lines, candidates, len(old_lines), scores))
        else:
            error_parts.append("💡 建议：")
            error_parts.append("1. 使用 Read 工具查看文件最新内容")
            error_parts.append("2. 复制完整的代码块（包含正确的缩进）")
            error_parts.append("3. 确保包含足够的上下文行（前后各 2-3 行）")
        
        return ToolResult(
            success=False,
            output="",
            error='\n'.join(error_parts)
        )

    def _build_multiple_matches_error(
        self, content: str, old_string: str, positions: List[int], match_type: str
    ) -> ToolResult:
        """构建多处匹配时的错误信息"""
        content_lines = content.splitlines()
        old_lines = old_string.splitlines()
        
        error_parts = ["⚠️ 发现多处匹配"]
        error_parts.append(f"匹配类型: {match_type}")
        error_parts.append(f"匹配数量: {len(positions)} 处")
        error_parts.append("")
        error_parts.append("请添加更多上下文行以唯一标识目标位置：")
        error_parts.append(self._build_candidates_report(content_lines, positions, len(old_lines)))
        error_parts.append("")
        error_parts.append("💡 建议：在 old_string 前后各添加 2-3 行上下文代码")
        
        return ToolResult(
            success=False,
            output="",
            error='\n'.join(error_parts)
        )

    def get_security_context(self) -> Dict[str, Any]:
        """返回安全上下文"""
        return {
            "is_sensitive": True,
            "paths": [self.parameters.get("file_path", "")],
            "command_preview": ""
        }

    # ============================================================
    # 模型输出（纯文本）
    # ============================================================

    def _build_model_output(
        self, path, old_string, new_string,
        original_content, new_content,
        reference, version, match_count, start_line, syntax_warning=None
    ) -> str:
        """给模型的纯文本输出"""
        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()

        parts = []
        parts.append(f"Edit: {path.name} - {reference} (v{version})")
        parts.append(f"  -{len(old_lines)} lines, +{len(new_lines)} lines at line {start_line}")
        parts.append(" ")

        # 简洁 diff
        for line in old_lines:
            parts.append(f"- {line}")
        for line in new_lines:
            parts.append(f"+ {line}")

        if match_count > 1:
            parts.append(f"\nWarning: {match_count} matches found, replaced first occurrence only.")

        if syntax_warning:
            parts.append(f"\n【语法警告】{syntax_warning}")
            parts.append("建议：检查并修正语法错误后再继续。")

        return '\n'.join(parts)

    # ============================================================
    # 终端显示（Rich markup）
    # ============================================================

    def _build_terminal_display(
        self, path, old_string, new_string,
        original_content, new_content,
        reference, version, match_count, start_line, syntax_warning=None
    ) -> str:
        """给终端的统一格式 diff 显示"""
        from claude_code.ui.theme import ICONS

        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()
        original_lines = original_content.splitlines()

        context_lines = 2
        added_count = len(new_lines) - len(old_lines)

        result = []
        # 开头空行，与其他工具分隔
        result.append("")
        # 标题行：✎ Edit: 文件名 [v2] (-3 lines, +5 lines)
        line_change = f"-{len(old_lines)} lines, +{len(new_lines)} lines"
        result.append(f"[bold]{ICONS.get('edit', '✎')} Edit:[/] [cyan]{escape(str(path.name))}[/] [dim]\\[{reference}] ({line_change})[/]")
        result.append(f"[dim]{'─' * 50}[/]")

        # 上文
        before_start = max(0, start_line - 1 - context_lines)
        for i in range(before_start, start_line - 1):
            if i < len(original_lines):
                content = self._truncate_line(original_lines[i])
                result.append(f"     [dim]{i + 1:4d}[/]  [dim]{escape(content)}[/]")

        # 删除行（红色字体）
        for i, line in enumerate(old_lines):
            content = self._truncate_line(line)
            result.append(f"     [dim]{start_line + i:4d}[/]  [red]- {escape(content)}[/]")

        # 新增行（绿色字体）
        for i, line in enumerate(new_lines):
            content = self._truncate_line(line)
            result.append(f"     [dim]{start_line + i:4d}[/]  [green]+ {escape(content)}[/]")

        # 下文
        new_file_lines = new_content.splitlines()
        after_start_new = start_line + added_count
        for i in range(context_lines):
            line_num = after_start_new + i
            if line_num < len(new_file_lines):
                content = self._truncate_line(new_file_lines[line_num])
                result.append(f"     [dim]{line_num + 1:4d}[/]  [dim]{escape(content)}[/]")

        if match_count > 1:
            result.append(f"\n[yellow]⚠️ 共 {match_count} 处匹配，已替换第 1 处[/]")

        if syntax_warning:
            result.append(f"[yellow]⚠ 语法警告:[/] [dim]{escape(syntax_warning[:80])}[/]")

        return '\n'.join(result)

    # ============================================================
    # 多层匹配方法（核心重构）
    # ============================================================

    def _find_all_matches(self, content: str, old_string: str) -> Tuple[List[int], str, List[float]]:
        """多层匹配策略，返回所有匹配位置、匹配类型和相似度分数
        
        Returns:
            (positions, match_type): 匹配位置列表（字符位置）和匹配类型描述
                match_type: "exact" | "whitespace_insensitive" | "fuzzy" | "none"
        """
        content_lines = content.splitlines()
        old_lines = old_string.splitlines()
        
        if not old_lines:
            return [], "none"
        
        # Layer 1: 精确匹配
        positions = self._exact_match(content_lines, old_lines)
        if positions:
            return positions, "exact"
        
        # Layer 2: 忽略空白匹配
        positions = self._whitespace_insensitive_match(content_lines, old_lines)
        if positions:
            return positions, "whitespace_insensitive"
        
        # Layer 3: 模糊匹配（相似度 >= 0.8）
        positions, _ = self._fuzzy_match(content_lines, old_lines, threshold=0.8)
        if positions:
            return positions, "fuzzy"
        
        return [], "none"

    def _exact_match(self, content_lines: List[str], old_lines: List[str]) -> List[int]:
        """
        精确匹配：逐字符完全匹配
        返回匹配起始位置的字符索引列表
        """
        content = '\n'.join(content_lines)
        old_string = '\n'.join(old_lines)
        
        positions = []
        start = 0
        while True:
            pos = content.find(old_string, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        
        return positions

    def _whitespace_insensitive_match(self, content_lines: List[str], old_lines: List[str]) -> List[int]:
        """
        忽略空白匹配：标准化空白后匹配
        返回匹配起始位置的字符索引列表
        """
        if not old_lines:
            return []
        
        # 标准化函数：去除首尾空白，合并多个空格
        def normalize(s: str) -> str:
            return ' '.join(s.split())
        
        normalized_old = [normalize(line) for line in old_lines]
        
        positions = []
        content = '\n'.join(content_lines)
        
        for i in range(len(content_lines) - len(old_lines) + 1):
            # 检查连续行是否匹配
            match = True
            for j, old_line in enumerate(normalized_old):
                if i + j >= len(content_lines):
                    match = False
                    break
                if normalize(content_lines[i + j]) != old_line:
                    match = False
                    break
            
            if match:
                # 计算字符位置
                char_pos = sum(len(content_lines[k]) + 1 for k in range(i))
                positions.append(char_pos)
        
        return positions

    def _fuzzy_match(
        self, content_lines: List[str], old_lines: List[str], threshold: float = 0.8
    ) -> Tuple[List[int], List[float]]:
        """
        模糊匹配：使用 difflib 计算相似度
        返回 (匹配起始位置列表, 相似度分数列表)
        """
        if not old_lines:
            return [], []
        
        candidates = []  # (position, score)
        old_text = '\n'.join(old_lines)
        
        for i in range(len(content_lines) - len(old_lines) + 1):
            candidate = '\n'.join(content_lines[i:i + len(old_lines)])
            ratio = SequenceMatcher(None, candidate, old_text).ratio()
            
            if ratio >= threshold:
                # 计算字符位置
                char_pos = sum(len(content_lines[k]) + 1 for k in range(i))
                candidates.append((char_pos, ratio))
        
        # 按相似度降序排序
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        positions = [c[0] for c in candidates]
        scores = [c[1] for c in candidates]
        
        return positions, scores

    def _build_candidates_report(
        self, content_lines: List[str], positions: List[int], 
        n_lines: int, scores: List[float] = None,
        max_candidates: int = 3, context_lines: int = 2
    ) -> str:
        """构建候选位置报告（用于错误提示）"""
        report = []
        
        for idx, pos in enumerate(positions[:max_candidates]):
            # 计算行号
            line_num = content_lines[:pos].count('\n') if pos > 0 else 0
            start = max(0, line_num - context_lines)
            end = min(len(content_lines), line_num + n_lines + context_lines)
            
            # 相似度分数（如果有）
            score_str = ""
            if scores and idx < len(scores):
                score_str = f" (相似度 {scores[idx]*100:.0f}%)"
            
            report.append(f"\n📍 候选 {idx + 1}{score_str}:")
            report.append(f"   Line {line_num + 1}-{line_num + n_lines}:")
            
            # 显示上下文 + 匹配区域
            for i in range(start, end):
                line_content = self._truncate_line(content_lines[i], 50)
                
                if i < line_num:
                    # 上文
                    report.append(f"   [dim]{i + 1:4d}[/]  [dim]{escape(line_content)}[/]")
                elif i < line_num + n_lines:
                    # 匹配区域（高亮）
                    report.append(f"   [bold]{i + 1:4d}[/]  [yellow]{escape(line_content)}[/]")
                else:
                    # 下文
                    report.append(f"   [dim]{i + 1:4d}[/]  [dim]{escape(line_content)}[/]")
        
        if len(positions) > max_candidates:
            report.append(f"\n   ... 还有 {len(positions) - max_candidates} 个候选")
        
        return '\n'.join(report)

    # ============================================================
    # 辅助方法
    # ============================================================

    def _find_start_line(self, original_content: str, old_string: str) -> int:
        """找到 old_string 在文件中的起始行号（1-based）"""
        pos = original_content.find(old_string)
        if pos == -1:
            return 1
        return original_content[:pos].count('\n') + 1

    def _find_similar_lines(self, content: str, target: str, max_suggestions: int = 3) -> str:
        """
        在 content 中查找与 target 最相似的几行，用于辅助调试。
        """
        if not target:
            return ""
        
        target_lines = target.splitlines()
        if not target_lines:
            return ""
        
        # 取第一行非空内容作为关键词
        keyword = target_lines[0].strip()
        if not keyword:
            if len(target_lines) > 1:
                keyword = target_lines[1].strip()
            else:
                return ""

        content_lines = content.splitlines()
        matches = []

        for i, line in enumerate(content_lines):
            if keyword in line:
                # 记录行号和前后各一行作为上下文
                start = max(0, i - 1)
                end = min(len(content_lines), i + 2)
                snippet = "\n".join(content_lines[start:end])
                matches.append(f"Line {i+1}:\n{snippet}")

                if len(matches) >= max_suggestions:
                    break

        if matches:
            return "\n---\n".join(matches)
        return ""

    def _truncate_line(self, line: str, max_len: int = 60) -> str:
        """截断过长的行"""
        if len(line) > max_len:
            return line[:max_len] + "..."
        return line

    def is_read_only(self) -> bool:
        return False

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数（支持 replace 和 lines 两种模式）"""
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"

        mode = parameters.get("mode", "replace")

        if mode == "replace":
            old_string = parameters.get("old_string")
            if not old_string:
                return "replace 模式缺少 old_string 参数"
        elif mode == "lines":
            start_line = parameters.get("start_line")
            end_line = parameters.get("end_line")
            if start_line is None:
                return "lines 模式缺少 start_line 参数"
            if end_line is None:
                return "lines 模式缺少 end_line 参数"
            if start_line < 1:
                return "start_line 必须 >= 1"
            if end_line < start_line:
                return "end_line 必须 >= start_line"
        else:
            return f"不支持的模式: {mode}"

        return None

    # ============================================================
    # lines 模式输出构建
    # ============================================================

    def _build_lines_model_output(
        self, path, start_line, end_line, old_content, new_content,
        reference, version, syntax_warning=None
    ) -> str:
        """lines 模式：给模型的纯文本输出"""
        old_lines = old_content.splitlines() if old_content else []
        new_lines = new_content.splitlines() if new_content else []

        parts = []
        parts.append(f"Edit: {path.name} - {reference} (v{version})")
        parts.append(f"  [lines 模式] 替换第 {start_line}-{end_line} 行")
        parts.append(f"  -{len(old_lines)} lines, +{len(new_lines)} lines")
        parts.append(" ")

        # 简洁 diff
        for line in old_lines:
            parts.append(f"- {line}")
        for line in new_lines:
            parts.append(f"+ {line}")

        if syntax_warning:
            parts.append(f"\n⚠️ Syntax Warning: {syntax_warning}")

        return '\n'.join(parts)

    def _build_lines_terminal_display(
        self, path, start_line, end_line, old_content, new_content,
        reference, version, syntax_warning=None
    ) -> str:
        """lines 模式：终端 Rich 格式显示"""
        old_lines = old_content.splitlines() if old_content else []
        new_lines = new_content.splitlines() if new_content else []

        parts = []
        parts.append("")
        parts.append(f"[bold]{ICONS.get('edit', '✎')} Edit:[/] [cyan]{escape(path.name)}[/] [dim]{reference} → v{version}[/]")
        parts.append(f"[dim]{'─' * 50}[/]")
        parts.append(f"[dim][lines 模式] 替换第 {start_line}-{end_line} 行[/]")
        parts.append("")

        # 红色删除行
        for i, line in enumerate(old_lines):
            line_num = start_line + i
            display_line = self._truncate_line(line, 80)
            parts.append(f"[red]-{line_num:>5}[/]  {escape(display_line)}")

        # 绿色新增行
        for i, line in enumerate(new_lines):
            line_num = start_line + i
            display_line = self._truncate_line(line, 80)
            parts.append(f"[green]+{line_num:>5}[/]  {escape(display_line)}")

        parts.append("")
        parts.append(f"[dim]{'─' * 50}[/]")
        parts.append(f"[{COLORS['success']}]{ICONS['success']} 已替换 {len(old_lines)} 行 → {len(new_lines)} 行[/]")

        if syntax_warning:
            parts.append(f"[yellow]⚠ 语法警告:[/] [dim]{escape(syntax_warning[:80])}[/]")

        return '\n'.join(parts)