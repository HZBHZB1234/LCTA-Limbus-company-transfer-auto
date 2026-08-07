"""输入反检测模块 - CommonLib RawInput 计数 Hook 管理器

通过注入 hooks/rawinput_hook.dll 到 LimbusCompany.exe 进程，对 CommonLib 的
RawInput 导出做 detour，控制游戏上报数据中的合成/真实输入计数：

- auto 模式：合成计数与比例恒为 0，真实计数保持 CommonLib 自身统计。
- manual 模式：4 个计数使用配置值（含真实计数，用于覆盖 PostMessage 类宏
  "既不记虚拟也不记真实"产生的双零数据）；合成比例由计数自动计算
  （synth/(real+synth)，钳制 < RATIO_MAX）；波动值（volatility，百分比）
  让 C 端 hook 按周期抖动计数再据此计算比例，避免恒定数值被检测。

配置项（launcher.work.*，计数与波动均为字符串，与 speed_factor 一致）：
    input_bypass                bool   是否在 Launcher 启动时启用
    input_bypass_mode           str    auto | manual
    input_bypass_mouse_real     str    手动模式：鼠标真实计数
    input_bypass_key_real       str    手动模式：键盘真实计数
    input_bypass_mouse_synth    str    手动模式：鼠标合成计数
    input_bypass_key_synth      str    手动模式：键盘合成计数
    input_bypass_volatility     str    手动模式：计数波动百分比 [0, 50]，0=关闭
"""

import ctypes
import ctypes.wintypes as wt
import logging
import os
import threading
from typing import Dict, List, Optional

from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager

_log_manager = LogManager()
logger = logging.getLogger(__name__)

TARGET_PROCESS = "LimbusCompany.exe"
MAP_NAME = "Local\\LCTA_RawInputHook_Config"
RH_MAGIC = 0x52484447
CONFIG_SIZE = 80  # 与 C 端 RH_CONFIG 结构大小一致

# 进程访问权限（minimal set，降低杀软误报）
PROCESS_ACCESS = (
    0x0002 | 0x0400 | 0x0008 | 0x0020 | 0x0010
)  # CREATE_THREAD|QUERY_INFORMATION|VM_OPERATION|VM_WRITE|VM_READ

TH32CS_SNAPPROCESS = 0x00000002
MAX_PATH_W = 260


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wt.ULONG)),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * MAX_PATH_W),
    ]


class RHConfig(ctypes.Structure):
    """与 hooks/rawinput_hook.c 的 RH_CONFIG 一一对应（自然对齐，80 字节）。"""

    _fields_ = [
        ("magic", ctypes.c_int32),
        ("mode", ctypes.c_int32),
        ("armed", ctypes.c_int32),
        ("volatility", ctypes.c_int32),
        ("mouse_real", ctypes.c_int64),
        ("key_real", ctypes.c_int64),
        ("mouse_synth", ctypes.c_int64),
        ("key_synth", ctypes.c_int64),
        ("mouse_ratio", ctypes.c_double),
        ("key_ratio", ctypes.c_double),
        ("commonlib_found", ctypes.c_int32),
        ("installed", ctypes.c_int32),
        ("installed_real", ctypes.c_int32),
        ("_pad2", ctypes.c_int32),
    ]


_kernel32 = ctypes.windll.kernel32

# ---- 64 位下句柄/指针必须显式声明，否则默认 c_int 截断 ----
_LPVOID = ctypes.c_void_p
_HANDLE = _LPVOID
_LPCWSTR = ctypes.c_wchar_p

