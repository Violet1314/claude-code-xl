"""Edit 工具 - 编辑文件（精确替换，集成缓存）"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import Tool, ToolResult
from ..file_cache import file_cache


class EditTool(Tool):
    """编辑文件工具（带缓存）"""

    name = "Edit"
    description = "精确替换文件中的内容。编辑后文件缓存自动更新，无需重新读取。"

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "old_string": {
                    "type": "string",
                    "description": "要替换的原始内容（必须完全匹配）"
                },
                "new_string": {
                    "type": "string",
                    "description": "替换后的新内容"
                }
            },
            "required": ["file_path", "old_string", "new_string"]
        }

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行编辑操作"""
        file_path = parameters.get("file_path", "")
        old_string = parameters.get("old_string", "")
        new_string = parameters.get("new_string", "")

        # 参数验证
        if not file_path:
            return ToolResult(success=False, output="", error="缺少 file_path 参数")

        if not old_string:
            return ToolResult(success=False, output="", error="缺少 old_string 参数")

        try:
            path = Path(file_path)

            if not path.exists():
                return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")

            # 读取文件内容
            with open(path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            # 检查是否存在 old_string
            if old_string not in original_content:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"未找到要替换的内容。请确保 old_string 与文件中的内容完全一致。"
                )

            # 统计匹配次数
            match_count = original_content.count(old_string)
            if match_count > 1:
                new_content = original_content.replace(old_string, new_string, 1)
            else:
                new_content = original_content.replace(old_string, new_string)

            # 写回文件
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            # 更新缓存
            cache_result = file_cache.apply_write(file_path, new_content)
            reference = cache_result.get("reference", "")
            version = cache_result.get("version", 0)

            # 生成简洁的 diff 摘要
            diff_summary = self._make_diff_summary(old_string, new_string)

            # 构建输出
            result = []
            result.append(f"✅ 编辑成功: {path.name}")
            result.append(f"📌 新引用: {reference} (v{version})")
            result.append(f"📝 变更: {diff_summary}")

            if match_count > 1:
                result.append(f"⚠️ 共 {match_count} 处匹配，已替换第 1 处")

            result.append(f"💡 缓存已更新，后续操作使用引用 {reference}")

            return ToolResult(
                success=True,
                output="\n".join(result),
                metadata={
                    "file_path": str(path.absolute()),
                    "old_length": len(old_string),
                    "new_length": len(new_string),
                    "match_count": match_count,
                    "cache_version": version,
                    "cache_reference": reference,
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足: {file_path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"编辑失败: {str(e)}")

    def _make_diff_summary(self, old: str, new: str) -> str:
        """生成 diff 摘要"""
        old_lines = old.strip().split('\n')
        new_lines = new.strip().split('\n')

        if len(old_lines) == 1 and len(new_lines) == 1:
            # 单行替换
            old_short = old[:40] + "..." if len(old) > 40 else old
            new_short = new[:40] + "..." if len(new) > 40 else new
            return f"`{old_short}` → `{new_short}`"
        else:
            # 多行替换
            return f"{len(old_lines)}行 → {len(new_lines)}行"

    def _generate_diff(
        self,
        file_path: str,
        original_content: str,
        new_content: str,
        old_string: str,
        new_string: str
    ) -> str:
        """
        生成类似官方风格的 diff 输出

        Args:
            file_path: 文件路径
            original_content: 原文件完整内容
            new_content: 新文件完整内容
            old_string: 被替换的内容
            new_string: 替换后的内容

        Returns:
            格式化的 diff 输出
        """
        original_lines = original_content.splitlines()
        old_lines = old_string.splitlines()
        new_lines = new_string.splitlines()

        removed_count = len(old_lines)
        added_count = len(new_lines)

        # 找到变化在文件中的起始行号
        start_line = self._find_start_line(original_lines, old_string)

        # 计算显示范围
        context_lines = 2  # 上下文行数
        display_start = max(1, start_line - context_lines)
        display_end = min(len(new_content.splitlines()), start_line + max(removed_count, added_count) + context_lines)

        # 构建输出
        result = []

        # 标题行
        result.append(f"[bold green]Update[/]([cyan]{file_path}[/])")
        result.append(f"  [dim]  [/][green bold]+{added_count}[/] [red bold]-{removed_count}[/]")
        result.append("")

        # 新文件的行列表（用于显示）
        new_file_lines = new_content.splitlines()

        # 记录当前在新文件中的位置
        new_line_idx = display_start - 1

        for line_num in range(display_start, display_end + 1):
            # 判断这一行是上下文还是变化
            is_before_context = line_num < start_line
            is_after_context = line_num >= start_line + added_count

            if is_before_context:
                # 上文（灰色，未变化）
                if line_num - 1 < len(new_file_lines):
                    content = self._truncate_line(new_file_lines[line_num - 1])
                    result.append(f"     [dim]{line_num:4d}[/]  [dim]{content}[/]")
            elif is_after_context:
                # 下文（灰色，未变化）
                if line_num - 1 < len(new_file_lines):
                    content = self._truncate_line(new_file_lines[line_num - 1])
                    result.append(f"     [dim]{line_num:4d}[/]  [dim]{content}[/]")
            else:
                # 变化区域
                change_idx = line_num - start_line

                # 显示删除的行
                if change_idx < removed_count:
                    old_line_content = self._truncate_line(old_lines[change_idx])
                    result.append(f"     [dim]{start_line + change_idx:4d}[/]  [white on #b85450]- {old_line_content}[/]")

                # 显示新增的行
                if change_idx < added_count:
                    new_line_content = self._truncate_line(new_lines[change_idx])
                    result.append(f"     [dim]{start_line + change_idx:4d}[/]  [white on #3d8c40]+ {new_line_content}[/]")

        return "\n".join(result)

    def _find_start_line(self, original_lines: List[str], old_string: str) -> int:
        """
        找到 old_string 在文件中的起始行号（1-based）

        Args:
            original_lines: 原文件的行列表
            old_string: 被替换的内容

        Returns:
            起始行号（从 1 开始）
        """
        old_lines = old_string.splitlines()
        if not old_lines:
            return 1

        first_line = old_lines[0].strip()

        for i, line in enumerate(original_lines):
            if first_line in line.strip() or line.strip() in first_line:
                # 检查后续行是否匹配
                match = True
                for j, old_line in enumerate(old_lines):
                    if i + j >= len(original_lines):
                        match = False
                        break
                    # 放宽匹配条件
                    if old_line.strip() and old_line.strip() not in original_lines[i + j].strip():
                        # 允许部分不匹配
                        pass
                if match:
                    return i + 1  # 行号从 1 开始

        return 1  # 默认返回第一行

    def _truncate_line(self, line: str, max_len: int = 60) -> str:
        """
        截断过长的行

        Args:
            line: 行内容
            max_len: 最大长度

        Returns:
            截断后的行
        """
        if len(line) > max_len:
            return line[:max_len] + "..."
        return line

    def is_read_only(self) -> bool:
        """非只读操作"""
        return False