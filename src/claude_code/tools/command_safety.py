"""命令安全检查器 - 独立于 BashTool 的命令安全检测模块

提取自 BashTool，将危险命令检测、交互式命令检测、Unix 语法检查、
敏感命令检测、路径范围检查解耦为独立组件，便于复用和单元测试。
"""
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class CommandSafetyChecker:
    """命令安全检查器
    
    职责：
    1. 危险命令检测 — 完全拒绝（如 rm -rf /）
    2. 敏感命令检测 — 需要每次确认，不缓存权限
    3. 交互式命令检测 — 拒绝（会导致卡住）
    4. Unix 语法检查 — 仅在 Windows 下警告（不兼容语法）
    5. 路径范围检查 — 命令中的路径是否超出项目目录
    """

    # 危险命令黑名单（完全拒绝）
    DANGEROUS_PATTERNS: List[str] = [
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
    SENSITIVE_PATTERNS: List[str] = [
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
    ]

    # 需要路径范围验证的命令模式
    PATH_SCOPE_PATTERNS: List[str] = [
        r'^rm\s',
        r'^Remove-Item',
        r'^ri\s',
        r'^mv\s',
        r'^Move-Item',
        r'^mi\s',
        r'^cp\s',
        r'^Copy-Item',
        r'^ci\s',
        r'^rd\s',
        r'^rmdir\s',
    ]

    # 交互式命令黑名单（会卡住）
    INTERACTIVE_PATTERNS: List[str] = [
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

    # Unix 语法检查模式（Windows 下不兼容）
    UNIX_SYNTAX_PATTERNS: List[Tuple[str, str]] = [
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

    def check_dangerous(self, command: str) -> Tuple[bool, str]:
        """检查危险命令（完全拒绝）
        
        Returns:
            (is_dangerous, reason) — 安全时返回 (False, "")
        """
        cmd_lower = command.strip().lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return True, f"匹配危险命令模式: {pattern}"
        return False, ""

    def is_sensitive(self, command: str) -> bool:
        """检查命令是否敏感（需要每次确认，不缓存权限）"""
        cmd_lower = command.strip().lower()
        for pattern in self.SENSITIVE_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return True
        return False

    def needs_path_scope_check(self, command: str) -> bool:
        """检查命令是否需要路径范围验证"""
        cmd_lower = command.strip().lower()
        for pattern in self.PATH_SCOPE_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
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
        """从命令中提取可能的路径参数"""
        import shlex
        paths = []
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        skip_next = False
        for i, token in enumerate(tokens):
            if skip_next:
                skip_next = False
                continue
            if token.startswith('-'):
                if token in ['-o', '--output', '-d', '--destination', '-t', '--target']:
                    skip_next = True
                continue
            if token.lower() in ['checkout', 'reset', 'clean', 'push', 'pull', 'add', 'commit']:
                continue
            if token in ['--', '.', '..']:
                continue
            if token and not token.startswith('<') and not token.startswith('>'):
                paths.append(token)
        return paths

    def check_interactive(self, command: str) -> Tuple[bool, str]:
        """检查交互式命令（会导致卡住）
        
        Returns:
            (is_interactive, reason) — 安全时返回 (False, "")
        """
        cmd_lower = command.strip().lower()
        for pattern in self.INTERACTIVE_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return True, f"交互式命令，会等待用户输入导致卡住: {pattern}"
        return False, ""

    # Unix→PowerShell 转换建议映射
    UNIX_TO_PS_SUGGESTIONS: List[Tuple[str, str, str]] = [
        # (正则, 错误描述, PowerShell 替代命令)
        (r'\bls\s+-[la]+\b', "ls -la 不兼容 PowerShell", "Get-ChildItem | Format-Table Mode, LastWriteTime, Length, Name"),
        (r'\bls\s+-[a]+\b', "ls -a 不兼容 PowerShell", "Get-ChildItem -Force"),
        (r'\bls\s+-[l]+\b', "ls -l 不兼容 PowerShell", "Get-ChildItem | Format-Table Mode, LastWriteTime, Length, Name"),
        (r'\brm\s+-[rf]+\b', "rm -rf 不兼容 PowerShell", "Remove-Item -Recurse -Force <path>"),
        (r'\brm\s+-r\b', "rm -r 不兼容 PowerShell", "Remove-Item -Recurse <path>"),
        (r'\brm\s+-f\b', "rm -f 不兼容 PowerShell", "Remove-Item -Force <path>"),
        (r'\bmkdir\s+-p\b', "mkdir -p 不兼容 PowerShell", "New-Item -ItemType Directory -Force <path>"),
        (r'\bcp\s+-r\b', "cp -r 不兼容 PowerShell", "Copy-Item -Recurse <src> <dst>"),
        (r'\bmv\s+-f\b', "mv -f 不兼容 PowerShell", "Move-Item -Force <src> <dst>"),
        (r'\bcat\s+', "cat 在 PowerShell 中是 Get-Content 的别名，但行为可能不同", "Get-Content <file>"),
        (r'\bfind\s+', "find 不兼容 PowerShell", "Get-ChildItem -Recurse -Filter <pattern>"),
        (r'\bgrep\s+', "grep 不兼容 PowerShell", "Select-String -Pattern <pattern> <file>"),
        (r'\bwhich\s+', "which 不兼容 PowerShell", "Get-Command <name>"),
        (r'\btouch\s+', "touch 不兼容 PowerShell", "New-Item -ItemType File <path>"),
        (r'\bchmod\s+', "chmod 不兼容 PowerShell", "icacls <path> 或 Set-Acl"),
        (r'\bchown\s+', "chown 不兼容 PowerShell", "icacls <path> 或 Set-Acl"),
    ]

    def get_powershell_suggestion(self, command: str) -> Optional[str]:
        """检测 Unix 风格命令并返回 PowerShell 转换建议

        Args:
            command: 用户输入的命令

        Returns:
            转换建议字符串，或 None（无需建议）
        """
        cmd_lower = command.strip().lower()
        for pattern, desc, ps_cmd in self.UNIX_TO_PS_SUGGESTIONS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return f"{desc}\n建议使用: {ps_cmd}"
        return None

    def check_unix_syntax(self, command: str) -> Optional[str]:
        """检查 Windows PowerShell 不兼容的 Unix 语法
        
        Returns:
            错误提示字符串，或 None（通过）
        """
        cmd_lower = command.lower()
        for pattern, message in self.UNIX_SYNTAX_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return message
        return None

    def run_all_checks(self, command: str) -> Tuple[Optional[str], str]:
        """执行全部安全检查
        
        Returns:
            (check_type, message) — 通过时返回 (None, "")，拦截时返回 (检查类型, 原因)
            check_type: "dangerous" | "interactive" | "unix_syntax"
        """
        # 1. 危险命令（最高优先级）
        is_dangerous, reason = self.check_dangerous(command)
        if is_dangerous:
            return "dangerous", reason

        # 2. 交互式命令
        is_interactive, reason = self.check_interactive(command)
        if is_interactive:
            return "interactive", reason

        # 3. Unix 语法检查（仅 Windows）
        if os.name == 'nt':
            unix_error = self.check_unix_syntax(command)
            if unix_error:
                return "unix_syntax", unix_error

        return None, ""


# 全局单例
command_safety_checker = CommandSafetyChecker()