_kernel32.CreateFileMappingW.restype = _HANDLE
_kernel32.CreateFileMappingW.argtypes = [
    _HANDLE, _LPVOID, wt.DWORD, wt.DWORD, wt.DWORD, _LPCWSTR,
]
_kernel32.MapViewOfFile.restype = _LPVOID
_kernel32.MapViewOfFile.argtypes = [_HANDLE, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
_kernel32.OpenProcess.restype = _HANDLE
_kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_kernel32.VirtualAllocEx.restype = _LPVOID
_kernel32.VirtualAllocEx.argtypes = [
    _HANDLE, _LPVOID, ctypes.c_size_t, wt.DWORD, wt.DWORD,
]
_kernel32.CreateRemoteThread.restype = _HANDLE
_kernel32.CreateRemoteThread.argtypes = [
    _HANDLE, _LPVOID, ctypes.c_size_t, _LPVOID, _LPVOID, wt.DWORD, _LPVOID,
]
_kernel32.GetModuleHandleW.restype = _HANDLE
_kernel32.GetModuleHandleW.argtypes = [_LPCWSTR]
_kernel32.GetProcAddress.restype = _LPVOID
_kernel32.GetProcAddress.argtypes = [_HANDLE, ctypes.c_char_p]
_kernel32.WriteProcessMemory.argtypes = [
    _HANDLE, _LPVOID, _LPVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
]
_kernel32.UnmapViewOfFile.argtypes = [_LPVOID]
_kernel32.CloseHandle.argtypes = [_HANDLE]
_kernel32.VirtualFreeEx.argtypes = [_HANDLE, _LPVOID, ctypes.c_size_t, wt.DWORD]
_kernel32.GetExitCodeThread.argtypes = [_HANDLE, ctypes.POINTER(wt.DWORD)]

# ---------------------------------------------------------------------------
# 纯解析/钳制函数（可单测）
# ---------------------------------------------------------------------------

RATIO_MAX = 0.9  # 合成比例 ≥0.9 会触发游戏的"重置判窗"逻辑，一律钳到其下
VOLATILITY_MAX = 50  # 波动值上限（百分比）


def parse_count(value: object, label: str, default: int = 0) -> int:
    """把配置值解析为 ≥0 的整数计数，非法输入回退默认值。"""
    try:
        n = int(float(str(value).strip()))
    except (TypeError, ValueError):
        _log_manager.log(f"输入反检测: {label} 不是合法数字，使用默认值 {default}")
        return default
    if n < 0:
        _log_manager.log(f"输入反检测: {label} 为负数 {n}，已钳制为 0")
        return 0
    return n


def parse_percent(value: object, label: str, default: float = 0.0) -> float:
    """把配置值解析为 [0, VOLATILITY_MAX] 的波动百分比，非法输入回退默认值。"""
    try:
        f = float(str(value).strip())
    except (TypeError, ValueError):
        _log_manager.log(f"输入反检测: {label} 不是合法数字，使用默认值 {default}")
        return default
    if f < 0.0:
        _log_manager.log(f"输入反检测: {label} 为负数 {f}，已钳制为 0")
        return 0.0
    if f > VOLATILITY_MAX:
        _log_manager.log(
            f"输入反检测: {label} 为 {f}，已钳制为 {VOLATILITY_MAX}（百分比上限）"
        )
        return float(VOLATILITY_MAX)
    return f


def parse_ratio(value: object, label: str, default: float = 0.0) -> float:
    """把配置值解析为 [0, RATIO_MAX) 的合成比例，非法输入回退默认值。"""
    try:
        f = float(str(value).strip())
    except (TypeError, ValueError):
        _log_manager.log(f"输入反检测: {label} 不是合法数字，使用默认值 {default}")
        return default
    if f < 0.0:
        _log_manager.log(f"输入反检测: {label} 为负数 {f}，已钳制为 0")
        return 0.0
    if f >= RATIO_MAX:
        _log_manager.log(
            f"输入反检测: {label} 为 {f}，已钳制为 {RATIO_MAX} "
            f"（≥{RATIO_MAX} 会触发游戏重置判窗）"
        )
        return RATIO_MAX
    return f


def auto_ratio(real: int, synth: int) -> float:
    """手动模式合成比例自动计算：synth/(real+synth)，分母为 0 时取 0。"""
    if real + synth <= 0:
        return 0.0
    return parse_ratio(synth / (real + synth), "自动计算比例")


def build_config(mode: str, armed: bool, values: Dict[str, object]) -> RHConfig:
    """根据模式与 4 个计数字段值构造共享内存配置（已钳制）。

    合成比例不来自配置，而是由计数自动计算（synth/(real+synth)）。
    """
    cfg = RHConfig()
    cfg.magic = RH_MAGIC
    cfg.mode = 1 if mode == "manual" else 0
    cfg.armed = 1 if armed else 0
    cfg.volatility = int(parse_percent(values.get("volatility", 0), "波动值"))
    cfg.mouse_real = parse_count(values.get("mouse_real", 0), "鼠标真实计数")
    cfg.key_real = parse_count(values.get("key_real", 0), "键盘真实计数")
    cfg.mouse_synth = parse_count(values.get("mouse_synth", 0), "鼠标合成计数")
    cfg.key_synth = parse_count(values.get("key_synth", 0), "键盘合成计数")
    cfg.mouse_ratio = auto_ratio(cfg.mouse_real, cfg.mouse_synth)
    cfg.key_ratio = auto_ratio(cfg.key_real, cfg.key_synth)
    return cfg


# ---------------------------------------------------------------------------
# 管理器
# ---------------------------------------------------------------------------


class InputBypassManager:
    """封装共享内存配置写入、DLL 注入/弹出、状态查询的单例管理器。"""

    _map_handle: Optional[int] = None
    _map_view: Optional[int] = None
    _map_lock = threading.Lock()
    _injected_pid: Optional[int] = None
    _remote_module: Optional[int] = None
    _cached_pid: Optional[int] = None

    # ---- 路径 / 进程检测 ----

    @classmethod
    def get_dll_path(cls) -> Optional[str]:
        """按打包/开发环境顺序查找 rawinput_hook.dll。"""
        candidates = []
        path_ = os.getenv("path_", "")
        if path_:
            candidates.append(os.path.join(path_, "hooks", "rawinput_hook.dll"))
        candidates.append(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "hooks", "rawinput_hook.dll")
        )
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    @classmethod
    def find_game_pid(cls) -> Optional[int]:
        """Toolhelp32 快照查找 LimbusCompany.exe（带 PID 存活缓存）。"""
        if cls._cached_pid is not None:
            handle = _kernel32.OpenProcess(0x1000, False, cls._cached_pid)  # QUERY_LIMITED_INFORMATION
            if handle:
                _kernel32.CloseHandle(handle)
                return cls._cached_pid
            cls._cached_pid = None

        snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == -1:
            return None
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if not _kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                return None
            while True:
                if entry.szExeFile.lower() == TARGET_PROCESS.lower():
                    cls._cached_pid = int(entry.th32ProcessID)
                    return cls._cached_pid
                if not _kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
        finally:
            _kernel32.CloseHandle(snapshot)
        return None

    # ---- 共享内存 ----

    @classmethod
    def _open_map(cls) -> bool:
        """创建/打开命名共享内存并映射。线程安全。"""
        with cls._map_lock:
            if cls._map_view is not None:
                return True
            name = ctypes.c_wchar_p(MAP_NAME)
            handle = _kernel32.CreateFileMappingW(
                -1, None, 0x04, 0, CONFIG_SIZE, name  # PAGE_READWRITE
            )
            if not handle:
                return False
            view = _kernel32.MapViewOfFile(handle, 0x0006, 0, 0, CONFIG_SIZE)  # FILE_MAP_ALL_ACCESS
            if not view:
                _kernel32.CloseHandle(handle)
                return False
            cls._map_handle = handle
            cls._map_view = view
            return True

    @classmethod
    def _write_config(cls, cfg: RHConfig) -> bool:
        if not cls._open_map():
            return False
        ctypes.memmove(cls._map_view, ctypes.byref(cfg), CONFIG_SIZE)
        return True

    @classmethod
    def _read_config(cls) -> Optional[RHConfig]:
        if not cls._open_map():
            return None
        cfg = RHConfig()
        ctypes.memmove(ctypes.byref(cfg), cls._map_view, CONFIG_SIZE)
        return cfg if cfg.magic == RH_MAGIC else None

    # ---- 配置 ----

    @classmethod
    def config_values(cls) -> Dict[str, object]:
        """从 ConfigManager 收集 4 个计数与波动值配置。"""
        return {
            "mouse_real": ConfigManager().get("launcher.work.input_bypass_mouse_real", "0"),
            "key_real": ConfigManager().get("launcher.work.input_bypass_key_real", "0"),
            "mouse_synth": ConfigManager().get("launcher.work.input_bypass_mouse_synth", "0"),
            "key_synth": ConfigManager().get("launcher.work.input_bypass_key_synth", "0"),
            "volatility": ConfigManager().get("launcher.work.input_bypass_volatility", "0"),
        }

    @classmethod
    def apply(cls) -> Dict:
        """读取当前配置写入共享内存（不注入，供 launcher 延迟注入与 WebUI 应用）。"""
        cm = ConfigManager()
        mode = cm.get("launcher.work.input_bypass_mode", "auto")
        if mode not in ("auto", "manual"):
            mode = "auto"
        armed = bool(cm.get("launcher.work.input_bypass", False))
        cfg = build_config(mode, armed, cls.config_values())
        ok = cls._write_config(cfg)
        if not ok:
            _log_manager.log("输入反检测: 无法创建共享内存")
        return {
            "success": ok,
            "armed": bool(cfg.armed),
            "mode": "manual" if cfg.mode else "auto",
        }

    # ---- 注入 / 弹出 ----

    @classmethod
    def is_injected(cls) -> bool:
        return cls._injected_pid is not None

    @classmethod
    def inject(cls, pid: Optional[int] = None) -> bool:
        """注入 rawinput_hook.dll 到 LimbusCompany.exe。

        前置条件：先调用 apply() 写入配置（否则 DLL 内 watcher 不会安装 detour）。
        """
        if pid is None:
            pid = cls.find_game_pid()
        if pid is None:
            raise RuntimeError("游戏未运行，请先启动 LimbusCompany.exe")

        if cls._injected_pid == pid and cls._remote_module is not None:
            return True

        dll_path = cls.get_dll_path()
        if not dll_path:
            raise RuntimeError("未找到 rawinput_hook.dll，请先运行 hooks/build.ps1 或重新安装")

        proc = _kernel32.OpenProcess(PROCESS_ACCESS, False, pid)
        if not proc:
            raise RuntimeError(f"无法打开游戏进程 (PID {pid})，请以管理员权限运行")

        path_w = ctypes.c_wchar_p(dll_path)
        n = (len(dll_path) + 1) * 2
        try:
            remote = _kernel32.VirtualAllocEx(proc, None, n, 0x3000, 0x04)  # MEM_COMMIT|RESERVE, PAGE_READWRITE
            if not remote:
                raise RuntimeError("VirtualAllocEx 失败")
            written = ctypes.c_size_t()
            if not _kernel32.WriteProcessMemory(proc, remote, path_w, n, ctypes.byref(written)):
                raise RuntimeError("WriteProcessMemory 失败")
            kernel32 = _kernel32.GetModuleHandleW("kernel32.dll")
            load_lib = _kernel32.GetProcAddress(kernel32, "LoadLibraryW")
            if not load_lib:
                raise RuntimeError("无法定位 LoadLibraryW")
            thread = _kernel32.CreateRemoteThread(proc, None, 0, load_lib, remote, 0, None)
            if not thread:
                raise RuntimeError("CreateRemoteThread 失败（杀毒软件可能拦截）")
            _kernel32.WaitForSingleObject(thread, 10000)
            exit_code = ctypes.c_ulong()
            _kernel32.GetExitCodeThread(thread, ctypes.byref(exit_code))
            _kernel32.CloseHandle(thread)
            if not exit_code.value:
                raise RuntimeError("DLL 加载失败（远程线程退出码为 0）")
            cls._injected_pid = pid
            cls._remote_module = int(exit_code.value)
            logger.info("已注入 rawinput_hook 到 %s (PID %d)", TARGET_PROCESS, pid)
            return True
        finally:
            if remote:
                _kernel32.VirtualFreeEx(proc, remote, 0, 0x8000)  # MEM_RELEASE
            _kernel32.CloseHandle(proc)

    @classmethod
    def eject(cls) -> bool:
        """从游戏进程弹出 DLL 并清理状态。"""
        if cls._injected_pid is None or cls._remote_module is None:
            return True
        pid = cls._injected_pid
        proc = _kernel32.OpenProcess(PROCESS_ACCESS, False, pid)
        try:
            if proc:
                kernel32 = _kernel32.GetModuleHandleW("kernel32.dll")
                free_lib = _kernel32.GetProcAddress(kernel32, "FreeLibrary")
                if free_lib:
                    param = ctypes.c_void_p(cls._remote_module)
                    thread = _kernel32.CreateRemoteThread(proc, None, 0, free_lib, param, 0, None)
                    if thread:
                        _kernel32.WaitForSingleObject(thread, 5000)
                        _kernel32.CloseHandle(thread)
        finally:
            if proc:
                _kernel32.CloseHandle(proc)
            cls._injected_pid = None
            cls._remote_module = None
            cls._cached_pid = None
        return True

    @classmethod
    def get_status(cls) -> Dict:
        """获取状态信息（供 WebUI 展示）。"""
        pid = cls.find_game_pid()
        cfg = cls._read_config()
        return {
            "running": pid is not None,
            "pid": pid,
            "dll_exists": cls.get_dll_path() is not None,
            "injected": cls.is_injected(),
            "armed": bool(cfg.armed) if cfg else False,
            "mode": "manual" if (cfg and cfg.mode) else "auto",
            "commonlib_found": bool(cfg.commonlib_found) if cfg else False,
            "installed": bool(cfg.installed) if cfg else False,
            "installed_real": bool(cfg.installed_real) if cfg else False,
        }

    @classmethod
    def close(cls):
        """弹出 DLL 并释放共享内存映射。"""
        try:
            cls.eject()
        except Exception as e:
            _log_manager.log_error(e)
        with cls._map_lock:
            if cls._map_view:
                _kernel32.UnmapViewOfFile(cls._map_view)
                cls._map_view = None
            if cls._map_handle:
                _kernel32.CloseHandle(cls._map_handle)
                cls._map_handle = None
            cls._cached_pid = None
