"""ProjectContext 工具 - 代码库索引与上下文感知

参考 Cursor / Copilot 的设计，提供项目结构感知能力：
- 自动扫描项目目录结构（可排除常见忽略目录）
- 识别项目类型（Python/Node.js/Rust/Go 等）
- 提取关键文件信息（入口文件、配置文件、依赖声明）
- 提供符号级上下文（Python/JS/TS 类/函数的轻量索引）
- 支持 query 相关性检索，按任务定位代码
"""
import os
import re
import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field

from ..base import Tool, ToolResult
from claude_code.core.path_manager import get_path_manager
from claude_code.utils.paths import EXCLUDED_DIRS
from claude_code.ui.theme import COLORS, ICONS
from rich.markup import escape


# ============================================================
# 项目类型识别
# ============================================================

PROJECT_TYPE_INDICATORS = {
    "python": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"],
    "node": ["package.json", "yarn.lock", "pnpm-lock.yaml"],
    "rust": ["Cargo.toml"],
    "go": ["go.mod"],
    "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "ruby": ["Gemfile"],
    "php": ["composer.json"],
    "dotnet": ["*.csproj", "*.fsproj", "*.vbproj"],
    "c_cpp": ["CMakeLists.txt", "Makefile", "configure"],
    "swift": ["Package.swift"],
}


@dataclass
class SymbolInfo:
    """符号信息（类/函数）"""
    name: str
    type: str  # "class" or "function"
    line: int
    file: str


@dataclass
class ProjectIndex:
    """项目索引"""
    project_type: str = "unknown"
    root_files: List[str] = field(default_factory=list)
    directories: List[str] = field(default_factory=list)
    key_files: Dict[str, str] = field(default_factory=dict)  # type -> path
    symbols: List[SymbolInfo] = field(default_factory=list)
    total_files: int = 0
    total_dirs: int = 0
    max_depth: int = 0


