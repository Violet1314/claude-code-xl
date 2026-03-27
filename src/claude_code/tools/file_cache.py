"""
文件缓存管理器 - 实现增量存储，减少 Token 消耗

核心设计：
1. 文件内容只完整存储一次（base_content）
2. 后续修改只存储 diff（patches）
3. tool_result 只返回引用，不返回完整内容
4. 对话历史中用引用代替完整代码

存储结构：
{
    "app.py": {
        "base_content": "原始700行",        # 只存一次
        "base_hash": "abc123",              # 用于检测外部修改
        "patches": [                         # 增量变化
            {"type": "edit", "old": "5", "new": "10", "line": 51},
        ],
        "version": 1,
        "last_read": 1234567890.0,
    }
}
"""

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import threading


@dataclass
class FilePatch:
    """文件修改记录"""
    type: str  # edit, write
    old: str = ""
    new: str = ""
    line: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class CachedFile:
    """缓存的文件"""
    base_content: str  # 原始内容
    base_hash: str     # 原始 hash
    patches: List[FilePatch] = field(default_factory=list)
    version: int = 0
    last_read: float = field(default_factory=time.time)

    def get_current_content(self) -> str:
        """获取当前内容（应用所有 patches）"""
        content = self.base_content
        # 简单实现：对于 edit 类型，直接替换
        for patch in self.patches:
            if patch.type == "edit":
                content = content.replace(patch.old, patch.new, 1)
            elif patch.type == "write":
                content = patch.new
        return content

    def get_content_hash(self) -> str:
        """获取当前内容的 hash"""
        return hashlib.md5(self.get_current_content().encode()).hexdigest()[:16]


