"""会话自动保存与恢复 - 防止崩溃丢失

核心设计：
1. 每 N 轮对话自动保存当前会话状态到 autosave.json
2. 启动时检测是否存在未恢复的自动保存，提示用户恢复
3. 正常退出时清除自动保存（避免误提示恢复已完成的会话）
4. 恢复后自动清除标记
"""
import os
import json
from typing import Dict, Any, Optional
from datetime import datetime

# 自动保存间隔（对话轮数）
AUTOSAVE_INTERVAL = 20

# 自动保存文件路径
AUTOSAVE_DIR = "data/sessions"
AUTOSAVE_FILENAME = "autosave.json"


def get_autosave_path() -> str:
    """获取自动保存文件路径"""
    os.makedirs(AUTOSAVE_DIR, exist_ok=True)
    return os.path.join(AUTOSAVE_DIR, AUTOSAVE_FILENAME)


def has_autosave() -> bool:
    """检查是否存在未恢复的自动保存"""
    path = get_autosave_path()
    if not os.path.exists(path):
        return False
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 检查是否有有效数据
        return bool(data.get("messages")) or bool(data.get("todos"))
    except (json.JSONDecodeError, IOError):
        return False


def get_autosave_info() -> Optional[Dict[str, Any]]:
    """获取自动保存的摘要信息（用于提示用户）"""
    path = get_autosave_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            "time": data.get("time", "未知时间"),
            "model": data.get("model", "未知模型"),
            "message_count": len(data.get("messages", [])),
            "plan_mode": data.get("plan_mode", False),
            "todo_count": len(data.get("todos", [])),
            "todo_progress": data.get("todo_progress", ""),
            "active_path": data.get("active_path", ""),
        }
    except (json.JSONDecodeError, IOError):
        return None


def save_autosave(
    messages: list,
    model_id: str = "",
    style_id: str = "",
    active_path: str = "",
    plan_mode: bool = False,
    plan_task: str = "",
    todos: list = None,
) -> bool:
    """保存会话状态到自动保存文件

    Args:
        messages: 对话消息列表
        model_id: 当前模型 ID
        style_id: 当前风格 ID
        active_path: 当前操作根目录
        plan_mode: 是否处于计划模式
        plan_task: 计划模式任务描述
        todos: Todo 列表数据

    Returns:
        是否保存成功
    """
    path = get_autosave_path()
    try:
        data = {
            "version": 1,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "messages": messages,
            "model": model_id,
            "style_id": style_id,
            "active_path": active_path,
            "plan_mode": plan_mode,
            "plan_task": plan_task,
            "todos": todos or [],
            "todo_progress": "",
        }

        # 计算 todo 进度
        if todos:
            done = sum(1 for t in todos if t.get("status") in ("completed", "failed"))
            data["todo_progress"] = f"{done}/{len(todos)}"

        # 防 surrogate 字符：先 dumps 再 encode/decode 替换非法码点
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        json_str = json_str.encode('utf-8', errors='replace').decode('utf-8')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(json_str)
        return True
    except (IOError, OSError, UnicodeEncodeError, UnicodeDecodeError, ValueError):
        return False


def load_autosave() -> Optional[Dict[str, Any]]:
    """加载自动保存数据

    Returns:
        保存的数据字典，或 None
    """
    path = get_autosave_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, IOError):
        return None


def clear_autosave() -> bool:
    """清除自动保存文件（正常退出时调用）"""
    path = get_autosave_path()
    try:
        if os.path.exists(path):
            os.remove(path)
        return True
    except OSError:
        return False


class AutosaveManager:
    """自动保存管理器（面向对象封装，供 app.py 使用）"""

    def __init__(self):
        self._interval = AUTOSAVE_INTERVAL

    def save(self, data: dict) -> bool:
        """保存会话快照"""
        messages = data.get("messages", [])
        todos = data.get("todos", [])
        return save_autosave(
            messages=messages,
            model_id=data.get("model", ""),
            style_id=data.get("style_id", ""),
            active_path=data.get("active_path", ""),
            plan_mode=data.get("plan_mode", False),
            plan_task=data.get("plan_task", ""),
            todos=todos,
        )

    def load(self) -> Optional[Dict[str, Any]]:
        """加载自动保存数据"""
        return load_autosave()

    def has_data(self) -> bool:
        """是否存在未恢复的自动保存"""
        return has_autosave()

    def get_info(self) -> Optional[Dict[str, Any]]:
        """获取自动保存摘要信息"""
        return get_autosave_info()

    def clear(self) -> bool:
        """清除自动保存文件"""
        return clear_autosave()
