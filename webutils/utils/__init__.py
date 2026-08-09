"""webutils.utils 门面：集中 re-export 拆分后的公共工具 API。"""

from __future__ import annotations

from .font import get_cache_font, save_cache_font
from .io import (
    zip_folder,
    extract_zip_smartly,
    decompress_zip,
    decompress_7z,
    decompress_by_extension,
    calculate_sha256,
    calculate_md5,
)
from .misc import get_steam_command, change_icon
from .net import download_with, download_with_github
from .shell import _move_folders

__all__ = [
    'zip_folder',
    'extract_zip_smartly',
    'decompress_zip',
    'decompress_7z',
    'decompress_by_extension',
    'download_with',
    'download_with_github',
    'calculate_sha256',
    'calculate_md5',
    'get_cache_font',
    'save_cache_font',
    'get_steam_command',
    'change_icon',
    '_move_folders',
]