class ProjectContextTool(Tool):
    """代码库索引与上下文感知工具"""
    name = "ProjectContext"
    description = (
        "扫描并索引当前项目结构，提供上下文感知能力。\n"
        "功能：\n"
        "- 识别项目类型（Python/Node.js/Rust/Go 等）\n"
        "- 提取目录结构和关键文件\n"
        "- 索引 Python/JS/TS 文件的类/函数符号（轻量级）\n"
        "- 提供 query 相关性检索，按任务定位相关代码\n"
        "- 提供项目概览，帮助模型理解代码库\n"
        "\n"
        "参数：\n"
        "- depth: 扫描深度（默认 3，最大 5）\n"
        "- index_symbols: 是否索引符号（默认 True，支持 Python/JS/TS 文件）\n"
        "- max_files: 最大文件数（默认 200）\n"
        "- query: 可选，按关键词搜索相关文件和符号（如 \"计划模式\" \"auth login\"）\n"
    )

    MAX_DEPTH = 5
    MAX_FILES = 200

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "depth": {
                    "type": "integer",
                    "description": "扫描深度（1-5，默认 3）",
                    "default": 3,
                },
                "index_symbols": {
                    "type": "boolean",
                    "description": "是否索引符号（类/函数），默认 True（支持 Python/JS/TS）",
                    "default": True,
                },
                "max_files": {
                    "type": "integer",
                    "description": "最大扫描文件数（默认 200）",
                    "default": 200,
                },
                "query": {
                    "type": "string",
                    "description": "按关键词搜索相关文件和符号（如 \"计划模式\" \"auth login\"），不指定则返回完整项目概览",
                    "default": "",
                },
            },
        }

    def execute(
        self,
        parameters: Dict[str, Any],
        interrupt_check: Callable[[], bool] = None,
    ) -> ToolResult:
        depth = min(parameters.get("depth", 3), self.MAX_DEPTH)
        index_symbols = parameters.get("index_symbols", True)
        max_files = parameters.get("max_files", self.MAX_FILES)
        query = parameters.get("query", "").strip()

        pm = get_path_manager()
        if pm is None:
            return ToolResult(
                success=False,
                error="路径管理器未初始化",
                display_output=f"[{COLORS['error']}]✗ 路径管理器未初始化[/]",
            )

        base_path = Path(pm.active_path)
        if not base_path.is_dir():
            return ToolResult(
                success=False,
                error=f"路径不存在: {base_path}",
                display_output=f"[{COLORS['error']}]✗ 路径不存在: {escape(str(base_path))}[/]",
            )

        # 构建索引
        index = self._build_index(base_path, depth, max_files, index_symbols, interrupt_check)

        # 如果有 query，返回相关性检索结果
        if query:
            query_lines = self._search_by_query(index, query)
            query_display = self._search_by_query_display(index, query)
            return ToolResult(
                success=True,
                output="\n".join(query_lines),
                summary=f"查询 \"{query}\": 找到 {len([l for l in query_lines if l.startswith('### ')])} 个相关文件",
                display_output="\n".join(query_display),
                raw_data=index,
            )

        # 构建输出
        output_lines = self._format_output(index)
        display_lines = self._format_display(index)

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            summary=f"项目索引: {index.project_type}, {index.total_files} 文件, {len(index.symbols)} 符号",
            display_output="\n".join(display_lines),
            raw_data=index,
        )

    def _build_index(
        self,
        base: Path,
        depth: int,
        max_files: int,
        index_symbols: bool,
        interrupt_check: Callable[[], bool] = None,
    ) -> ProjectIndex:
        index = ProjectIndex()
        file_count = 0

        for root, dirs, files in os.walk(base):
            # 深度控制
            rel = Path(root).relative_to(base)
            current_depth = len(rel.parts)
            if current_depth >= depth:
                dirs.clear()
                continue

            # 排除目录
            dirs[:] = [
                d for d in dirs
                if d not in EXCLUDED_DIRS and not d.startswith('.')
            ]

            index.directories.append(str(rel) if str(rel) != '.' else '.')
            index.total_dirs += 1
            index.max_depth = max(index.max_depth, current_depth)

            for f in files:
                if file_count >= max_files:
                    break
                if interrupt_check and interrupt_check():
                    break

                file_count += 1
                index.total_files += 1
                index.root_files.append(str(rel / f) if str(rel) != '.' else f)

                # 项目类型识别
                if f in ("requirements.txt", "setup.py", "pyproject.toml", "Pipfile"):
                    index.project_type = "python"
                    index.key_files["python"] = str(rel / f)
                elif f == "package.json":
                    index.project_type = "node"
                    index.key_files["node"] = str(rel / f)
                elif f == "Cargo.toml":
                    index.project_type = "rust"
                    index.key_files["rust"] = str(rel / f)
                elif f == "go.mod":
                    index.project_type = "go"
                    index.key_files["go"] = str(rel / f)
                elif f in ("pom.xml", "build.gradle", "build.gradle.kts"):
                    index.project_type = "java"
                    index.key_files["java"] = str(rel / f)
                elif f == "Gemfile":
                    index.project_type = "ruby"
                    index.key_files["ruby"] = str(rel / f)
                elif f == "composer.json":
                    index.project_type = "php"
                    index.key_files["php"] = str(rel / f)
                elif f == "CMakeLists.txt":
                    index.project_type = "c_cpp"
                    index.key_files["c_cpp"] = str(rel / f)
                elif f == "Makefile":
                    if not index.key_files.get("c_cpp"):
                        index.project_type = "c_cpp"
                        index.key_files["c_cpp"] = str(rel / f)

                # Python 符号索引
                if index_symbols and f.endswith(".py"):
                    filepath = base / rel / f
                    try:
                        symbols = self._extract_python_symbols(filepath, str(rel / f))
                        index.symbols.extend(symbols)
                    except Exception:
                        pass

                # JS/TS 符号索引
                if index_symbols and f.endswith((".js", ".jsx", ".ts", ".tsx")):
                    filepath = base / rel / f
                    try:
                        symbols = self._extract_js_ts_symbols(filepath, str(rel / f))
                        index.symbols.extend(symbols)
                    except Exception:
                        pass

            if file_count >= max_files:
                break

        if not index.project_type and index.total_files > 0:
            index.project_type = "generic"

        return index

    def _extract_python_symbols(self, filepath: Path, rel_path: str) -> List[SymbolInfo]:
        """提取 Python 文件中的类和函数"""
        symbols = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source, filename=str(filepath))

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    symbols.append(SymbolInfo(
                        name=node.name,
                        type="class",
                        line=node.lineno,
                        file=rel_path,
                    ))
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    symbols.append(SymbolInfo(
                        name=node.name,
                        type="function",
                        line=node.lineno,
                        file=rel_path,
                    ))
        except (SyntaxError, UnicodeDecodeError):
            pass
        return symbols

    # JS/TS 符号正则（轻量级，不需要完整 AST）
    _JS_TS_PATTERNS = [
        # class 声明
        re.compile(r'^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)', re.MULTILINE),
        # function 声明
        re.compile(r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)', re.MULTILINE),
        # const/let/var 箭头函数
        re.compile(r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[\w]+)\s*=>', re.MULTILINE),
        # interface 声明（TypeScript）
        re.compile(r'^\s*(?:export\s+)?interface\s+(\w+)', re.MULTILINE),
        # type 声明（TypeScript）
        re.compile(r'^\s*(?:export\s+)?type\s+(\w+)\s*=', re.MULTILINE),
    ]

    def _extract_js_ts_symbols(self, filepath: Path, rel_path: str) -> List[SymbolInfo]:
        """提取 JavaScript/TypeScript 文件中的类、函数、接口"""
        symbols = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()
            for pattern in self._JS_TS_PATTERNS:
                for match in pattern.finditer(source):
                    name = match.group(1)
                    # 计算行号
                    line_no = source[:match.start()].count('\n') + 1
                    # 区分类型：interface/type 归为 class 类别
                    sym_type = "class" if "class " in match.group(0) or "interface " in match.group(0) or "type " in match.group(0) else "function"
                    symbols.append(SymbolInfo(
                        name=name,
                        type=sym_type,
                        line=line_no,
                        file=rel_path,
                    ))
        except (UnicodeDecodeError, OSError):
            pass
        return symbols

    def _search_by_query(self, index: ProjectIndex, query: str) -> List[str]:
        """根据 query 关键词搜索相关文件和符号

        匹配策略：
        1. 文件名包含关键词 → 高相关性
        2. 符号名包含关键词 → 高相关性
        3. 文件路径包含关键词 → 中相关性
        """
        query_lower = query.lower()
        query_words = set(re.split(r'[\s_\-]+', query_lower)) - {'', 'the', 'a', 'an', 'of', 'in', 'for', 'to'}

        # 文件相关性评分
        file_scores: Dict[str, int] = {}

        for rel_path in index.root_files:
            score = 0
            filename = Path(rel_path).stem.lower()
            filepath_lower = rel_path.lower().replace(os.sep, '/')

            # 文件名完全匹配关键词
            for word in query_words:
                if word in filename:
                    score += 10
                elif word in filepath_lower:
                    score += 3

            # 符号名匹配
            for sym in index.symbols:
                if sym.file == rel_path:
                    sym_lower = sym.name.lower()
                    for word in query_words:
                        if word in sym_lower:
                            score += 5

            if score > 0:
                file_scores[rel_path] = score

        # 按分数排序，取前 10
        ranked = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)[:10]

        # 构建结果
        lines = [f"## 相关文件（query: \"{query}\"）", ""]
        if not ranked:
            lines.append("未找到与查询高度相关的文件，请尝试不同的关键词。")
            return lines

        for rel_path, score in ranked:
            lines.append(f"### {rel_path}")
            # 列出该文件中匹配的符号
            matched = [
                s for s in index.symbols
                if s.file == rel_path and any(w in s.name.lower() for w in query_words)
            ]
            if matched:
                for sym in matched[:8]:  # 每文件最多 8 个符号
                    icon = "🔷" if sym.type == "class" else "🔹"
                    lines.append(f"- {icon} {sym.name} (行 {sym.line})")
                if len(matched) > 8:
                    lines.append(f"  ... 还有 {len(matched) - 8} 个匹配符号")
            lines.append("")

        return lines

    def _search_by_query_display(self, index: ProjectIndex, query: str) -> List[str]:
        """query 检索的终端显示版本（Rich Markup）"""
        query_words = [w.lower() for w in query.split() if len(w) >= 2]
        if not query_words:
            return [f"[dim]查询词过短，请输入至少 2 个字符[/]"]

        file_scores: Dict[str, int] = {}
        for rel_path in index.root_files:
            score = 0
            filepath_lower = rel_path.lower()
            for word in query_words:
                if word in filepath_lower:
                    score += 10
            for sym in index.symbols:
                if sym.file == rel_path:
                    for word in query_words:
                        if word in sym.name.lower():
                            score += 5
            if score > 0:
                file_scores[rel_path] = score

        ranked = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)[:10]

        lines = [f"[bold]◆ 相关文件（query: \"{escape(query)}\"）[/]", ""]
        if not ranked:
            lines.append("[dim]未找到与查询高度相关的文件[/]")
            return lines

        for rel_path, score in ranked:
            lines.append(f"  [cyan]{escape(rel_path)}[/]")
            matched = [
                s for s in index.symbols
                if s.file == rel_path and any(w in s.name.lower() for w in query_words)
            ]
            if matched:
                for sym in matched[:6]:
                    icon = "🔷" if sym.type == "class" else "🔹"
                    lines.append(f"    [dim]{icon} {escape(sym.name)} (行 {sym.line})[/]")
                if len(matched) > 6:
                    lines.append(f"    [dim]... 还有 {len(matched) - 6} 个匹配符号[/]")

        return lines

    def _format_output(self, index: ProjectIndex) -> List[str]:
        lines = []
        lines.append(f"## 项目概览")
        lines.append(f"项目类型: {index.project_type}")
        lines.append(f"文件总数: {index.total_files}")
        lines.append(f"目录总数: {index.total_dirs}")
        lines.append(f"最大深度: {index.max_depth}")
        lines.append("")

        if index.key_files:
            lines.append("## 关键文件")
            for ptype, path in index.key_files.items():
                lines.append(f"- {ptype}: {path}")
            lines.append("")

        lines.append("## 目录结构")
        for d in sorted(index.directories):
            indent = "  " * (d.count(os.sep))
            lines.append(f"{indent}{d}/")
        lines.append("")

        if index.symbols:
            lines.append("## 符号索引")
            # 按文件分组
            by_file: Dict[str, List[SymbolInfo]] = {}
            for s in index.symbols:
                by_file.setdefault(s.file, []).append(s)

            for fpath, syms in sorted(by_file.items()):
                lines.append(f"### {fpath}")
                for s in sorted(syms, key=lambda x: x.line):
                    icon = "🔷" if s.type == "class" else "🔹"
                    lines.append(f"- {icon} {s.type} {s.name} (行 {s.line})")
            lines.append("")

        return lines

    def _format_display(self, index: ProjectIndex) -> List[str]:
        lines = []
        type_icon = ICONS.get("folder", "▸")
        lines.append(f"[bold]{type_icon} 项目索引[/]  [dim]类型: {index.project_type}[/]")
        lines.append(f"[dim]  文件: {index.total_files}  目录: {index.total_dirs}  符号: {len(index.symbols)}[/]")

        if index.key_files:
            lines.append(f"[dim]  关键文件:[/]")
            for ptype, path in index.key_files.items():
                lines.append(f"[dim]    {ptype}: {escape(path)}[/]")

        # 目录结构（最多显示 15 个）
        if index.directories:
            lines.append(f"[dim]  目录结构（前 15 个）:[/]")
            for d in sorted(index.directories)[:15]:
                indent = "  " * (d.count(os.sep) + 1)
                lines.append(f"{indent}[dim]{escape(d)}/[/]")

            if len(index.directories) > 15:
                lines.append(f"[dim]    ... 还有 {len(index.directories) - 15} 个目录[/]")

        # 符号统计
        if index.symbols:
            class_count = sum(1 for s in index.symbols if s.type == "class")
            func_count = sum(1 for s in index.symbols if s.type == "function")
            lines.append(f"[dim]  符号: {class_count} 类, {func_count} 函数[/]")

        return lines

    def is_read_only(self) -> bool:
        return True

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        depth = parameters.get("depth", 3)
        if not isinstance(depth, int) or depth < 1 or depth > self.MAX_DEPTH:
            return f"depth 必须是 1-{self.MAX_DEPTH} 之间的整数"
        return None

    def get_security_context(self) -> Dict[str, Any]:
        return {"is_sensitive": False, "paths": [], "command_preview": ""}
