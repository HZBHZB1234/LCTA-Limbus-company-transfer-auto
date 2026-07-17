"""文件操作、下载、哈希计算与 Windows Shell API 工具函数。"""

# ============================================================
# 标准库
# ============================================================
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from ctypes import wintypes
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set

# ============================================================
# 第三方库
# ============================================================
import requests

# ============================================================
# 本地模块
# ============================================================
from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager

if TYPE_CHECKING:
    from webFunc.GithubDownload import ReleaseAsset

# ============================================================
# 模块级初始化
# ============================================================
_log_manager = LogManager()
_7Z_DOWNLOAD_URL = "https://www.7-zip.org/"


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
    except Exception as e:
        _log_manager.log(f"解压失败: {e}")
        _log_manager.log_error(e)
        return False


# ----------------------------------------------------------
# 7-Zip 相关
# ----------------------------------------------------------

def _find_7z_exe() -> str:
    """查找 7z 可执行文件，找不到抛出 FileNotFoundError。"""
    # 1. 项目自带（assets/7za.exe）
    bundled = Path(__file__).parent.parent / 'assets' / '7za.exe'
    if bundled.exists():
        return str(bundled)

    # 2. 系统 PATH
    for name in ('7z', '7za', '7z.exe', '7za.exe'):
        found = shutil.which(name)
        if found:
            return found

    # 3. 常见安装路径
    for p in (r'C:\Program Files\7-Zip\7z.exe',
              r'C:\Program Files (x86)\7-Zip\7z.exe'):
        if os.path.exists(p):
            return p

    raise FileNotFoundError("未找到 7z 可执行文件")


def _extract_7z(file_path, output_dir) -> bool:
    """通过 subprocess 调用 7z 解压 .7z 文件。"""
    try:
        exe = _find_7z_exe()
    except FileNotFoundError:
        _log_manager.log(
            "================================================================"
        )
        _log_manager.log("未找到 7-Zip，无法解压 .7z 文件。")
        _log_manager.log(f"请安装 7-Zip：{_7Z_DOWNLOAD_URL}")
        _log_manager.log("（或手动将 7z.exe 放置到程序 assets/ 目录下）")
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
# 下载
# ============================================================

def download_with(url, save_path, size=0, chunk_size=1024 * 100,
                  modal_id=None, progress_=[0, 100], headers={}, validate=True):
    """从指定 URL 下载文件，支持进度回调。"""
    try:
        with requests.get(url, stream=True, headers=headers, verify=validate) as r:
            r.raise_for_status()

            if size == 0:
                total_size = int(r.headers.get('Content-Length', 0))
            else:
                total_size = size
            chunk_len = total_size // chunk_size + 1
            downloaded_chunk = 0

            _log_manager.log(f"开始下载文件，总大小: {total_size // 1024} KB")

            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if modal_id:
                        _log_manager.check_running(modal_id, log=False)
                    f.write(chunk)

                    downloaded_chunk += 1
                    _log_manager.update_modal_progress(
                        progress_[0] + (progress_[1] - progress_[0]) * downloaded_chunk / chunk_len,
                        f"已下载 {downloaded_chunk * chunk_size // 1024} KB / {total_size // 1024} KB",
                        modal_id, log=True
                    )

            _log_manager.log("\n下载完成")
        return True
    except Exception as e:
        _log_manager.log(f"\n下载失败: {e}")
        _log_manager.log_error(e)
        return False


