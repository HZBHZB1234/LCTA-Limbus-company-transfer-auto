# -*- coding: utf-8 -*-
"""加载页 CG 存档注入：存档加解密与 CG 模型读写（零 hook，纯文件层）。

存档格式（逆向自 GameAssembly.dll，见 LimbusDecompile/docs/LOADING_CG_INJECT.md）:
    save_slot_<id>.json = Base64( AES-256-CBC + PKCS7 ( JsonUtility JSON ) )
密钥来自 PlayerPrefs 注册表（明文）:
    HKCU\\Software\\ProjectMoon\\LimbusCompany\\LocalSave.LocalGameOptionData_h<hash>
    值内 JSON 的 "key"（32B Base64）与 "iv"（16B Base64）

写盘策略：即时写入，不生成 .bak 备份（用户明确选择）。
"""
import base64
import ctypes
import json
import os
import re
import winreg
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

REG_PATH = r"Software\ProjectMoon\LimbusCompany"
GAME_EXE = "LimbusCompany.exe"
CG_KEY = "UserLocalStoryCGSaveModel"


# ---------------- 路径与状态 ----------------

def get_save_dir() -> Path:
    """存档目录：%LOCALAPPDATA%\\..\\LocalLow\\ProjectMoon\\LimbusCompany"""
    base = os.environ.get("LOCALAPPDATA", "")
    return (Path(base) / ".." / "LocalLow" / "ProjectMoon" / "LimbusCompany").resolve()


def get_cache_root() -> Path:
    """Unity 缓存目录（bundle 扫描用）"""
    base = os.environ.get("LOCALAPPDATA", "")
    return (Path(base) / ".." / "LocalLow" / "Unity" / "ProjectMoon_LimbusCompany").resolve()


def list_save_slots() -> list:
    """列出全部存档槽（按修改时间倒序）。返回 [{slot, path, mtime}]"""
    d = get_save_dir()
    if not d.is_dir():
        return []
    slots = []
    for f in sorted(d.glob("save_slot_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        slots.append({
            "slot": f.stem.replace("save_slot_", ""),
            "path": str(f),
            "mtime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size": f.stat().st_size,
        })
    return slots


def is_game_running() -> bool:
    """通过进程快照检测 LimbusCompany.exe 是否在运行（ctypes，无第三方依赖）。"""
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
        return False
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            if pe.szExeFile.lower() == GAME_EXE.lower():
                return True
            ok = kernel32.Process32NextW(snap, ctypes.byref(pe))
        return False
    finally:
        kernel32.CloseHandle(snap)


# ---------------- 密钥（注册表 PlayerPrefs） ----------------

def get_credential() -> tuple:
    """读取注册表加密密钥。返回 (key_bytes, iv_bytes)，未找到抛 RuntimeError。"""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as k:
        names = []
        i = 0
        while True:
            try:
                names.append(winreg.EnumValue(k, i))
            except OSError:
                break
            i += 1
    hit = None
    for name, value, _ in names:
        if name.startswith("LocalSave.LocalGameOptionData_"):
            hit = value
            break
    if hit is None:
        raise RuntimeError("注册表未找到 LocalGameOptionData（请先运行一次游戏生成密钥）")
    if isinstance(hit, bytes):
        hit = hit.rstrip(b"\x00").decode("utf-8")
    data = json.loads(hit)
    return base64.b64decode(data["key"]), base64.b64decode(data["iv"])


# ---------------- 加解密（.NET Aes：AES-256-CBC + PKCS7 + Base64） ----------------

_net_crypto = None


def _get_net_crypto():
    """惰性加载 .NET System.Security.Cryptography（首次调用时经 clr_bootstrap 初始化 CLR）。

    存档加密与游戏 Unity 的 C# Aes 实现同源，直接调用参考实现保证字节级兼容；
    pythonnet 为本程序硬依赖（WebUI/Launcher 启动必经 ensure_clr），无需额外加密库。
    """
    global _net_crypto
    if _net_crypto is None:
        from webutils.clr_bootstrap import ensure_clr
        clr = ensure_clr()
        from System import Array, Byte
        import System.Security.Cryptography as crypto
        _net_crypto = (crypto, Array, Byte)
    return _net_crypto


def aes_crypt(data: bytes, key: bytes, iv: bytes, encrypt: bool) -> bytes:
    """AES-256-CBC + PKCS7（.NET Aes）；encrypt=True 返回密文，否则返回去填充明文。"""
    crypto, Array, Byte = _get_net_crypto()
    aes = crypto.Aes.Create()
    aes.KeySize = 256
    aes.Mode = crypto.CipherMode.CBC
    aes.Padding = crypto.PaddingMode.PKCS7
    aes.Key = Array[Byte](list(key))
    aes.IV = Array[Byte](list(iv))
    if encrypt:
        enc = aes.CreateEncryptor()
        return bytes(enc.TransformFinalBlock(bytearray(data), 0, len(data)))
    dec = aes.CreateDecryptor()
    return bytes(dec.TransformFinalBlock(bytearray(data), 0, len(data)))