class FileCacheManager:
    """
    文件缓存管理器

    功能：
    - 文件只读取一次，后续从缓存获取
    - 编辑操作记录 diff，不重新读取
    - 检测外部修改，提示用户
    - 生成引用而非完整内容
    """

    def __init__(self, cache_file: str = None):
        """
        初始化缓存管理器

        Args:
            cache_file: 缓存持久化文件路径（可选）
        """
        self._cache: Dict[str, CachedFile] = {}
        self._cache_file = cache_file
        self._lock = threading.Lock()

        # 统计信息
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "tokens_saved": 0,
        }

        # 加载持久化缓存
        if cache_file and os.path.exists(cache_file):
            self._load_cache()

    def _get_file_key(self, file_path: str) -> str:
        """获取文件的缓存 key"""
        return str(Path(file_path).absolute())

    def _compute_hash(self, content: str) -> str:
        """计算内容 hash"""
        return hashlib.md5(content.encode()).hexdigest()[:16]

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
            content: 已知内容（如果已读取过，可传入避免重复读取）
            force_refresh: 是否强制刷新

        Returns:
            {
                "cached": bool,         # 是否命中缓存
                "content": str,         # 当前内容
                "version": int,         # 版本号
                "changed": bool,        # 是否有外部修改
                "reference": str,       # 引用标识
            }
        """
        key = self._get_file_key(file_path)

        with self._lock:
            # 检查缓存
            if key in self._cache and not force_refresh:
                cached = self._cache[key]

                # 如果提供了内容，检查是否有外部修改
                if content is not None:
                    current_hash = self._compute_hash(content)
                    expected_hash = cached.get_content_hash()

                    if current_hash != expected_hash:
                        # 外部修改，需要更新
                        self._update_base(key, content)
                        return {
                            "cached": False,
                            "content": content,
                            "version": cached.version + 1,
                            "changed": True,
                            "reference": self._make_reference(file_path, cached.version + 1),
                        }

                # 缓存命中
                cached.last_read = time.time()
                self.stats["cache_hits"] += 1

                return {
                    "cached": True,
                    "content": cached.get_current_content(),
                    "version": cached.version,
                    "changed": False,
                    "reference": self._make_reference(file_path, cached.version),
                }

            # 缓存未命中
            self.stats["cache_misses"] += 1

            if content is None:
                # 需要实际读取文件
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    try:
                        with open(file_path, 'r', encoding='gbk') as f:
                            content = f.read()
                    except Exception:
                        content = ""

            # 存入缓存
            cached = CachedFile(
                base_content=content,
                base_hash=self._compute_hash(content),
                patches=[],
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

    def _update_base(self, key: str, content: str):
        """更新基础内容（外部修改时）"""
        old_cached = self._cache.get(key)
        if old_cached:
            # 创建新版本
            new_cached = CachedFile(
                base_content=content,
                base_hash=self._compute_hash(content),
                patches=[],
                version=old_cached.version + 1,
            )
            self._cache[key] = new_cached

    # ============================================================
    # 核心方法：编辑
    # ============================================================

    def apply_edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
    ) -> Dict[str, Any]:
        """
        应用编辑操作

        Args:
            file_path: 文件路径
            old_string: 要替换的内容
            new_string: 新内容

        Returns:
            {
                "success": bool,
                "reference": str,       # 新引用
                "diff_summary": str,    # diff 摘要
            }
        """
        key = self._get_file_key(file_path)

        with self._lock:
            if key not in self._cache:
                return {
                    "success": False,
                    "error": "文件未在缓存中",
                }

            cached = self._cache[key]
            current = cached.get_current_content()

            # 验证 old_string 存在
            if old_string not in current:
                return {
                    "success": False,
                    "error": "未找到要替换的内容",
                }

            # 记录 patch
            patch = FilePatch(
                type="edit",
                old=old_string,
                new=new_string,
                line=current[:current.index(old_string)].count('\n') + 1,
            )
            cached.patches.append(patch)
            cached.version += 1

            # 计算 diff 摘要
            diff_summary = self._make_diff_summary(old_string, new_string)

            return {
                "success": True,
                "reference": self._make_reference(file_path, cached.version),
                "diff_summary": diff_summary,
                "version": cached.version,
            }

    def apply_write(
        self,
        file_path: str,
        content: str,
    ) -> Dict[str, Any]:
        """
        应用写入操作（覆盖整个文件）

        Args:
            file_path: 文件路径
            content: 新内容

        Returns:
            {
                "success": bool,
                "reference": str,
            }
        """
        key = self._get_file_key(file_path)

        with self._lock:
            # 计算新版本号
            old_version = 0
            if key in self._cache:
                old_version = self._cache[key].version

            # 创建新的缓存条目
            cached = CachedFile(
                base_content=content,
                base_hash=self._compute_hash(content),
                patches=[],
                version=old_version + 1,
            )
            self._cache[key] = cached

            return {
                "success": True,
                "reference": self._make_reference(file_path, cached.version),
                "version": cached.version,
            }

    # ============================================================
    # 引用生成
    # ============================================================

    def _make_reference(self, file_path: str, version: int) -> str:
        """生成文件引用"""
        name = Path(file_path).name
        return f"[file:{name}:v{version}]"

    def _make_diff_summary(self, old: str, new: str) -> str:
        """生成 diff 摘要"""
        old_lines = old.strip().split('\n')
        new_lines = new.strip().split('\n')

        if len(old_lines) == 1 and len(new_lines) == 1:
            # 单行替换
            old_short = old[:30] + "..." if len(old) > 30 else old
            new_short = new[:30] + "..." if len(new) > 30 else new
            return f"`{old_short}` → `{new_short}`"
        else:
            # 多行替换
            return f"{len(old_lines)}行 → {len(new_lines)}行"

    # ============================================================
    # tool_result 生成
    # ============================================================

    def make_read_result(
        self,
        file_path: str,
        content: str,
        offset: int = 1,
        limit: int = None,
        show_content: bool = True,
    ) -> str:
        """
        生成 Read 工具的结果（使用引用）

        Args:
            file_path: 文件路径
            content: 文件内容
            offset: 起始行
            limit: 行数限制
            show_content: 是否显示内容（False 则只返回引用）

        Returns:
            结果字符串
        """
        # 确保文件在缓存中
        result = self.read_file(file_path, content)
        reference = result["reference"]
        version = result["version"]

        lines = content.split('\n')
        total_lines = len(lines)

        # 构建结果
        parts = []

        # 文件信息
        file_name = Path(file_path).name
        file_size = len(content.encode('utf-8'))
        parts.append(f"📄 {file_name} ({total_lines}行, {file_size/1024:.1f}KB)")
        parts.append(f"📌 缓存引用: {reference}")

        if show_content:
            # 显示内容（带截断）
            if limit and total_lines > limit:
                # 分段显示
                end_line = min(offset + limit - 1, total_lines)
                parts.append(f"\n显示 {offset}-{end_line} 行:")

                for i in range(offset - 1, end_line):
                    line = lines[i]
                    if len(line) > 100:
                        line = line[:97] + "..."
                    parts.append(f"{i+1:6d}\t{line}")

                if end_line < total_lines:
                    parts.append(f"\n... (省略 {total_lines - end_line} 行)")
            else:
                # 显示全部（如果不太长）
                if total_lines <= 100 and len(content) < 5000:
                    parts.append(f"\n完整内容:")
                    for i, line in enumerate(lines, 1):
                        if len(line) > 100:
                            line = line[:97] + "..."
                        parts.append(f"{i:6d}\t{line}")
                else:
                    parts.append(f"\n💡 内容已缓存，使用 offset/limit 读取特定部分")
                    parts.append(f"   完整内容可通过引用 {reference} 获取")

        parts.append(f"\n📊 Token 节省: 使用引用避免重复传输")

        return '\n'.join(parts)

    def make_edit_result(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        success: bool,
        error: str = None,
    ) -> str:
        """
        生成 Edit 工具的结果
        """
        if not success:
            return f"❌ 编辑失败: {error}"

        # 应用编辑并获取引用
        result = self.apply_edit(file_path, old_string, new_string)
        reference = result.get("reference", "")
        diff_summary = result.get("diff_summary", "")

        parts = []
        parts.append(f"✅ 编辑成功")
        parts.append(f"📌 新引用: {reference}")
        parts.append(f"📝 变更: {diff_summary}")
        parts.append(f"💡 后续操作使用引用 {reference} 而非完整内容")

        return '\n'.join(parts)

    # ============================================================
    # 状态查询
    # ============================================================

    def get_cached_files(self) -> List[Dict[str, Any]]:
        """获取所有缓存的文件信息"""
        result = []
        with self._lock:
            for key, cached in self._cache.items():
                result.append({
                    "path": key,
                    "version": cached.version,
                    "patches": len(cached.patches),
                    "last_read": cached.last_read,
                    "hash": cached.get_content_hash(),
                })
        return result

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                **self.stats,
                "cached_files": len(self._cache),
            }

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self.stats = {
                "cache_hits": 0,
                "cache_misses": 0,
                "tokens_saved": 0,
            }

    # ============================================================
    # 持久化（可选）
    # ============================================================

    def _load_cache(self):
        """加载缓存"""
        if not self._cache_file or not os.path.exists(self._cache_file):
            return

        try:
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for key, item in data.get("files", {}).items():
                patches = [
                    FilePatch(**p) for p in item.get("patches", [])
                ]
                self._cache[key] = CachedFile(
                    base_content=item["base_content"],
                    base_hash=item["base_hash"],
                    patches=patches,
                    version=item.get("version", 0),
                    last_read=item.get("last_read", time.time()),
                )
        except Exception:
            pass

    def save_cache(self):
        """保存缓存"""
        if not self._cache_file:
            return

        data = {"files": {}}

        with self._lock:
            for key, cached in self._cache.items():
                data["files"][key] = {
                    "base_content": cached.base_content,
                    "base_hash": cached.base_hash,
                    "patches": [
                        {"type": p.type, "old": p.old, "new": p.new, "line": p.line}
                        for p in cached.patches
                    ],
                    "version": cached.version,
                    "last_read": cached.last_read,
                }

        with open(self._cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# 全局缓存管理器
file_cache = FileCacheManager()