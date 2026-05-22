"""Todo 工具 - 计划模式的任务管理工具"""
from typing import Any, Dict, List, Optional, Callable

from ..base import Tool, ToolResult
from ..context import tool_context
from claude_code.core.todo import TodoList, TodoItem
from claude_code.config.defaults import PLAN


def get_todo_list() -> TodoList:
    """获取全局 TodoList 实例（通过 ToolContext 统一管理）"""
    return tool_context.todo_list


def reset_todo_list() -> None:
    """重置全局 TodoList（新会话时调用）"""
    tool_context.todo_list = TodoList()


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
                    "description": "任务列表，每项包含 content 和可选的 priority、depends_on",
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
                            "depends_on": {
                                "type": "array",
                                "description": "依赖的任务ID列表（如 [\"t1\", \"t2\"]），被依赖的任务必须先完成才能开始此任务",
                                "items": {"type": "string"},
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
        todo = TodoList.create_from_dicts(items_data)

        # 替换全局实例（通过 ToolContext）
        tool_context.todo_list = todo

        # 构建输出
        input_count = len(items_data)
        skipped_count = max(0, input_count - todo.total_count)
        output_lines = [f"已创建 {todo.total_count} 个任务："]
        if skipped_count > 0:
            output_lines.append(
                f"⚠ 另有 {skipped_count} 个任务因超过上限或内容为空被忽略（上限 {PLAN.MAX_ITEMS} 个）"
            )
        for item in todo.items:
            dep_str = f" ← {', '.join(item.depends_on)}" if item.depends_on else ""
            output_lines.append(f"  {item.icon} {item.id}  {item.content}  [{item.priority}]{dep_str}")

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
    """更新任务状态（支持批量）"""
    name = "TodoUpdate"
    description = (
        "更新任务状态。模型执行任务时使用此工具标记进度。\n"
        "支持两种模式：\n"
        "- 单任务模式：id + status，一次更新一个任务\n"
        "- 批量模式：updates 数组，一次更新多个任务（推荐用于并行推进，减少调用次数）\n"
        "状态值：pending（待处理）→ in_progress（进行中）→ completed（已完成）/ failed（失败）\n"
        "\n"
        "⚠ 状态转换规则（强制约束）：\n"
        "- pending → in_progress：开始执行任务时调用\n"
        "- in_progress → completed：完成实际工作后调用\n"
        "- in_progress → failed：任务失败时调用\n"
        "- in_progress → pending：任务暂无法推进，暂停并释放进行中名额\n"
        "\n"
        "✗ 禁止的转换：\n"
        "- pending → completed：必须先标记 in_progress，执行实际工作后再标记 completed\n"
        "- pending → failed：必须先标记 in_progress\n"
        "- completed/failed → 任意状态：已结束的任务不可变更\n"
        "\n"
        "正确示例（批量）：TodoUpdate(updates=[{\"id\":\"t1\",\"status\":\"in_progress\"},{\"id\":\"t2\",\"status\":\"in_progress\"}])\n"
        "正确示例（单任务）：TodoUpdate(id=\"t1\", status=\"completed\")"
    )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "任务ID，如 t1、t2（单任务模式，与 updates 互斥）",
                },
                "status": {
                    "type": "string",
                    "description": "新状态：pending / in_progress / completed / failed（单任务模式）",
                    "enum": ["pending", "in_progress", "completed", "failed"],
                },
                "notes": {
                    "type": "string",
                    "description": "执行备注或完成说明（可选）",
                },
                "evidence": {
                    "type": "string",
                    "description": "完成证据摘要（可选）",
                },
                "files": {
                    "type": "array",
                    "description": "相关文件路径列表（可选）",
                    "items": {"type": "string"},
                },
                "tests": {
                    "type": "array",
                    "description": "相关测试或验证命令列表（可选）",
                    "items": {"type": "string"},
                },
                "error": {
                    "type": "string",
                    "description": "失败原因或阻塞信息（可选）",
                },
                "updates": {
                    "type": "array",
                    "description": "批量更新列表（批量模式，与 id/status 互斥）。每项包含 id 和 status",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "任务ID，如 t1",
                            },
                            "status": {
                                "type": "string",
                                "description": "新状态：pending / in_progress / completed / failed",
                                "enum": ["pending", "in_progress", "completed", "failed"],
                            },
                            "notes": {
                                "type": "string",
                                "description": "执行备注或完成说明（可选）",
                            },
                            "evidence": {
                                "type": "string",
                                "description": "完成证据摘要（可选）",
                            },
                            "files": {
                                "type": "array",
                                "description": "相关文件路径列表（可选）",
                                "items": {"type": "string"},
                            },
                            "tests": {
                                "type": "array",
                                "description": "相关测试或验证命令列表（可选）",
                                "items": {"type": "string"},
                            },
                            "error": {
                                "type": "string",
                                "description": "失败原因或阻塞信息（可选）",
                            },
                        },
                        "required": ["id", "status"],
                    },
                },
            },
            "errorMessage": {
                "id": "单任务模式：必须提供 id（任务ID），如 id=\"t1\"",
                "status": "单任务模式：必须提供 status（新状态），可选值：pending / in_progress / completed / failed",
                "updates": "批量模式：必须提供 updates 数组，如 updates=[{\"id\":\"t1\",\"status\":\"completed\"}]",
            },
        }

    def execute(self, parameters: Dict[str, Any], interrupt_check: Callable[[], bool] = None) -> ToolResult:
        updates = parameters.get("updates")
        item_id = parameters.get("id", "")
        status = parameters.get("status", "")

        # 批量模式
        if updates and isinstance(updates, list):
            return self._execute_batch(updates)

        # 单任务模式
        return self._execute_single(
            item_id,
            status,
            notes=parameters.get("notes", ""),
            evidence=parameters.get("evidence", ""),
            files=parameters.get("files"),
            tests=parameters.get("tests"),
            error=parameters.get("error", ""),
        )

    def _execute_single(
        self,
        item_id: str,
        status: str,
        notes: str = "",
        evidence: str = "",
        files: Optional[List[str]] = None,
        tests: Optional[List[str]] = None,
        error: str = "",
    ) -> ToolResult:
        """单任务更新（向后兼容）"""
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

        # 记录执行证据/备注
        evidence_updated = any([notes, evidence, files is not None, tests is not None, error])
        if evidence_updated:
            todo.apply_evidence(
                item_id,
                notes=notes,
                evidence=evidence,
                files=files,
                tests=tests,
                error=error,
            )

        # 构建输出
        output = f"任务 {item_id} [{item.content}] 状态: {old_status} → {status}"
        if evidence_updated:
            output += "\n已记录执行证据/备注"
        progress = f"进度: {todo.progress_text}"

        # 如果是刚完成的任务，在 metadata 中记录以便 UI 闪烁
        metadata = {}
        if status == "completed":
            metadata["flash_id"] = item_id

        return ToolResult(
            success=True,
            output=f"{output}\n{progress}",
            summary=f"{item_id}: {old_status} → {status}",
            display_output=f"  {item.icon} {item_id}  {item.content}  [dim]{old_status} →[/] [{status}]",
            metadata=metadata,
        )

    def _execute_batch(self, updates: List[Dict[str, Any]]) -> ToolResult:
        """批量更新多个任务状态"""
        todo = get_todo_list()

        if not todo.items:
            return ToolResult(
                success=False,
                output="",
                error="当前没有任务计划，请先使用 TodoCreate 创建",
            )

        results = []
        success_count = 0
        fail_count = 0
        flash_ids = []

        for update in updates:
            uid = update.get("id", "")
            ustatus = update.get("status", "")
            
            item = todo.get_item(uid)
            if item is None:
                results.append(f"  ✗ {uid}: 未找到")
                fail_count += 1
                continue

            old_status = item.status
            success, error_msg = todo.update_status(uid, ustatus)
            if not success:
                results.append(f"  ✗ {uid} [{item.content}]: {error_msg}")
                fail_count += 1
            else:
                todo.apply_evidence(
                    uid,
                    notes=update.get("notes", ""),
                    evidence=update.get("evidence", ""),
                    files=update.get("files"),
                    tests=update.get("tests"),
                    error=update.get("error", ""),
                )
                evidence_note = " +证据" if any([
                    update.get("notes"),
                    update.get("evidence"),
                    update.get("files") is not None,
                    update.get("tests") is not None,
                    update.get("error"),
                ]) else ""
                results.append(f"  {item.icon} {uid} [{item.content}]: {old_status} → {ustatus}{evidence_note}")
                success_count += 1
                if ustatus == "completed":
                    flash_ids.append(uid)

        # 判断批量更新结果状态
        if fail_count == 0:
            batch_success = True
            status_label = "全部成功"
        elif success_count > 0:
            batch_success = True  # 部分成功也算成功（已生效的不可回滚）
            status_label = "部分成功"
        else:
            batch_success = False
            status_label = "全部失败"

        output_lines = [f"批量更新{status_label}: ✓{success_count}  ✗{fail_count}"]
        output_lines.extend(results)
        output_lines.append(f"进度: {todo.progress_text}")

        metadata = {}
        if flash_ids:
            metadata["flash_ids"] = flash_ids

        return ToolResult(
            success=batch_success,
            output="\n".join(output_lines),
            summary=f"批量更新{status_label}: ✓{success_count} ✗{fail_count} | 进度 {todo.progress_text}",
            display_output=f"[bold]● 批量更新[/] {status_label} ✓{success_count} ✗{fail_count} | {todo.progress_text}",
            metadata=metadata,
        )

    def is_read_only(self) -> bool:
        return False

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        updates = parameters.get("updates")
        # 批量模式
        if updates:
            if not isinstance(updates, list):
                return "updates 必须是数组"
            for i, update in enumerate(updates):
                if not update.get("id"):
                    return f"updates[{i}] 缺少 id"
                if not update.get("status"):
                    return f"updates[{i}] 缺少 status"
            return None
        # 单任务模式
        if not parameters.get("id"):
            return "缺少 id 参数（单任务模式）或 updates 参数（批量模式）"
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
