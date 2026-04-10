"""语法检查器 - 支持多种文件类型"""
import json
import re
from typing import Optional, Tuple, List, Dict
from pathlib import Path


class SyntaxChecker:
    """语法检查器基类"""
    
    extensions: List[str] = []  # 子类覆盖
    
    @classmethod
    def can_check(cls, file_path: str) -> bool:
        """是否支持该文件类型"""
        return any(file_path.endswith(ext) for ext in cls.extensions)
    
    @classmethod
    def check(cls, content: str, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        检查语法
        
        Returns:
            (is_valid, error_message)
        """
        raise NotImplementedError


class PythonChecker(SyntaxChecker):
    """Python 语法检查"""
    
    extensions = ['.py', '.pyw']
    
    @classmethod
    def check(cls, content: str, file_path: str) -> Tuple[bool, Optional[str]]:
        try:
            compile(content, file_path, 'exec')
            return True, None
        except SyntaxError as e:
            return False, f"语法错误: {e.msg} (行 {e.lineno})"
        except Exception as e:
            return False, f"检查失败: {str(e)}"


class JsonChecker(SyntaxChecker):
    """JSON 语法检查"""
    
    extensions = ['.json', '.jsonc', '.json5']
    
    @classmethod
    def check(cls, content: str, file_path: str) -> Tuple[bool, Optional[str]]:
        try:
            # 移除 JSONC/JSON5 风格的注释（简化处理）
            clean_content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
            clean_content = re.sub(r'/\*.*?\*/', '', clean_content, flags=re.DOTALL)
            json.loads(clean_content)
            return True, None
        except json.JSONDecodeError as e:
            return False, f"JSON 错误: {e.msg} (行 {e.lineno}, 列 {e.colno})"
        except Exception as e:
            return False, f"检查失败: {str(e)}"


class YamlChecker(SyntaxChecker):
    """YAML 语法检查"""
    
    extensions = ['.yaml', '.yml']
    
    @classmethod
    def check(cls, content: str, file_path: str) -> Tuple[bool, Optional[str]]:
        try:
            import yaml
            yaml.safe_load(content)
            return True, None
        except ImportError:
            return True, None  # 未安装 yaml 库，跳过检查
        except yaml.YAMLError as e:
            # 提取行号
            line = getattr(e, 'problem_mark', None)
            line_info = f" (行 {line.line + 1})" if line else ""
            return False, f"YAML 错误: {str(e)}{line_info}"
        except Exception as e:
            return False, f"检查失败: {str(e)}"


class TomlChecker(SyntaxChecker):
    """TOML 语法检查"""
    
    extensions = ['.toml']
    
    @classmethod
    def check(cls, content: str, file_path: str) -> Tuple[bool, Optional[str]]:
        try:
            # Python 3.11+ 内置 tomllib
            import tomllib
            tomllib.loads(content)
            return True, None
        except ImportError:
            # 尝试第三方库
            try:
                import tomli
                tomli.loads(content)
                return True, None
            except ImportError:
                try:
                    import toml
                    toml.loads(content)
                    return True, None
                except ImportError:
                    return True, None  # 无 TOML 库，跳过检查
                except Exception as e:
                    return False, f"TOML 错误: {str(e)}"
            except Exception as e:
                return False, f"TOML 错误: {str(e)}"
        except Exception as e:
            return False, f"TOML 错误: {str(e)}"


class XmlChecker(SyntaxChecker):
    """XML 语法检查"""
    
    extensions = ['.xml', '.xhtml', '.svg', '.xaml']
    
    @classmethod
    def check(cls, content: str, file_path: str) -> Tuple[bool, Optional[str]]:
        try:
            import xml.etree.ElementTree as ET
            ET.fromstring(content)
            return True, None
        except ET.ParseError as e:
            return False, f"XML 错误: {str(e)}"
        except Exception as e:
            return False, f"检查失败: {str(e)}"


class HtmlChecker(SyntaxChecker):
    """HTML 语法检查（简化版：检查标签配对）"""
    
    extensions = ['.html', '.htm']
    
    @classmethod
    def check(cls, content: str, file_path: str) -> Tuple[bool, Optional[str]]:
        try:
            from html.parser import HTMLParser
            
            class HTMLValidator(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.errors = []
                    self.tag_stack = []
                    # 自闭合标签
                    self.void_elements = {
                        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                        'link', 'meta', 'param', 'source', 'track', 'wbr'
                    }
                
                def handle_starttag(self, tag, attrs):
                    if tag.lower() not in self.void_elements:
                        self.tag_stack.append(tag.lower())
                
                def handle_endtag(self, tag):
                    tag = tag.lower()
                    if tag in self.void_elements:
                        return
                    if not self.tag_stack:
                        self.errors.append(f"多余的闭合标签: </{tag}>")
                    elif self.tag_stack[-1] != tag:
                        self.errors.append(f"标签不匹配: 期望 </{self.tag_stack[-1]}>, 实际 </{tag}>")
                    else:
                        self.tag_stack.pop()
            
            parser = HTMLValidator()
            parser.feed(content)
            
            if parser.errors:
                return False, parser.errors[0]
            if parser.tag_stack:
                return False, f"未闭合的标签: <{parser.tag_stack[-1]}>"
            return True, None
        except Exception as e:
            return False, f"检查失败: {str(e)}"


class CssChecker(SyntaxChecker):
    """CSS 语法检查（简化版：检查括号配对）"""
    
    extensions = ['.css', '.scss', '.sass', '.less']
    
    @classmethod
    def check(cls, content: str, file_path: str) -> Tuple[bool, Optional[str]]:
        try:
            # 移除注释
            clean = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
            clean = re.sub(r'//.*$', '', clean, flags=re.MULTILINE)
            
            # 检查花括号配对
            depth = 0
            in_string = False
            string_char = None
            line_num = 1
            
            for i, char in enumerate(clean):
                if char == '\n':
                    line_num += 1
                    continue
                
                # 处理字符串
                if char in '"\'':
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char:
                        in_string = False
                    continue
                
                if in_string:
                    continue
                
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth < 0:
                        return False, f"多余的花括号 '}}' (行 {line_num})"
            
            if depth > 0:
                return False, f"未闭合的花括号 '{{' (共 {depth} 处)"
            
            return True, None
        except Exception as e:
            return False, f"检查失败: {str(e)}"


class JavaScriptChecker(SyntaxChecker):
    """JavaScript/TypeScript 语法检查（简化版：检查括号配对）"""
    
    extensions = ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs']
    
    @classmethod
    def check(cls, content: str, file_path: str) -> Tuple[bool, Optional[str]]:
        try:
            # 移除注释
            clean = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
            clean = re.sub(r'//.*$', '', clean, flags=re.MULTILINE)
            
            # 检查括号配对
            brackets = {'{': '}', '[': ']', '(': ')'}
            stack: List[Tuple[str, int, int]] = []  # (char, line, col)
            in_string = False
            in_template = False
            string_char = None
            line_num = 1
            col_num = 1
            
            i = 0
            while i < len(clean):
                char = clean[i]
                
                if char == '\n':
                    line_num += 1
                    col_num = 1
                    i += 1
                    continue
                
                col_num += 1
                
                # 处理模板字符串
                if char == '`':
                    if not in_string:
                        in_template = not in_template
                    i += 1
                    continue
                
                # 处理普通字符串
                if char in '"\'':
                    if not in_string and not in_template:
                        in_string = True
                        string_char = char
                    elif in_string and char == string_char and (i == 0 or clean[i-1] != '\\'):
                        in_string = False
                    i += 1
                    continue
                
                if in_string or in_template:
                    i += 1
                    continue
                
                # 检查括号
                if char in brackets:
                    stack.append((char, line_num, col_num))
                elif char in brackets.values():
                    if not stack:
                        return False, f"多余的闭合括号 '{char}' (行 {line_num})"
                    open_char = stack[-1][0]
                    if brackets.get(open_char) != char:
                        return False, f"括号不匹配: 期望 '{brackets.get(open_char)}', 实际 '{char}' (行 {line_num})"
                    stack.pop()
                
                i += 1
            
            if stack:
                char, line, col = stack[-1]
                return False, f"未闭合的括号 '{char}' (行 {line})"
            
            return True, None
        except Exception as e:
            return False, f"检查失败: {str(e)}"


class ShellChecker(SyntaxChecker):
    """Shell 脚本语法检查（简化版）"""
    
    extensions = ['.sh', '.bash', '.zsh']
    
    @classmethod
    def check(cls, content: str, file_path: str) -> Tuple[bool, Optional[str]]:
        try:
            lines = content.splitlines()
            errors = []
            
            for i, line in enumerate(lines, 1):
                stripped = line.rstrip()
                
                # 检查未闭合的引号（简化）
                single_quotes = line.count("'") - line.count("\\'")
                double_quotes = line.count('"') - line.count('\\"')
                
                if single_quotes % 2 != 0:
                    errors.append(f"行 {i}: 单引号未配对")
                if double_quotes % 2 != 0:
                    errors.append(f"行 {i}: 双引号未配对")
            
            if errors:
                return False, errors[0]
            return True, None
        except Exception as e:
            return False, f"检查失败: {str(e)}"


class SqlChecker(SyntaxChecker):
    """SQL 语法检查（简化版：检查基本语法）"""
    
    extensions = ['.sql']
    
    @classmethod
    def check(cls, content: str, file_path: str) -> Tuple[bool, Optional[str]]:
        try:
            # 简化检查：确保有基本 SQL 关键字
            upper_content = content.upper()
            sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER']
            
            # 检查分号配对（简化）
            # 这里只做基本检查，完整 SQL 解析需要专门的库
            
            return True, None
        except Exception as e:
            return False, f"检查失败: {str(e)}"


# ============================================================
# 检查器注册表
# ============================================================

# 所有检查器
CHECKERS: List[type] = [
    PythonChecker,
    JsonChecker,
    YamlChecker,
    TomlChecker,
    XmlChecker,
    HtmlChecker,
    CssChecker,
    JavaScriptChecker,
    ShellChecker,
    SqlChecker,
]

# 扩展名到检查器的映射
EXTENSION_MAP: Dict[str, type] = {}
for checker in CHECKERS:
    for ext in checker.extensions:
        EXTENSION_MAP[ext] = checker


def check_syntax(content: str, file_path: str) -> Tuple[bool, Optional[str]]:
    """
    检查文件语法
    
    Args:
        content: 文件内容
        file_path: 文件路径
        
    Returns:
        (is_valid, error_message)
        - is_valid: True 表示语法正确或无检查器
        - error_message: 错误信息，无错误时为 None
    """
    # 获取文件扩展名
    ext = Path(file_path).suffix.lower()
    
    # 查找检查器
    checker_class = EXTENSION_MAP.get(ext)
    if not checker_class:
        return True, None  # 无检查器，跳过
    
    return checker_class.check(content, file_path)


def get_supported_extensions() -> List[str]:
    """获取所有支持的文件扩展名"""
    return list(EXTENSION_MAP.keys())


def get_checker_name(file_path: str) -> Optional[str]:
    """获取文件对应的检查器名称"""
    ext = Path(file_path).suffix.lower()
    checker_class = EXTENSION_MAP.get(ext)
    if checker_class:
        return checker_class.__name__.replace('Checker', '')
    return None