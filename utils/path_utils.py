import os
import sys

def ensure_path_in_syspath(path):
    """确保路径在sys.path中"""
    if path not in sys.path:
        sys.path.insert(0, path)

def get_relative_path(base_path, full_path):
    """获取相对路径"""
    if full_path.startswith(base_path):
        return full_path[len(base_path):].lstrip(os.sep)
    return full_path

def find_file_in_directory(directory, filename):
    """在目录中查找文件"""
    for root, dirs, files in os.walk(directory):
        if filename in files:
            return os.path.join(root, filename)
    return None