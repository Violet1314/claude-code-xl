"""Todo 工具 - 计划模式的任务管理工具"""
from typing import Any, Dict, List, Optional, Callable

from ..base import Tool, ToolResult
from claude_code.core.todo import TodoList, TodoItem
from claude_code.config.defaults import PLAN


# 全局 TodoList 实例（整个应用共享）
_todo_list: Optional[TodoList] = None


def get_todo_list() -> TodoList:
    """获取全局 TodoList 实例"""
    global _todo_list
    if _todo_list is None:
        _todo_list = TodoList()
    return _todo_list


def reset_todo_list() -> None:
    """重置全局 TodoList（新会话时调用）"""
    global _todo_list
    _todo_list = TodoList()


class TodoCreateTool(Tool):
    """创建任务计划"""
    name = "TodoCreate"
    description = (
        "创建任务计划。批量添加任务项，模型自主规划执行步骤时使用。\n"
        "注意：\n"
        "- items 是任务数组，每项包含 content（任务描述）和可选的 priority（high/medium/low）\n"
        "- 调用此工具会清空之前的计划，请一次性提交完整计划\n"
        "- 任务数量上限为 20 个"
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "任务列表，每项包含 content 和可选的 priority",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "任务描述",
                            },
                            "priority": {
                                "type": "string",
                                "description": "优先级：high/medium/low，默认 medium",
                                "enum": ["high", "medium", "low"],
                            },
                        },
                        "required": ["content"],
                    },
                },
            },
            "required": ["items"],
            "errorMessage": {
                "items": "必须提供 items（任务列表数组），每项包含 content 字段，如 items=[{\"content\": \"任务描述\"}]"
            },
        }

    def execute(self, parameters: Dict[str, Any], interrupt_check: Callable[[], bool] = None) -> ToolResult:
        items_data = parameters.get("items", [])
        if not items_data:
            return ToolResult(
                success=False,
                output="",
                error="任务列表不能为空",
            )

        # 使用 TodoList.create_from_dicts 批量创建（内置校验）
        # 直接创建新实例替换全局引用，无需先 clear() 旧实例
        todo = TodoList.create_from_dicts(items_data)

        # 替换全局实例
        global _todo_list
        _todo_list = todo

        # 构建输出
        input_count = len(items_data)
        skipped_count = max(0, input_count - todo.total_count)
        output_lines = [f"已创建 {todo.total_count} 个任务："]
        if skipped_count > 0:
            output_lines.append(
                f"⚠ 另有 {skipped_count} 个任务因超过上限或内容为空被忽略（上限 {PLAN.MAX_ITEMS} 个）"
            )
        for item in todo.items:
            output_lines.append(f"  {item.icon} {item.id}  {item.content}  [{item.priority}]")

        display_output = f"[bold green]● 计划已创建[/] 共 {todo.total_count} 个任务"
        if skipped_count > 0:
            display_output += f" [yellow](忽略 {skipped_count} 个)[/]"

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            summary=f"创建计划：{todo.total_count} 个任务" + (f"，忽略 {skipped_count} 个" if skipped_count else ""),
            display_output=display_output,
        )
    def is_read_only(self) -> bool:
        return False

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        items = parameters.get("items")
        if not items:
            return "缺少 items 参数"
        if not isinstance(items, list):
            return "items 必须是数组"
        return None

    def get_security_context(self) -> Dict[str, Any]:
        return {"is_sensitive": False, "paths": [], "command_preview": ""}


