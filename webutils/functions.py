import zipfile
import requests
import requests
import json
from pyunpack import Archive
import os
import time
import zipfile
import hashlib
import shutil
import base64
from .log_h import LogManager

def zip_folder(folder_path, output_path, logger_:LogManager=None):
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(folder_path):
                # 添加空文件夹到zip
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    arc_path = os.path.relpath(dir_path, os.path.dirname(folder_path))
                    zipf.write(dir_path, arc_path)
                # 添加文件到zip
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_path = os.path.relpath(file_path, os.path.dirname(folder_path))
                    zipf.write(file_path, arc_path)
        return True
    except Exception as e:
        logger_.log(f"压缩文件夹失败: {e}")
        logger_.log_error(e)
        return False
    
def decompress_7z(file_path, output_dir='.', logger_: LogManager=None):
    if not os.path.exists(file_path):
        logger_.log(f"压缩文件不存在: {file_path}")
        return False

    if output_dir is None:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_dir = os.path.join(os.getcwd(), base_name)
    
    os.makedirs(output_dir, exist_ok=True)

    try:
        logger_.log(f"开始解压文件: {file_path}")
        Archive(file_path).extractall(output_dir)
        logger_.log(f"解压完成")
        return True
    except Exception as e:
        logger_.log(f"解压失败: {e}")
        logger_.log_error(e)
        return False

def download_with(url, save_path, size=0, chunk_size=1024*100, logger_: LogManager=None, modal_id=None, progress_=[0,100]):
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()  # 检查请求是否成功
            
            # 获取文件总大小
            if size == 0:
                total_size = int(r.headers.get('Content-Length', 0))
            else:
                total_size = size
            chunk_len = total_size//chunk_size +1
            downloaded_chunk = 0
            
            logger_.log(f"开始下载文件，总大小: {total_size // 1024} KB")
            
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if modal_id:
                        logger_.check_running(modal_id)
                    f.write(chunk)
                    
                    downloaded_chunk += 1
                    logger_.update_modal_progress(
                        progress_[0] + (progress_[1]-progress_[0]) * downloaded_chunk / chunk_len,
                        f"已下载 {downloaded_chunk * chunk_size // 1024} KB / {total_size // 1024} KB",
                        modal_id
                    )
            
            logger_.log("\n下载完成")
        return True
    except Exception as e:
        logger_.log(f"\n下载失败: {e}")
        logger_.log_error(e)
        return False

def calculate_sha256(file_path, logger_: LogManager=None):
    """
    计算指定文件的SHA256哈希值
    
    Args:
        file_path (str): 文件路径
        logger_ (LogManager, optional): 日志管理器
        
    Returns:
        str: 文件的SHA256哈希值，如果出错则返回None
    """
    if not os.path.exists(file_path):
        if logger_:
            logger_.log(f"文件不存在: {file_path}")
        return None
        
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            # 逐块读取文件以节省内存
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        if logger_:
            logger_.log(f"计算文件SHA256失败: {e}")
            logger_.log_error(e)
        return None

def calculate_md5(file_path, logger_: LogManager=None):
    """
    计算指定文件的MD5哈希值
    
    Args:
        file_path (str): 文件路径
        logger_ (LogManager, optional): 日志管理器
        
    Returns:
        str: 文件的MD5哈希值，如果出错则返回None
    """
    if not os.path.exists(file_path):
        if logger_:
            logger_.log(f"文件不存在: {file_path}")
        return None
        
    md5_hash = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            # 逐块读取文件以节省内存
            for byte_block in iter(lambda: f.read(4096), b""):
                md5_hash.update(byte_block)
        return md5_hash.hexdigest()
    except Exception as e:
        if logger_:
            logger_.log(f"计算文件MD5失败: {e}")
            logger_.log_error(e)
        return None
