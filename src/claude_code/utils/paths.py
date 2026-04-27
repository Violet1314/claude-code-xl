"""路径工具 - 文件路径解析与验证"""
import os
import glob as glob_module
from pathlib import Path
from typing import List, Set

from claude_code.config.defaults import WORKPLACE_DIR

# 支持的代码文件扩展名
SUPPORTED_EXTENSIONS: Set[str] = {
    # 编程语言
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', 
    '.c', '.cpp', '.h', '.cs', '.php', '.rb', '.swift', '.kt', '.scala',
    # Shell
    '.sh', '.bash', '.zsh', '.ps1',
    # 配置
    '.json', '.yaml', '.yml', '.toml', '.xml', '.ini', '.env', '.conf',
    # 文档
    '.md', '.txt', '.rst',
    # Web
    '.html', '.css', '.scss', '.less', '.vue', '.svelte',
    # 数据
    '.sql', '.graphql',
}

# 自动排除的目录（通用工程无关目录）
EXCLUDED_DIRS: Set[str] = {
    # Python
    '.venv', 'venv', 'env', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', '.tox', '.nox',
    # Node.js
    'node_modules', '.next', '.nuxt', 'bower_components',
    # 版本控制
    '.git', '.svn', '.hg',
    # 构建产物
    'dist', 'build', '.build', 'out', 'target',
    # IDE
    '.idea', '.vscode',
    # 其他语言
    'vendor',  # Go/PHP
    '.gradle', '.cargo',
}

def resolve_path(path: str) -> str:
    """
    解析路径：相对路径转绝对路径，规范化

    注意：此函数不做安全边界校验（不检查是否越界操作根目录）。
    工具执行场景应使用 PathManager.resolve()，它会进行越界保护。
    此函数仅适用于用户主动操作（如文件挂载）等不需要安全边界的场景。

    Args:
        path: 输入路径（可能带引号）

    Returns:
        规范化的绝对路径
    """
    if not path:
        return ""

    # 去除首尾空格和引号
    cleaned = path.strip().strip('"').strip("'")

    # 转为绝对路径并规范化
    absolute = os.path.abspath(cleaned)
    return os.path.normpath(absolute)


def resolve_workplace_path(path: str) -> str:
    """
    解析 Workplace 隔离路径

    规则：
    - 绝对路径：保持原样（用户明确指定）
    - 相对路径：重定向到 workplace 目录（隔离保护）
    - 已包含 workplace 前缀的路径：不再重复添加

    Args:
        path: 输入路径

    Returns:
        处理后的路径
    """
    if not path:
        return ""

    # 去除首尾空格和引号
    cleaned = path.strip().strip('"').strip("'")

    # 判断是否为绝对路径
    if os.path.isabs(cleaned):
        # 绝对路径保持原样（用户明确指定）
        return os.path.normpath(cleaned)

    # 检查是否已经以 workplace 开头（避免重复添加）
    normalized = os.path.normpath(cleaned)
    parts = normalized.split(os.sep)
    if parts and parts[0] == "workplace":
        # 已经包含 workplace 前缀，直接返回
        return normalized

    # 相对路径重定向到 workplace
    workplace_path = os.path.join(WORKPLACE_DIR, cleaned)
    return os.path.normpath(workplace_path)

def is_hidden(path: str) -> bool:
    """
    检查是否为隐藏文件/目录
    
    Args:
        path: 文件路径
        
    Returns:
        是否隐藏
    """
    if not path:
        return False
    return os.path.basename(path).startswith('.')

def is_supported_extension(path: str) -> bool:
    """
    检查文件扩展名是否支持
    
    Args:
        path: 文件路径
        
    Returns:
        是否支持
    """
    if not path:
        return False
    ext = os.path.splitext(path)[1].lower()
    return ext in SUPPORTED_EXTENSIONS

def get_extension(path: str) -> str:
    """
    获取文件扩展名（不含点号）
    
    Args:
        path: 文件路径
        
    Returns:
        扩展名，如 'py', 'js'
    """
    if not path:
        return ""
    ext = os.path.splitext(path)[1].lower()
    return ext.lstrip('.')

def expand_glob(pattern: str) -> List[str]:
    """
    展开通配符模式
    
    Args:
        pattern: 通配符模式，如 '*.py', 'src/**/*.js'
        
    Returns:
        匹配的文件路径列表
    """
    if not pattern:
        return []
    
    resolved = resolve_path(pattern)
    
    # 检查是否包含通配符
    if '*' in resolved or '?' in resolved:
        matches = glob_module.glob(resolved, recursive=True)
        # 只返回文件，排除目录
        return [p for p in matches if os.path.isfile(p)]
    
    return [resolved] if os.path.isfile(resolved) else []

