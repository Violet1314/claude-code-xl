"""Read 工具 - 读取文件内容（集成缓存 + 文件不存在时自动搜索回退）"""
from pathlib import Path
from typing import Any, Dict, Optional, Callable

from ..base import Tool, ToolResult
from ..file_cache import file_cache
from claude_code.core.path_manager import get_path_manager
from claude_code.ui.theme import COLORS, ICONS
from rich.markup import escape

class ReadTool(Tool):
    """读取文件工具（带缓存）"""

    name = "Read"
    description = (
        "读取用户本机文件内容。文件会被完整缓存，后续操作使用缓存引用节省 Token。"
    )

    # 文件大小限制 (1MB)
    MAX_FILE_SIZE = 1 * 1024 * 1024
    # 默认读取行数限制
    DEFAULT_LIMIT = 1500
    # 终端显示阈值
    TERMINAL_DISPLAY_THRESHOLD = 80
    TERMINAL_HEAD_LINES = 30
    TERMINAL_TAIL_LINES = 20
    # 搜索回退结果上限
    MAX_SEARCH_RESULTS = 10

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
                "offset": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始），可选",
                    "default": 1
                },
                "limit": {
                    "type": "integer",
                    "description": "读取的最大行数，默认 1500 行。大文件建议分段读取。",
                    "default": 1500
                }
            },
            "required": ["file_path"],
            "errorMessage": {
                "file_path": "必须提供 file_path，如 file_path=\"E:\\项目目录\\src\\file.py\""
            }
        }

    def execute(
        self,
        parameters: Dict[str, Any],
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> ToolResult:
        """执行读取操作"""
        # 参数验证（与 Edit/Bash 工具一致）
        validation_error = self.validate_parameters(parameters)
        if validation_error:
            return ToolResult(success=False, output="", error=validation_error)

        file_path = parameters.get("file_path", "")
        offset = int(parameters.get("offset", 1))
        limit = int(parameters.get("limit", self.DEFAULT_LIMIT))

        # 使用 PathManager 统一路径解析
        pm = get_path_manager()
        file_path, boundary_ok = pm.resolve_safe(file_path)
        if not boundary_ok:
            return ToolResult(
                success=False, output="",
                error=f"路径越界: {file_path} 不在操作根目录 {pm.active_path} 下，禁止访问"
            )

        try:
            path = Path(file_path)
            if not path.exists():
                # 文件不存在时，自动回退到 Glob 搜索同名文件
                return self._handle_file_not_found(file_path, pm)
            if not path.is_file():
                return ToolResult(success=False, output="", error=f"不是文件: {file_path}\n下一步: 确认路径指向文件而非目录，或使用 Glob 搜索正确路径")

            file_size = path.stat().st_size
            if file_size > self.MAX_FILE_SIZE:
                return ToolResult(
                    success=False, output="",
                    error=f"文件过大 ({file_size / 1024:.1f}KB)，超过 1MB 限制\n下一步: 使用 offset+limit 分段读取，或使用 Grep 搜索关键内容"
                )

            # 统一由 executor 的 Spinner 显示进度，工具内部不再显示
            content = self._read_file(path)

            # 使用 splitlines() 计算实际行数，但保留原始内容用于精确匹配
            # splitlines() 不保留末尾空行，更符合"行数"概念
            lines_for_count = content.splitlines()
            total_lines = len(lines_for_count)

            # 但模型输出需要保留完整原始内容（包括末尾换行），确保 Edit 精确匹配
            # 使用 split('\n') 获取每行内容，但最后一行如果是空字符串则不显示
            raw_lines = content.split('\n')
            # 如果文件末尾有换行，最后一项是空字符串，不需要作为单独一行显示
            if raw_lines and raw_lines[-1] == '':
                raw_lines = raw_lines[:-1]
            lines = raw_lines
            cache_result = file_cache.read_file(file_path, content)
            reference = cache_result["reference"]
            version = cache_result["version"]
            was_cached = cache_result["cached"]
            size_kb = file_size / 1024

            # v2.8.37+ 优化：检测重复读取，返回缓存摘要而非完整内容
            abs_path = str(path.absolute())
            is_recent = file_cache.is_recent_read(abs_path)
            if is_recent and was_cached and not (parameters.get("offset") or parameters.get("limit")):
                cached_summary = file_cache.get_file_summary(abs_path)
                summary_text = cached_summary or f"{path.name} ({total_lines} lines)"
                compact_output = (
                    f"[文件已缓存] {path.name} — 内容未变化，上次已返回完整内容。\n"
                    f"摘要: {summary_text}\n"
                    f"提示: 如需重新查看完整内容，请指定行号范围（如 offset=1, limit=100）"
                )
                file_cache.mark_recent_read(abs_path)
                return ToolResult(
                    success=True,
                    output=compact_output,
                    display_output=f"[dim]◇ 重复读取: {escape(str(path))} → 返回缓存摘要[/]",
                    summary=f"Read {path.name} (cached, recent)",
                    metadata={
                        "file_path": abs_path,
                        "total_lines": total_lines,
                        "cached": True,
                        "recent_read": True,
                    }
                )

            # 构建输出
            output = self._build_model_output(
                path, lines, total_lines, size_kb, reference, offset, limit, was_cached
            )
            # 判断是否为精确行段读取（用户指定了 offset/limit）
            has_explicit_range = (offset > 1) or (limit < total_lines)
            display_output = self._build_terminal_display(
                path, lines, total_lines, size_kb, reference, version, was_cached,
                has_explicit_range=has_explicit_range
            )

            # 记录读取操作
            start_line = offset
            end_line = min(offset + limit - 1, total_lines)
            abs_path_full = str(path.absolute())
            file_cache.record_read(abs_path_full, total_lines, start_line, end_line)
            # 标记为最近读取，用于后续重复 Read 检测
            file_cache.mark_recent_read(abs_path_full)

            return ToolResult(
                success=True,
                output=output,
                display_output=display_output,
                summary=f"Read {path.name} ({total_lines} lines)",
                metadata={
                    "file_path": str(path.absolute()),
                    "total_lines": total_lines,
                    "start_line": start_line,
                    "end_line": end_line,
                    "file_size": file_size,
                    "cache_version": version,
                    "cache_reference": reference,
                }
            )

        except PermissionError:
            return ToolResult(success=False, output="", error=f"权限不足，无法读取: {file_path}\n下一步: 检查文件权限，或使用 Bash 执行 Get-Acl 查看")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"读取失败: {str(e)}\n下一步: 检查文件路径和编码，或使用 Bash cat/type 命令读取")

    # ============================================================
    # 模型输出（纯文本，无 Rich markup）
    # ============================================================

    def _build_model_output(
        self, path, lines, total_lines, size_kb, reference, offset, limit, was_cached=False
    ) -> str:
        """构建给模型的纯文本输出"""
        parts = []

        # 文件元信息
        parts.append(f"File: {path.name} ({total_lines} lines, {size_kb:.1f}KB)")
        parts.append(f"Path: {path.absolute()}")

        # 结构概览：提取关键符号位置，帮助 API 一次定位精准读取
        if offset <= 1:  # 仅首次全量读取时展示结构概览，精确行段不重复
            symbol_header = self._build_symbol_header(lines, str(path))
            if symbol_header:
                parts.append(symbol_header)

        if was_cached:
            parts.append(f"Cache: [{reference}]")

        # 内容区
        start_line = max(1, offset)
        end_line = min(total_lines, start_line + limit)

        parts.append(f"Content (lines {start_line}-{end_line}):")
        for i in range(start_line - 1, end_line):
            # 不使用 rstrip()，保留原始内容（包括行尾空格），确保 Edit 精确匹配
            parts.append(f"{i+1:5d} | {lines[i]}")

        if end_line < total_lines:
            parts.append(f"  ... ({total_lines - end_line} more lines)")

        return '\n'.join(parts)

    # ============================================================
    # 结构概览提取
    # ============================================================

    def _build_symbol_header(self, lines: list, file_path: str) -> str:
        """
        从文件内容提取关键符号位置，生成结构概览头部

        让 API 一次就能知道文件有哪些类/函数、在哪一行，
        避免盲目分段读取浪费 2-3 轮工具调用。

        Returns:
            结构概览字符串，无法提取时返回空字符串
        """
        symbols = self._extract_symbol_positions(lines, file_path)
        if not symbols:
            return ""

        # 限制符号数量，避免 token 膨胀（最多 15 个，优先顶层）
        MAX_SYMBOLS = 15
        if len(symbols) > MAX_SYMBOLS:
            symbols = symbols[:MAX_SYMBOLS]

        # 格式：class App L42 | def chat L520 | def run L1577
        symbol_parts = []
        for kind, name, line_no in symbols:
            symbol_parts.append(f"{kind} {name} L{line_no}")

        return "[结构] " + " | ".join(symbol_parts)

    def _extract_symbol_positions(self, lines: list, file_path: str) -> list:
        """
        提取文件中的关键符号位置（类/函数定义 + 行号）

        Args:
            lines: 文件行列表
            file_path: 文件路径（用于判断文件类型）

        Returns:
            [(kind, name, line_no), ...] 列表，如 [("class", "App", 42)]
        """
        import re

        ext = Path(file_path).suffix.lower()
        symbols = []

        if ext == ".py":
            symbols = self._extract_python_symbols(lines)
        elif ext in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
            symbols = self._extract_js_symbols(lines)
        elif ext in (".go",):
            symbols = self._extract_go_symbols(lines)
        elif ext in (".rs",):
            symbols = self._extract_rust_symbols(lines)
        elif ext in (".java", ".kt"):
            symbols = self._extract_java_symbols(lines)

        return symbols

    def _extract_python_symbols(self, lines: list) -> list:
        """Python: 使用 AST 提取顶层 class/function 定义"""
        try:
            import ast
            source = "\n".join(lines)
            tree = ast.parse(source)
            symbols = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    symbols.append(("class", node.name, node.lineno))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(("def", node.name, node.lineno))
            return symbols
        except Exception:
            # AST 解析失败，回退到正则
            return self._extract_by_regex(lines, [
                r'^(\s*)(class\s+\w+)',
                r'^(\s*)(def\s+\w+)',
                r'^(\s*)(async\s+def\s+\w+)',
            ])

    def _extract_js_symbols(self, lines: list) -> list:
        """JS/TS: 正则提取顶层 function/class/export 定义"""
        return self._extract_by_regex(lines, [
            r'^(export\s+)?(default\s+)?(class\s+\w+)',
            r'^(export\s+)?(default\s+)?(function\s+\w+)',
            r'^(export\s+)?(default\s+)?(async\s+function\s+\w+)',
            r'^(export\s+)?(const\s+\w+\s*=\s*(?:async\s+)?\()',  # const foo = () =>
        ])

    def _extract_go_symbols(self, lines: list) -> list:
        """Go: 正则提取 func/type/struct 定义"""
        return self._extract_by_regex(lines, [
            r'^func\s+(\w+)',
            r'^type\s+(\w+)\s+struct',
            r'^type\s+(\w+)\s+interface',
        ])

    def _extract_rust_symbols(self, lines: list) -> list:
        """Rust: 正则提取 fn/struct/impl/trait 定义"""
        return self._extract_by_regex(lines, [
            r'^(pub\s+)?(async\s+)?fn\s+(\w+)',
            r'^(pub\s+)?struct\s+(\w+)',
            r'^impl\s+(\w+)',
            r'^(pub\s+)?trait\s+(\w+)',
        ])

    def _extract_java_symbols(self, lines: list) -> list:
        """Java/Kotlin: 正则提取 class/interface/object 定义"""
        return self._extract_by_regex(lines, [
            r'^(public\s+)?(abstract\s+)?(class\s+\w+)',
            r'^(public\s+)?(interface\s+\w+)',
            r'^(public\s+)?(enum\s+\w+)',
            r'^(public\s+)?(static\s+)?\w+\s+\w+\s*\(',  # method
        ])

    def _extract_by_regex(self, lines: list, patterns: list) -> list:
        """
        通用正则提取：遍历行，匹配模式，提取符号名和行号

        仅提取顶层符号（缩进 <= 4 空格），避免嵌套符号膨胀 token
        """
        import re
        symbols = []
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if indent > 4:  # 跳过深层嵌套
                continue
            for pattern in patterns:
                m = re.match(pattern, line)
                if m:
                    # 提取最后一个匹配组作为符号名（去掉关键字）
                    name = m.group(m.lastindex or 0).strip().split()[-1].rstrip('(')
                    # 推断类型
                    raw = m.group(0)
                    if 'class' in raw:
                        kind = 'class'
                    elif 'struct' in raw:
                        kind = 'struct'
                    elif 'interface' in raw or 'trait' in raw:
                        kind = 'interface'
                    elif 'impl' in raw:
                        kind = 'impl'
                    else:
                        kind = 'def'
                    symbols.append((kind, name, i + 1))
                    break  # 一行只匹配一个模式
        return symbols

    # ============================================================
    # 终端显示（省略模式）
    # ============================================================

    def _build_terminal_display(
        self, path, lines, total_lines, size_kb, reference, version, was_cached,
        has_explicit_range=False
    ) -> str:
        """构建给终端的摘要行（文件内容通过 output 传给模型，终端只显示摘要）
        
        Args:
            has_explicit_range: 用户指定了 offset/limit，精确行段模式，终端显示完整行段不省略
        """
        # 格式化大小
        if size_kb < 1024:
            size_str = f"{size_kb:.1f}KB"
        else:
            size_str = f"{size_kb / 1024:.1f}MB"

        base = f"  {ICONS.get('read', '◇')} Read [cyan]{escape(path.name)}[/]  [dim]{total_lines} lines · {size_str}[/]"
        
        # 精确行段模式：显示行段范围，提示不省略
        if has_explicit_range:
            return f"{base} [dim](精确行段，不省略)[/]"
        
        return base

    # ============================================================
    # 文件读取
    # ============================================================

    def _read_file(self, path: Path) -> str:
        """读取文件内容"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(path, 'r', encoding='gbk') as f:
                return f.read()

    # ============================================================
    # 文件不存在时的自动搜索回退
    # ============================================================

    def _handle_file_not_found(self, file_path: str, pm) -> ToolResult:
        """文件不存在时的处理：自动搜索同名文件并给出精确路径建议"""
        from claude_code.utils.paths import format_file_not_found_error
        error_msg = format_file_not_found_error(file_path, pm.active_path, self.MAX_SEARCH_RESULTS)
        return ToolResult(success=False, output="", error=error_msg)

    # ============================================================
    # 工具属性
    # ============================================================

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        file_path = parameters.get("file_path")
        if not file_path:
            return "缺少 file_path 参数"

        # offset 验证（类型 + 范围）
        try:
            offset = int(parameters.get("offset", 1))
        except (ValueError, TypeError):
            return "offset 必须是整数"
        if offset < 1:
            return "offset 必须 >= 1"

        # limit 验证（类型 + 范围）
        try:
            limit = int(parameters.get("limit", self.DEFAULT_LIMIT))
        except (ValueError, TypeError):
            return "limit 必须是整数"
        if limit < 1:
            return "limit 必须 >= 1"

        return None

    def is_read_only(self) -> bool:
        """只读操作"""
        return True
