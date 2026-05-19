"""
文件缓存管理器 - 减少重复读取，节省 Token
核心设计：
1. 文件内容只完整存储一次
2. 后续修改直接更新基础内容并递增版本
3. 【优化】读取计数按版本隔离，写入后新版本计数器重置，避免误拦截
4. 【优化】语义摘要：缓存文件的结构化摘要（类名、函数签名、import），
   长对话中模型可通过 get_file_summary() 查询文件概览，减少盲目重读
"""
import ast
import hashlib
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field
import threading


@dataclass
class CachedFile:
    """缓存的文件对象"""
    base_content: str
    base_hash: str
    version: int = 0
    last_read: float = field(default_factory=time.time)
    
    # 【优化】版本统计信息: {version_id: {"count": int, "ranges": List[Tuple[int, int]]}}
    version_stats: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    
    # 【v2.8.36】语义摘要：缓存文件的结构化摘要
    summary: Optional[Dict[str, Any]] = field(default=None, repr=False)

    def get_content_hash(self) -> str:
        """获取当前内容的 hash"""
        return hashlib.md5(self.base_content.encode()).hexdigest()[:16]

    def get_version_stats(self, ver: int) -> Dict[str, Any]:
        """获取指定版本的统计信息，不存在则初始化"""
        if ver not in self.version_stats:
            self.version_stats[ver] = {"count": 0, "ranges": []}
        return self.version_stats[ver]


