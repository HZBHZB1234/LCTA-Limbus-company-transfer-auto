"""文件操作、压缩/解压与哈希计算工具函数。"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Optional, Set

from globalManagers.LogManager import LogManager
from .net import download_with

_log_manager = LogManager()
_7Z_DOWNLOAD_URL = "https://www.7-zip.org/"
# 官网直连的 7zr.exe（独立单文件控制台版，无需安装、无需再解压 7z），仅需解压 .7z 时足够
_7ZR_DOWNLOAD_URL = "https://www.7-zip.org/a/7zr.exe"
# 下载后大小校验阈值（约 1MB 的可执行文件，远小于此值视为下载不完整）
_7Z_MIN_SIZE = 500 * 1024
# 常见 7-Zip 安装路径（测试可覆盖为空以强制走自动下载分支）
_SYSTEM_7Z_PATHS = (
    r'C:\Program Files\7-Zip\7z.exe',
    r'C:\Program Files (x86)\7-Zip\7z.exe',
)


# ============================================================
# 压缩 / 解压
# ============================================================

def zip_folder(folder_path, output_path):
    """将文件夹压缩为 ZIP 文件。"""
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(folder_path):
                # 添加空文件夹到 zip
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    arc_path = os.path.relpath(dir_path, os.path.dirname(folder_path))
                    zipf.write(dir_path, arc_path)
                # 添加文件到 zip
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_path = os.path.relpath(file_path, os.path.dirname(folder_path))
                    zipf.write(file_path, arc_path)
        return True
    except Exception as e:
        _log_manager.log(f"压缩文件夹失败: {e}")
        _log_manager.log_error(e)
        return False


def extract_zip_smartly(zip_path: str, target_dir: str) -> Optional[str]:
    """智能解压 ZIP 文件。

    如果压缩包根目录只有一个文件夹，则直接解压该文件夹内容到目标目录；
    如果根目录有多个条目，则在目标目录下创建以压缩包名称命名的文件夹。
    """
    os.makedirs(target_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            root_items: Set[str] = set()

            for info in zip_ref.infolist():
                root_item = info.filename.split('/')[0] if '/' in info.filename else info.filename
                if root_item:
                    root_items.add(root_item)

            if not root_items:
                return None

            if len(root_items) == 1:
                zip_ref.extractall(target_dir)
            else:
                zip_name = Path(zip_path).stem
                extract_dir = os.path.join(target_dir, zip_name)
                os.makedirs(extract_dir, exist_ok=True)
                zip_ref.extractall(extract_dir)
                return zip_name

    except zipfile.BadZipFile:
        raise ValueError(f"文件 '{zip_path}' 不是有效的 ZIP 文件或已损坏")
    except PermissionError:
        raise PermissionError(f"没有权限解压文件到目录: {target_dir}")
    except Exception as e:
        raise RuntimeError(f"解压文件时发生错误: {str(e)}")


def decompress_zip(file_path, output_dir='.'):
    """解压 ZIP 文件到指定目录。"""
    if not os.path.exists(file_path):
        _log_manager.log(f"压缩文件不存在: {file_path}")
        return False
    if output_dir is None:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_dir = os.path.join(os.getcwd(), base_name)

    os.makedirs(output_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(output_dir)
        return True
    except Exception as e:
        _log_manager.log(f"解压失败: {e}")
        _log_manager.log_error(e)
        return False


# ----------------------------------------------------------
# 7-Zip 相关
# ----------------------------------------------------------

def _code_root_dir() -> str:
    """获取 code 目录（path_ 环境变量，开发时为项目根，打包后为 <app>/code/）。"""
    path_ = os.getenv('path_')
    if path_:
        return path_
    return str(Path(__file__).resolve().parent.parent.parent)


def _downloaded_7z_exe() -> Path:
    """自动下载的 7z 可执行文件路径（code 目录下 tools/7z/）。"""
    return Path(_code_root_dir()) / 'tools' / '7z' / '7zr.exe'


def _ensure_7z_exe() -> str:
    """若环境无 7z，从官网自动下载 7zr.exe 到 code 目录 tools/7z/，返回其路径。"""
    target = _downloaded_7z_exe()
    if target.exists():
        return str(target)

    os.makedirs(target.parent, exist_ok=True)
    try:
        _log_manager.log(f"未找到 7-Zip，正在从官网自动下载 7zr.exe...")
        if not download_with(_7ZR_DOWNLOAD_URL, str(target)):
            raise RuntimeError("下载失败")
        if target.stat().st_size < _7Z_MIN_SIZE:
            raise RuntimeError(f"下载文件大小异常: {target.stat().st_size} 字节")
        with open(target, 'rb') as f:
            if f.read(2) != b'MZ':
                raise RuntimeError("下载文件不是有效的可执行程序")
        _log_manager.log(f"7zr.exe 已下载到 {target}")
        return str(target)
    except Exception as e:
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass
        _log_manager.log(f"自动下载 7zr.exe 失败: {e}")
        raise FileNotFoundError("未找到 7z 可执行文件") from e


def _find_7z_exe() -> str:
    """查找 7z 可执行文件；环境无 7z 时自动从官网下载，仍失败抛出 FileNotFoundError。"""
    # 1. 项目自带（assets/7za.exe）
    bundled = Path(__file__).parent.parent / 'assets' / '7za.exe'
    if bundled.exists():
        return str(bundled)

    # 2. 已自动下载的 7z（tools/7z/）
    for cached in (_downloaded_7z_exe(),
                   Path(_code_root_dir()) / 'tools' / '7z' / '7za.exe'):
        if cached.exists():
            return str(cached)

    # 3. 系统 PATH
    for name in ('7z', '7za', '7z.exe', '7za.exe'):
        found = shutil.which(name)
        if found:
            return found

    # 4. 常见安装路径
    for p in _SYSTEM_7Z_PATHS:
        if os.path.exists(p):
            return p

    # 5. 环境无 7z：自动从官网下载到 code 目录
    return _ensure_7z_exe()


def _extract_7z(file_path, output_dir) -> bool:
    """通过 subprocess 调用 7z 解压 .7z 文件。"""
    try:
        exe = _find_7z_exe()
    except FileNotFoundError:
        _log_manager.log(
            "================================================================"
        )
        _log_manager.log("未找到 7-Zip 且自动下载失败，无法解压 .7z 文件。")
        _log_manager.log(f"请检查网络后重试，或手动安装 7-Zip：{_7Z_DOWNLOAD_URL}")
        _log_manager.log("（或将 7z.exe 放置到程序 code 目录 tools/7z/ 下）")
        _log_manager.log(
            "================================================================"
        )
        return False

    try:
        result = subprocess.run(
            [exe, 'x', str(file_path), f'-o{output_dir}', '-y'],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            _log_manager.log(f"7z 解压失败 (返回码 {result.returncode}): {result.stderr.strip()}")
            return False
        return True
    except subprocess.TimeoutExpired:
        _log_manager.log("7z 解压超时（超过 300 秒）")
        return False
    except Exception as e:
        _log_manager.log(f"7z 解压异常: {e}")
        _log_manager.log_error(e)
        return False


def decompress_7z(file_path, output_dir='.'):
    """解压 .7z 文件到指定目录。"""
    if not os.path.exists(file_path):
        _log_manager.log(f"压缩文件不存在: {file_path}")
        return False

    if output_dir is None:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_dir = os.path.join(os.getcwd(), base_name)

    os.makedirs(output_dir, exist_ok=True)

    try:
        _log_manager.log(f"开始解压文件: {file_path}")
        if _extract_7z(file_path, output_dir):
            _log_manager.log(f"解压完成")
            return True
        return False
    except Exception as e:
        _log_manager.log(f"解压失败: {e}")
        _log_manager.log_error(e)
        return False


def decompress_by_extension(file_path, output_dir='.'):
    """根据文件扩展名自动选择解压方式（.zip / .7z）。"""
    if file_path.endswith('.zip'):
        return decompress_zip(file_path, output_dir)
    elif file_path.endswith('.7z'):
        return decompress_7z(file_path, output_dir)
    else:
        return False


# ============================================================
# 哈希计算
# ============================================================

def _hash_file(file_path, hash_obj):
    """通用文件哈希计算。"""
    if not os.path.exists(file_path):
        _log_manager.log(f"文件不存在: {file_path}")
        return None
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                hash_obj.update(byte_block)
        return hash_obj.hexdigest()
    except Exception as e:
        _log_manager.log(f"计算文件哈希失败: {e}")
        _log_manager.log_error(e)
        return None


def calculate_sha256(file_path):
    """计算指定文件的 SHA256 哈希值。"""
    return _hash_file(file_path, hashlib.sha256())


def calculate_md5(file_path):
    """计算指定文件的 MD5 哈希值。"""
    return _hash_file(file_path, hashlib.md5())
