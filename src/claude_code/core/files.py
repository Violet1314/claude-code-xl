"""文件管理 - 挂载、验证与上下文构建"""
import os
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from claude_code.config.defaults import FILE
from claude_code.utils.tokens import estimate_tokens
from claude_code.utils.paths import (
    resolve_path,
    expand_glob,
    is_hidden,
    is_supported_extension,
    get_extension,
)

@dataclass
class AttachedFile:
    """挂载文件信息"""
    path: str
    content: str
    size: int
    tokens: int

class FileManager:
    """文件挂载管理器"""
    
    def __init__(
        self,
        max_file_size: int = None,
        max_file_count: int = None,
        max_total_chars: int = None,
    ):
        """
        初始化文件管理器
        
        Args:
            max_file_size: 单文件最大字节数
            max_file_count: 最大挂载文件数
            max_total_chars: 总字符数限制
        """
        self._files: Dict[str, AttachedFile] = {}
        self.max_file_size = max_file_size or FILE.MAX_FILE_SIZE
        self.max_file_count = max_file_count or FILE.MAX_FILE_COUNT
        self.max_total_chars = max_total_chars or FILE.MAX_TOTAL_CHARS
    
    @property
    def count(self) -> int:
        """当前挂载文件数"""
        return len(self._files)
    
    @property
    def total_chars(self) -> int:
        """当前总字符数"""
        return sum(len(f.content) for f in self._files.values())
    
    @property
    def total_tokens(self) -> int:
        """当前总 token 数"""
        return sum(f.tokens for f in self._files.values())
    
    @property
    def is_empty(self) -> bool:
        """是否无挂载文件"""
        return len(self._files) == 0
    
    def get_files(self) -> Dict[str, AttachedFile]:
        """获取所有挂载文件"""
        return self._files.copy()
    
    def _read_file(self, path: str) -> Optional[str]:
        """
        读取文件内容，支持多种编码
        
        Args:
            path: 文件路径
            
        Returns:
            文件内容或 None
        """
        encodings = ['utf-8', 'gbk', 'latin-1']
        
        for encoding in encodings:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception:
                return None
        
        return None
    
    def _validate_file(self, path: str) -> Tuple[bool, str]:
        """
        验证文件是否可挂载
        
        Args:
            path: 文件路径
            
        Returns:
            (是否有效, 原因)
        """
        # 已挂载
        if path in self._files:
            return False, "已挂载"
        
        # 文件数量限制
        if self.count >= self.max_file_count:
            return False, f"超过最大数量 {self.max_file_count}"
        
        # 文件存在
        if not os.path.isfile(path):
            return False, "文件不存在"
        
        # 隐藏文件
        if is_hidden(path):
            return False, "隐藏文件"
        
        # 扩展名
        if not is_supported_extension(path):
            ext = get_extension(path) or "无扩展名"
            return False, f"不支持 .{ext}"
        
        # 文件大小
        try:
            size = os.path.getsize(path)
            if size > self.max_file_size:
                return False, f"超过 {self.max_file_size // 1024}KB"
        except OSError:
            return False, "无法读取大小"
        
        return True, ""
    
    def add(self, patterns: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        添加文件（支持通配符）
        
        Args:
            patterns: 路径或通配符模式列表
            
        Returns:
            (成功列表, 失败列表[(路径, 原因)])
        """
        added: List[str] = []
        skipped: List[Tuple[str, str]] = []
        
        # 展开所有路径
        paths_to_add: List[str] = []
        for pattern in patterns:
            expanded = expand_glob(pattern)
            if expanded:
                paths_to_add.extend(expanded)
            else:
                # 非通配符模式，直接解析
                resolved = resolve_path(pattern)
                paths_to_add.append(resolved)
        
        for path in paths_to_add:
            # 验证
            valid, reason = self._validate_file(path)
            if not valid:
                skipped.append((path, reason))
                continue
            
            # 读取内容
            content = self._read_file(path)
            if content is None:
                skipped.append((path, "读取失败"))
                continue
            
            # 检查总字符限制
            if self.total_chars + len(content) > self.max_total_chars:
                skipped.append((path, "总字符超限"))
                continue
            
            # 添加成功
            size = os.path.getsize(path)
            tokens = estimate_tokens(content)
            self._files[path] = AttachedFile(
                path=path,
                content=content,
                size=size,
                tokens=tokens,
            )
            added.append(path)
        
        return added, skipped
    
    def drop(self, patterns: List[str]) -> List[str]:
        """
        移除文件
        
        Args:
            patterns: 路径列表，支持 'all' 清空全部
            
        Returns:
            已移除的路径列表
        """
        removed: List[str] = []
        
        # 清空全部
        if patterns and patterns[0].lower() == 'all':
            removed = list(self._files.keys())
            self._files.clear()
            return removed
        
        for pattern in patterns:
            path = resolve_path(pattern)
            
            # 精确匹配
            if path in self._files:
                del self._files[path]
                removed.append(path)
                continue
            
            # 文件名模糊匹配
            basename = os.path.basename(path)
            matches = [p for p in self._files if os.path.basename(p) == basename]
            for match in matches:
                del self._files[match]
                removed.append(match)
        
        return removed
    
    def refresh(self) -> Tuple[List[str], List[str]]:
        """
        刷新所有文件内容
        
        Returns:
            (刷新成功列表, 已移除列表)
        """
        refreshed: List[str] = []
        removed: List[str] = []
        
        for path in list(self._files.keys()):
            # 文件不存在
            if not os.path.isfile(path):
                del self._files[path]
                removed.append(path)
                continue
            
            # 重新读取
            content = self._read_file(path)
            if content is None:
                del self._files[path]
                removed.append(path)
                continue
            
            # 更新
            size = os.path.getsize(path)
            tokens = estimate_tokens(content)
            self._files[path] = AttachedFile(
                path=path,
                content=content,
                size=size,
                tokens=tokens,
            )
            refreshed.append(path)
        
        return refreshed, removed
    
    def build_context(self) -> Optional[str]:
        """
        构建文件上下文消息
        
        Returns:
            上下文字符串或 None
        """
        if self.is_empty:
            return None
        
        parts = [f"[📎 已挂载 {self.count} 个文件]\n"]
        
        for path, file in self._files.items():
            ext = get_extension(path)
            parts.append(f"--- {path} ---")
            parts.append(f"```{ext}\n{file.content}\n```\n")
        
        return "\n".join(parts)
    
    def clear(self) -> int:
        """
        清空所有挂载
        
        Returns:
            清空的文件数
        """
        count = self.count
        self._files.clear()
        return count