"""
文件缓存管理器 - 减少重复读取，节省 Token
核心设计：
文件内容只完整存储一次
后续修改直接更新基础内容
通过引用标识追踪文件版本
"""
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field
import threading


@dataclass
class CachedFile:
    """缓存的文件"""
    base_content: str
    base_hash: str
    version: int = 0
    last_read: float = field(default_factory=time.time)
    read_count: int = 0
    read_ranges: List[Tuple[int, int]] = field(default_factory=list)

    def get_content_hash(self) -> str:
        """获取当前内容的 hash"""
        return hashlib.md5(self.base_content.encode()).hexdigest()[:16]


class FileCacheManager:
    """
    文件缓存管理器
    功能：
    - 文件只读取一次，后续从缓存获取
    - 写入/编辑后自动更新缓存版本
    - 检测外部修改
    - 生成版本引用标识
    """

    def __init__(self):
        self._cache: Dict[str, CachedFile] = {}
        self._lock = threading.Lock()

    def _get_file_key(self, file_path: str) -> str:
        """获取文件的缓存 key"""
        return str(Path(file_path).absolute())

    def _compute_hash(self, content: str) -> str:
        """计算内容 hash"""
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _make_reference(self, file_path: str, version: int) -> str:
        """生成文件引用"""
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

        Args:
            file_path: 文件路径
            content: 已知内容（传入避免重复读取）
            force_refresh: 是否强制刷新

        Returns:
            {
                "cached": bool,
                "content": str,
                "version": int,
                "changed": bool,
                "reference": str,
            }
        """
        key = self._get_file_key(file_path)

        with self._lock:
            if key in self._cache and not force_refresh:
                cached = self._cache[key]

                # 检查外部修改
                if content is not None:
                    current_hash = self._compute_hash(content)
                    expected_hash = cached.get_content_hash()

                    if current_hash != expected_hash:
                        # 外部修改，更新缓存
                        new_version = cached.version + 1
                        self._cache[key] = CachedFile(
                            base_content=content,
                            base_hash=self._compute_hash(content),
                            version=new_version,
                        )
                        return {
                            "cached": False,
                            "content": content,
                            "version": new_version,
                            "changed": True,
                            "reference": self._make_reference(file_path, new_version),
                        }

                # 缓存命中
                cached.last_read = time.time()
                return {
                    "cached": True,
                    "content": cached.base_content,
                    "version": cached.version,
                    "changed": False,
                    "reference": self._make_reference(file_path, cached.version),
                }

            # 缓存未命中
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
            )
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

        Args:
            file_path: 文件路径
            content: 新内容

        Returns:
            { "success": bool,  "reference": str,  "version": int}
        """
        key = self._get_file_key(file_path)

        with self._lock:
            old_version = 0
            if key in self._cache:
                old_version = self._cache[key].version

            cached = CachedFile(
                base_content=content,
                base_hash=self._compute_hash(content),
                version=old_version + 1,
            )
            self._cache[key] = cached

            return {
                "success": True,
                "reference": self._make_reference(file_path, cached.version),
                "version": cached.version,
            }

    # ============================================================
    # 读取追踪
    # ============================================================

    def record_read(self, file_path: str, total_lines: int, start_line: int, end_line: int) -> None:
        """记录一次读取操作"""
        key = self._get_file_key(file_path)
        with self._lock:
            if key in self._cache:
                self._cache[key].read_count += 1
                self._cache[key].read_ranges.append((start_line, end_line))

    def get_read_count(self, file_path: str) -> int:
        """获取文件的读取次数"""
        key = self._get_file_key(file_path)
        with self._lock:
            if key in self._cache:
                return self._cache[key].read_count
            return 0

    def has_read(self, file_path: str) -> bool:
        """检查是否已读取过该文件"""
        key = self._get_file_key(file_path)
        with self._lock:
            if key in self._cache:
                return self._cache[key].read_count > 0
            return False

    def get_read_ranges(self, file_path: str) -> Optional[List[Tuple[int, int]]]:
        """获取文件的已读取行范围"""
        key = self._get_file_key(file_path)
        with self._lock:
            if key in self._cache:
                return self._cache[key].read_ranges.copy()
            return None

    def get_read_files(self) -> Dict[str, Tuple[int, List[Tuple[int, int]]]]:
        """获取所有已读文件信息"""
        with self._lock:
            result = {}
            for key, cached in self._cache.items():
                if cached.read_count > 0:
                    total_lines = cached.base_content.count('\n') + 1
                    result[key] = (total_lines, cached.read_ranges.copy())
            return result

    # ============================================================
    # 管理方法
    # ============================================================

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()


# 全局缓存管理器
file_cache = FileCacheManager()