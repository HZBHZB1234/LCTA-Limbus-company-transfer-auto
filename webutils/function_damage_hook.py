"""伤害倍率 Hook 管理器 - GameAssembly.dll 原生 MinHook detour

通过注入 hooks/damage_hook.dll 到 LimbusCompany.exe，对
BattleUnitModel$$GetTakeAttackDmgMultiplier（基类实现）做 MinHook detour：
当受伤方是敌人时把返回值乘以 multiplier（默认 3.0）。所有子类覆写最终都
call 基类实现，单点 detour 全覆盖（详见 docs/DAMAGE_HOOK.md）。

偏移数据不内嵌编译期常量，而是从 JSON API 获取（默认
https://web.lcta.top/damage_hook.json，可用 launcher.work.damage_hook_api
覆盖），并做本地缓存 + 游戏更新自动失效：

- 缓存键 = 本地 GameAssembly.dll SHA-256（版本锚定，与 MINHOOK_GUIDE.md
  的 08-06 构建验证方式一致）；缓存文件与本地指纹元数据存放于
  %LOCALAPPDATA%/LCTA/damage-hook/。
- 命中判定：本地 GameAssembly.dll 哈希与缓存记录的哈希一致 → 直接使用缓存，
  不发网络请求（140MB 文件只算一次哈希，mtime/size 未变时跳过重算）。
- 失效路径：
  1. 启动前：本地哈希与缓存不一致（游戏已更新）→ 拉 API 刷新缓存；
     API 尚未发布新版偏移（payload 哈希 != 本地哈希）→ 保留旧缓存并标记
     stale，降级用旧偏移注入（用户确认保留降级）。
  2. 运行中：游戏更新 → DLL 内 prologue 自检失败回写 verified=0 →
     管理器检测后强制刷新偏移、重写共享内存并置 retry_requested →
     DLL 热摘除旧钩并按新偏移重装（进程无需重启）。

配置项（launcher.work.*）：
    damage_hook               bool   是否在 Launcher 启动时注入
    damage_hook_multiplier    str    伤害倍率（默认 3.0，钳制 [0.1, 1000]）
    damage_hook_log           bool   伤害事件日志开关（DLL 写入共享内存环形缓冲，
                                     后台线程增量抽取后经 LogManager 落盘 logs/app.log）
    damage_hook_api           str    偏移 JSON API 地址
"""

import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import logging
import os
import threading
from typing import Dict, Optional

import requests

from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager

_log_manager = LogManager()
logger = logging.getLogger(__name__)

TARGET_PROCESS = "LimbusCompany.exe"
MAP_NAME = "Local\\LCTA_DamageHook_Config"
DH_MAGIC = 0x44484744
LOG_RING_CAP = 128  # 与 C 端 DH_LOG_RING_CAP 一致（2 的幂）
LOG_RING_INTERVAL = 0.5  # 伤害日志抽取线程轮询间隔（秒）

DEFAULT_API_URL = "https://web.lcta.top/damage_hook.json"
MULTIPLIER_MIN = 0.1
MULTIPLIER_MAX = 1000.0

# 与 C 端 DH_ERR_* 一致
DH_ERR_TEXT = {
    0: "正常",
    1: "共享内存不可用",
    2: "GameAssembly.dll 60 秒内未加载",
    3: "版本不匹配（prologue 校验失败）",
    4: "MinHook 初始化失败",
    5: "MinHook 创建钩子失败",
    6: "MinHook 启用钩子失败",
}

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


class DHConfig(ctypes.Structure):
    """与 hooks/damage_hook.c 的 DH_CONFIG 一一对应（自然对齐，16584 字节）。"""

    _fields_ = [
        ("magic", ctypes.c_int32),
        ("enabled", ctypes.c_int32),
        ("log", ctypes.c_int32),
        ("retry_requested", ctypes.c_int32),
        ("multiplier", ctypes.c_float),
        ("rva_take_attack", ctypes.c_int32),
        ("rva_opponent_faction", ctypes.c_int32),
        ("prologue", ctypes.c_ubyte * 16),
        ("gameassembly_found", ctypes.c_int32),
        ("verified", ctypes.c_int32),
        ("installed", ctypes.c_int32),
        ("last_error", ctypes.c_int32),
        ("log_count", ctypes.c_int32),
        ("last_log", ctypes.c_char * 128),
        ("log_head", ctypes.c_int32),
        ("log_ring", (ctypes.c_char * 128) * LOG_RING_CAP),
        ("_pad", ctypes.c_int32),
    ]