def decrypt_save(save_path: str, key: bytes, iv: bytes) -> str:
    """解密存档文件，返回明文 JSON 字符串。"""
    b64 = Path(save_path).read_text(encoding="utf-8-sig").strip()
    return aes_crypt(base64.b64decode(b64), key, iv, encrypt=False).decode("utf-8")


def encrypt_save(plain_json: str, key: bytes, iv: bytes) -> str:
    """加密明文 JSON，返回可直接写盘的 Base64 字符串。"""
    return base64.b64encode(
        aes_crypt(plain_json.encode("utf-8"), key, iv, encrypt=True)
    ).decode()


# ---------------- CG 模型读写 ----------------

def load_root(save_path: str) -> dict:
    """解密存档并解析根 JSON。"""
    key, iv = get_credential()
    return json.loads(decrypt_save(save_path, key, iv))


def save_root(save_path: str, root: dict) -> None:
    """序列化根 JSON 并加密写盘（即时写入，无备份）。"""
    key, iv = get_credential()
    plain = json.dumps(root, ensure_ascii=False, separators=(",", ":"))
    Path(save_path).write_text(encrypt_save(plain, key, iv), encoding="utf-8")


def _cg_model(root: dict) -> tuple:
    """定位 UserLocalStoryCGSaveModel：返回 (index, cg_dict)。不存在抛 RuntimeError。"""
    keys = root["_stringDic"]["keys"]
    for i, k in enumerate(keys):
        if k == CG_KEY:
            return i, json.loads(root["_stringDic"]["values"][i])
    raise RuntimeError("存档中不存在 UserLocalStoryCGSaveModel（未游玩过加载页 CG？）")


def read_cg_model(save_path: str) -> dict:
    """读取当前存档的 CG 状态。

    forced_list：原始对象数组（{"id","gacksung"}，兼容历史字符串条目原样返回）；
    forced_ids：可读/可操作的存档 ID 列表（"CG/10101_normal"），前端显示与回传均用它。
    """
    root = load_root(save_path)
    _, cg = _cg_model(root)
    forced = cg.get("_forcedCharacterCgIdList") or []
    return {
        "save_path": str(save_path),
        "cg_id_list": cg.get("_cgIdList") or [],
        "forced_list": forced,
        "forced_ids": [forced_entry_id(e) for e in forced],
        "latest_cg": cg.get("_latestCg") or "",
        "freeview_list": cg.get("_freeviewCgIdList") or [],
    }


def forced_entry_id(entry) -> str:
    """forced 条目 → 存档 ID 字符串（"CG/10101_normal"）；兼容历史字符串条目。"""
    if isinstance(entry, dict):
        suffix = "_gacksung" if entry.get("gacksung") else "_normal"
        return f"CG/{entry.get('id', '?')}{suffix}"
    return lenient_cg_id(str(entry))


def set_forced_cg(save_path: str, forced_ids: list) -> dict:
    """整体覆写锁定列表（方案 A：仅人格 CG），输入为字符串 ID 列表（存档或 key 形式）。

    每个条目经 normalize → parse_forced_entry 转为 {"id","gacksung"} 对象写盘；
    非人格资源（Dummy、BG/ 自定义等）抛 ValueError（引导走方案 B 解锁池注入）。
    """
    norm = [parse_forced_entry(i) for i in (forced_ids or [])]
    root = load_root(save_path)
    idx, cg = _cg_model(root)
    cg["_forcedCharacterCgIdList"] = norm
    root["_stringDic"]["values"][idx] = json.dumps(cg, ensure_ascii=False, separators=(",", ":"))
    save_root(save_path, root)
    return read_cg_model(save_path)


def set_cg_id_list(save_path: str, cg_id: str) -> dict:
    """方案 B：向解锁池 _cgIdList 追加字符串 ID（幂等），非人格资源的锁定通道。

    注意：游戏 Save 时 SetCgIdList 会用 _freeviewCgIdList 重建解锁池，
    方案 B 条目在下次游戏保存后可能消失，需要时重新注入（返回 pool_unstable 提示位）。
    """
    cg_id = normalize_cg_id(cg_id)
    root = load_root(save_path)
    idx, cg = _cg_model(root)
    pool = cg.get("_cgIdList") or []
    if cg_id not in pool:
        pool.append(cg_id)
        cg["_cgIdList"] = pool
        root["_stringDic"]["values"][idx] = json.dumps(cg, ensure_ascii=False, separators=(",", ":"))
        save_root(save_path, root)
    model = read_cg_model(save_path)
    model["pool_unstable"] = True
    return model


def remove_cg_id_list(save_path: str, cg_id: str) -> dict:
    """从解锁池 _cgIdList 移除指定条目。"""
    cg_id = normalize_cg_id(cg_id)
    root = load_root(save_path)
    idx, cg = _cg_model(root)
    cg["_cgIdList"] = [i for i in (cg.get("_cgIdList") or []) if i != cg_id]
    root["_stringDic"]["values"][idx] = json.dumps(cg, ensure_ascii=False, separators=(",", ":"))
    save_root(save_path, root)
    return read_cg_model(save_path)


