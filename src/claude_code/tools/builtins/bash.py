"""Bash 工具 - 执行 shell 命令（支持流式输出）"""
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from ..base import Tool, ToolResult
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

    # 危险命令黑名单（完全拒绝）
    DANGEROUS_PATTERNS = [
        r'^rm\s+(-[rf]+\s+)*/\s*$',           # rm -rf /
        r'^rm\s+(-[rf]+\s+)*/\*',              # rm -rf /*
        r'^sudo\s+rm\s+(-[rf]+)*',             # sudo rm -rf
        r'^mkfs',                              # 格式化磁盘
        r'^fdisk',                              # 分区操作
        r'^dd\s+.*of=/dev/',                   # dd 写入设备
        r'^:\(\)\s*\{\s*:\|: &\s*\}\s*;',      # fork bomb
        r'^chmod\s+(-R\s+)?777\s+/',           # chmod 777 /
        r'^chown\s+(-R\s+)?\S+\s+/',           # chown root /
        r'^>\s*/dev/sd[a-z]',                  # 写入磁盘设备
        r'^curl\s+.*\|\s*(bash|sh)',           # curl | bash
        r'^wget\s+.*\|\s*(bash|sh)',           # wget | sh
        r'^eval\s+.*\$\(',                      # eval 命令注入
        r'^exec\s+>',                          # exec 重定向
        r'^shutdown',                          # 关机
        r'^reboot',                            # 重启
        r'^halt',                              # 停机
        r'^poweroff',                          # 关机
        r'^init\s+[06]',                       # 切换运行级别
    ]

    # 敏感命令（需要每次确认，不缓存权限）
    SENSITIVE_PATTERNS = [
        r'^rm\s',
        r'^mv\s',
        r'^cp\s',
        r'^del\s',
        r'^erase\s',
        r'^move\s',
        r'^copy\s',
        r'^rd\s',
        r'^rmdir\s',
        r'^Remove-Item',
        r'^ri\s',
        r'^Move-Item',
        r'^mi\s',
        r'^Copy-Item',
        r'^ci\s',
        r'^Clear-Content',
        r'^sudo\s',
        r'^runas\s',
        r'^chmod\s',
        r'^chown\s',
        r'^icacls\s',
        r'^kill\s',
        r'^pkill\s',
        r'^killall\s',
        r'^taskkill\s',
        r'^Stop-Process',
        r'^apt\s+',
        r'^yum\s+',
        r'^dnf\s+',
        r'^pip\s+install',
        r'^npm\s+install',
        r'^winget\s+',
        r'^choco\s+',
        r'^git\s+push',
        r'^git\s+reset\s+--hard',
        r'^git\s+clean\s+-',
        r'^git\s+checkout\s+--',
        r'^format\s',
    ]

    # 需要路径范围检查的命令（文件系统操作）
    PATH_SCOPE_PATTERNS = [
        r'^rm\s',
        r'^del\s',
        r'^erase\s',
        r'^rd\s',
        r'^rmdir\s',
        r'^Remove-Item',
        r'^mv\s',
        r'^cp\s',
        r'^move\s',
        r'^copy\s',
        r'^Move-Item',
        r'^Copy-Item',
        r'^git\s+checkout\s+--',
        r'^git\s+reset\s+--',
        r'^git\s+clean',
    ]

    # 交互式命令模式（会等待用户输入导致卡住）
    INTERACTIVE_PATTERNS = [
        r'\bpython\b.*\binput\s*\(',       # python input()
        r'\bpython\b.*\drawinput\s*\(',    # python raw_input()
        r'\bnode\b.*\breadline\s*\(',      # node readline
        r'\bpython\b.*-i\b',               # python -i (交互模式)
        r'\bnode\b.*-i\b',                 # node -i (交互模式)
        r'\bipython\b',                    # ipython
        r'\bpsql\b',                       # postgres interactive
        r'\bmysql\b(?!.*-e)',              # mysql (无 -e 参数)
        r'\bmongo\b',                      # mongodb shell
        r'\bredis-cli\b(?!.*-.*\b)',       # redis-cli (无命令参数)
        r'\bvim?\b\s+',                    # vim/vi
        r'\bnano\b',                       # nano
        r'\bless\b',                       # less
        r'\bmore\b',                       # more
        r'\btop\b',                        # top
        r'\bhtop\b',                       # htop
        r'\bgit\s+commit\b(?!.*-m)',       # git commit (无 -m 参数)
        r'\bgit\s+rebase\s+-i\b',          # git rebase -i
        r'\bsftp\b',                       # sftp
        r'\bftp\b',                        # ftp
        r'\btelnet\b',                     # telnet
        r'\bssh\b(?!.*@.*".*")',           # ssh (无命令参数)
    ]

    # Unix 语法检查模式
    UNIX_SYNTAX_PATTERNS = [
        (r'mkdir\s+-p\s+', "PowerShell 不支持 -p 参数。\n正确语法：mkdir dir1, dir2（多个目录用逗号分隔）"),
        (r'ls\s+-[la]+\b', "PowerShell 的 ls 不支持 -l/-a/-la 参数。\n正确语法：Get-ChildItem（显示详细信息）或 ls（简单列表）"),
        (r'rm\s+-[rf]+\b', "PowerShell 的 rm 不支持 -r/-f 参数。\n正确语法：Remove-Item -Recurse -Force path"),
        (r'cp\s+-r\b', "PowerShell 的 cp 不支持 -r 参数。\n正确语法：Copy-Item -Recurse src dst"),
        (r'cat\s+-n\b', "PowerShell 的 cat 不支持 -n 参数。\n正确语法：Get-Content path"),
        (r'^touch\s+', "PowerShell 没有 touch 命令。\n正确语法：New-Item -Type File -Path name -Force"),
        (r'^which\s+', "PowerShell 没有 which 命令。\n正确语法：Get-Command name"),
        (r'^find\s+', "PowerShell 没有 Unix find 命令。\n正确语法：Get-ChildItem -Recurse -Filter pattern"),
        (r'^grep\s+', "PowerShell 没有 grep 命令。\n正确语法：Select-String -Pattern regex -Path file"),
        (r'^chmod\s+', "PowerShell 没有 chmod 命令。\n正确语法：icacls 或 Set-Acl"),
        (r'^chown\s+', "PowerShell 没有 chown 命令。\n正确语法：icacls 或 Set-Acl"),
    ]

    def get_parameters_schema(self) -> Dict[str, Any]:
        """参数定义"""
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒），默认 120",
                    "default": 120
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录，默认当前目录",
                    "default": "."
                }
            },
            "required": ["command"]
        }

    def _check_dangerous(self, command: str) -> Tuple[bool, str]:
        """检查命令是否危险"""
        cmd = command.strip().lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True, "此命令可能导致系统损坏或数据丢失"
        return False, ""

    def _check_interactive(self, command: str) -> Tuple[bool, str]:
        """检查命令是否为交互式命令（会导致卡住）"""
        for pattern in self.INTERACTIVE_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True, "此命令需要交互式输入，会卡住直到超时。请使用非交互式替代方案（如 -e 参数、-m 参数、管道输入等）"
        return False, ""

    def _check_unix_syntax(self, command: str) -> Optional[str]:
        """检查 Windows PowerShell 不兼容的 Unix 语法"""
        cmd_lower = command.lower()
        for pattern, message in self.UNIX_SYNTAX_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return message
        return None

    def _run_pre_checks(self, command: str) -> Optional[ToolResult]:
        """
        执行前置检查，返回拦截结果或 None（通过）
        """
        # 1. 危险命令
        is_dangerous, reason = self._check_dangerous(command)
        if is_dangerous:
            return ToolResult(success=False, output="", error=f"危险命令已拦截: {reason}")

        # 2. 交互式命令
        is_interactive, reason = self._check_interactive(command)
        if is_interactive:
            return ToolResult(success=False, output="", error=f"交互式命令已拦截: {reason}")

        # 3. Unix 语法检查 (Windows)
        if os.name == 'nt':
            unix_error = self._check_unix_syntax(command)
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
        progress: BashStreamingDisplay
    ) -> Tuple[int, List[str], List[str], Optional[str]]:
        """
        执行 subprocess 并收集输出

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

        try:
            while True:
                # 检查超时
                if progress.is_timeout():
                    process.kill()
                    progress.set_error(f"命令执行超时（{timeout}秒）")
                    progress.stop(False, -1)
                    return -1, [], [], f"命令执行超时（{timeout}秒）"

                # 读取 stdout
                stdout_line = process.stdout.readline()
                if stdout_line:
                    decoded = self._decode_line(stdout_line, is_windows)
                    if decoded:
                        stdout_lines.append(decoded)
                        progress.feed_output(decoded)

                # 读取 stderr
                if process.stderr:
                    try:
                        stderr_line = process.stderr.readline()
                        if stderr_line:
                            decoded = self._decode_line(stderr_line, is_windows)
                            if decoded:
                                stderr_lines.append(decoded)
                                progress.feed_output(f"[stderr] {decoded}")
                    except Exception:
                        pass

                # 检查进程是否结束
                if process.poll() is not None:
                    # 读取剩余输出
                    remaining_stdout = process.stdout.read()
                    remaining_stderr = process.stderr.read() if process.stderr else b''
                    if remaining_stdout:
                        for line in remaining_stdout.splitlines():
                            decoded = self._decode_line(line, is_windows)
                            if decoded:
                                stdout_lines.append(decoded)
                    if remaining_stderr:
                        for line in remaining_stderr.splitlines():
                            decoded = self._decode_line(line, is_windows)
                            if decoded:
                                stderr_lines.append(decoded)
                    break

        except Exception as e:
            process.kill()
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

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行命令"""
        # 参数验证（与 Read/Edit 工具一致）
        validation_error = self.validate_parameters(parameters)
        if validation_error:
            return ToolResult(success=False, output="", error=validation_error)

        from claude_code.config.defaults import WORKPLACE_DIR

        command = parameters.get("command", "").strip()
        timeout = min(int(parameters.get("timeout", 120)), self.MAX_EXECUTION_TIME)

        # 路径隔离逻辑
        user_cwd = parameters.get("cwd", ".")
        work_dir = Path(user_cwd).resolve()
        if not Path(user_cwd).is_absolute():
            work_dir = Path(WORKPLACE_DIR).resolve()
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
                command, work_dir, timeout, progress
            )
            if exec_error:
                return ToolResult(success=False, output="", error=exec_error)

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
        cmd = command.strip().lower()
        for pattern in self.SENSITIVE_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True
        return False

    def needs_path_scope_check(self, command: str) -> bool:
        """检查命令是否需要路径范围验证"""
        cmd = command.strip().lower()
        for pattern in self.PATH_SCOPE_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True
        return False

    def check_path_scope(self, command: str, project_dir: Path) -> Dict[str, Any]:
        """检查命令中的路径是否在项目目录范围内"""
        outside_paths = []
        paths = self._extract_paths_from_command(command)
        for path_str in paths:
            try:
                path = Path(path_str)
                if not path.is_absolute():
                    path = Path.cwd() / path
                path = path.resolve()
                try:
                    path.relative_to(project_dir)
                except ValueError:
                    outside_paths.append(str(path))
            except Exception:
                pass
        return {
            "in_scope": len(outside_paths) == 0,
            "outside_paths": outside_paths,
            "project_dir": str(project_dir)
        }

    def _extract_paths_from_command(self, command: str) -> List[str]:
        """从命令中提取路径参数"""
        paths = []
        quoted_pattern = r'["\']([^"\']+)["\']'
        for match in re.finditer(quoted_pattern, command):
            paths.append(match.group(1))
        remaining = re.sub(quoted_pattern, '', command)
        tokens = remaining.split()
        for token in tokens:
            if token.startswith('-'):
                continue
            if token.lower() in ['rm', 'del', 'erase', 'rd', 'rmdir', 'mv', 'cp', 'move', 'copy', 'git']:
                continue
            if token.lower() in ['checkout', 'reset', 'clean', 'push', 'pull', 'add', 'commit']:
                continue
            if token in ['--', '.', '..']:
                continue
            if token and not token.startswith('<') and not token.startswith('>'):
                paths.append(token)
        return paths

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