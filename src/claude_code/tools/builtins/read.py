"""Read 工具 - 读取文件内容（集成缓存）"""
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import Tool, ToolResult
from ..file_cache import file_cache


class ReadTool(Tool):
    """读取文件工具（带缓存）"""

    name = "Read"
    description = (
        "读取用户本机文件内容。你可以直接访问用户提供的任何本地路径，无需用户手动粘贴内容。"
        "文件会被缓存，后续操作使用缓存引用而非完整内容，节省 Token。"
        "当用户提到文件路径时，立即调用此工具读取。"
    )

    # 文件大小限制 (1MB)
    MAX_FILE_SIZE = 1 * 1024 * 1024
    # 默认读取行数限制（提高到1000，减少分次读取）
    DEFAULT_LIMIT = 1000
    # 摘要模式阈值（行数）
    SUMMARY_THRESHOLD = 100
    # 摘要预览行数
    PREVIEW_LINES = 30

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要读取的文件路径（绝对路径或相对路径）"
                },
                "offset": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始），可选",
                    "default": 1
                },
                "limit": {
                    "type": "integer",
                    "description": f"读取的最大行数，默认 {self.DEFAULT_LIMIT} 行。大文件建议分段读取。",
                    "default": self.DEFAULT_LIMIT
                },
                "summary": {
                    "type": "boolean",
                    "description": "是否返回摘要模式。大文件默认 true，设置 false 获取完整内容。",
                    "default": True
                }
            },
            "required": ["file_path"]
        }

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行读取操作"""
        file_path = parameters.get("file_path", "")

        # 参数类型转换
        try:
            offset = int(parameters.get("offset", 1))
        except (ValueError, TypeError):
            offset = 1

        try:
            limit = int(parameters.get("limit", self.DEFAULT_LIMIT))
        except (ValueError, TypeError):
            limit = self.DEFAULT_LIMIT

        # summary 参数（默认 True）
        summary = parameters.get("summary", True)
        if isinstance(summary, str):
            summary = summary.lower() not in ("false", "0", "no")

        # 判断是否指定了具体的读取范围
        has_specific_range = offset > 1 or limit < self.DEFAULT_LIMIT

        if not file_path:
            return ToolResult(success=False, output="", error="缺少 file_path 参数")

        try:
            path = Path(file_path)

            if not path.exists():
                return ToolResult(success=False, output="", error=f"文件不存在: {file_path}")

            if not path.is_file():
                return ToolResult(success=False, output="", error=f"不是文件: {file_path}")

            file_size = path.stat().st_size
            if file_size > self.MAX_FILE_SIZE:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"文件过大 ({file_size / 1024:.1f}KB)，超过 1MB 限制"
                )

            # 读取文件
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(path, 'r', encoding='gbk') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"文件编码不支持: {file_path}"
                    )

            lines = content.split('\n')
            total_lines = len(lines)

            # 存入缓存
            cache_result = file_cache.read_file(file_path, content)
            reference = cache_result["reference"]
            version = cache_result["version"]
            was_cached = cache_result["cached"]

            # 决定输出模式
            use_summary = (
                summary
                and not has_specific_range
                and total_lines >= self.SUMMARY_THRESHOLD
            )

            # 构建输出
            output_parts = []

            # 文件头信息
            size_kb = file_size / 1024
            cache_status = "(已缓存)" if was_cached else "(新缓存)"
            output_parts.append(f"📄 {path.name} ({total_lines}行, {size_kb:.1f}KB) {cache_status}")
            output_parts.append(f"📌 引用: {reference}")

            if use_summary:
                # 摘要模式
                structure = self._analyze_structure(lines, path.suffix.lower())
                if structure:
                    output_parts.append("\n结构概览:")
                    for item in structure[:15]:
                        output_parts.append(f"  {item}")
                    if len(structure) > 15:
                        output_parts.append("  ... (更多结构省略)")

                output_parts.append(f"\n预览 (前 {self.PREVIEW_LINES} 行):")
                for i, line in enumerate(lines[:self.PREVIEW_LINES], 1):
                    line_content = line.rstrip('\n\r')
                    if len(line_content) > 80:
                        line_content = line_content[:77] + "..."
                    output_parts.append(f"{i:6d}\t{line_content}")

                if total_lines > self.PREVIEW_LINES:
                    output_parts.append(f"\n       ... (省略 {total_lines - self.PREVIEW_LINES} 行)")

                output_parts.append(f"\n💡 使用 Read(offset=N, limit=M) 读取特定部分")
                output_parts.append(f"   使用 summary=false 获取完整内容")
            else:
                # 完整/分段模式
                start_line = max(1, offset)
                end_line = min(total_lines, start_line + limit - 1)

                output_parts.append(f"\n显示 {start_line}-{end_line} 行:")

                for i in range(start_line - 1, end_line):
                    line = lines[i]
                    if len(line) > 120:
                        line = line[:117] + "..."
                    output_parts.append(f"{i+1:6d}\t{line.rstrip(chr(10))}")

                if end_line < total_lines:
                    output_parts.append(f"\n... (还有 {total_lines - end_line} 行)")

            # 缓存提示
            if not was_cached:
                output_parts.append(f"\n📊 文件已缓存，后续操作使用引用节省 Token")

            output = '\n'.join(output_parts)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "file_path": str(path.absolute()),
                    "total_lines": total_lines,
                    "start_line": offset if not use_summary else 1,
                    "end_line": min(offset + limit - 1, total_lines) if not use_summary else total_lines,
                    "file_size": file_size,
                    "summary_mode": use_summary,
                    "cache_version": version,
                    "cache_reference": reference,
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足，无法读取: {file_path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"读取失败: {str(e)}")

    def _analyze_structure(self, lines: List[str], file_ext: str) -> List[str]:
        """
        分析文件结构

        Args:
            lines: 文件行列表
            file_ext: 文件扩展名

        Returns:
            结构描述列表
        """
        structure = []

        # Python 文件
        if file_ext == '.py':
            structure = self._analyze_python(lines)
        # JavaScript/TypeScript
        elif file_ext in ('.js', '.ts', '.jsx', '.tsx'):
            structure = self._analyze_javascript(lines)
        # 通用：识别缩进块
        else:
            structure = self._analyze_generic(lines)

        return structure

    def _analyze_python(self, lines: List[str]) -> List[str]:
        """分析 Python 文件结构"""
        structure = []
        current_class = None

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # 跳过空行和注释
            if not stripped or stripped.startswith('#'):
                continue

            # class 定义
            if stripped.startswith('class ') and ':' in stripped:
                match = re.match(r'class\s+(\w+)', stripped)
                if match:
                    class_name = match.group(1)
                    structure.append(f"L{i:4d}  class {class_name}")
                    current_class = class_name

            # def 定义（顶级方法或类方法）
            elif stripped.startswith('def ') and ':' in stripped:
                match = re.match(r'def\s+(\w+)', stripped)
                if match:
                    func_name = match.group(1)
                    # 判断缩进级别
                    indent = len(line) - len(line.lstrip())
                    if indent == 0:
                        structure.append(f"L{i:4d}  def {func_name}()")
                        current_class = None
                    elif current_class and indent == 4:
                        structure.append(f"L{i:4d}    def {func_name}()  # in {current_class}")

        # 限制输出数量
        if len(structure) > 20:
            structure = structure[:20]
            structure.append("  ... (更多结构省略)")

        return structure

    def _analyze_javascript(self, lines: List[str]) -> List[str]:
        """分析 JavaScript/TypeScript 文件结构"""
        structure = []

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            if not stripped or stripped.startswith('//'):
                continue

            # function 定义
            if re.match(r'(export\s+)?(async\s+)?function\s+\w+', stripped):
                match = re.search(r'function\s+(\w+)', stripped)
                if match:
                    structure.append(f"L{i:4d}  function {match.group(1)}()")

            # const/let function = () =>
            elif re.match(r'(export\s+)?(const|let)\s+\w+\s*=\s*(async\s*)?\([^)]*\)\s*=>', stripped):
                match = re.match(r'(export\s+)?(const|let)\s+(\w+)', stripped)
                if match:
                    structure.append(f"L{i:4d}  const {match.group(3)}()")

            # class 定义
            elif stripped.startswith('class ') and '{' in stripped:
                match = re.match(r'class\s+(\w+)', stripped)
                if match:
                    structure.append(f"L{i:4d}  class {match.group(1)}")

        if len(structure) > 20:
            structure = structure[:20]
            structure.append("  ... (更多结构省略)")

        return structure

    def _analyze_generic(self, lines: List[str]) -> List[str]:
        """通用结构分析（基于缩进）"""
        structure = []
        prev_indent = -1

        for i, line in enumerate(lines, start=1):
            if not line.strip():
                continue

            indent = len(line) - len(line.lstrip())

            # 检测缩进变化（新块开始）
            if indent > prev_indent and indent == 0:
                content = line.strip()[:60]
                if content:
                    structure.append(f"L{i:4d}  {content}")

            prev_indent = indent

        if len(structure) > 15:
            structure = structure[:15]
            structure.append("  ... (更多结构省略)")

        return structure

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"

        offset = parameters.get("offset", 1)
        if offset < 1:
            return "offset 必须 >= 1"

        limit = parameters.get("limit", self.DEFAULT_LIMIT)
        if limit < 1:
            return "limit 必须 >= 1"

        return None

    def is_read_only(self) -> bool:
        """只读操作"""
        return True