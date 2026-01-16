import zipfile
import requests
import requests
import json
from pyunpack import Archive
import os
import time
import zipfile
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set
import shutil
import base64
from .log_manage import LogManager
if TYPE_CHECKING:
    from web_function.GithubDownload import ReleaseAsset

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
    
def extract_zip_smartly(zip_path: str, target_dir: str) -> Optional[str]:
    """
    智能解压ZIP文件
    
    如果压缩包根目录只有一个文件夹，则直接解压该文件夹内容到目标目录；
    如果压缩包根目录有多个文件或文件夹，则在目标目录下创建以压缩包名称命名的文件夹，
    然后将内容解压到该文件夹中。
    
    Args:
        zip_path (str): ZIP文件路径
        target_dir (str): 目标解压目录
    
    Returns:
        Optional[str]: 返回解压的根文件夹名称，如果直接解压到目标目录则返回None
    """
    # 确保目标目录存在
    os.makedirs(target_dir, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # 使用集合来存储根目录项，避免重复
            root_items: Set[str] = set()
            
            # 一次性获取所有必要信息
            for info in zip_ref.infolist():
                # 获取根目录项
                root_item = info.filename.split('/')[0] if '/' in info.filename else info.filename
                # 只添加非空的根目录项
                if root_item:
                    root_items.add(root_item)
            
            # 如果没有根目录项，直接返回
            if not root_items:
                return None
            
            # 只有一个根目录项的情况
            if len(root_items) == 1:
                zip_ref.extractall(target_dir)
            else:
                zip_name = Path(zip_path).stem  # 使用Path获取无扩展名的文件名
                extract_dir = os.path.join(target_dir, zip_name)
                os.makedirs(extract_dir, exist_ok=True)
                    
                zip_ref.extractall(extract_dir)
                return zip_name
    
    except zipfile.BadZipFile:
        raise ValueError(f"文件 '{zip_path}' 不是有效的ZIP文件或已损坏")
    except PermissionError:
        raise PermissionError(f"没有权限解压文件到目录: {target_dir}")
    except Exception as e:
        raise RuntimeError(f"解压文件时发生错误: {str(e)}")

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

def download_with(url, save_path, size=0, chunk_size=1024*100, logger_: LogManager=None, modal_id=None, progress_=[0,100], headers={}):
    try:
        with requests.get(url, stream=True, headers=headers) as r:
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

def download_with_github(asset: 'ReleaseAsset', save_path, chunk_size=1024*100, 
                        logger_: LogManager=None, modal_id=None, 
                        progress_=[0,100], use_proxy=True):
    """
    下载ReleaseAsset中的文件，支持代理轮换重试
    
    Args:
        asset: ReleaseAsset对象，包含下载URL和代理管理器
        save_path: 保存路径
        chunk_size: 分块大小
        logger_: 日志管理器
        modal_id: 模态窗口ID
        progress_: 进度范围
        use_proxy: 是否使用代理
    Returns:
        bool: 下载是否成功
    """
    if not asset:
        if logger_:
            logger_.log("ReleaseAsset为空，无法下载")
        return False
    
    # 确保保存目录存在
    save_dir = os.path.dirname(save_path)
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
    
    if not use_proxy or not hasattr(asset, 'proxys') or not asset.proxys:
        # 不使用代理，直接下载
        if logger_:
            logger_.log(f"不使用代理，直接下载: {asset.name}")
        return download_with(
            asset.download_url, save_path, 
            size=asset.size, chunk_size=chunk_size,
            logger_=logger_, modal_id=modal_id, 
            progress_=progress_
        )
    
    # 使用代理管理器
    proxy_manager = asset.proxys
    
    # 准备尝试的URL列表：代理URL + 原始URL
    urls_to_try = []
    
    # 如果有代理，先添加代理URL
    if hasattr(proxy_manager, 'proxies') and proxy_manager.proxies:
        for proxy in proxy_manager.proxies:
            # 构建代理URL
            proxy_url = proxy.rstrip('/') + '/' + asset.download_url.lstrip('/')
            urls_to_try.append(proxy_url)
    
    # 最后添加原始URL作为备选
    urls_to_try.append(asset.download_url)
    
    if logger_:
        logger_.log(f"开始下载 {asset.name} (大小: {asset.size} bytes)")
        logger_.log(f"将尝试 {len(urls_to_try)} 个URL")
    
    # 尝试所有URL直到成功
    for i, url in enumerate(urls_to_try):
        try:
            if logger_:
                if i < len(urls_to_try) - 1:
                    logger_.log(f"尝试下载 (代理 {i+1}/{len(urls_to_try)-1}): {url}")
                else:
                    logger_.log(f"尝试直接下载 (不使用代理): {url}")
            
            # 使用download_with函数下载
            success = download_with(
                url, save_path, 
                size=asset.size, chunk_size=chunk_size,
                logger_=logger_, modal_id=modal_id, 
                progress_=progress_,
                headers={
                    'Accept': 'application/octet-stream',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            
            if success:
                # 验证文件大小
                if os.path.exists(save_path):
                    actual_size = os.path.getsize(save_path)
                    if asset.size > 0 and actual_size != asset.size:
                        if logger_:
                            logger_.log(f"警告: 文件大小不匹配。期望: {asset.size}, 实际: {actual_size}")
                        # 文件大小不匹配，继续尝试下一个URL
                        continue
                    
                    if logger_:
                        if i < len(urls_to_try) - 1:
                            logger_.log(f"下载成功! 使用代理 {i+1}/{len(urls_to_try)-1}")
                        else:
                            logger_.log("下载成功! 使用直接连接")
                    return True
                else:
                    if logger_:
                        logger_.log(f"文件未创建: {save_path}")
            
        except Exception as e:
            if logger_:
                logger_.log(f"下载失败 (URL {i+1}/{len(urls_to_try)}): {e}")
                logger_.log_error(e)
            
            # 短暂延迟后重试
            time.sleep(0.5)
    
    # 所有尝试都失败
    if logger_:
        logger_.log(f"所有下载尝试都失败: {asset.name}")
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

def decompress_zip(file_path, output_dir='.', logger_: LogManager=None):
    if not os.path.exists(file_path):
        logger_.log(f"压缩文件不存在: {file_path}")
        return False
    if output_dir is None:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_dir = os.path.join(os.getcwd(), base_name)
    
    os.makedirs(output_dir, exist_ok=True)
    try: 
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(output_dir)
    except Exception as e:
        logger_.log(f"解压失败: {e}")
        logger_.log_error(e)
        return False


def decompress_by_extension(file_path, output_dir='.', logger_: LogManager=None):
    if file_path.endswith('.zip'):
        return decompress_zip(file_path, output_dir, logger_=logger_)
    elif file_path.endswith('.7z'):
        return decompress_7z(file_path, output_dir, logger_=logger_)
    else:
        return False