"""UI 组件模块测试"""
import pytest

from claude_code.ui.components import (
    CLAUDE_LOGO,
    CODE_LOGO,
    show_logo,
    show_welcome,
    show_status_bar,
    show_model_list,
    show_style_list,
    show_history_list,
    show_files_list,
    get_input_border,
)

class TestLogo:
    """Logo 测试"""
    
    def test_claude_logo_lines(self):
        assert len(CLAUDE_LOGO) == 6
    
    def test_code_logo_lines(self):
        assert len(CODE_LOGO) == 6
    
    def test_show_logo_no_error(self):
        try:
            show_logo()
        except Exception as e:
            pytest.fail(f"show_logo raised: {e}")

class TestWelcome:
    """欢迎界面测试"""
    
    def test_show_welcome_default(self):
        try:
            show_welcome()
        except Exception as e:
            pytest.fail(f"show_welcome raised: {e}")
    
    def test_show_welcome_with_model(self):
        try:
            show_welcome("Claude Sonnet 4")
        except Exception as e:
            pytest.fail(f"show_welcome raised: {e}")

class TestStatusBar:
    """状态栏测试"""
    
    def test_show_status_bar_basic(self):
        try:
            show_status_bar("claude-sonnet", 1000)
        except Exception as e:
            pytest.fail(f"show_status_bar raised: {e}")
    
    def test_show_status_bar_with_files(self):
        try:
            show_status_bar("model", 5000, file_count=3)
        except Exception as e:
            pytest.fail(f"show_status_bar raised: {e}")
    
    def test_show_status_bar_zero_tokens(self):
        try:
            show_status_bar("model", 0)
        except Exception as e:
            pytest.fail(f"show_status_bar raised: {e}")

class TestModelList:
    """模型列表测试"""
    
    def test_show_model_list(self):
        models = [
            {"id": "m1", "name": "Model 1", "context_limit": 100000},
            {"id": "m2", "name": "Model 2", "context_limit": 200000},
        ]
        try:
            show_model_list(models)
        except Exception as e:
            pytest.fail(f"show_model_list raised: {e}")
    
    def test_show_model_list_with_current(self):
        models = [
            {"id": "m1", "name": "Model 1", "context_limit": 100000},
        ]
        try:
            show_model_list(models, current_id="m1")
        except Exception as e:
            pytest.fail(f"show_model_list raised: {e}")
    
    def test_show_model_list_empty(self):
        try:
            show_model_list([])
        except Exception as e:
            pytest.fail(f"show_model_list raised: {e}")

class TestStyleList:
    """风格列表测试"""
    
    def test_show_style_list(self):
        styles = [
            {"id": "expert", "name": "Expert", "desc": "专业模式"},
            {"id": "casual", "name": "Casual", "desc": "休闲模式"},
        ]
        try:
            show_style_list(styles)
        except Exception as e:
            pytest.fail(f"show_style_list raised: {e}")
    
    def test_show_style_list_with_current(self):
        styles = [{"id": "expert", "name": "Expert", "desc": ""}]
        try:
            show_style_list(styles, current_id="expert")
        except Exception as e:
            pytest.fail(f"show_style_list raised: {e}")

class TestHistoryList:
    """历史列表测试"""
    
    def test_show_history_list(self):
        history = [
            {"id": "1", "title": "会话1", "time": "2024-01-01", "count": 5},
            {"id": "2", "title": "会话2", "time": "2024-01-02", "count": 10},
        ]
        try:
            show_history_list(history)
        except Exception as e:
            pytest.fail(f"show_history_list raised: {e}")
    
    def test_show_history_list_empty(self):
        try:
            show_history_list([])
        except Exception as e:
            pytest.fail(f"show_history_list raised: {e}")

class TestFilesList:
    """文件列表测试"""
    
    def test_show_files_list(self):
        files = [
            {"path": "/path/to/file.py", "tokens": 100},
            {"path": "/path/to/other.js", "tokens": 200},
        ]
        try:
            show_files_list(files, total_tokens=300)
        except Exception as e:
            pytest.fail(f"show_files_list raised: {e}")
    
    def test_show_files_list_empty(self):
        try:
            show_files_list([])
        except Exception as e:
            pytest.fail(f"show_files_list raised: {e}")

class TestInputBorder:
    """输入边框测试"""
    
    def test_get_input_border_default(self):
        top, bottom = get_input_border()
        
        assert top.startswith('┌')
        assert bottom.startswith('└')
        assert '─' in top
        assert '─' in bottom
    
    def test_get_input_border_custom_width(self):
        top, bottom = get_input_border(width=50)
        
        assert len(top) == 51  # 1 corner + 50 dashes
        assert len(bottom) == 51
    
    def test_borders_same_length(self):
        top, bottom = get_input_border(width=80)
        assert len(top) == len(bottom)