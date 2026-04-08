"""
文件缓存管理器 - 减少重复读取，节省 Token
核心设计：
1. 文件内容只完整存储一次
2. 后续修改直接更新基础内容并递增版本
3. 【优化】读取计数按版本隔离，写入后新版本计数器重置，避免误拦截
"""
import hashlib
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
                            version_stats=cached.version_stats.copy() 
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
                version_stats=old_stats
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


# 全局缓存管理器实例
file_cache = FileCacheManager()