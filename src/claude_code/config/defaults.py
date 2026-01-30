"""默认配置 - 所有常量的单一数据源"""
from dataclasses import dataclass, field
from typing import Dict

@dataclass(frozen=True)
class FileDefaults:
    """文件挂载相关配置"""
    MAX_FILE_SIZE: int = 100 * 1024          # 100KB
    MAX_FILE_COUNT: int = 30                  # 最大挂载文件数
    MAX_TOTAL_CHARS: int = 500_000            # 总字符限制 500K

@dataclass(frozen=True)
class APIDefaults:
    """API 请求相关配置"""
    MAX_TOKENS: int = 4096                    # 默认最大输出 token
    TEMPERATURE: float = 0.7                  # 默认温度
    MAX_RETRIES: int = 3                      # 最大重试次数
    CONNECT_TIMEOUT: float = 10.0             # 连接超时（秒）
    READ_TIMEOUT: float = 120.0               # 读取超时（秒）
    WRITE_TIMEOUT: float = 30.0               # 写入超时（秒）
    POOL_TIMEOUT: float = 10.0                # 连接池超时（秒）

@dataclass(frozen=True)
class ConversationDefaults:
    """对话管理相关配置"""
    DEFAULT_CONTEXT_LIMIT: int = 100_000      # 默认上下文限制
    SUMMARY_MAX_TOKENS: int = 50              # 摘要生成最大 token

@dataclass(frozen=True)
class UIDefaults:
    """UI 显示相关配置"""
    MIN_WIDTH: int = 40                       # 最小终端宽度
    MAX_WIDTH: int = 120                      # 最大终端宽度

# 全局单例
FILE = FileDefaults()
API = APIDefaults()
CONVERSATION = ConversationDefaults()
UI = UIDefaults()

# 版本信息
VERSION = "2.0.0"
APP_NAME = "Claude Code Terminal"