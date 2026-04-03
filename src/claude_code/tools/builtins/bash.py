"""Bash 工具 - 执行 shell 命令（支持流式输出）"""
import os
import re
import subprocess
import shlex
import locale
import threading
import queue
from typing import Any, Dict, List, Optional, Tuple, Generator
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

    def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行命令"""
        command = parameters.get("command", "").strip()
        try:
            timeout = int(parameters.get("timeout", 120))
        except (ValueError, TypeError):
            timeout = 120
        timeout = min(timeout, self.MAX_EXECUTION_TIME)
        cwd = parameters.get("cwd", ".")

        if not command:
            return ToolResult(success=False, output="", error="缺少 command 参数")

        # 检查黑名单
        is_dangerous, danger_reason = self._check_dangerous(command)
        if is_dangerous:
            return ToolResult(success=False, output="", error=f"危险命令已拦截: {danger_reason}")

        # Windows 环境下检查 Unix 不兼容语法
        if os.name == 'nt':
            unix_error = self._check_unix_syntax(command)
            if unix_error:
                return ToolResult(success=False, output="", error=unix_error)

        # 检查工作目录
        work_dir = Path(cwd).resolve()
        if not work_dir.exists():
            return ToolResult(success=False, output="", error=f"工作目录不存在: {cwd}")

        try:
            is_windows = os.name == 'nt'
            progress = BashStreamingDisplay(command, timeout)
            progress.start()

            if is_windows:
                win_command = command.replace('&&', ';')
                ps_command = f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {win_command}"
                process = subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", ps_command],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(work_dir)
                )
            else:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(work_dir)
                )

            output_lines = []
            output_bytes = b""

            try:
                while True:
                    if progress.is_timeout():
                        process.kill()
                        progress.stop(False, -1)
                        return ToolResult(success=False, output="", error=f"命令执行超时（{timeout}秒）")

                    line = process.stdout.readline()
                    if not line:
                        if process.poll() is not None:
                            break
                        continue

                    output_bytes += line

                    try:
                        if is_windows:
                            decoded = None
                            for encoding in ['utf-8', 'utf-16-le', 'gbk']:
                                try:
                                    decoded = line.decode(encoding).rstrip('\r\n')
                                    break
                                except (UnicodeDecodeError, UnicodeError):
                                    continue
                            if decoded is None:
                                decoded = line.decode('utf-8', errors='replace').rstrip('\r\n')
                        else:
                            decoded = line.decode('utf-8', errors='replace').rstrip('\r\n')

                        if decoded:
                            output_lines.append(decoded)
                            progress.feed_output(decoded)
                    except Exception:
                        pass

            except Exception as e:
                process.kill()
                progress.stop(False, -1)
                return ToolResult(success=False, output="", error=f"读取输出失败: {str(e)}")
            
            return_code = process.wait()
            output = '\n'.join(output_lines)
            if len(output) > self.MAX_OUTPUT_LENGTH:
                output = output[:self.MAX_OUTPUT_LENGTH] + f"\n... (输出过长，已截断，共 {len(output)} 字符)"

            success = return_code == 0
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

    def _check_dangerous(self, command: str) -> Tuple[bool, str]:
        """检查命令是否危险"""
        cmd = command.strip().lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True, "此命令可能导致系统损坏或数据丢失"
        return False, ""

    def _check_unix_syntax(self, command: str) -> Optional[str]:
        """检查 Windows PowerShell 不兼容的 Unix 语法"""
        unix_patterns = [
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
        cmd_lower = command.lower()
        for pattern, message in unix_patterns:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return message
        return None

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