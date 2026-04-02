"""Edit 工具 - 编辑文件（精确替换，集成缓存）"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import Tool, ToolResult
from ..file_cache import file_cache
from claude_code.utils.paths import resolve_workplace_path


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

        # Workplace 隔离：相对路径重定向到 workplace 目录
        file_path = resolve_workplace_path(file_path)

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

            # 生成 diff 显示
            diff_output = self._generate_diff(
                str(path),
                original_content,
                new_content,
                old_string,
                new_string
            )

            # 构建输出
            result = []
            result.append(f"✅ 编辑成功: {path.name}")
            # 转义方括号，避免被 Rich markup 解析
            escaped_reference = reference.replace("[", "\\[") if reference else ""
            result.append(f"📌 新引用: {escaped_reference} (v{version})")
            result.append("")  # 空行
            result.append(diff_output)  # diff 显示

            if match_count > 1:
                result.append(f"\n⚠️ 共 {match_count} 处匹配，已替换第 1 处")

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
        old_lines = old_string.splitlines() if old_string else []
        new_lines = new_string.splitlines() if new_string else []

        removed_count = len(old_lines)
        added_count = len(new_lines)

        # 找到变化在文件中的起始行号
        start_line = self._find_start_line(original_lines, old_string)

        # 构建输出
        result = []

        # 标题行
        result.append(f"[bold green]Update[/]([cyan]{file_path}[/])")
        result.append(f"  [dim]  [/][green bold]+{added_count}[/] [red bold]-{removed_count}[/]")
        result.append("")

        # 上下文行数
        context_lines = 2

        # 显示上文（变化之前的行）
        for i in range(max(0, start_line - context_lines - 1), start_line - 1):
            if i < len(original_lines):
                content = self._truncate_line(original_lines[i])
                result.append(f"     [dim]{i + 1:4d}[/]  [dim]{content}[/]")

        # 显示删除的行（红色背景）
        for i, line in enumerate(old_lines):
            content = self._truncate_line(line)
            result.append(f"     [dim]{start_line + i:4d}[/]  [white on #b85450]- {content}[/]")

        # 显示新增的行（绿色背景）
        for i, line in enumerate(new_lines):
            content = self._truncate_line(line)
            result.append(f"     [dim]{start_line + i:4d}[/]  [white on #3d8c40]+ {content}[/]")

        # 显示下文（变化之后的行）
        # 删除/替换后的行号从 start_line + added_count 开始
        after_start = start_line + removed_count  # 原文件中的行号
        new_file_lines = new_content.splitlines()
        after_start_new = start_line + added_count  # 新文件中的行号

        for i in range(context_lines):
            line_num_new = after_start_new + i
            if line_num_new < len(new_file_lines):
                content = self._truncate_line(new_file_lines[line_num_new])
                result.append(f"     [dim]{line_num_new + 1:4d}[/]  [dim]{content}[/]")

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

        # 使用精确匹配：检查连续多行是否完全匹配
        first_line = old_lines[0]

        for i in range(len(original_lines) - len(old_lines) + 1):
            # 检查从第 i 行开始是否完全匹配
            match = True
            for j, old_line in enumerate(old_lines):
                if i + j >= len(original_lines):
                    match = False
                    break
                # 精确匹配（不使用 strip，保留缩进）
                if original_lines[i + j] != old_line:
                    match = False
                    break

            if match:
                return i + 1  # 行号从 1 开始

        # 如果精确匹配失败，尝试宽松匹配
        first_line_stripped = old_lines[0].strip()
        for i in range(len(original_lines) - len(old_lines) + 1):
            if original_lines[i].strip() == first_line_stripped:
                # 检查后续行
                match = True
                for j, old_line in enumerate(old_lines):
                    if i + j >= len(original_lines):
                        match = False
                        break
                    if original_lines[i + j].strip() != old_line.strip():
                        match = False
                        break
                if match:
                    return i + 1

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

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"

        old_string = parameters.get("old_string")
        if not old_string:
            return "缺少 old_string 参数"

        # new_string 可以为空（表示删除内容）
        # old_string 不能为空（无法匹配空字符串）

        return None