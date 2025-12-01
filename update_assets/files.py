import os
import json
import fnmatch
from pathlib import Path

def load_gitignore_patterns():
    """
    加载.gitignore中的忽略模式
    """
    patterns = []
    gitignore_path = Path('.gitignore')
    
    if gitignore_path.exists():
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 忽略空行和注释行
                if line and not line.startswith('#'):
                    patterns.append(line)
    
    # 默认添加一些常见的忽略项
    patterns.extend(['.git', '.gitignore', 'files.json'])
    
    return patterns

def should_ignore(path, patterns):
    """
    判断路径是否应该被忽略
    """
    path_str = str(path)
    
    for pattern in patterns:
        # 处理绝对路径模式
        if pattern.startswith('/'):
            if fnmatch.fnmatch(path_str, pattern[1:]):
                return True
        else:
            # 处理相对路径模式
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(os.path.basename(path_str), pattern):
                return True
            
            # 处理目录下的文件匹配
            parts = path_str.split(os.sep)
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
    
    return False

def get_all_files():
    """
    获取当前目录下所有文件（排除.gitignore中指定的文件）
    """
    patterns = load_gitignore_patterns()
    files = []
    
    # 遍历当前目录及其子目录
    for root, dirs, filenames in os.walk('.'):
        # 移除需要忽略的目录
        dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d), patterns)]
        
        for filename in filenames:
            file_path = os.path.join(root, filename)
            # 检查文件是否应该被忽略
            if not should_ignore(file_path, patterns):
                # 转换为相对路径
                relative_path = os.path.relpath(file_path, '.')
                files.append(relative_path)
    
    return files

def write_to_json(files):
    """
    将文件列表写入JSON文件
    """
    data = {
        "files": sorted(files),
        "count": len(files)
    }
    
    with open('update_assets\\files.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    """
    主函数
    """
    print("正在扫描当前目录下的文件...")
    files = get_all_files()
    
    print(f"找到 {len(files)} 个文件")
    print("正在写入 files.json...")
    write_to_json(files)
    
    print("完成！结果已保存到 files.json")

if __name__ == "__main__":
    main()