def download_with_github(asset: 'ReleaseAsset', save_path, chunk_size=1024 * 100,
                         modal_id=None,
                         progress_=[0, 100], use_proxy=True):
    """下载 ReleaseAsset 中的文件，支持代理轮换重试。"""
    if not asset:
        _log_manager.log("ReleaseAsset 为空，无法下载")
        return False

    # 确保保存目录存在
    save_dir = os.path.dirname(save_path)
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)

    if not use_proxy or not hasattr(asset, 'proxys') or not asset.proxys:
        _log_manager.log(f"不使用代理，直接下载: {asset.name}")
        return download_with(
            asset.download_url, save_path,
            size=asset.size, chunk_size=chunk_size,
            modal_id=modal_id,
            progress_=progress_
        )

    proxy_manager = asset.proxys

    def _build_url(proxy_url: str):
        if not proxy_url:
            return asset.download_url
        return proxy_url.rstrip('/') + '/' + asset.download_url.lstrip('/')

    _log_manager.log(f"开始下载 {asset.name} (大小: {asset.size} bytes)")

    len_proxies = len(proxy_manager.proxies)
    for i, proxy in enumerate(proxy_manager.get_proxies()):
        try:
            url = _build_url(proxy)
            _log_manager.log(f"尝试下载 (代理 {i + 1}/{len_proxies}): {url}")

            success = download_with(
                url, save_path,
                size=asset.size, chunk_size=chunk_size,
                modal_id=modal_id,
                progress_=progress_,
                headers={
                    'Accept': 'application/octet-stream',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )

            if success:
                if os.path.exists(save_path):
                    actual_size = os.path.getsize(save_path)
                    if asset.size > 0 and actual_size != asset.size:
                        _log_manager.log(f"警告: 文件大小不匹配。期望: {asset.size}, 实际: {actual_size}")
                        continue

                    _log_manager.log(f"下载成功! 使用链接 {url}")
                    proxy_manager.set_proxy_by_url(proxy)
                    return True
                else:
                    _log_manager.log(f"文件未创建: {save_path}")
                    raise FileNotFoundError(f"文件未创建: {save_path}")
            else:
                _log_manager.log(f"下载失败 (URL {i + 1}/{len_proxies})")

        except Exception as e:
            _log_manager.log(f"下载失败 (URL {i + 1}/{len_proxies}): {e}")
            _log_manager.log_error(e)
            time.sleep(0.1)

    _log_manager.log(f"所有下载尝试都失败: {asset.name}")
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


# ============================================================
# 字体缓存
# ============================================================

def get_cache_font() -> str:
    """获取缓存中的中文字体路径。"""
    game_path = ConfigManager().get('game_path', '')
    cache_normal = os.path.join(game_path, 'LimbusCompany_Data', 'lang', 'LLC_zh-CN', 'Font', 'Context', 'ChineseFont.ttf')
    if ConfigManager().get('enable_cache', False):
        cache_path = Path(ConfigManager().get('cache_path', '')) / 'ChineseFont.ttf'
        if cache_path.exists():
            return str(cache_path)
        else:
            cache_path = Path(cache_normal)
            if cache_path.exists():
                return str(cache_path)
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    from .function_llc import font_assets_seven
                    download_with_github(
                        font_assets_seven, Path(temp_dir) / 'font.7z',
                        chunk_size=1024 * 100
                    )
                    r = decompress_7z(Path(temp_dir) / 'font.7z',
                                      ConfigManager().get('cache_path', '.'))
                    if r:
                        return get_cache_font()
            except Exception as e:
                _log_manager.log_error(e)
                return cache_normal

    cache_path = Path(cache_normal)
    if cache_path.exists():
        return str(cache_path)
    else:
        return ''


# ============================================================
# Steam 启动命令
# ============================================================

def get_steam_command():
    """生成用于 Steam 启动选项的命令行字符串。"""
    froze = os.getenv('is_frozen', '')
    cwd = Path(os.getcwd())
    if froze == 'true':
        this_launcher = list(cwd.glob('LCTA*.exe'))[0]
    elif froze == 'false':
        if os.getenv('debug', '') == 'true':
            this_launcher = cwd / 'start_webui.py'
            if not this_launcher.exists():
                raise FileNotFoundError(f"启动脚本不存在: {this_launcher}")
            if (cwd / 'venv').exists():
                cmd = f'"{cwd / "venv" / "Scripts" / "python.exe"}" "{this_launcher}" -launcher %command%'
                return cmd
        else:
            this_launcher = cwd / 'launcher.exe'
            if not this_launcher.exists():
                raise FileNotFoundError(f"启动器不存在: {this_launcher}")
    else:
        raise RuntimeError(f"未知的 is_frozen 值: {froze}")
    cmd = f'"{this_launcher}" -launcher %command%'
    return cmd


# ============================================================
# 窗口图标（占位）
# ============================================================

def change_icon():
    """更改窗口图标（暂未实现）。"""
    return


# ============================================================
# Windows Shell API 文件操作
# ============================================================

FO_MOVE = 0x0001
FO_COPY = 0x0002
FO_DELETE = 0x0003
FO_RENAME = 0x0004

FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_SILENT = 0x0004
FOF_SIMPLEPROGRESS = 0x0100
FOF_NOCONFIRMMKDIR = 0x0200


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ('hwnd', wintypes.HWND),
        ('wFunc', ctypes.c_uint),
        ('pFrom', ctypes.c_void_p),
        ('pTo', ctypes.c_void_p),
        ('fFlags', ctypes.c_uint),
        ('fAnyOperationsAborted', wintypes.BOOL),
        ('hNameMappings', ctypes.c_void_p),
        ('lpszProgressTitle', ctypes.c_wchar_p),
    ]


_shell32 = ctypes.windll.shell32
_SHFileOperationW = _shell32.SHFileOperationW
_SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
_SHFileOperationW.restype = ctypes.c_int


def _move_folders(src_list, dst_dir, hwnd=None,
                  flags=FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOCONFIRMMKDIR):
    """使用 Windows Shell API 移动多个文件夹（支持跨驱动器）。"""
    src_str = '\0'.join(src_list) + '\0'
    src_buffer = ctypes.create_unicode_buffer(src_str)

    dst_str = dst_dir + '\0'
    dst_buffer = ctypes.create_unicode_buffer(dst_str)

    op = SHFILEOPSTRUCTW()
    op.hwnd = hwnd if hwnd is not None else None
    op.wFunc = FO_MOVE
    op.pFrom = ctypes.addressof(src_buffer)
    op.pTo = ctypes.addressof(dst_buffer)
    op.fFlags = flags
    op.fAnyOperationsAborted = False
    op.hNameMappings = None
    op.lpszProgressTitle = None

    ret = _SHFileOperationW(ctypes.byref(op))

    aborted = op.fAnyOperationsAborted != 0
    success = (ret == 0) and not aborted

    return success, aborted, ret
