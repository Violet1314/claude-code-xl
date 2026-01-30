"""控制台输出模块测试"""
import pytest
from io import StringIO
from rich.console import Console as RichConsole

from claude_code.ui import console

class TestGetConsole:
    """get_console 函数测试"""
    
    def test_returns_console_instance(self):
        result = console.get_console()
        assert isinstance(result, RichConsole)
    
    def test_returns_same_instance(self):
        """应返回同一个单例"""
        c1 = console.get_console()
        c2 = console.get_console()
        assert c1 is c2

class TestStatusMessages:
    """状态消息函数测试"""
    
    def test_success_no_error(self):
        """success 函数应正常执行"""
        try:
            console.success("测试成功")
        except Exception as e:
            pytest.fail(f"success 抛出异常: {e}")
    
    def test_error_no_error(self):
        """error 函数应正常执行"""
        try:
            console.error("测试错误")
        except Exception as e:
            pytest.fail(f"error 抛出异常: {e}")
    
    def test_warning_no_error(self):
        """warning 函数应正常执行"""
        try:
            console.warning("测试警告")
        except Exception as e:
            pytest.fail(f"warning 抛出异常: {e}")
    
    def test_info_no_error(self):
        """info 函数应正常执行"""
        try:
            console.info("测试信息")
        except Exception as e:
            pytest.fail(f"info 抛出异常: {e}")
    
    def test_dim_no_error(self):
        """dim 函数应正常执行"""
        try:
            console.dim("暗色文本")
        except Exception as e:
            pytest.fail(f"dim 抛出异常: {e}")

class TestContentRendering:
    """内容渲染函数测试"""
    
    def test_markdown_empty(self):
        """空内容不应报错"""
        try:
            console.markdown("")
            console.markdown(None)
        except Exception as e:
            pytest.fail(f"markdown 空内容报错: {e}")
    
    def test_markdown_normal(self):
        """正常 Markdown 渲染"""
        try:
            console.markdown("# 标题\n\n正文内容")
        except Exception as e:
            pytest.fail(f"markdown 渲染报错: {e}")
    
    def test_code_empty(self):
        """空代码不应报错"""
        try:
            console.code("")
            console.code(None)
        except Exception as e:
            pytest.fail(f"code 空内容报错: {e}")
    
    def test_code_python(self):
        """Python 代码渲染"""
        try:
            console.code("def hello():\n    print('Hello')", "python")
        except Exception as e:
            pytest.fail(f"code 渲染报错: {e}")
    
    def test_code_different_languages(self):
        """不同语言代码渲染"""
        languages = ["javascript", "json", "bash", "sql"]
        for lang in languages:
            try:
                console.code("// test", lang)
            except Exception as e:
                pytest.fail(f"code {lang} 渲染报错: {e}")

class TestLayoutElements:
    """布局元素函数测试"""
    
    def test_rule_no_error(self):
        try:
            console.rule()
            console.rule("#555555")
        except Exception as e:
            pytest.fail(f"rule 报错: {e}")
    
    def test_blank_no_error(self):
        try:
            console.blank()
            console.blank(3)
        except Exception as e:
            pytest.fail(f"blank 报错: {e}")

class TestRawOutput:
    """原始输出函数测试"""
    
    def test_print_no_error(self):
        try:
            console.print("普通文本")
            console.print("[bold]带标记[/]")
        except Exception as e:
            pytest.fail(f"print 报错: {e}")
    
    def test_print_raw_no_error(self):
        try:
            console.print_raw("[这不是标记]")
        except Exception as e:
            pytest.fail(f"print_raw 报错: {e}")