class FileCacheManager:
    """
    文件缓存管理器
    功能：
    - 文件只读取一次，后续从缓存获取
    - 写入/编辑后自动更新缓存版本
    - 检测外部修改
    - 生成版本引用标识
    - 【优化】按版本追踪读取次数，防止跨版本误拦截
    """
    
    def __init__(self):
        self._cache: Dict[str, CachedFile] = {}
        self._lock = threading.Lock()

    def _get_file_key(self, file_path: str) -> str:
        """获取文件的缓存 key (绝对路径)"""
        return str(Path(file_path).absolute())

    def _compute_hash(self, content: str) -> str:
        """计算内容 hash"""
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _make_reference(self, file_path: str, version: int) -> str:
        """生成文件引用标识"""
        name = Path(file_path).name
        return f"[file:{name}:v{version}]"

    # ============================================================
    # 核心方法：读取
    # ============================================================

    def read_file(
        self,
        file_path: str,
        content: str = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        读取文件（优先从缓存）
        """
        key = self._get_file_key(file_path)

        with self._lock:
            if key in self._cache and not force_refresh:
                cached = self._cache[key]

                # 检查外部修改 (如果传入了 content)
                if content is not None:
                    current_hash = self._compute_hash(content)
                    expected_hash = cached.get_content_hash()

                    if current_hash != expected_hash:
                        # 外部修改，更新缓存并递增版本
                        new_version = cached.version + 1
                        new_cached = CachedFile(
                            base_content=content,
                            base_hash=current_hash,
                            version=new_version,
                            # 保留旧版本统计
                            version_stats=cached.version_stats.copy(),
                            summary=self._build_summary(content, file_path),
                        )
                        # 初始化新版本统计
                        new_cached.get_version_stats(new_version)
                        
                        self._cache[key] = new_cached
                        
                        return {
                            "cached": False,
                            "content": content,
                            "version": new_version,
                            "changed": True,
                            "reference": self._make_reference(file_path, new_version),
                        }

                # 缓存命中且内容未变
                cached.last_read = time.time()
                return {
                    "cached": True,
                    "content": cached.base_content,
                    "version": cached.version,
                    "changed": False,
                    "reference": self._make_reference(file_path, cached.version),
                }

            # 缓存未命中，需要读取磁盘或接受传入内容
            if content is None:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    try:
                        with open(file_path, 'r', encoding='gbk') as f: 
                            content = f.read()
                    except Exception:
                        content = ""

            cached = CachedFile(
                base_content=content,
                base_hash=self._compute_hash(content),
                version=0,
                summary=self._build_summary(content, file_path),
            )
            # 初始化版本 0 的统计
            cached.get_version_stats(0)
            
            self._cache[key] = cached

            return {
                "cached": False,
                "content": content,
                "version": 0,
                "changed": False,
                "reference": self._make_reference(file_path, 0),
            }

    # ============================================================
    # 核心方法：写入
    # ============================================================

    def apply_write(
        self,
        file_path: str,
        content: str,
    ) -> Dict[str, Any]:
        """
        应用写入操作（覆盖整个文件的缓存）
        """
        key = self._get_file_key(file_path)

        with self._lock:
            old_version = 0
            old_stats = {}
            
            if key in self._cache:
                old_version = self._cache[key].version
                # 保留旧版本的统计记录
                old_stats = self._cache[key].version_stats.copy()

            new_version = old_version + 1
            
            cached = CachedFile(
                base_content=content,
                base_hash=self._compute_hash(content),
                version=new_version,
                version_stats=old_stats,
                summary=self._build_summary(content, file_path),
            )
            
            # 初始化新版本的统计（计数器从 0 开始）
            cached.get_version_stats(new_version)
            
            self._cache[key] = cached

            return {
                "success": True,
                "reference": self._make_reference(file_path, cached.version),
                "version": cached.version,
            }

    # ============================================================
    # 读取追踪 (优化版)
    # ============================================================

    def record_read(self, file_path: str, total_lines: int, start_line: int, end_line: int) -> Dict[str, Any]:
        """
        记录一次读取操作
        
        Returns:
            {'count': int, 'blocked': bool}
        """
        key = self._get_file_key(file_path)
        
        with self._lock:
            if key not in self._cache:
                return {"count": 0, "blocked": False}
                
            cached = self._cache[key]
            current_version = cached.version
            
            # 获取当前版本的统计数据
            stats = cached.get_version_stats(current_version)
            
# 增加计数
            stats["count"] += 1
            # 记录范围
            stats["ranges"].append((start_line, end_line))

            current_count = stats["count"]
            # 不再限制读取次数
            return {"count": current_count, "blocked": False}

    def get_read_count(self, file_path: str) -> int:
        """获取当前版本的读取次数"""
        key = self._get_file_key(file_path)
        with self._lock:
            if key in self._cache:
                cached = self._cache[key]
                stats = cached.get_version_stats(cached.version)
                return stats["count"]
            return 0

    def has_read(self, file_path: str) -> bool:
        """检查当前版本是否已读取过该文件"""
        return self.get_read_count(file_path) > 0

    def is_cached(self, file_path: str) -> bool:
        """检查文件是否在缓存中（任何版本）"""
        key = self._get_file_key(file_path)
        with self._lock:
            return key in self._cache

    def get_read_ranges(self, file_path: str) -> List[Tuple[int, int]]:
        """获取当前版本已读取的行范围列表"""
        key = self._get_file_key(file_path)
        with self._lock:
            if key in self._cache:
                cached = self._cache[key]
                stats = cached.get_version_stats(cached.version)
                return stats.get("ranges", [])
            return []

    def reset_read_count(self, file_path: str) -> bool:
        """
        重置文件的读取计数（用于 Edit 失败时解锁 Read）
        返回: 是否成功重置
        """
        key = self._get_file_key(file_path)
        with self._lock:
            if key in self._cache:
                cached = self._cache[key]
                # 重置当前版本的计数
                cached.version_stats[cached.version] = {"count": 0, "ranges": []}
                return True
            return False

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()

    # ============================================================
    # 语义摘要 (v2.8.36) - 供长对话中模型查询文件概览
    # ============================================================

    @staticmethod
    def _format_python_signature(node) -> Optional[str]:
        """将 Python AST 函数节点格式化为签名字符串
        
        例如：def process(data, config=None) -> str
        """
        try:
            args = []
            # 普通参数
            for arg in node.args.args:
                name = arg.arg
                if arg.annotation:
                    ann = ast.unparse(arg.annotation) if hasattr(ast, 'unparse') else ""
                    args.append(f"{name}: {ann}" if ann else name)
                else:
                    args.append(name)
            # *args
            if node.args.vararg:
                args.append(f"*{node.args.vararg.arg}")
            # keyword-only 参数
            for arg in node.args.kwonlyargs:
                name = arg.arg
                if arg.annotation:
                    ann = ast.unparse(arg.annotation) if hasattr(ast, 'unparse') else ""
                    args.append(f"{name}: {ann}" if ann else name)
                else:
                    args.append(name)
            # **kwargs
            if node.args.kwarg:
                args.append(f"**{node.args.kwarg.arg}")
            # 默认值不展开（太长），仅标注参数名和类型注解
            sig = f"{node.name}({', '.join(args)})"
            # 返回值注解
            if node.returns:
                ret = ast.unparse(node.returns) if hasattr(ast, 'unparse') else ""
                if ret:
                    sig = f"{sig} -> {ret}"
            return sig
        except Exception:
            return node.name if hasattr(node, 'name') else None

    def _build_summary(self, content: str, file_path: str) -> Optional[Dict[str, Any]]:
        """
        构建文件语义摘要（轻量级，不依赖外部库）
        
        支持：
        - Python：提取 class/def/import
        - JS/TS：提取 class/function/export
        - JSON/YAML：提取顶层 key
        - 其他：提取非空行数和文件类型
        
        Args:
            content: 文件内容
            file_path: 文件路径
        
        Returns:
            摘要字典，或解析失败时返回 None
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        lines = content.splitlines()
        total_lines = len(lines)
        
        summary: Dict[str, Any] = {
            "lines": total_lines,
            "size": len(content),
        }
        
        # Python 文件：提取类、函数签名、import
        if ext == ".py":
            try:
                tree = ast.parse(content)
                classes = []
                functions = []
                imports = []
                # 收集类定义的行号范围，用于判断顶层函数
                class_ranges = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        class_ranges.append((node.lineno, node.end_lineno or node.lineno))
                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, ast.ClassDef):
                        methods = []
                        for n in node.body:
                            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                sig = self._format_python_signature(n)
                                methods.append(sig if sig else n.name)
                        classes.append({"name": node.name, "methods": methods[:8]})
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # 仅收集顶层函数（不在类内部）
                        sig = self._format_python_signature(node)
                        functions.append(sig if sig else node.name)
                    elif isinstance(node, (ast.Import, ast.ImportFrom)):
                        for alias in node.names:
                            imports.append(alias.name)
                if classes:
                    summary["classes"] = classes[:10]
                if functions:
                    summary["functions"] = functions[:15]
                if imports:
                    summary["imports"] = imports[:10]
            except SyntaxError:
                pass
        
        # JS/TS：提取 class/function/export
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            class_pattern = re.compile(r"(?:export\s+)?(?:class|interface)\s+(\w+)")
            func_pattern = re.compile(r"(?:export\s+)?(?:function|const|let|var)\s+(\w+)")
            import_pattern = re.compile(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]")
            classes = [m.group(1) for m in class_pattern.finditer(content)]
            functions = [m.group(1) for m in func_pattern.finditer(content)]
            imports = [m.group(1) for m in import_pattern.finditer(content)]
            if classes:
                summary["classes"] = classes[:10]
            if functions:
                summary["functions"] = functions[:15]
            if imports:
                summary["imports"] = imports[:10]
        
        # JSON：提取顶层 key 及其值的类型
        elif ext == ".json":
            try:
                import json
                data = json.loads(content)
                if isinstance(data, dict):
                    key_types = {}
                    for k, v in list(data.items())[:15]:
                        key_types[k] = type(v).__name__
                    summary["keys"] = list(key_types.keys())
                    summary["key_types"] = key_types
                elif isinstance(data, list) and data:
                    summary["type"] = "array"
                    summary["length"] = len(data)
                    # 采样第一个元素的类型
                    first = data[0]
                    if isinstance(first, dict):
                        summary["item_keys"] = list(first.keys())[:10]
            except Exception:
                pass
        
        # YAML：提取顶层 key
        elif ext in (".yaml", ".yml"):
            try:
                top_keys = []
                for line in lines:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and ":" in stripped:
                        key = stripped.split(":")[0].strip()
                        if key and not key.startswith("-"):
                            top_keys.append(key)
                if top_keys:
                    summary["keys"] = top_keys[:15]
            except Exception:
                pass
        
        # 所有文件都提取 shebang（如果有）
        if lines and lines[0].startswith("#!/"):
            summary["shebang"] = lines[0].strip()
        
        # 如果摘要为空（只有 lines/size），返回 None 表示无需缓存摘要
        if len(summary) <= 2:
            return None
        return summary

    def get_file_summary(self, file_path: str) -> Optional[str]:
        """
        获取文件语义摘要的格式化文本（供模型查询）
        
        Returns:
            格式化摘要文本，文件未缓存或无摘要时返回 None
        """
        key = self._get_file_key(file_path)
        with self._lock:
            if key not in self._cache:
                return None
            cached = self._cache[key]
            if not cached.summary:
                return None
            
            path = Path(file_path)
            parts = [f"文件: {path.name} ({cached.summary.get('lines', 0)} 行)"]
            
            if "classes" in cached.summary:
                for cls in cached.summary["classes"]:
                    methods_str = ", ".join(cls.get("methods", [])) if cls.get("methods") else ""
                    if methods_str:
                        parts.append(f"  class {cls['name']}: {methods_str}")
                    else:
                        parts.append(f"  class {cls['name']}")
            
            if "functions" in cached.summary:
                funcs = cached.summary["functions"]
                # 函数签名可能较长，每行一个
                if any("(" in f for f in funcs):
                    parts.append("  函数:")
                    for f in funcs:
                        parts.append(f"    def {f}")
                else:
                    parts.append(f"  函数: {', '.join(funcs)}")
            
            if "imports" in cached.summary:
                imps = cached.summary["imports"]
                parts.append(f"  import: {', '.join(imps)}")
            
            if "key_types" in cached.summary:
                # JSON: 显示 key: type 格式
                kt = cached.summary["key_types"]
                type_strs = [f"{k}: {v}" for k, v in kt.items()]
                parts.append(f"  顶层键: {', '.join(type_strs)}")
            elif "keys" in cached.summary:
                keys = cached.summary["keys"]
                parts.append(f"  顶层键: {', '.join(keys)}")
            
            if "item_keys" in cached.summary:
                parts.append(f"  数组元素键: {', '.join(cached.summary['item_keys'])}")
            
            if "shebang" in cached.summary:
                parts.append(f"  shebang: {cached.summary['shebang']}")
            
            return "\n".join(parts)


# 全局缓存管理器实例
file_cache = FileCacheManager()