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
        r'^rm\s+(-[rf]+\s+)*/*\s*$',           # rm -rf /
        r'^rm\s+(-[rf]+\s+)*/\*',              # rm -rf /*
        r'^sudo\s+rm\s+(-[rf]+)*',             # sudo rm -rf
        r'^mkfs',                              # 格式化磁盘
        r'^fdisk',                             # 分区操作
        r'^dd\s+.*of=/dev/',                   # dd 写入设备
        r'^:\(\)\s*\{\s*:\|:&\s*\}\s*;:',      # fork bomb
        r'^chmod\s+(-R\s+)?777\s+/',           # chmod 777 /
        r'^chown\s+(-R\s+)?\S+\s+/',           # chown root /
        r'^>\s*/dev/sd[a-z]',                  # 写入磁盘设备
        r'^curl\s+.*\|\s*(bash|sh)',           # curl | bash
        r'^wget\s+.*\|\s*(bash|sh)',           # wget | sh
        r'^eval\s+.*\$\(',                     # eval 命令注入
        r'^exec\s+>',                          # exec 重定向
        r'^shutdown',                          # 关机
        r'^reboot',                            # 重启
        r'^halt',                              # 停机
        r'^poweroff',                          # 关机
        r'^init\s+[06]',                       # 切换运行级别
    ]

    # 敏感命令（需要每次确认，不缓存权限）
    SENSITIVE_PATTERNS = [
        # Unix 删除/移动/复制
        r'^rm\s',                              # 删除文件
        r'^mv\s',                              # 移动文件
        r'^cp\s',                              # 复制文件（可能覆盖）
        # Windows CMD 删除/移动/复制
        r'^del\s',                             # Windows 删除
        r'^erase\s',                           # Windows 删除
        r'^move\s',                            # Windows 移动
        r'^copy\s',                            # Windows 复制
        r'^rd\s',                              # Windows 删除目录
        r'^rmdir\s',                           # Windows 删除目录
        # PowerShell 删除/移动/复制（危险！）
        r'^Remove-Item',                       # PowerShell 删除
        r'^ri\s',                              # PowerShell 删除别名
        r'^Move-Item',                         # PowerShell 移动
        r'^mi\s',                              # PowerShell 移动别名
        r'^Copy-Item',                         # PowerShell 复制
        r'^ci\s',                              # PowerShell 复制别名
        r'^Clear-Content',                     # PowerShell 清空内容
        # 提权
        r'^sudo\s',                            # Unix 提权
        r'^runas\s',                           # Windows 提权
        # 权限修改
        r'^chmod\s',                           # 修改权限
        r'^chown\s',                           # 修改所有者
        r'^icacls\s',                          # Windows ACL
        # 进程管理
        r'^kill\s',                            # 杀进程
        r'^pkill\s',                           # 批量杀进程
        r'^killall\s',                         # 批量杀进程
        r'^taskkill\s',                        # Windows 杀进程
        r'^Stop-Process',                      # PowerShell 杀进程
        # 包管理器
        r'^apt\s+',                            # Debian/Ubuntu
        r'^yum\s+',                            # RHEL/CentOS
        r'^dnf\s+',                            # Fedora
        r'^pip\s+install',                     # pip 安装
        r'^npm\s+install',                     # npm 安装
        r'^winget\s+',                         # Windows 包管理器
        r'^choco\s+',                          # Chocolatey
        # Git 危险操作
        r'^git\s+push',                        # git push
        r'^git\s+reset\s+--hard',              # git reset --hard
        r'^git\s+clean\s+-',                   # git clean
        r'^git\s+checkout\s+--',               # git checkout 覆盖
        # 格式化
        r'^format\s',                          # Windows 格式化
    ]

    # 需要路径范围检查的命令（文件系统操作）
    PATH_SCOPE_PATTERNS = [
        # 删除操作
        r'^rm\s',
        r'^del\s',
        r'^erase\s',
        r'^rd\s',
        r'^rmdir\s',
        r'^Remove-Item',
        # 移动/复制操作
        r'^mv\s',
        r'^cp\s',
        r'^move\s',
        r'^copy\s',
        r'^Move-Item',
        r'^Copy-Item',
        # Git 危险操作
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

        # 参数类型转换（AI 可能传入字符串）
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
            return ToolResult(
                success=False,
                output="",
                error=f"危险命令已拦截: {danger_reason}"
            )

        # Windows 环境下检查 Unix 不兼容语法
        if os.name == 'nt':
            unix_error = self._check_unix_syntax(command)
            if unix_error:
                return ToolResult(
                    success=False,
                    output="",
                    error=unix_error
                )

        # 检查工作目录
        work_dir = Path(cwd).resolve()
        if not work_dir.exists():
            return ToolResult(success=False, output="", error=f"工作目录不存在: {cwd}")

        try:
            # 判断操作系统
            is_windows = os.name == 'nt'

            # 创建进度显示
            progress = BashStreamingDisplay(command, timeout)
            progress.start()

            # 执行命令（流式输出）
            if is_windows:
                # Windows: 使用 PowerShell
                win_command = command.replace('&&', ';')
                ps_command = f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {win_command}"

                process = subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", ps_command],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(work_dir)
                )
            else:
                # Unix: 使用 bash
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(work_dir)
                )

            # 流式读取输出
            output_lines = []
            output_bytes = b""

            try:
                while True:
                    # 检查超时
                    if progress.is_timeout():
                        process.kill()
                        progress.stop(False, -1)
                        return ToolResult(
                            success=False,
                            output="",
                            error=f"命令执行超时（{timeout}秒）"
                        )

                    # 读取一行
                    line = process.stdout.readline()
                    if not line:
                        # 检查进程是否结束
                        if process.poll() is not None:
                            break
                        continue

                    output_bytes += line

                    # 解码并显示
                    try:
                        if is_windows:
                            # 尝试多种编码
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
                return ToolResult(
                    success=False,
                    output="",
                    error=f"读取输出失败: {str(e)}"
                )

            # 等待进程结束
            return_code = process.wait()

            # 合并输出
            output = '\n'.join(output_lines)

            # 截断输出
            if len(output) > self.MAX_OUTPUT_LENGTH:
                output = output[:self.MAX_OUTPUT_LENGTH] + f"\n... (输出过长，已截断，共 {len(output)} 字符)"

            # 停止进度显示
            success = return_code == 0
            progress.stop(success, return_code)

            # 非零返回码时，输出作为错误信息
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
            return ToolResult(
                success=False,
                output="",
                error=f"命令执行超时（{timeout}秒）"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"执行失败: {str(e)}"
            )

    def _check_dangerous(self, command: str) -> Tuple[bool, str]:
        """
        检查命令是否危险

        Returns:
            (是否危险, 原因)
        """
        # 标准化命令
        cmd = command.strip().lower()

        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True, "此命令可能导致系统损坏或数据丢失"

        return False, ""

    def _check_unix_syntax(self, command: str) -> Optional[str]:
        """
        检查 Windows PowerShell 不兼容的 Unix 语法

        Args:
            command: 命令字符串

        Returns:
            错误提示字符串，如果兼容则返回 None
        """
        # Unix 不兼容语法检测规则
        unix_patterns = [
            # mkdir -p
            (r'mkdir\s+-p\s+', "PowerShell 不支持 -p 参数。\n正确语法：mkdir dir1, dir2（多个目录用逗号分隔）"),
            # ls -la, ls -l, ls -a
            (r'ls\s+-[la]+\b', "PowerShell 的 ls 不支持 -l/-a/-la 参数。\n正确语法：Get-ChildItem（显示详细信息）或 ls（简单列表）"),
            # rm -rf, rm -r, rm -f
            (r'rm\s+-[rf]+\b', "PowerShell 的 rm 不支持 -r/-f 参数。\n正确语法：Remove-Item -Recurse -Force path"),
            # cp -r
            (r'cp\s+-r\b', "PowerShell 的 cp 不支持 -r 参数。\n正确语法：Copy-Item -Recurse src dst"),
            # mv (基本兼容，但提示)
            # cat -n
            (r'cat\s+-n\b', "PowerShell 的 cat 不支持 -n 参数。\n正确语法：Get-Content path"),
            # touch
            (r'^touch\s+', "PowerShell 没有 touch 命令。\n正确语法：New-Item -Type File -Path name -Force"),
            # which
            (r'^which\s+', "PowerShell 没有 which 命令。\n正确语法：Get-Command name"),
            # find（Unix find）
            (r'^find\s+', "PowerShell 没有 Unix find 命令。\n正确语法：Get-ChildItem -Recurse -Filter pattern"),
            # grep（作为命令调用，不是 Select-String）
            (r'^grep\s+', "PowerShell 没有 grep 命令。\n正确语法：Select-String -Pattern regex -Path file"),
            # chmod
            (r'^chmod\s+', "PowerShell 没有 chmod 命令。\n正确语法：icacls 或 Set-Acl"),
            # chown
            (r'^chown\s+', "PowerShell 没有 chown 命令。\n正确语法：icacls 或 Set-Acl"),
        ]

        cmd_lower = command.lower()
        for pattern, message in unix_patterns:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return message

        return None

    def is_sensitive(self, command: str) -> bool:
        """
        检查命令是否敏感（需要每次确认）

        Args:
            command: 命令字符串

        Returns:
            是否敏感
        """
        cmd = command.strip().lower()

        for pattern in self.SENSITIVE_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True

        return False

    def needs_path_scope_check(self, command: str) -> bool:
        """
        检查命令是否需要路径范围验证

        Args:
            command: 命令字符串

        Returns:
            是否需要检查路径范围
        """
        cmd = command.strip().lower()

        for pattern in self.PATH_SCOPE_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True

        return False

    def check_path_scope(
        self,
        command: str,
        project_dir: Path
    ) -> Dict[str, Any]:
        """
        检查命令中的路径是否在项目目录范围内

        Args:
            command: 命令字符串
            project_dir: 项目目录

        Returns:
            {
                "in_scope": bool,           # 是否全部在项目内
                "outside_paths": [str],     # 项目外的路径列表
                "project_dir": str          # 项目目录
            }
        """
        outside_paths = []

        # 从命令中提取路径
        paths = self._extract_paths_from_command(command)

        for path_str in paths:
            try:
                path = Path(path_str)

                # 处理相对路径
                if not path.is_absolute():
                    path = Path.cwd() / path

                path = path.resolve()

                # 检查是否在项目目录内
                try:
                    path.relative_to(project_dir)
                except ValueError:
                    # 不在项目目录内
                    outside_paths.append(str(path))
            except Exception:
                # 无法解析的路径，跳过
                pass

        return {
            "in_scope": len(outside_paths) == 0,
            "outside_paths": outside_paths,
            "project_dir": str(project_dir)
        }

    def _extract_paths_from_command(self, command: str) -> List[str]:
        """
        从命令中提取路径参数

        Args:
            command: 命令字符串

        Returns:
            提取的路径列表
        """
        paths = []

        # 简单的路径提取策略：
        # 1. 处理引号内的路径
        # 2. 处理空格分隔的路径参数

        # 匹配单引号或双引号内的内容
        quoted_pattern = r'["\']([^"\']+)["\']'
        for match in re.finditer(quoted_pattern, command):
            paths.append(match.group(1))

        # 移除引号部分，处理剩余的空格分隔参数
        remaining = re.sub(quoted_pattern, '', command)

        # 分词
        tokens = remaining.split()

        # 跳过选项参数（以 - 开头的），提取可能的路径
        for token in tokens:
            # 跳过选项
            if token.startswith('-'):
                continue
            # 跳过命令本身（第一个词）
            if token.lower() in ['rm', 'del', 'erase', 'rd', 'rmdir', 'mv', 'cp', 'move', 'copy', 'git']:
                continue
            # 跳过 git 子命令
            if token.lower() in ['checkout', 'reset', 'clean', 'push', 'pull', 'add', 'commit']:
                continue
            # 跳过特殊符号
            if token in ['--', '.', '..']:
                continue
            # 剩下的可能是路径
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

        # 参数类型转换
        try:
            timeout = int(parameters.get("timeout", 120))
        except (ValueError, TypeError):
            timeout = 120

        if timeout < 1 or timeout > 600:
            return "timeout 必须在 1-600 秒之间"

        return None