CONFIG_SIZE = ctypes.sizeof(DHConfig)  # 16584，与 C 端 DH_CONFIG 结构大小一致


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
# 纯解析/校验函数（可单测）
# ---------------------------------------------------------------------------


def parse_multiplier(value: object, default: float = 3.0) -> float:
    """把配置值解析为 [MULTIPLIER_MIN, MULTIPLIER_MAX] 的倍率。"""
    try:
        f = float(str(value).strip())
    except (TypeError, ValueError):
        _log_manager.log(f"伤害倍率: 倍率 {value!r} 不是合法数字，使用默认值 {default}")
        return default
    if f < MULTIPLIER_MIN:
        _log_manager.log(f"伤害倍率: 倍率 {f} 小于下限，已钳制为 {MULTIPLIER_MIN}")
        return MULTIPLIER_MIN
    if f > MULTIPLIER_MAX:
        _log_manager.log(f"伤害倍率: 倍率 {f} 超过上限，已钳制为 {MULTIPLIER_MAX}")
        return MULTIPLIER_MAX
    return f


def parse_prologue_bytes(value: object) -> Optional[bytes]:
    """把 "48 8B C4 ..." 形式的 prologue 解析为 16 字节；非法返回 None。"""
    if isinstance(value, bytes):
        value = value.decode("ascii", "ignore")
    if not isinstance(value, str):
        return None
    try:
        raw = bytes.fromhex("".join(value.split()))
    except ValueError:
        return None
    if len(raw) != 16:
        return None
    return raw


def validate_payload(payload: Dict) -> Optional[Dict]:
    """校验 API payload（已展开的 damage_hook 对象），合法返回规范化 dict。"""
    try:
        gameassembly_sha256 = str(payload["gameassembly_sha256"]).strip().upper()
        if len(gameassembly_sha256) != 64 or any(
            c not in "0123456789ABCDEF" for c in gameassembly_sha256
        ):
            return None
        rva_take = int(payload["rva_get_take_attack_dmg_multiplier"])
        rva_faction = int(payload["rva_get_opponent_faction"])
        if rva_take <= 0 or rva_faction <= 0:
            return None
        prologue = parse_prologue_bytes(payload.get("prologue"))
        if prologue is None:
            return None
        size = int(payload.get("gameassembly_size", 0) or 0)
        return {
            "game_version": str(payload.get("game_version", "unknown")),
            "gameassembly_sha256": gameassembly_sha256,
            "gameassembly_size": size,
            "rva_get_take_attack_dmg_multiplier": int(rva_take),
            "rva_get_opponent_faction": int(rva_faction),
            "prologue": " ".join(f"{b:02X}" for b in prologue),
        }
    except (KeyError, TypeError, ValueError):
        return None


def extract_damage_hook_payload(data: Dict) -> Dict:
    """兼容两种响应：{damage_hook: {...}} 或直接是 payload。"""
    if isinstance(data.get("damage_hook"), dict):
        return data["damage_hook"]
    return data


def build_config(offsets: Dict, multiplier: float, enabled: bool, log: bool) -> DHConfig:
    """根据偏移与配置构造共享内存配置（已钳制）。"""
    cfg = DHConfig()
    cfg.magic = DH_MAGIC
    cfg.enabled = 1 if enabled else 0
    cfg.log = 1 if log else 0
    cfg.retry_requested = 0
    cfg.multiplier = multiplier
    cfg.rva_take_attack = int(offsets["rva_get_take_attack_dmg_multiplier"])
    cfg.rva_opponent_faction = int(offsets["rva_get_opponent_faction"])
    prologue = bytes.fromhex(offsets["prologue"].replace(" ", ""))
    for i in range(16):
        cfg.prologue[i] = prologue[i]
    return cfg


def _decode_log_entry(raw: bytes) -> str:
    """把环形缓冲里的一条日志清洗为可读字符串（NUL 截断 + 非法字节丢弃）。"""
    return raw.split(b"\x00", 1)[0].decode("utf-8", "ignore").strip()