# ---------------- CG ID 模型（上游 2026-08-12 确认，见 LOADING_CG_INJECT.md 十一至十四节） ----------------
#
# 三态形式：
#   key 形式    : "Story_CG/10101_normal" / "Unit_CG/10101_normal"（catalog/索引/页面展示）
#  存档字符串 ID : "CG/10101_normal" / "BG/xxx"（_cgIdList 内容；
#                游戏 isFullPath = !StartsWith(ID,"CG/") && !StartsWith(ID,"BG/")，
#                拼 key = "Story_"|"Unit_" + ID + ".png"）
#   forced 对象  : {"id": 10101, "gacksung": false}（_forcedCharacterCgIdList 元素，
#                 List<LocalCharacterCGData>，GetText = Format("CG/{0}{1}")，仅人格 CG）
#
# 人格 CG 命名：<人格ID>_normal | <人格ID>_gacksung → {"id": <人格ID>, "gacksung": bool}
# 方案 A（稳定）：forced 对象数组锁定人格 CG（已验证成功）
# 方案 B（不稳定）：_cgIdList 注入任意字符串 ID（CG/Dummy、BG/xxx），游戏保存时被重建
SAVE_CG_PREFIXES = ("CG/", "BG/")
KEY_LABELS = ("Story_", "Unit_")
PERSONALITY_RE = re.compile(r"^(\d+)_(normal|gacksung)$")


def is_personality_name(name: str) -> bool:
    """判断名字是否为可锁定（人格 CG）命名：<人格ID>_normal|_gacksung。"""
    return bool(PERSONALITY_RE.match(name or ""))


def key_to_save_id(cg_id: str) -> str:
    """key 形式 → 存档字符串 ID（剥 Story_/Unit_ label 前缀）；非 key 形式原样返回。"""
    low = cg_id.lower()
    for label in KEY_LABELS:
        if low.startswith(label.lower() + "cg/"):
            # "Story_CG/10101_normal" → 剥 "Story_CG/"（label + "CG/"）→ "10101_normal"
            return "CG/" + cg_id[len(label) + 3:]
    return cg_id


def parse_forced_entry(cg_id: str) -> dict:
    """存档字符串 ID → forced 对象 {"id": int, "gacksung": bool}（仅人格 CG）。

    非人格资源（Dummy、BG/ 自定义等）抛 ValueError，引导走方案 B（解锁池注入）。
    """
    cg_id = normalize_cg_id(cg_id)
    if not cg_id.startswith("CG/"):
        raise ValueError(f"「{cg_id}」为非人格资源（BG/ 自定义或 Dummy 类），无法写入锁定列表；"
                         f"将改用「解锁池注入」（方案 B）")
    m = PERSONALITY_RE.match(cg_id[3:])
    if not m:
        raise ValueError(f"「{cg_id}」不是人格 CG（需 <人格ID>_normal/_gacksung 命名），"
                         f"无法写入锁定列表；将改用「解锁池注入」（方案 B）")
    return {"id": int(m.group(1)), "gacksung": m.group(2) == "gacksung"}


def normalize_cg_id(cg_id: str) -> str:
    """规范化 CG ID → 存档字符串 ID 形式（CG/<名> 或 BG/<名>）。

    接受：CG/、BG/（存档形式）；Story_CG/、Unit_CG/（key 形式，自动转换）；
    剥 .png 后缀、前缀大小写归一、校验非法字符；裸名拒绝（需从扫描列表选择）。
    """
    cg_id = (cg_id or "").strip().strip("\"'")
    if not cg_id:
        raise ValueError("CG ID 不能为空")
    if cg_id.lower().endswith(".png"):
        cg_id = cg_id[:-4]
    low = cg_id.lower()
    if low.startswith("story_cg/") or low.startswith("unit_cg/"):
        return key_to_save_id(cg_id)
    for prefix in SAVE_CG_PREFIXES:
        if low.startswith(prefix.lower()):
            rest = cg_id[len(prefix):]
            if not rest:
                raise ValueError(f"CG ID 缺少名字部分：{cg_id}")
            if "/" in rest or "\\" in rest or ".." in rest:
                raise ValueError(f"非法 CG ID：{cg_id}")
            return prefix + rest
    raise ValueError(
        f"CG ID 需以 CG/ 或 BG/ 开头（如 CG/10101_normal；也可粘贴 Story_CG/10101_normal 形式的地址键）")


def lenient_cg_id(cg_id: str) -> str:
    """宽松规范化（仅去空白/引号/尾 .png，不做前缀校验）。

    用于 originals store 查询等需要兼容历史键的场景。
    """
    cg_id = (cg_id or "").strip().strip("\"'")
    if cg_id.lower().endswith(".png"):
        cg_id = cg_id[:-4]
    return cg_id