def get_relative_display(path: str, base: str = None) -> str:
    """
    获取用于显示的相对路径
    
    Args:
        path: 绝对路径
        base: 基准目录，默认为当前目录
        
    Returns:
        相对路径字符串
    """
    if not path:
        return ""
    
    base = base or os.getcwd()
    
    try:
        return os.path.relpath(path, base)
    except ValueError:
        # Windows 跨盘符时无法计算相对路径
        return path
    
def get_file_icon(file_ext: str) -> str:
    """根据文件扩展名获取图标"""
    from claude_code.ui.theme import ICONS

    icons = {
        '.py': ICONS.get('file_py', '▹'),
        '.js': ICONS.get('file_js', '▹'),
        '.ts': ICONS.get('file_ts', '▹'),
        '.jsx': ICONS.get('file_js', '▹'),
        '.tsx': ICONS.get('file_ts', '▹'),
        '.json': ICONS.get('file_json', '▹'),
        '.md': ICONS.get('file_md', '▹'),
        '.txt': ICONS.get('file_txt', '▹'),
        '.yaml': ICONS.get('file_yaml', '▹'),
        '.yml': ICONS.get('file_yaml', '▹'),
        '.html': ICONS.get('file_html', '▹'),
        '.css': ICONS.get('file_css', '▹'),
        '.scss': ICONS.get('file_css', '▹'),
    }
    return icons.get(file_ext, ICONS.get('file_default', '▹'))


def format_size(size: int) -> str:
    """
    格式化文件大小为人类可读字符串

    Args:
        size: 文件大小（字节数）

    Returns:
        格式化后的字符串，如 "1.5KB", "2.3MB"
    """
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / (1024 * 1024):.1f}MB"


def search_file_in_project(file_path: str, base_path: str, max_results: int = 10) -> List[str]:
    """
    在项目目录下递归搜索同名文件

    当工具收到不存在的文件路径时，提取文件名在操作根目录下搜索，
    返回候选路径列表，帮助模型快速定位正确路径。

    Args:
        file_path: 原始请求路径（从中提取文件名）
        base_path: 搜索根目录（通常是操作根目录）
        max_results: 最大返回结果数

    Returns:
        匹配的绝对路径列表（按路径深度排序，浅层优先）
    """
    target_name = Path(file_path).name
    if not target_name or target_name in ('.', '..'):
        return []

    base = Path(base_path)
    if not base.is_dir():
        return []

    matches = []
    try:
        for match in base.rglob(target_name):
            # 排除无关目录
            if _should_exclude_path(match, base):
                continue
            # 只匹配文件，不匹配目录
            if match.is_file():
                matches.append(str(match))
                if len(matches) >= max_results:
                    break
    except (PermissionError, OSError):
        pass

    # 按路径深度排序（浅层优先）
    matches.sort(key=lambda p: len(Path(p).relative_to(base).parts))
    return matches


def format_file_not_found_error(file_path: str, base_path: str, max_results: int = 10) -> str:
    """
    文件不存在时的统一错误格式化：自动搜索同名文件并给出精确路径建议

    供 Read/Edit 等工具共用，避免重复代码。

    策略：
    1. 提取文件名（如 app.py）
    2. 在 base_path 下递归搜索同名文件（排除无关目录）
    3. 唯一匹配时直接给出精确路径，多匹配时列出候选
    4. 返回格式化的错误信息字符串，调用方包装为 ToolResult 即可

    Args:
        file_path: 原始请求路径
        base_path: 搜索根目录（通常是操作根目录）
        max_results: 最大搜索结果数

    Returns:
        格式化的错误信息字符串
    """
    matches = search_file_in_project(file_path, base_path, max_results)

    if not matches:
        return f"文件不存在: {file_path}\n在项目中也未找到同名文件，请确认路径是否正确。"

    # 唯一匹配：直接给出精确路径
    if len(matches) == 1:
        exact_path = matches[0]
        return (
            f"文件不存在: {file_path}\n"
            f"ℹ 找到唯一匹配，请使用精确路径重试:\n"
            f"  file_path=\"{exact_path}\""
        )

    # 多个匹配：列出候选路径
    lines = [f"文件不存在: {file_path}"]
    lines.append(f"ℹ 在项目中找到 {len(matches)} 个同名文件:")
    for i, match in enumerate(matches[:max_results], 1):
        lines.append(f"  {i}. {match}")
    if len(matches) > max_results:
        lines.append(f"  ... 还有 {len(matches) - max_results} 个")
    lines.append(f"请使用完整路径重试，如: file_path=\"{matches[0]}\"")

    return '\n'.join(lines)


def _should_exclude_path(path: Path, base: Path) -> bool:
    """检查路径是否在排除目录下"""
    try:
        rel = path.relative_to(base)
    except ValueError:
        rel = path
    for part in rel.parts:
        if part in EXCLUDED_DIRS or part.endswith('.egg-info'):
            return True
    return False