def drain_new_log_entries(cfg: DHConfig, last_count: int) -> Dict:
    """从共享内存环形缓冲中抽取自 last_count 以来的新伤害日志条目。

    返回 {"entries": [str, ...], "count": 新总计数, "dropped": 因缓冲溢出被
    覆盖丢弃的条数}：
    - count < last_count（共享内存被重写/重建）→ 视作重置，只抽取当前剩余。
    - 增量超过容量 → 中间条目已被覆盖，返回容量内的最新条目并计 dropped。
    - 槽位 = log_head % CAP，head 单调递增，条目先写后增 head，无半条。
    """
    count = int(cfg.log_count)
    head = int(cfg.log_head)
    if count < 0 or head < 0:
        return {"entries": [], "count": count if count >= 0 else 0,
                "dropped": 0}
    if count < last_count or last_count < 0:
        last_count = 0
    new = count - last_count
    dropped = 0
    if new <= 0:
        return {"entries": [], "count": count, "dropped": 0}
    if new > LOG_RING_CAP:
        dropped = new - LOG_RING_CAP
        new = LOG_RING_CAP
    start = head - new
    entries = []
    for i in range(new):
        raw = bytes(cfg.log_ring[(start + i) % LOG_RING_CAP])
        text = _decode_log_entry(raw)
        if text:
            entries.append(text)
    return {"entries": entries, "count": count, "dropped": dropped}


# ---------------------------------------------------------------------------
# 缓存路径 / 本地指纹
# ---------------------------------------------------------------------------


def cache_dir() -> str:
    """缓存目录：环境变量覆盖优先，默认 %LOCALAPPDATA%/LCTA/damage-hook。"""
    override = os.getenv("LCTA_DAMAGE_HOOK_CACHE", "").strip()
    if override:
        return override
    base = os.getenv("LOCALAPPDATA")
    if base:
        return os.path.join(base, "LCTA", "damage-hook")
    return os.path.join(os.path.expanduser("~"), ".lcta", "damage-hook")


def offsets_cache_path() -> str:
    return os.path.join(cache_dir(), "offsets-cache.json")


def local_meta_path() -> str:
    return os.path.join(cache_dir(), "local-meta.json")


def sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def local_gameassembly_hash() -> Optional[Dict]:
    """本地 GameAssembly.dll 的 {sha256, size}，带 mtime/size 元数据缓存。

    GameAssembly.dll 约 140MB，全量哈希约 0.5-1s；mtime+size 未变时跳过重算。
    文件缺失（游戏未安装/未配置）返回 None。
    """
    game_path = str(ConfigManager().get("game_path", "")).strip()
    if not game_path:
        return None
    ga = os.path.join(game_path, "GameAssembly.dll")
    if not os.path.isfile(ga):
        return None

    try:
        st = os.stat(ga)
        meta = {}
        meta_path = local_meta_path()
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        if (
            meta.get("path") == ga
            and meta.get("size") == st.st_size
            and meta.get("mtime") == st.st_mtime
            and len(str(meta.get("sha256", ""))) == 64
        ):
            return {"sha256": meta["sha256"], "size": st.st_size, "from_cache": True}
    except (OSError, json.JSONDecodeError):
        meta = {}

    digest = sha256_of_file(ga)
    try:
        os.makedirs(cache_dir(), exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {"path": ga, "size": st.st_size, "mtime": st.st_mtime,
                 "sha256": digest},
                f,
            )
    except OSError:
        pass
    return {"sha256": digest, "size": st.st_size, "from_cache": False}


# ---------------------------------------------------------------------------
# 管理器
# ---------------------------------------------------------------------------