class TodoUpdateTool(Tool):
    """更新任务状态"""
    name = "TodoUpdate"
    description = (
        "更新任务状态。模型执行任务时使用此工具标记进度。\n"
        "状态值：pending（待处理）→ in_progress（进行中）→ completed（已完成）/ failed（失败）\n"
        "\n"
        "⚠ 状态转换规则（强制约束）：\n"
        "- pending → in_progress：开始执行任务时调用\n"
        "- in_progress → completed：完成实际工作后调用\n"
        "- in_progress → failed：任务失败时调用\n"
        "\n"
        "✗ 禁止的转换：\n"
        "- pending → completed：必须先标记 in_progress，执行实际工作后再标记 completed\n"
        "- pending → failed：必须先标记 in_progress\n"
        "- completed/failed → 任意状态：已结束的任务不可变更\n"
        "\n"
        "正确示例：TodoUpdate(id=\"t1\", status=\"in_progress\") → 执行工作 → TodoUpdate(id=\"t1\", status=\"completed\")"
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "任务ID，如 t1、t2",
                },
                "status": {
                    "type": "string",
                    "description": "新状态：pending / in_progress / completed / failed",
                    "enum": ["pending", "in_progress", "completed", "failed"],
                },
            },
            "required": ["id", "status"],
            "errorMessage": {
                "id": "必须提供 id（任务ID），如 id=\"t1\"",
                "status": "必须提供 status（新状态），可选值：pending / in_progress / completed / failed"
            },
        }

    def execute(self, parameters: Dict[str, Any], interrupt_check: Callable[[], bool] = None) -> ToolResult:
        item_id = parameters.get("id", "")
        status = parameters.get("status", "")

        todo = get_todo_list()

        if not todo.items:
            return ToolResult(
                success=False,
                output="",
                error="当前没有任务计划，请先使用 TodoCreate 创建",
            )

        # 查找任务
        item = todo.get_item(item_id)
        if item is None:
            return ToolResult(
                success=False,
                output="",
                error=f"未找到任务 {item_id}，当前任务ID: {', '.join(i.id for i in todo.items)}",
            )

        # 记录旧状态
        old_status = item.status

        # 更新状态（带状态机验证）
        success, error_msg = todo.update_status(item_id, status)
        if not success:
            return ToolResult(
                success=False,
                output="",
                error=error_msg,
            )

        # 构建输出
        output = f"任务 {item_id} [{item.content}] 状态: {old_status} → {status}"
        progress = f"进度: {todo.progress_text}"

        return ToolResult(
            success=True,
            output=f"{output}\n{progress}",
            summary=f"{item_id}: {old_status} → {status}",
            display_output=f"  {item.icon} {item_id}  {item.content}  [dim]{old_status} →[/] [{status}]",
        )

    def is_read_only(self) -> bool:
        return False

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        if not parameters.get("id"):
            return "缺少 id 参数"
        if not parameters.get("status"):
            return "缺少 status 参数"
        return None

    def get_security_context(self) -> Dict[str, Any]:
        return {"is_sensitive": False, "paths": [], "command_preview": ""}


class TodoListTool(Tool):
    """查看当前任务计划"""
    name = "TodoList"
    description = (
        "查看当前任务计划及进度。返回所有任务的状态概览。\n"
        "当需要了解当前执行进度或确认任务列表时使用。"
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    def execute(self, parameters: Dict[str, Any], interrupt_check: Callable[[], bool] = None) -> ToolResult:
        todo = get_todo_list()

        if not todo.items:
            return ToolResult(
                success=True,
                output="当前没有任务计划",
                summary="无任务",
                display_output="[dim]当前没有任务计划[/]",
            )

        # 构建输出
        output_lines = [
            f"执行计划 [{todo.progress_text}]",
            "",
        ]
        for item in todo.items:
            output_lines.append(f"  {item.icon} {item.id}  {item.content}  [{item.status}]")

        output_lines.append("")
        output_lines.append(f"✓{todo.completed_count}  ✗{todo.failed_count}  ○{todo.pending_count}")

        return ToolResult(
            success=True,
            output="\n".join(output_lines),
            summary=f"计划进度: {todo.progress_text}",
            display_output=f"[bold]● 执行计划[/] [{todo.progress_text}]",
        )

    def is_read_only(self) -> bool:
        return True

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        return None

    def get_security_context(self) -> Dict[str, Any]:
        return {"is_sensitive": False, "paths": [], "command_preview": ""}
