"""Bash 工具 - 执行 shell 命令（支持流式输出 + 可中断 + 沙箱安全）"""
import os
import re
import subprocess
import threading
import queue
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
from ..base import Tool, ToolResult
from ..command_safety import CommandSafetyChecker
from claude_code.ui.progress_display import BashStreamingDisplay


class BashTool(Tool):
    """Shell 命令执行工具（沙箱模式）"""
    name = "Bash"
    description = (
        "执行 shell 命令。"
        "⚠️ 不支持交互式命令（如 python -i、vim 等），会卡住直到超时。"
        "输出限制：默认 3000 字符，测试/构建类命令自动提升至 10000。"
        "沙箱：工作目录限制在操作根目录内，禁止访问系统关键路径，命令执行前自动安全扫描。"
    )

    # 输出限制
    DEFAULT_MAX_OUTPUT_LENGTH = 3000
    MAX_EXECUTION_TIME = 120  # 秒

    # 动态输出限制：根据命令类型调整
    OUTPUT_LIMITS = {
        "verbose": 10000,   # 测试/构建/安装类命令（输出信息量大）
        "normal": 5000,     # 默认
    }

    # 匹配 verbose 类命令的关键词
    VERBOSE_COMMANDS = (
        "pytest", "python -m pytest", "pip install", "pip list",
        "npm install", "npm test", "cargo build", "cargo test",
        "go test", "go build", "mvn", "gradle",
        "dotnet build", "dotnet test",
    )

    # 安全检查器（独立模块）
    _safety_checker = CommandSafetyChecker()

    # 沙箱配置
    SANDBOX_ENABLED = True
    # 禁止访问的系统路径（Windows）
    SANDBOX_BLOCKED_PATHS = [
        r"C:\Windows",
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        r"C:\ProgramData",
    ]


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
                "max_output_length": {
                    "type": "integer",
                    "description": "最大输出字符数，默认 3000（测试/构建命令自动 10000）",
                    "default": 0
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录（默认使用操作根目录）",
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
                # 附加 PowerShell 转换建议
                ps_suggestion = self._safety_checker.get_powershell_suggestion(command)
                error_msg = unix_error
                if ps_suggestion:
                    error_msg = f"{unix_error}\n\n{ps_suggestion}"
                return ToolResult(success=False, output="", error=error_msg)

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

    def _get_output_limit(self, command: str, explicit_limit: int = 0) -> int:
        """根据命令类型动态确定输出限制

        Args:
            command: 要执行的命令
            explicit_limit: 用户显式指定的限制（0 表示自动）

        Returns:
            输出字符上限
        """
        if explicit_limit and explicit_limit > 0:
            return explicit_limit
        cmd_lower = command.lower().strip()
        for verbose_cmd in self.VERBOSE_COMMANDS:
            if verbose_cmd in cmd_lower:
                return self.OUTPUT_LIMITS["verbose"]
        return self.OUTPUT_LIMITS["normal"]

    def _build_final_output(
        self,
        stdout_lines: List[str],
        stderr_lines: List[str],
        success: bool,
        return_code: int = 0,
        max_output_length: int = None
    ) -> str:
        """
        构建最终输出（含截断 + 结构化标签）

        成功时：stdout + stderr（如有），标记 [exit=0]
        失败时：[exit=N] + [STDERR] + [STDOUT]，错误信息优先展示
        """
        max_len = max_output_length or self.DEFAULT_MAX_OUTPUT_LENGTH

        if success:
            output = '\n'.join(stdout_lines)
            if stderr_lines:
                stderr_text = '\n'.join(stderr_lines)
                output += f'\n[STDERR]\n{stderr_text}'
        else:
            # 失败：exit code + 结构化标签，stderr 优先
            parts = [f"[exit={return_code}]"]
            if stderr_lines:
                stderr_text = '\n'.join(stderr_lines)
                parts.append(f"[STDERR]\n{stderr_text}")
            if stdout_lines:
                stdout_text = '\n'.join(stdout_lines)
                parts.append(f"[STDOUT]\n{stdout_text}")
            if not stderr_lines and not stdout_lines:
                parts.append(f"(命令执行失败，无输出)")
            output = '\n'.join(parts)

        # 截断处理：优先保留错误信息
        if len(output) > max_len:
            if not success and stderr_lines:
                stderr_text = '\n'.join(stderr_lines)
                if len(stderr_text) > max_len:
                    output = stderr_text[:max_len] + f"\n... (STDERR 已截断，共 {len(stderr_text)} 字符)"
                else:
                    stdout_text = '\n'.join(stdout_lines) if stdout_lines else ""
                    remaining = max_len - len(stderr_text) - 10
                    if stdout_text and remaining > 0:
                        output = stderr_text + f'\n[STDOUT]\n{stdout_text[:remaining]}' + f"\n... (STDOUT 已截断)"
                    else:
                        output = stderr_text
            else:
                output = output[:max_len] + f"\n... (输出过长，已截断，共 {len(output)} 字符)"

        return output

    def _check_sandbox(self, command: str, work_dir: Path) -> Optional[ToolResult]:
        """沙箱安全检查：限制工作目录和禁止访问系统路径"""
        if not self.SANDBOX_ENABLED:
            return None

        # 1. 检查 cwd 是否为绝对路径且在允许范围内
        if work_dir.is_absolute():
            # 解析真实路径（处理 .. 和符号链接）
            try:
                real_cwd = work_dir.resolve()
            except Exception:
                return ToolResult(
                    success=False, output="",
                    error=f"沙箱安全限制：无法解析工作目录 {work_dir}"
                )

            # 2. 检查是否命中黑名单路径
            cwd_str = str(real_cwd).lower()
            for blocked in self.SANDBOX_BLOCKED_PATHS:
                if cwd_str.startswith(blocked.lower()):
                    return ToolResult(
                        success=False, output="",
                        error=f"沙箱安全限制：禁止在系统路径 {blocked} 下执行命令"
                    )

        # 3. 检查命令中是否包含绝对路径逃逸尝试
        # 匹配 Windows 绝对路径如 C:\, D:\ 等
        abs_path_pattern = re.compile(r'[A-Z]:\\', re.IGNORECASE)
        for match in abs_path_pattern.finditer(command):
            path_candidate = command[max(0, match.start()-2):match.end()+50]
            # 简单判断：如果命令中包含非 cwd 的绝对路径，警告
            try:
                cmd_path = Path(path_candidate.split()[0].strip('"'))
                if cmd_path.is_absolute():
                    real_cmd_path = cmd_path.resolve()
                    # 检查是否在黑名单中
                    cmd_path_str = str(real_cmd_path).lower()
                    for blocked in self.SANDBOX_BLOCKED_PATHS:
                        if cmd_path_str.startswith(blocked.lower()):
                            return ToolResult(
                                success=False, output="",
                                error=f"沙箱安全限制：命令尝试访问系统路径 {blocked}"
                            )
            except (ValueError, OSError):
                pass  # 路径解析失败，跳过

        return None

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
        max_output = int(parameters.get("max_output_length", 0))

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

        # 沙箱安全检查（工作目录限制、系统路径黑名单）
        sandbox_result = self._check_sandbox(command, work_dir)
        if sandbox_result:
            return sandbox_result

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
            output = self._build_final_output(
                stdout_lines, stderr_lines, success,
                return_code=return_code,
                max_output_length=self._get_output_limit(command, max_output)
            )

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
                # 构建增强错误信息：附加 exit code + 常见原因提示
                error_msg = output if output else f"命令返回非零退出码: {return_code}"
                hint = self._get_exit_code_hint(return_code, command)
                if hint:
                    error_msg = f"{error_msg}\n\n诊断: 退出码 {return_code} — {hint}"
                return ToolResult(
                    success=False,
                    output="",
                    error=error_msg,
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

    @staticmethod
    def _get_exit_code_hint(return_code: int, command: str) -> str:
        """根据退出码和命令给出常见原因提示"""
        hints = {
            1: "一般性错误，检查命令语法和参数",
            2: "命令用法错误，检查参数格式",
            126: "权限不足，无法执行该命令",
            127: "命令未找到，检查命令名是否正确或是否已安装",
            128: "退出参数无效",
            130: "命令被 Ctrl+C 中断",
        }
        hint = hints.get(return_code, "")
        # 特殊场景补充
        if not hint:
            if return_code > 128:
                signal_num = return_code - 128
                hint = f"被信号 {signal_num} 终止"
            elif 'pip' in command and return_code == 1:
                hint = "pip 安装失败，检查包名、网络连接或 Python 版本兼容性"
            elif 'pytest' in command and return_code == 1:
                hint = "测试失败，查看输出中的 FAILED 用例"
            elif 'git' in command and return_code == 1:
                hint = "git 操作失败，检查仓库状态、分支名或远程配置"
        return hint

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