class DamageHookManager:
    """封装偏移缓存/API 拉取、共享内存写入、DLL 注入/弹出、状态查询。"""

    _map_handle: Optional[int] = None
    _map_view: Optional[int] = None
    _map_lock = threading.Lock()
    _injected_pid: Optional[int] = None
    _remote_module: Optional[int] = None
    _cached_pid: Optional[int] = None
    _offsets: Optional[Dict] = None      # 最近一次 resolve 结果（含 source/stale）
    _offsets_lock = threading.Lock()

    # 伤害日志抽取线程：DLL 写共享内存环形缓冲 → 后台线程增量抽取 → LogManager 落盘
    _drain_thread: Optional[threading.Thread] = None
    _drain_stop: Optional[threading.Event] = None
    _drained_count: int = 0

    # ---- 路径 / 进程检测 ----

    @classmethod
    def get_dll_path(cls) -> Optional[str]:
        """按打包/开发环境顺序查找 damage_hook.dll。"""
        candidates = []
        path_ = os.getenv("path_", "")
        if path_:
            candidates.append(os.path.join(path_, "hooks", "damage_hook.dll"))
        candidates.append(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "hooks", "damage_hook.dll")
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

    # ---- 偏移获取（API + 缓存 + 自动失效） ----

    @classmethod
    def api_url(cls) -> str:
        url = str(ConfigManager().get("launcher.work.damage_hook_api", "")).strip()
        return url or DEFAULT_API_URL

    @classmethod
    def _read_cache(cls) -> Optional[Dict]:
        try:
            with open(offsets_cache_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    @classmethod
    def _write_cache(cls, local_hash: str, local_size: int, offsets: Dict) -> None:
        try:
            os.makedirs(cache_dir(), exist_ok=True)
            with open(offsets_cache_path(), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "fetched_at": None,  # 保留旧字段名兼容（见 _read_cache）
                        "local_sha256": local_hash,
                        "local_size": local_size,
                        "offsets": offsets,
                    },
                    f,
                    ensure_ascii=False,
                )
        except OSError as e:
            _log_manager.log(f"伤害倍率: 写入偏移缓存失败: {e}")

    @classmethod
    def _fetch_from_api(cls) -> Optional[Dict]:
        """拉取并校验 API payload；返回规范化 offsets dict 或 None。"""
        url = cls.api_url()
        try:
            resp = requests.get(url, timeout=(10, 30))
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            _log_manager.log(f"伤害倍率: 拉取偏移 API 失败: {e}")
            return None
        except ValueError:
            _log_manager.log("伤害倍率: 偏移 API 返回非 JSON 内容")
            return None
        if not isinstance(data, dict):
            _log_manager.log("伤害倍率: 偏移 API 返回格式错误")
            return None
        offsets = validate_payload(extract_damage_hook_payload(data))
        if offsets is None:
            _log_manager.log("伤害倍率: 偏移 API payload 校验失败（字段缺失或格式错误）")
            return None
        return offsets

    @classmethod
    def resolve_offsets(cls, force_refresh: bool = False) -> Dict:
        """获取偏移（带缓存与游戏更新自动失效）。

        返回 {success, source, stale, reason, offsets, local_sha256, ...}：
        - 本地哈希 == 缓存哈希 → source=cache, stale=False
        - 哈希不一致或 force → 拉 API：
            API 哈希 == 本地哈希 → source=api, 写入缓存, stale=False
            API 哈希 != 本地哈希（新版未发布）→ 保留旧缓存, stale=True（降级）
            拉取失败 → 有旧缓存则 stale=True（降级），否则失败
        - 本地 GameAssembly.dll 缺失 → 失败（reason=game_missing）
        """
        local = local_gameassembly_hash()
        if local is None:
            return {"success": False, "reason": "game_missing",
                    "message": "未找到 GameAssembly.dll（请先在设置中配置游戏目录）"}

        cache = cls._read_cache()
        cached_ok = (
            cache is not None
            and cache.get("local_sha256") == local["sha256"]
            and isinstance(cache.get("offsets"), dict)
            and validate_payload(cache["offsets"]) is not None
        )
        if cached_ok and not force_refresh:
            offsets = cache["offsets"]
            with cls._offsets_lock:
                cls._offsets = {"source": "cache", "stale": False, "offsets": offsets}
            return {"success": True, "source": "cache", "stale": False,
                    "offsets": offsets, "local_sha256": local["sha256"],
                    "message": f"使用缓存偏移（版本 {offsets.get('game_version', '?')}）"}

        if force_refresh:
            _log_manager.log("伤害倍率: 手动/检测到更新，刷新偏移...")

        api_offsets = cls._fetch_from_api()
        if api_offsets is not None and api_offsets["gameassembly_sha256"] == local["sha256"]:
            cls._write_cache(local["sha256"], local["size"], api_offsets)
            with cls._offsets_lock:
                cls._offsets = {"source": "api", "stale": False, "offsets": api_offsets}
            return {"success": True, "source": "api", "stale": False,
                    "offsets": api_offsets, "local_sha256": local["sha256"],
                    "message": f"已从 API 获取新偏移（版本 {api_offsets['game_version']}）"}

        if api_offsets is not None:
            _log_manager.log(
                "伤害倍率: API 尚未发布当前游戏版本的偏移，保留旧缓存降级使用"
            )

        # 降级路径：旧缓存存在则继续使用（标记 stale）
        if cache is not None and isinstance(cache.get("offsets"), dict):
            offsets = cache["offsets"]
            if validate_payload(offsets) is None:
                offsets = None
        else:
            offsets = None

        if offsets is not None:
            with cls._offsets_lock:
                cls._offsets = {"source": "cache", "stale": True, "offsets": offsets}
            return {"success": True, "source": "cache", "stale": True,
                    "offsets": offsets, "local_sha256": local["sha256"],
                    "message": "游戏已更新但偏移尚未发布，使用旧偏移降级注入（可能不生效）"}
        return {"success": False, "reason": "no_offsets",
                "message": "无法获取伤害倍率偏移（网络不可用且无本地缓存）"}

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
            cls._start_drain_thread()
            return True

    @classmethod
    def _write_config(cls, cfg: DHConfig) -> bool:
        if not cls._open_map():
            return False
        ctypes.memmove(cls._map_view, ctypes.byref(cfg), CONFIG_SIZE)
        return True

    @classmethod
    def _read_config(cls) -> Optional[DHConfig]:
        if not cls._open_map():
            return None
        cfg = DHConfig()
        ctypes.memmove(ctypes.byref(cfg), cls._map_view, CONFIG_SIZE)
        return cfg if cfg.magic == DH_MAGIC else None

    # ---- 配置 ----

    @classmethod
    def apply(cls, offsets: Optional[Dict] = None) -> Dict:
        """解析偏移（或使用调用方传入）并写入共享内存。

        若 DLL 已注入且已装钩（installed=1），自动置 retry_requested=1，
        让 DLL 按新偏移热重装（游戏更新后无需重启进程）。
        """
        cm = ConfigManager()
        enabled = bool(cm.get("launcher.work.damage_hook", False))
        multiplier = parse_multiplier(cm.get("launcher.work.damage_hook_multiplier", "3.0"))
        log = bool(cm.get("launcher.work.damage_hook_log", False))

        if offsets is None:
            result = cls.resolve_offsets()
            if not result["success"]:
                _log_manager.log(f"伤害倍率: {result['message']}")
                return {"success": False, "message": result["message"]}
            offsets = result["offsets"]

        prev = cls._read_config()
        retry = 1 if (prev is not None and prev.installed) else 0

        cfg = build_config(offsets, multiplier, enabled, log)
        cfg.retry_requested = retry
        ok = cls._write_config(cfg)
        if not ok:
            _log_manager.log("伤害倍率: 无法创建共享内存")
        else:
            _log_manager.log(
                f"伤害倍率: 配置已写入（倍率 {multiplier}，"
                f"{'启用' if enabled else '未启用'}，"
                f"偏移来自{cfg.rva_take_attack:#x}，retry={retry}）"
            )
        return {
            "success": ok,
            "enabled": enabled,
            "multiplier": multiplier,
            "retry_requested": bool(retry),
        }

    # ---- 伤害日志抽取（共享内存环形缓冲 → LogManager 落盘 logs/app.log） ----

    @classmethod
    def _start_drain_thread(cls) -> None:
        """启动后台抽取线程（幂等）。DLL 写环形缓冲后逐条写入本地日志。"""
        if cls._drain_thread is not None and cls._drain_thread.is_alive():
            return
        cls._drain_stop = threading.Event()  # 每代线程新建事件，避免复用已置位事件
        cls._drained_count = 0
        thread = threading.Thread(
            target=cls._drain_loop, name="damage-hook-log-drain", daemon=True
        )
        thread.start()
        cls._drain_thread = thread

    @classmethod
    def _drain_loop(cls) -> None:
        """轮询共享内存并抽取新日志条目；共享内存关闭或 stop 事件置位时退出。"""
        stop = cls._drain_stop
        while stop is None or not stop.is_set():
            try:
                cls._drain_and_log()
            except Exception as e:
                _log_manager.log_error(e)
            stop.wait(LOG_RING_INTERVAL)

    @classmethod
    def _drain_and_log(cls) -> None:
        """抽取自上次以来的新日志条目并经 LogManager 写入本地日志。

        与 close() 的共享内存释放互斥：读取在 _map_lock 内完成（拷贝出 cfg
        副本后再处理日志），避免 UnmapViewOfFile 与 memmove 竞争。
        """
        with cls._map_lock:
            if cls._map_view is None:
                return
            cfg = DHConfig()
            ctypes.memmove(ctypes.byref(cfg), cls._map_view, CONFIG_SIZE)
        if cfg.magic != DH_MAGIC:
            return
        result = drain_new_log_entries(cfg, cls._drained_count)
        cls._drained_count = result["count"]
        for entry in result["entries"]:
            _log_manager.log(f"伤害倍率: {entry}")
        if result["dropped"]:
            _log_manager.log(
                f"伤害倍率: 有 {result['dropped']} 条伤害日志因缓冲溢出被覆盖丢弃"
            )

    # ---- 注入 / 弹出 ----

    @classmethod
    def is_injected(cls) -> bool:
        return cls._injected_pid is not None

    @classmethod
    def inject(cls, pid: Optional[int] = None) -> bool:
        """注入 damage_hook.dll 到 LimbusCompany.exe。

        前置条件：先调用 apply() 写入偏移配置（否则 DLL 无法装钩）。
        """
        if pid is None:
            pid = cls.find_game_pid()
        if pid is None:
            raise RuntimeError("游戏未运行，请先启动 LimbusCompany.exe")

        if cls._injected_pid == pid and cls._remote_module is not None:
            return True

        dll_path = cls.get_dll_path()
        if not dll_path:
            raise RuntimeError("未找到 damage_hook.dll，请先运行 hooks/build.ps1 或重新安装")

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
            load_lib = _kernel32.GetProcAddress(kernel32, b"LoadLibraryW")
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
            logger.info("已注入 damage_hook 到 %s (PID %d)", TARGET_PROCESS, pid)
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
                free_lib = _kernel32.GetProcAddress(kernel32, b"FreeLibrary")
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

    # ---- 状态 ----

    @classmethod
    def get_status(cls) -> Dict:
        """获取状态信息（供 WebUI 展示）。"""
        pid = cls.find_game_pid()
        cfg = cls._read_config()
        with cls._offsets_lock:
            resolved = cls._offsets or {}
        last_log = ""
        log_count = 0
        last_error = 0
        verified = False
        installed = False
        ga_found = False
        if cfg is not None:
            verified = bool(cfg.verified)
            installed = bool(cfg.installed)
            ga_found = bool(cfg.gameassembly_found)
            log_count = int(cfg.log_count)
            last_error = int(cfg.last_error)
            try:
                last_log = cfg.last_log.decode("utf-8", "ignore").split("\x00", 1)[0]
            except Exception:
                last_log = ""
        return {
            "running": pid is not None,
            "pid": pid,
            "dll_exists": cls.get_dll_path() is not None,
            "injected": cls.is_injected(),
            "gameassembly_found": ga_found,
            "verified": verified,
            "installed": installed,
            "last_error": last_error,
            "last_error_text": DH_ERR_TEXT.get(last_error, "未知错误"),
            "log_count": log_count,
            "last_log": last_log,
            "offsets_source": resolved.get("source"),
            "offsets_stale": bool(resolved.get("stale")),
            "game_version": (resolved.get("offsets") or {}).get("game_version"),
        }

    @classmethod
    def refresh_offsets(cls) -> Dict:
        """强制刷新偏移并重新下发（游戏更新后的失效恢复路径）。"""
        result = cls.resolve_offsets(force_refresh=True)
        if not result["success"]:
            return result
        cls.apply(offsets=result["offsets"])
        return result

    @classmethod
    def close(cls):
        """弹出 DLL 并释放共享内存映射（同时停止日志抽取线程并冲刷剩余条目）。"""
        try:
            cls.eject()
        except Exception as e:
            _log_manager.log_error(e)
        # 冲刷剩余日志条目后再释放共享内存
        try:
            cls._drain_and_log()
        except Exception as e:
            _log_manager.log_error(e)
        stop = cls._drain_stop
        if stop is not None:
            stop.set()
        if cls._drain_thread is not None:
            cls._drain_thread.join(timeout=LOG_RING_INTERVAL + 1)
            cls._drain_thread = None
        with cls._map_lock:
            if cls._map_view:
                _kernel32.UnmapViewOfFile(cls._map_view)
                cls._map_view = None
            if cls._map_handle:
                _kernel32.CloseHandle(cls._map_handle)
                cls._map_handle = None
            cls._cached_pid = None
