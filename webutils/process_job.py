# -*- coding: utf-8 -*-
"""Windows Job Object 工具：把子进程绑定到父进程寿命。

当 LCTA 进程以任何方式结束（正常退出 / 被 TerminateProcess / 解释器崩溃）时，
内核会关闭 job 句柄并自动杀死其中的 aria2c 子进程，从根本上避免孤儿进程残留。

非 Windows 平台全部降级为空操作，不影响既有行为。
"""
import sys

try:
    import ctypes
    from ctypes import wintypes
except Exception:  # pragma: no cover - 非 Windows
    ctypes = None


# Windows 常量
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def _configure_kernel32(kernel32):
    """设置 kernel32 相关 API 的 argtypes/restype，避免 64 位句柄被截断。"""
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]


class ChildProcessJob:
    """无名 Job Object，设置 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE。

    典型用法::

        job = ChildProcessJob()
        proc = subprocess.Popen(...)
        job.assign(proc.pid)
        # 之后无需手动管理：父进程退出时内核杀死 proc
        # stop() 中终止 proc 后再 job.close() 释放句柄即可
    """

    def __init__(self):
        self._handle = None
        if sys.platform == "win32" and ctypes is not None:
            self._handle = self._create()

    @staticmethod
    def _create():
        if ctypes is None:
            return None
        kernel32 = ctypes.windll.kernel32
        _configure_kernel32(kernel32)
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return None
        try:

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_ulonglong),
                    ("PerJobUserTimeLimit", ctypes.c_ulonglong),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel32.SetInformationJobObject(
                handle,
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info),
                ctypes.sizeof(info),
            ):
                kernel32.CloseHandle(handle)
                return None
            return handle
        except Exception:
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass
            return None

    def assign(self, pid):
        """把指定 PID 的进程加入 job。

        失败（如父进程本身已在某 job 中、导致子进程无法二次加入）时静默跳过，
        此时退化为既有的 stop() 显式清理路径，不影响功能。
        """
        if self._handle is None or not pid:
            return False
        kernel32 = ctypes.windll.kernel32
        hproc = kernel32.OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, int(pid)
        )
        if not hproc:
            return False
        try:
            kernel32.AssignProcessToJobObject(self._handle, hproc)
            return True
        except Exception:
            return False
        finally:
            kernel32.CloseHandle(hproc)

    def close(self):
        if self._handle is not None:
            try:
                ctypes.windll.kernel32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None


def attach_kill_on_parent_exit(process):
    """便捷函数：为已存在的子进程创建 job 并加入。

    返回 ChildProcessJob（成功）或 None（非 Windows / 创建或绑定失败）。
    """
    if sys.platform != "win32" or process is None:
        return None
    job = ChildProcessJob()
    if job._handle is None:
        return None
    job.assign(getattr(process, "pid", None))
    return job
