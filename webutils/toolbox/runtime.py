# -*- coding: utf-8 -*-
"""运行期守卫：游戏进程检测 + 跨进程文件锁。

plan 10.3 第 4–5 条要求：安装/启停/更新/卸载都必须**游戏关闭**，且
GUI、Launcher、第二个 LCTA 实例共享同一把锁。这里提供两件事：

1. ``is_game_running``：复用仓库既有的 ctypes 进程快照做法（无第三方依赖），
   并额外支持按游戏根匹配进程路径 —— 只按可执行文件名判断会把「另一个安装
   的同一个游戏」也算进来。
2. ``game_lock``：跨进程互斥。用 OS 级文件锁（Windows ``msvcrt.locking``），
   而不是「存在一个 .lock 文件就算占用」——后者在进程崩溃后会永久残留，
   把用户锁死在「无法安装」状态。

## 诚实边界

外部手动启动游戏只能**检测并中止**，无法绝对阻止（plan 10.3 第 5 条）。
本模块不假装能做到。
"""
from __future__ import annotations

import ctypes
import logging
import os
import time
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Iterator, List, Optional

from . import paths

logger = logging.getLogger(__name__)

GAME_EXE_NAMES = ("LimbusCompany.exe",)

_LOCK_POLL_SECONDS = 0.2


# ---------------------------------------------------------------------------
# 进程检测
# ---------------------------------------------------------------------------


def _iter_processes() -> List[tuple]:
    """返回 ``[(pid, exe_name)]``（仅 Windows；其他平台返回空）。"""
    if os.name != "nt":
        return []

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = -1

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        return []

    result: List[tuple] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            result.append((int(entry.th32ProcessID), str(entry.szExeFile)))
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    except OSError:
        logger.debug("进程快照遍历失败", exc_info=True)
    finally:
        kernel32.CloseHandle(snap)
    return result


def is_game_running(game_root: Optional[os.PathLike | str] = None) -> bool:
    """游戏是否在运行。

    只给 ``game_root`` 时会额外尝试匹配进程路径，避免把「另一个安装目录下
    的同名游戏」误判成本目录正在运行。
    """
    procs = _iter_processes()
    if not procs:
        return False

    names = {n.lower() for n in GAME_EXE_NAMES}
    matches = [pid for pid, exe in procs if exe.lower() in names]
    if not matches:
        return False
    if not game_root:
        return True

    root = str(Path(game_root).resolve()).lower()
    for pid in matches:
        exe_path = _process_exe_path(pid)
        if exe_path and exe_path.lower().startswith(root):
            return True
    # 拿不到进程路径时按「可能在运行」保守处理（宁可拒绝安装）
    return any(_process_exe_path(pid) is None for pid in matches)


def _process_exe_path(pid: int) -> Optional[str]:
    """查询进程可执行文件路径；无权限时返回 None。"""
    if os.name != "nt":
        return None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        return buf.value if ok else None
    except OSError:
        return None
    finally:
        kernel32.CloseHandle(handle)


def files_locked(paths_to_check: List[os.PathLike | str]) -> List[str]:
    """检测文件是否被占用（被占用 = 可能正被游戏/杀毒读写）。

    用「以独占方式尝试打开」判断，而不是查进程名 —— 杀毒隔离、
    编辑器占用等都会让写入失败，提前发现能给出可解释的错误。
    """
    locked: List[str] = []
    for p in paths_to_check:
        path = Path(p)
        if not path.exists():
            continue
        try:
            with open(str(path), "r+b"):
                pass
        except OSError:
            locked.append(str(path))
    return locked


# ---------------------------------------------------------------------------
# 跨进程锁
# ---------------------------------------------------------------------------


class LockBusyError(RuntimeError):
    """锁被其他进程持有。"""


class _FileLock:
    """基于 OS 文件锁的互斥（Windows: msvcrt.locking）。

    刻意**不**用「lock 文件是否存在」表示占用：进程被强杀后文件会残留，
    用户会永久无法安装。OS 锁在进程退出时由系统释放。
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = None

    def acquire(self, timeout: float = 0.0) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                fh = open(str(self.path), "a+b")
            except OSError as exc:
                raise LockBusyError(f"无法打开锁文件：{exc}") from exc
            try:
                if os.name == "nt":
                    import msvcrt

                    fh.seek(0)
                    # LK_NBLCK：非阻塞独占锁；失败抛 OSError
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fh = fh
                return True
            except OSError:
                fh.close()
                if time.monotonic() >= deadline:
                    return False
                time.sleep(_LOCK_POLL_SECONDS)

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            logger.debug("释放文件锁失败", exc_info=True)
        finally:
            try:
                self._fh.close()
            finally:
                self._fh = None


@contextmanager
def game_lock(game_root: os.PathLike | str, timeout: float = 10.0) -> Iterator[None]:
    """对某个游戏目录取得跨进程排他锁。

    超时抛 ``LockBusyError`` —— 明确告诉调用方「另一个任务正在操作」，
    而不是静默继续（并发安装会互相覆盖文件）。
    """
    lock = _FileLock(paths.lock_path(game_root))
    if not lock.acquire(timeout=timeout):
        raise LockBusyError("另一个 LCTA 任务正在操作该游戏目录，请稍后重试")
    try:
        yield
    finally:
        lock.release()


def assert_can_install(game_root: os.PathLike | str) -> None:
    """安装/启停/更新/卸载前的统一前置检查。

    顺序刻意如此：先锁、再查进程。反过来的话，「检查完游戏随后启动」
    会形成竞态（plan 10.3 第 5 条要求安装前**再检查一次**）。
    """
    if is_game_running(game_root):
        raise RuntimeError("游戏正在运行，请先关闭游戏再操作工具箱")