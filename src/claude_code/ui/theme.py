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

    # 背景层次
    "bg_base": "#0D0D0D",           # 终端基础背景
    "bg_elevated": "#1A1A1A",       # 卡片/面板背景
    "bg_overlay": "#262626",        # 浮层/下拉背景

    # 边框层次
    "border_subtle": "#6A6A6A",     # 卡片边框（明亮的灰色）
    "border_default": "#7A7A7A",    # 默认边框
    "border_emphasis": "#8A8A8A",   # 强调边框（焦点）

    # 文字层次
    "text_primary": "#FAFAFA",      # 主要文字
    "text_secondary": "#A1A1AA",    # 次要文字
    "text_muted": "#71717A",        # 暗淡文字

    # 输入区域
    "input_bg": "#1F1F1F",          # 深灰背景
    "input_text": "#E5E7EB",        # 近白色文字

    # 基础色（兼容旧代码）
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
    # 品牌与用户
    'claude': '◆',
    "user": "❯",
    
    # 状态
    "success": "✓",
    "error": "✗",
    "warning": "⚠",
    "info": "ℹ",
    "thinking": "⠋",

    # 文件系统
    "file": "📎",

    # 工具专属图标
    "read": "📖",           
    "write": "✏️",          
    "edit": "✎",           
    "bash": "⚡",           
    "grep": "🔍",           
    "glob": "📁",           
    "ask": "❓",            

    # 文件类型图标
    "file_py": "🐍",        
    "file_js": "📜",        
    "file_ts": "📘",        
    "file_json": "📋",      
    "file_md": "📝",        
    "file_txt": "📄",       
    "file_yaml": "⚙",       
    "file_html": "🌐",      
    "file_css": "🎨",       
    "file_default": "📄",   

    # 其他
    "folder": "📁",         
    "link": "🔗",           
    "lock": "🔒",           
    "star": "⭐",           
    "clock": "⏱",          
    "token": "◆",           
    "price": "$",           
}

# ============================================================
# Powerline 符号
# ============================================================
POWERLINE = {
    "right_hard": "▶",       
    "right_soft": "›",       
    "left_hard": "◀",        
    "left_soft": "‹",        
    "separator": "│",        
}

# ============================================================
# Prompt Toolkit 样式
# ============================================================
PROMPT_STYLE = Style.from_dict({
    # 补全菜单
    'completion-menu': f'bg:{COLORS["bg_elevated"]} {COLORS["text_secondary"]}',
    'completion-menu.completion.current': f'bg:{COLORS["primary"]} #000000 bold',
    'completion-menu.meta.completion': f'bg:{COLORS["bg_dark"]} {COLORS["text_muted"]}',
    
    # 命令与标签
    'command': f'{COLORS["success"]} bold',
    'model-tag': f'bg:{COLORS["primary"]} #000000 bold',
    'file-tag': f'{COLORS["info"]} italic',
    'info': f'{COLORS["info"]}',

    # 输入区域
    'input-area': f'bg:{COLORS["input_bg"]} {COLORS["input_text"]}',
    # 关键修复：确保 input-lead 使用正确的 fg 颜色
    'input-lead': f'fg:{COLORS["primary"]} bold bg:{COLORS["input_bg"]}',
    'cursor': f'{COLORS["primary"]} bold',

    # 菜单样式
    'menu-selected': f'bg:{COLORS["primary"]} #ffffff bold',
    'menu-text': f'{COLORS["input_text"]}',
    'menu-dim': '#666666 italic',
    'menu-border': f'{COLORS["primary"]}',
})

# ============================================================
# Logo 渐变色
# ============================================================
LOGO_GRADIENT = [
    "#C1502E",  # 深橙红
    "#D97757",  # 标准橙（主品牌色）
    "#E8956F",  # 浅橙
    "#F4A582",  # 更浅橙
    "#FBBF93",  # 米橙
    "#FFD4B3",  # 极浅橙
]

# ============================================================
# 编程名言
# ============================================================
PROGRAMMING_QUOTES = [
    '"Code is poetry." — WordPress',
    '"Talk is cheap. Show me the code." — Linus Torvalds',
    '"First, solve the problem. Then, write the code." — John Johnson',
    '"Simplicity is the soul of efficiency." — Austin Freeman',
    '"Make it work, make it right, make it fast." — Kent Beck',
    '"Programs must be written for people to read." — Harold Abelson',
    '"The best error message is the one that never shows up." — Thomas Fuchs',
    '"Any fool can write code that a computer can understand." — Martin Fowler',
]