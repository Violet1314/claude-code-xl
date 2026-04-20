"""Bash 工具 - 执行 shell 命令（支持流式输出 + 可中断）"""
import os
import subprocess
import threading
import queue
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
from ..base import Tool, ToolResult
from ..command_safety import CommandSafetyChecker
from claude_code.ui.progress_display import BashStreamingDisplay


class BashTool(Tool):
    """Shell 命令执行工具"""
    name = "Bash"
    description = (
        "执行 shell 命令。"
        "当前环境：Windows PowerShell。"
        "注意：必须使用 PowerShell 语法，不支持 Unix 参数如 -p、-r。"
        "正确示例：mkdir data, output（逗号分隔）| Get-ChildItem（或简写 ls）| Remove-Item -Recurse -Force | Copy-Item -Recurse"
        "错误示例：mkdir -p data output | ls -la | rm -rf | cp -r"
        "⚠️ 不支持交互式命令：不要执行需要用户输入的命令（如 python script.py 等待 input()），这类命令会卡住直到超时。"
        "所有命令都需要用户确认。"
    )

    # 输出限制
    MAX_OUTPUT_LENGTH = 5000
    MAX_EXECUTION_TIME = 120  # 秒

    # 安全检查器（独立模块）
    _safety_checker = CommandSafetyChecker()


    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令",
                    "example": "Get-ChildItem"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒），默认 120",
                    "default": 120
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录（必须使用绝对路径，默认使用操作根目录）",
                    "default": "."
                }
            },
            "required": ["command"],
            "errorMessage": {
                "command": "必须提供 command（要执行的 shell 命令），如 command=\"Get-ChildItem\""
            }
        }

    def _run_pre_checks(self, command: str) -> Optional[ToolResult]:
        """
        执行前置检查，返回拦截结果或 None（通过）
        """
        # 1. 危险命令
        is_dangerous, reason = self._safety_checker.check_dangerous(command)
        if is_dangerous:
            return ToolResult(success=False, output="", error=f"危险命令已拦截: {reason}")

        # 2. 交互式命令
        is_interactive, reason = self._safety_checker.check_interactive(command)
        if is_interactive:
            return ToolResult(success=False, output="", error=f"交互式命令已拦截: {reason}")

        # 3. Unix 语法检查 (Windows)
        if os.name == 'nt':
            unix_error = self._safety_checker.check_unix_syntax(command)
            if unix_error:
                return ToolResult(success=False, output="", error=unix_error)

        return None  # 通过

    def _decode_line(self, line: bytes, is_windows: bool) -> str:
        """解码单行输出"""
        if is_windows:
            # Windows: UTF-8 优先，GBK 兜底
            try:
                return line.decode('utf-8').rstrip('\r\n')
            except UnicodeDecodeError:
                return line.decode('gbk', errors='replace').rstrip('\r\n')
        else:
            return line.decode('utf-8', errors='replace').rstrip('\n')

    def _run_subprocess(
        self,
        command: str,
        work_dir: Path,
        timeout: int,
        progress: BashStreamingDisplay,
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> Tuple[int, List[str], List[str], Optional[str]]:
        """
        执行 subprocess 并收集输出（线程读取，支持中断）

        Returns:
            (return_code, stdout_lines, stderr_lines, error_message)
        """
        is_windows = os.name == 'nt'

        if is_windows:
            win_command = command.replace(' &&', ';')
            ps_command = f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {win_command}"
            process = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(work_dir)
            )
        else:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(work_dir)
            )

        stdout_lines = []
        stderr_lines = []

        # 使用线程异步读取输出，避免 readline() 阻塞导致无法响应中断
        stdout_queue = queue.Queue()
        stderr_queue = queue.Queue()

        def _read_stream(stream, q, is_stderr=False):
            """线程函数：持续读取流并放入队列"""
            try:
                for line in stream:
                    q.put((line, is_stderr))
                q.put(None)  # 结束标记
            except Exception:
                q.put(None)

        # 启动读取线程
        stdout_thread = threading.Thread(
            target=_read_stream, args=(process.stdout, stdout_queue, False),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=_read_stream, args=(process.stderr, stderr_queue, True),
            daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()

        try:
            while True:
                # 优先检查中断（CTRL+C）- 这是修复的关键
                if interrupt_check and interrupt_check():
                    process.kill()
                    stdout_thread.join(timeout=0.5)
                    stderr_thread.join(timeout=0.5)
                    progress.set_error("用户中断执行")
                    progress.stop(False, -1)
                    return -1, [], [], "用户中断执行"

                # 检查超时
                if progress.is_timeout():
                    process.kill()
                    stdout_thread.join(timeout=0.5)
                    stderr_thread.join(timeout=0.5)
                    progress.set_error(f"命令执行超时（{timeout}秒）")
                    progress.stop(False, -1)
                    return -1, [], [], f"命令执行超时（{timeout}秒）"

                # 从队列获取输出（非阻塞，timeout=0.1秒）
                try:
                    item = stdout_queue.get(timeout=0.1)
                    if item is None:
                        # stdout 流结束
                        pass
                    else:
                        line, is_stderr = item
                        decoded = self._decode_line(line, is_windows)
                        if decoded:
                            stdout_lines.append(decoded)
                            progress.feed_output(decoded)
                except queue.Empty:
                    pass

                try:
                    item = stderr_queue.get(timeout=0.1)
                    if item is None:
                        # stderr 流结束
                        pass
                    else:
                        line, is_stderr = item
                        decoded = self._decode_line(line, is_windows)
                        if decoded:
                            stderr_lines.append(decoded)
                            progress.feed_output(f"[stderr] {decoded}")
                except queue.Empty:
                    pass

                # 检查进程是否结束且队列是否清空
                if process.poll() is not None:
                    # 等待线程结束，确保所有输出被收集
                    stdout_thread.join(timeout=1.0)
                    stderr_thread.join(timeout=1.0)

                    # 收集队列剩余数据
                    while not stdout_queue.empty():
                        try:
                            item = stdout_queue.get_nowait()
                            if item is not None:
                                line, _ = item
                                decoded = self._decode_line(line, is_windows)
                                if decoded:
                                    stdout_lines.append(decoded)
                        except queue.Empty:
                            break

                    while not stderr_queue.empty():
                        try:
                            item = stderr_queue.get_nowait()
                            if item is not None:
                                line, _ = item
                                decoded = self._decode_line(line, is_windows)
                                if decoded:
                                    stderr_lines.append(decoded)
                        except queue.Empty:
                            break

                    break

        except Exception as e:
            process.kill()
            stdout_thread.join(timeout=0.5)
            stderr_thread.join(timeout=0.5)
            error_msg = f"读取输出失败: {str(e)}"
            progress.set_error(error_msg)
            progress.stop(False, -1)
            return -1, [], [], error_msg

        return_code = process.wait()
        return return_code, stdout_lines, stderr_lines, None

    def _build_final_output(
        self,
        stdout_lines: List[str],
        stderr_lines: List[str],
        success: bool
    ) -> str:
        """
        构建最终输出（含截断）
        """
        # 成功：stdout + stderr（如有）
        # 失败：stderr + stdout（如有）
        if success:
            output = '\n'.join(stdout_lines)
            if stderr_lines:
                output += '\n[stderr]\n' + '\n'.join(stderr_lines)
        else:
            if stderr_lines:
                output = '[stderr]\n' + '\n'.join(stderr_lines)
                if stdout_lines:
                    output += '\n[stdout]\n' + '\n'.join(stdout_lines)
            else:
                output = '\n'.join(stdout_lines) if stdout_lines else "(命令执行失败，无输出)"

        # 截断处理：优先保留错误信息
        if len(output) > self.MAX_OUTPUT_LENGTH:
            if not success and stderr_lines:
                stderr_text = '\n'.join(stderr_lines)
                if len(stderr_text) > self.MAX_OUTPUT_LENGTH:
                    output = stderr_text[:self.MAX_OUTPUT_LENGTH] + f"\n... (stderr 已截断，共 {len(stderr_text)} 字符)"
                else:
                    stdout_text = '\n'.join(stdout_lines) if stdout_lines else ""
                    remaining = self.MAX_OUTPUT_LENGTH - len(stderr_text) - 10
                    if stdout_text and remaining > 0:
                        output = stderr_text + '\n[stdout]\n' + stdout_text[:remaining] + f"\n... (stdout 已截断)"
                    else:
                        output = stderr_text
            else:
                output = output[:self.MAX_OUTPUT_LENGTH] + f"\n... (输出过长，已截断，共 {len(output)} 字符)"

        return output

    def execute(
        self,
        parameters: Dict[str, Any],
        interrupt_check: Optional[Callable[[], bool]] = None
    ) -> ToolResult:
        """执行命令"""
        # 参数验证（与 Read/Edit 工具一致）
        validation_error = self.validate_parameters(parameters)
        if validation_error:
            return ToolResult(success=False, output="", error=validation_error)

        command = parameters.get("command", "").strip()
        timeout = min(int(parameters.get("timeout", 120)), self.MAX_EXECUTION_TIME)

        # 使用 PathManager 统一路径解析
        from claude_code.core.path_manager import get_path_manager
        pm = get_path_manager()
        user_cwd = parameters.get("cwd", ".")
        work_dir_str, _ = pm.resolve_safe(user_cwd)
        work_dir = Path(work_dir_str)
        work_dir.mkdir(parents=True, exist_ok=True)

        # 前置检查（危险命令、交互式命令、Unix 语法）
        pre_check_result = self._run_pre_checks(command)
        if pre_check_result:
            return pre_check_result

        # 检查工作目录
        if not work_dir.exists():
            return ToolResult(success=False, output="", error=f"工作目录不存在: {work_dir}")

        try:
            progress = BashStreamingDisplay(command, timeout)
            progress.start()

            return_code, stdout_lines, stderr_lines, exec_error = self._run_subprocess(
                command, work_dir, timeout, progress, interrupt_check
            )
            if exec_error:
                # 区分用户中断和其他错误
                is_interrupted = exec_error == "用户中断执行"
                return ToolResult(
                    success=False,
                    output="",
                    error=exec_error,
                    interrupted=is_interrupted
                )

            success = return_code == 0
            output = self._build_final_output(stdout_lines, stderr_lines, success)

            progress.stop(success, return_code)

            if success:
                return ToolResult(
                    success=True,
                    output=output if output else "(命令执行完成，无输出)",
                    metadata={
                        "command": command,
                        "return_code": return_code,
                        "cwd": str(work_dir),
                        "timeout": timeout
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=output if output else f"命令返回非零退出码: {return_code}",
                    metadata={
                        "command": command,
                        "return_code": return_code,
                        "cwd": str(work_dir),
                        "timeout": timeout
                    }
                )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="", error=f"命令执行超时（{timeout}秒）")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"执行失败: {str(e)}")

    def is_sensitive(self, command: str) -> bool:
        """检查命令是否敏感"""
        return self._safety_checker.is_sensitive(command)

    def needs_path_scope_check(self, command: str) -> bool:
        """检查命令是否需要路径范围验证"""
        return self._safety_checker.needs_path_scope_check(command)

    def check_path_scope(self, command: str, project_dir: Path) -> Dict[str, Any]:
        """检查命令中的路径是否在项目目录范围内"""
        return self._safety_checker.check_path_scope(command, project_dir)

    def is_read_only(self) -> bool:
        """Bash 不是只读操作"""
        return False

    def validate_parameters(self, parameters: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        command = parameters.get("command")
        if not command:
            return "缺少 command 参数"
        try:
            timeout = int(parameters.get("timeout", 120))
        except (ValueError, TypeError):
            timeout = 120
        if timeout < 1 or timeout > 600:
            return "timeout 必须在 1-600 秒之间"
        return None

    def get_security_context(self) -> Dict[str, Any]:
        """返回 Bash 工具的安全上下文"""
        command = self.parameters.get("command", "")
        return {
            "is_sensitive": self.is_sensitive(command),
            "paths": [],  # Bash 路径检查由 permission.py 单独处理
            "command_preview": command[:50] + "..." if len(command) > 50 else command
        }