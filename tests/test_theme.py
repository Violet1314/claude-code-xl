"""主题配置模块测试"""
import pytest
from claude_code.ui.theme import COLORS, ICONS, PROMPT_STYLE, LOGO_GRADIENT

class TestColors:
    """颜色配置测试"""
    
    def test_primary_color_exists(self):
        assert "primary" in COLORS
        assert COLORS["primary"].startswith("#")
    
    def test_status_colors_exist(self):
        required = ["success", "warning", "error", "info"]
        for color in required:
            assert color in COLORS, f"缺少状态色: {color}"
    
    def test_color_format(self):
        """所有颜色应为有效的十六进制格式"""
        for name, value in COLORS.items():
            assert value.startswith("#"), f"{name} 格式错误"
            # #RGB 或 #RRGGBB
            assert len(value) in (4, 7), f"{name} 长度错误: {value}"

class TestIcons:
    """图标配置测试"""
    
    def test_required_icons_exist(self):
        required = ["claude", "user", "success", "error", "warning"]
        for icon in required:
            assert icon in ICONS, f"缺少图标: {icon}"
    
    def test_icons_not_empty(self):
        for name, value in ICONS.items():
            assert len(value) > 0, f"图标 {name} 为空"

class TestPromptStyle:
    """Prompt 样式测试"""
    
    def test_style_is_valid(self):
        """确保样式对象可用"""
        assert PROMPT_STYLE is not None
    
    def test_style_has_entries(self):
        """样式应包含条目"""
        # Style 对象内部有 style_rules
        assert hasattr(PROMPT_STYLE, 'style_rules')

class TestLogoGradient:
    """Logo 渐变色测试"""
    
    def test_gradient_length(self):
        """渐变色应有 6 个色阶"""
        assert len(LOGO_GRADIENT) == 6
    
    def test_gradient_format(self):
        """所有渐变色应为有效格式"""
        for color in LOGO_GRADIENT:
            assert color.startswith("#")
            assert len(color) == 7  # #RRGGBB