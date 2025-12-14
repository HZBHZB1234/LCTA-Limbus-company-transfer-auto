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
    
def extract_zip_smartly(zip_path, target_dir):
    """
    智能解压ZIP文件
    
    如果压缩包根目录只有一个文件夹，则直接解压该文件夹内容到目标目录；
    如果压缩包根目录有多个文件或文件夹，则在目标目录下创建以压缩包名称命名的文件夹，
    然后将内容解压到该文件夹中。
    
    Args:
        zip_path (str): ZIP文件路径
        target_dir (str): 目标解压目录
    """
    # 确保目标目录存在
    os.makedirs(target_dir, exist_ok=True)
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # 获取所有文件列表
        file_list = zip_ref.namelist()
        
        # 过滤出不在根目录的文件（即路径中包含'/'的）
        root_items = set()
        for file_path in file_list:
            # 移除末尾的斜杠（文件夹标识）
            clean_path = file_path.rstrip('/')
            # 获取根目录下的项目
            root_item = clean_path.split('/')[0]
            root_items.add(root_item)
        
        # 判断根目录是否只有一个文件夹
        if len(root_items) == 1:
            single_item = list(root_items)[0]
            # 检查这个项目是否是文件夹（通过检查是否有以它开头的路径）
            is_folder = any(f.startswith(single_item + '/') for f in file_list if f != single_item + '/')
            
            if is_folder:
                # 只有一个根文件夹，提取其内容
                for member in file_list:
                    if member.startswith(single_item + '/'):
                        # 去掉前缀，直接解压内容
                        target_path = os.path.join(target_dir, member[len(single_item)+1:])
                        # 创建目标目录
                        if member.endswith('/'):
                            os.makedirs(target_path, exist_ok=True)
                        else:
                            os.makedirs(os.path.dirname(target_path), exist_ok=True)
                            # 解压文件
                            with zip_ref.open(member) as source, open(target_path, 'wb') as target:
                                target.write(source.read())
                return single_item
            else:
                # 只有一个文件，直接解压
                zip_ref.extractall(target_dir)
                return None
        else:
            # 有多个根项目，在目标目录下创建以zip文件名为名的文件夹
            zip_name = os.path.splitext(os.path.basename(zip_path))[0]
            extract_dir = os.path.join(target_dir, zip_name)
            os.makedirs(extract_dir, exist_ok=True)
            zip_ref.extractall(extract_dir)
            return zip_name

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
                        logger_.check_running(modal_id, log=False)
                    f.write(chunk)
                    
                    downloaded_chunk += 1
                    logger_.update_modal_progress(
                        progress_[0] + (progress_[1]-progress_[0]) * downloaded_chunk / chunk_len,
                        f"已下载 {downloaded_chunk * chunk_size // 1024} KB / {total_size // 1024} KB",
                        modal_id, log=False
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
