"""Claude Code 主题配置 - 官方风格"""
from prompt_toolkit.styles import Style

# ============================================================
# 颜色配置
# ============================================================

COLORS = {
    # 品牌色
    "primary": "#D97757",           # Claude 官方橙色
    "primary_dim": "#B45309",       # 深橙色
    
    # 状态色
    "success": "#4ADE80",           # 薄荷绿
    "warning": "#FBBF24",           # 琥珀黄
    "error": "#F87171",             # 珊瑚红
    "info": "#60A5FA",              # 提示蓝
    
    # 输入区域
    "input_bg": "#1F1F1F",          # 深灰背景
    "input_text": "#E5E7EB",        # 近白色文字
    
    # 基础色
    "system": "#6B7280",            # 系统文本灰
    "bg_dark": "#0A0A0A",           # 极深背景
    "user": "#60A5FA",              # 用户消息色
    "assistant": "#FFFFFF",         # AI 回复色
    "border": "#333333",            # 边框色
    "border_dim": "#262626",        # 暗边框色
}

# ============================================================
# 图标配置
# ============================================================

ICONS = {
    "claude": "⚡",
    "user": "❯",
    "success": "✓",
    "error": "✗",
    "warning": "⚠",
    "thinking": "⠋",
    "file": "📎",
}

# ============================================================
# Prompt Toolkit 样式
# ============================================================

PROMPT_STYLE = Style.from_dict({
    # 补全菜单
    'completion-menu': 'bg:#1A1A1A #D1D5DB',
    'completion-menu.completion.current': f'bg:{COLORS["primary"]} #000000 bold',
    'completion-menu.meta.completion': 'bg:#121212 #888888',
    
    # 命令与标签
    'command': f'{COLORS["success"]} bold',
    'model-tag': f'bg:{COLORS["primary"]} #000000 bold',
    'file-tag': f'{COLORS["info"]} italic',
    'info': f'{COLORS["info"]}',
    
    # 输入区域
    'input-area': f'bg:{COLORS["input_bg"]} {COLORS["input_text"]}',
    'input-lead': f'bg:{COLORS["input_bg"]} {COLORS["primary"]} bold',
    'cursor': f'{COLORS["primary"]} bold',
    
    # 菜单样式
    'menu-selected': f'bg:{COLORS["primary"]} #ffffff bold',
    'menu-text': f'{COLORS["input_text"]}',
    'menu-dim': '#666666 italic',
    'menu-border': f'{COLORS["primary"]}',
})

# ============================================================
# Logo 渐变色（从深到浅）
# ============================================================

LOGO_GRADIENT = [
    "#C1502E",  # 深橙红
    "#D97757",  # 标准橙（主品牌色）
    "#E8956F",  # 浅橙
    "#F4A582",  # 更浅橙
    "#FBBF93",  # 米橙
    "#FFD4B3",  # 极浅橙
]