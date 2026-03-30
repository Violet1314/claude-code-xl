"""AskUserQuestion 工具 - 向用户询问问题"""
from typing import Any, Dict, List, Optional

from ..base import Tool, ToolResult
from claude_code.ui.input import interactive_menu
from claude_code.ui import console
from claude_code.ui.theme import COLORS, ICONS

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


class AskUserQuestionTool(Tool):
    """向用户询问问题工具"""

    name = "AskUserQuestion"
    description = (
        "向用户询问问题，获取用户的选择或输入。"
        "适用于：需要用户决策、选择实现方案、澄清需求等场景。"
        "当任务有多种实现方式时，应主动询问用户偏好。"
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "要询问的问题"
                },
                "options": {
                    "type": "array",
                    "description": "选项列表（可选），如果不提供则允许自由输入",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "选项显示文本"
                            },
                            "value": {
                                "type": "string",
                                "description": "选项值"
                            },
                            "desc": {
                                "type": "string",
                                "description": "选项描述（可选）"
                            }
                        },
                        "required": ["label", "value"]
                    }
                },
                "header": {
                    "type": "string",
                    "description": "简短标题，显示在菜单顶部（可选）"
                },
                "default": {
                    "type": "string",
                    "description": "默认值（用于自由输入模式）"
                }
            },
            "required": ["question"]
        }

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行询问"""
        question = parameters.get("question", "")
        options = parameters.get("options", [])
        header = parameters.get("header", "")
        default = parameters.get("default", "")

        if not question:
            return ToolResult(success=False, output="", error="缺少 question 参数")

        try:
            if options:
                # 有选项：显示选择菜单
                result = self._show_options_menu(question, options, header)
            else:
                # 无选项：显示输入框
                result = self._show_input_prompt(question, default)

            if result is None:
                return ToolResult(
                    success=False,
                    output="",
                    error="用户取消了输入",
                    metadata={"cancelled": True}
                )

            return ToolResult(
                success=True,
                output=result,
                metadata={"user_response": result}
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=f"询问失败: {str(e)}")

    def _show_options_menu(
        self,
        question: str,
        options: List[Dict],
        header: str
    ) -> Optional[str]:
        """
        显示选项菜单

        Args:
            question: 问题文本
            options: 选项列表
            header: 标题

        Returns:
            用户选择的值或 None
        """
        # 显示问题
        console.blank()
        console.print(f"[bold {COLORS['primary']}]{ICONS['claude']} 需要你的决策[/]")
        console.rule()

        # 问题文本
        for line in question.split('\n'):
            console.print(f"  {line}")

        console.blank()

        # 转换选项格式
        menu_options = []
        for opt in options:
            menu_options.append({
                "name": opt.get("label", opt.get("value", "")),
                "value": opt.get("value", ""),
                "desc": opt.get("desc", ""),
            })

        # 添加"其他"选项（允许自由输入）
        menu_options.append({
            "name": "其他（自由输入）",
            "value": "__free_input__",
            "desc": "输入自定义内容",
        })

        # 显示菜单
        title = header if header else "选择"
        choice = interactive_menu(title, menu_options)

        if choice is None:
            # 用户取消
            console.print(f"[dim]已取消[/]")
            return None

        if choice == "__free_input__":
            # 自由输入
            return self._show_input_prompt("请输入你的选择", "")

        return choice

    def _show_input_prompt(self, question: str, default: str) -> Optional[str]:
        """
        显示输入框

        Args:
            question: 问题文本
            default: 默认值

        Returns:
            用户输入或 None
        """
        console.blank()
        console.print(f"[bold {COLORS['primary']}]{ICONS['claude']} 问题[/]")
        console.rule()
        console.print(f"  {question}")
        console.blank()

        try:
            kb = KeyBindings()

            @kb.add('escape')
            @kb.add('c-c')
            def _(event):
                event.app.exit(result=None)

            session = PromptSession(key_bindings=kb)

            prompt_text = "> "
            if default:
                prompt_text = f"> [{default}]: "

            result = session.prompt(prompt_text)

            if not result.strip() and default:
                return default

            return result.strip() if result.strip() else None

        except (EOFError, KeyboardInterrupt):
            console.print(f"[dim]已取消[/]")
            return None

    def is_read_only(self) -> bool:
        """只读操作（不修改文件）"""
        return True

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        question = parameters.get("question")
        if not question:
            return "缺少 question 参数"

        options = parameters.get("options", [])
        if options:
            for i, opt in enumerate(options):
                if not opt.get("label") and not opt.get("value"):
                    return f"选项 {i+1} 缺少 label 或 value"

        return None