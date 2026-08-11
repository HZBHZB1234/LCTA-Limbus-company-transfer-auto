"""Windows Shell API 文件操作工具函数。"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

FO_MOVE = 0x0001
FO_COPY = 0x0002
FO_DELETE = 0x0003
FO_RENAME = 0x0004

FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_SILENT = 0x0004
FOF_SIMPLEPROGRESS = 0x0100
FOF_NOCONFIRMMKDIR = 0x0200

# FOLDERID_Downloads
_FOLDERID_DOWNLOADS = (
    0x374DE290, 0x123F, 0x4565, (0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B)
)


class _GUID(ctypes.Structure):
    _fields_ = [
        ('Data1', wintypes.DWORD),
        ('Data2', wintypes.WORD),
        ('Data3', wintypes.WORD),
        ('Data4', wintypes.BYTE * 8),
    ]


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

try:
    _ole32 = ctypes.windll.ole32
except Exception:  # pragma: no cover - 非 Windows
    _ole32 = None


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


def get_downloads_dir() -> str:
    """解析系统真实的「下载」目录（支持用户迁移/重定向后的已知文件夹）。

    优先用 SHGetKnownFolderPath(FOLDERID_Downloads)，失败或非 Windows
    时回退 Path.home() / "Downloads"。
    """
    if os.name == "nt":
        try:
            _shell32.SHGetKnownFolderPath.restype = ctypes.POINTER(wintypes.WCHAR)
            _shell32.SHGetKnownFolderPath.argtypes = [
                ctypes.POINTER(_GUID), wintypes.DWORD,
                wintypes.HANDLE, ctypes.POINTER(ctypes.POINTER(wintypes.WCHAR)),
            ]
            guid = _GUID(*_FOLDERID_DOWNLOADS)
            path_ptr = ctypes.POINTER(wintypes.WCHAR)()
            if _shell32.SHGetKnownFolderPath(
                ctypes.byref(guid), 0, None, ctypes.byref(path_ptr)
            ) == 0 and path_ptr:
                try:
                    return ctypes.wstring_at(path_ptr)
                finally:
                    _ole32.CoTaskMemFree(path_ptr)
        except Exception:
            pass
    return str(Path.home() / "Downloads")
