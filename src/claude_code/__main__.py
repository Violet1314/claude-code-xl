"""入口点 - python -m claude_code"""
import sys

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