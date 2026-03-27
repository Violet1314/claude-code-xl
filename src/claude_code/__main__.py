"""入口点 - python -m claude_code"""
import sys
import os

# Windows 终端编码修复
if sys.platform == 'win32':
    # 设置控制台编码为 UTF-8
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # 尝试重新配置 stdout/stderr
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from claude_code.app import Application
from claude_code.ui import console

def main():
    """主入口函数"""
    try:
        app = Application()
        app.run()
    except KeyboardInterrupt:
        console.print("\n[dim]已退出[/]")
        sys.exit(0)
    except Exception as e:
        console.error(f"启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()