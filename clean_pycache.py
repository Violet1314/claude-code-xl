# clean_pycache.py
"""清理项目中的 __pycache__ 目录"""
import os
import shutil

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
EXCLUDE_DIRS = {".venv", ".pytest_cache"}

def find_pycache(root: str) -> list[str]:
    """查找所有 __pycache__ 目录（排除指定目录）"""
    results = []
    for dirpath, dirnames, _ in os.walk(root):
        # 排除目录，直接从 dirnames 中移除可阻止 os.walk 进入
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        if os.path.basename(dirpath) == "__pycache__":
            results.append(dirpath)
            dirnames.clear()  # 不再进入子目录
    return results

def main():
    dirs = find_pycache(PROJECT_DIR)

    if not dirs:
        print("✅ 未找到 __pycache__ 目录")
        return

    print(f"找到 {len(dirs)} 个 __pycache__ 目录：\n")
    for d in dirs:
        rel = os.path.relpath(d, PROJECT_DIR)
        size = sum(f.stat().st_size for f in os.scandir(d) if f.is_file())
        print(f"  📁 {rel}  ({size / 1024:.1f} KB)")

    print()
    confirm = input("是否删除以上目录？(y/n): ").strip().lower()

    if confirm == "y":
        for d in dirs:
            shutil.rmtree(d)
            print(f"  🗑️  已删除: {os.path.relpath(d, PROJECT_DIR)}")
        print(f"\n✅ 已清理 {len(dirs)} 个目录")
    else:
        print("❌ 已取消")

if __name__ == "__main__":
    main()