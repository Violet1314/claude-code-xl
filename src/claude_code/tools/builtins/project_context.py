"""ProjectContext 工具 - 代码库索引与上下文感知

参考 Cursor / Copilot 的设计，提供项目结构感知能力：
- 自动扫描项目目录结构（可排除常见忽略目录）
- 识别项目类型（Python/Node.js/Rust/Go 等）
- 提取关键文件信息（入口文件、配置文件、依赖声明）
- 提供符号级上下文（类/函数/导入的轻量索引）
"""
import os
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
        "- 索引 Python 文件的类/函数符号（轻量级）\n"
        "- 提供项目概览，帮助模型理解代码库\n"
        "\n"
        "参数：\n"
        "- depth: 扫描深度（默认 3，最大 5）\n"
        "- index_symbols: 是否索引符号（默认 True，仅限 Python 文件）\n"
        "- max_files: 最大文件数（默认 200）\n"
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
                    "description": "是否索引 Python 符号（类/函数），默认 True",
                    "default": True,
                },
                "max_files": {
                    "type": "integer",
                    "description": "最大扫描文件数（默认 200）",
                    "default": 200,
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
