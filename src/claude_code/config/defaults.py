"""默认配置 - 所有常量的单一数据源"""
from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class FileDefaults:
    """文件挂载相关配置"""
    MAX_FILE_SIZE: int = 200 * 1024          # 200KB（单文件放宽）
    MAX_FILE_COUNT: int = 50                  # 最大挂载文件数
    MAX_TOTAL_CHARS: int = 800_000            # 总字符限制 800K

@dataclass(frozen=True)
class APIDefaults:
    """API 请求相关配置（针对国内中转 API 优化）"""
    MAX_TOKENS: int = 32768                   # 最大输出 token（适配 Kimi K2.5）
    TEMPERATURE: float = 0.7                  # 默认温度
    MAX_RETRIES: int = 5                      # 最大重试次数（中转服务不稳定）
    CONNECT_TIMEOUT: float = 30.0             # 连接超时（秒）- 国内→境外链路较长
    READ_TIMEOUT: float = 180.0               # 读取超时（秒）- 大文件/复杂任务预留
    WRITE_TIMEOUT: float = 30.0               # 写入超时（秒）
    POOL_TIMEOUT: float = 15.0                # 连接池超时（秒）- 高峰期可能排队

@dataclass(frozen=True)
class ConversationDefaults:
    """对话管理相关配置"""
    DEFAULT_CONTEXT_LIMIT: int = 200_000      # 默认上下文限制（适配 256K 模型）
    SUMMARY_MAX_TOKENS: int = 100             # 摘要生成最大 token（更详细）

@dataclass(frozen=True)
class UIDefaults:
    """UI 显示相关配置"""
    MIN_WIDTH: int = 40                       # 最小终端宽度
    MAX_WIDTH: int = 120                      # 最大终端宽度

@dataclass(frozen=True)
class ToolDefaults:
    """工具执行相关配置"""
    MAX_TOOL_ROUNDS: int = 80         # 最大循环轮次
    MAX_TOOLS_PER_ROUND: int = 50     # 每轮最大工具数

@dataclass(frozen=True)
class PlanDefaults:
    """计划模式相关配置"""
    MAX_ITEMS: int = 20                       # 单个计划最大任务数
    MIN_ITEMS: int = 1                        # 最小任务数
    MAX_CONTENT_LEN: int = 200                # 任务描述最大长度
    REMINDER_MAX: int = 3                     # 计划模式最大连续提醒次数（熔断阈值）
    NO_TOOL_ROUNDS_MAX: int = 2               # 连续无工具调用轮次阈值

# 全局单例
FILE = FileDefaults()
API = APIDefaults()
CONVERSATION = ConversationDefaults()
UI = UIDefaults()
TOOL = ToolDefaults()
PLAN = PlanDefaults()

# Workplace 隔离目录
WORKPLACE_DIR = "workplace"

# 版本信息
VERSION = "2.8.32 | Author: XieLong"
APP_NAME = "Claude Code Terminal"
