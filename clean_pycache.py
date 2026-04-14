"""
清理项目中的 __pycache__ 目录，并重置项目根目录结构。
确保根目录下只保留指定的白名单文件和目录。
注意：白名单目录（如 .venv）内部的内容将被完整保留，不做任何修改。
"""
import os
import shutil
import sys

# 获取脚本所在目录作为项目根目录
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# ================= 配置区域 =================

# 1. 必须存在的文件 (白名单)
REQUIRED_FILES = {
    "重启claude code终端步骤.txt",
    "重构进度总结.md",
    "打包exe教程.md",
    "README.md",
    "pyproject.toml",
    "clean_pycache.py",  # 脚本自身必须保留
    ".gitignore"
}

# 2. 必须存在的目录 (白名单)
REQUIRED_DIRS = {
    "tests",
    "src",
    "data",
    ".venv",
    ".pytest_cache"
}

# 3. 需要清理缓存的目录 (仅在这些白名单目录中查找 __pycache__)
# .venv 和 .pytest_cache 通常不需要也不应该被此脚本清理内部结构
DIRS_TO_CLEAN_CACHE = {"src", "tests", "data"} 

# ===========================================

def get_root_contents():
    """获取项目根目录下的所有直接子项（文件和文件夹）"""
    try:
        entries = os.listdir(PROJECT_DIR)
    except PermissionError:
        print("❌ 权限不足，无法读取项目根目录")
        sys.exit(1)
    return set(entries)

def check_and_report_status():
    """检查当前状态，报告缺失的必要文件或目录"""
    current_contents = get_root_contents()
    
    missing_files = REQUIRED_FILES - current_contents
    missing_dirs = REQUIRED_DIRS - current_contents
    
    if missing_files:
        print("⚠️  警告：以下必需文件不存在:")
        for f in sorted(missing_files):
            print(f"   - {f}")
            
    if missing_dirs:
        print("⚠️  警告：以下必需目录不存在:")
        for d in sorted(missing_dirs):
            print(f"   - {d}")
            
    if not missing_files and not missing_dirs:
        print("✅ 所有必需的文件和目录均已存在。")
        
    return missing_files, missing_dirs

def find_pycache_in_targets(root: str, target_dirs: set) -> list[str]:
    """
    仅在指定的目标目录中递归查找 __pycache__
    """
    results = []
    
    for target_dir in target_dirs:
        target_path = os.path.join(root, target_dir)
        if not os.path.isdir(target_path):
            continue
            
        for dirpath, dirnames, filenames in os.walk(target_path):
            if os.path.basename(dirpath) == "__pycache__":
                results.append(dirpath)
                # 找到 __pycache__ 后，不需要再进入其子目录（通常也没有）
                dirnames.clear()
                
    return results

def clean_non_whitelist_items():
    """
    删除根目录下所有不在白名单中的文件和目录。
    """
    current_contents = get_root_contents()
    
    # 计算需要删除的内容：当前内容 - (白名单文件 | 白名单目录)
    allowed_items = REQUIRED_FILES | REQUIRED_DIRS
    items_to_delete = current_contents - allowed_items
    
    if not items_to_delete:
        return 0

    deleted_count = 0
    for item_name in sorted(items_to_delete):
        item_path = os.path.join(PROJECT_DIR, item_name)
        try:
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
                print(f"  🗑️  删除目录: {item_name}/")
            else:
                os.remove(item_path)
                print(f"  🗑️  删除文件: {item_name}")
            deleted_count += 1
        except Exception as e:
            print(f"  ❌ 删除失败 {item_name}: {e}")
            
    return deleted_count

def clean_pycache_in_allowed_dirs():
    """
    仅在指定的源代码目录中清理 __pycache__
    避开 .venv 和 .pytest_cache 等受保护目录
    """
    print("\n🔍 正在扫描指定目录 (src, tests, data) 内的 __pycache__ ...")
    
    all_pycaches = find_pycache_in_targets(PROJECT_DIR, DIRS_TO_CLEAN_CACHE)
        
    if not all_pycaches:
        print("✅ 未发现需要清理的 __pycache__ 目录")
        return 0

    print(f"找到 {len(all_pycaches)} 个 __pycache__ 目录：")
    total_size = 0
    for d in all_pycaches:
        rel = os.path.relpath(d, PROJECT_DIR)
        try:
            size = sum(f.stat().st_size for f in os.scandir(d) if f.is_file())
            total_size += size
            print(f"  📁 {rel}  ({size / 1024:.1f} KB)")
        except FileNotFoundError:
            pass 

    print(f"\n总计大小: {total_size / 1024:.1f} KB")
    
    if total_size == 0:
        print("✅ 缓存目录为空或已清理")
        return 0
        
    confirm = input("是否删除以上 __pycache__ 目录？(y/n): ").strip().lower()
    
    deleted_count = 0
    if confirm == "y":
        for d in all_pycaches:
            try:
                shutil.rmtree(d)
                rel = os.path.relpath(d, PROJECT_DIR)
                print(f"  🗑️  已删除: {rel}")
                deleted_count += 1
            except Exception as e:
                print(f"  ❌ 删除失败 {d}: {e}")
        print(f"\n✅ 已清理 {deleted_count} 个 __pycache__ 目录")
    else:
        print("❌ 已取消清理 __pycache__")
        
    return deleted_count

def main():
    print("="*40)
    print("🧹 项目结构清洗与缓存清理工具")
    print("="*40)
    print(f"📂 当前项目路径: {PROJECT_DIR}\n")

    # 第一步：检查必需文件/目录的存在情况
    print("--- 1. 检查必需项 ---")
    missing_files, missing_dirs = check_and_report_status()
    
    if missing_files or missing_dirs:
        print("\n⚠️  注意：上述必需项缺失。本脚本不会自动创建它们。")
        print("    继续执行将删除其他所有非白名单文件。\n")
    
    # 第二步：清理非白名单内容
    print("--- 2. 清理非白名单内容 ---")
    current_contents = get_root_contents()
    allowed_items = REQUIRED_FILES | REQUIRED_DIRS
    items_to_delete = current_contents - allowed_items
    
    if not items_to_delete:
        print("✅ 根目录下没有需要删除的非白名单文件或目录。")
    else:
        print(f"即将删除以下 {len(items_to_delete)} 项（不在白名单中）：")
        for item in sorted(items_to_delete):
            path = os.path.join(PROJECT_DIR, item)
            type_str = "DIR " if os.path.isdir(path) else "FILE"
            print(f"  [{type_str}] {item}")
        
        print()
        confirm_clean = input("⚠️  确认删除以上非白名单内容？(y/n): ").strip().lower()
        
        if confirm_clean == "y":
            deleted_count = clean_non_whitelist_items()
            print(f"✅ 非白名单内容清理完成，共删除 {deleted_count} 项。")
        else:
            print("❌ 用户取消操作，退出。")
            return

    # 第三步：清理指定目录内部的 __pycache__
    # 注意：这里只清理 src, tests, data 等开发目录，绝不触碰 .venv
    print("\n--- 3. 清理源代码缓存 ---")
    clean_pycache_in_allowed_dirs()

    print("\n" + "="*40)
    print("🎉 清洗完成！")
    print("当前根目录应仅包含指定的白名单文件和目录。")
    print(".venv 和其他白名单目录内部保持原样。")
    print("="*40)

if __name__ == "__main__":
    main()