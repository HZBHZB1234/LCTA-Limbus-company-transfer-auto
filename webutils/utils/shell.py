"""Windows Shell API 文件操作工具函数。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

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
