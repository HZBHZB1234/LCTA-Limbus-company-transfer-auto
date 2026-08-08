# -*- coding: utf-8 -*-
"""CheatCore 解密加载器（公共仓库）——作弊工具箱的密钥门与插件加载

私有仓库 LCTA_CheatingCore 的作弊工具箱（Python 管理器 + hook DLL +
前端 HTML/JS）在构建期被加密打包为 ``cheat_core/cheat_core.bin`` 随发布包分发，
本模块负责运行期：用户输入解密密钥 → 校验 → 解密 → 释放到运行时目录 → 导入
``cheatcore`` 包，并触发插件注册（webutils/cheat_plugins.py）。未解锁前公共仓库
只有密钥门，不包含任何实现代码。

加密格式与门槛说明见私有仓库 README 与 tools/cheat_encrypt.py。错误密钥不落日志。
"""

import hashlib
import json
import logging
import os
import struct
import sys
import threading
import importlib
from typing import Dict, List, Optional, Tuple

from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager

_log_manager = LogManager()
logger = logging.getLogger(__name__)

MAGIC = b"LCTACC01"
ANCHOR = b"LCTA-CHEAT-KEY-OK!"
KEY_MIN_LEN = 8

KEY_CONFIG = "cheat_core.unlock_key"
BLOB_DIR_NAME = "cheat_core"
BLOB_FILE_NAME = "cheat_core.bin"
PACKAGE_NAME = "cheatcore"

# 解锁状态：{unlocked, reason, source, key, package}
_state = {"unlocked": False, "reason": "need_key", "source": None, "key": None, "package": None}
_state_lock = threading.Lock()


# ---------------------------------------------------------------------------
# 路径解析
# ---------------------------------------------------------------------------


def _repo_root() -> str:
    """公共仓库根目录（本文件位于 <root>/webutils/cheat_core.py）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dev_src_dir() -> Optional[str]:
    """开发模式源码目录：LCTA_CHEAT_DEV_SRC 环境变量 > 仓库根目录下的私有仓库克隆。

    开发模式下不校验密钥、不读取 blob，直接以 cheatcore 包导入本地克隆。
    """
    override = os.getenv("LCTA_CHEAT_DEV_SRC", "").strip()
    if override and os.path.isfile(os.path.join(override, "manifest.json")):
        return override
    repo_clone = os.path.join(_repo_root(), "LCTA_CheatingCore")
    if os.path.isfile(os.path.join(repo_clone, "manifest.json")):
        return repo_clone
    return None


def blob_path() -> Optional[str]:
    """查找随包分发的 cheat_core.bin（打包环境 path_ 优先，开发环境回退仓库相对路径）。"""
    candidates = []
    path_ = os.getenv("path_", "").strip()
    if path_:
        candidates.append(os.path.join(path_, BLOB_DIR_NAME, BLOB_FILE_NAME))
    candidates.append(os.path.join(_repo_root(), BLOB_DIR_NAME, BLOB_FILE_NAME))
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def runtime_dir() -> str:
    """解密释放目录：LCTA_CHEAT_CORE_DIR 环境变量覆盖，默认 %LOCALAPPDATA%/LCTA/cheat-core。"""
    override = os.getenv("LCTA_CHEAT_CORE_DIR", "").strip()
    if override:
        return override
    base = os.getenv("LOCALAPPDATA")
    if base:
        return os.path.join(base, "LCTA", "cheat-core")
    return os.path.join(os.path.expanduser("~"), ".lcta", "cheat-core")


# ---------------------------------------------------------------------------
# Blob 解析（与 tools/cheat_encrypt.py 的 parse/decrypt 逻辑一致）
# ---------------------------------------------------------------------------


def _xor(data: bytes, key: bytes) -> bytes:
    if not key:
        raise ValueError("密钥为空")
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


def _parse_blob(data: bytes) -> Tuple[Dict, bytes]:
    """解析 blob → (manifest, 密文 payload)。格式非法抛 ValueError。"""
    if len(data) < len(MAGIC) + 4 or data[: len(MAGIC)] != MAGIC:
        raise ValueError("cheat_core.bin magic 不匹配")
    mlen = struct.unpack("<I", data[len(MAGIC): len(MAGIC) + 4])[0]
    end = len(MAGIC) + 4 + mlen
    if mlen <= 0 or end > len(data):
        raise ValueError("cheat_core.bin manifest 长度非法")
    try:
        manifest = json.loads(data[len(MAGIC) + 4: end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"cheat_core.bin manifest 解析失败: {e}") from e
    return manifest, data[end:]


def _decrypt_files(data: bytes, key: bytes) -> List[Tuple[str, bytes]]:
    """解密 blob → [(dest 相对路径, 明文字节)...]。密钥错误/数据损坏抛 ValueError。"""
    manifest, cipher = _parse_blob(data)
    payload = _xor(cipher, key)
    if not payload.startswith(ANCHOR):
        raise ValueError("anchor 校验失败")
    files = []
    offset = len(ANCHOR)
    for item in manifest.get("files", []):
        size = int(item["size"])
        chunk = payload[offset: offset + size]
        if len(chunk) != size:
            raise ValueError("blob 数据不完整")
        if hashlib.sha256(chunk).hexdigest() != item.get("sha256"):
            raise ValueError(f"文件 {item.get('dest')} 校验失败")
        files.append((item["dest"], chunk))
        offset += size
    return files


# ---------------------------------------------------------------------------
# 运行时目录管理
# ---------------------------------------------------------------------------


def _write_files(files: List[Tuple[str, bytes]]) -> None:
    """把解密文件写入运行时目录：先写 .tmp 再 os.replace，最后清理陈旧文件。"""
    root = runtime_dir()
    os.makedirs(root, exist_ok=True)
    dests = set()
    for rel, data in files:
        rel = rel.replace("\\", "/")
        dests.add(rel)
        target = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
    # 清理不在 manifest 中的陈旧文件（防止旧版本残留）
    for dirpath, _dirs, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace("\\", "/")
            if rel not in dests:
                try:
                    os.remove(full)
                except OSError:
                    pass


def _purge_package_modules() -> None:
    """清除已缓存的 cheatcore 及其子模块（插件内部模块名由注册表决定）。"""
    sys.modules.pop(PACKAGE_NAME, None)
    for name in list(sys.modules):
        if name.startswith(PACKAGE_NAME + "."):
            sys.modules.pop(name, None)


def _import_package() -> object:
    """把运行时（或开发）目录加入 sys.path 并导入 cheatcore 包。"""
    cached = _state.get("package")
    if cached is not None:
        return cached
    if dev_src_dir() is not None:
        base = dev_src_dir()
    else:
        base = runtime_dir()
    if base not in sys.path:
        sys.path.insert(0, base)
    _purge_package_modules()
    package = importlib.import_module(PACKAGE_NAME)
    _state["package"] = package
    return package


def _reload_plugins() -> None:
    """解锁后刷新插件注册表（失败仅告警，不影响解锁状态）。"""
    try:
        from webutils.cheat_plugins import CheatPluginHost
        CheatPluginHost.reload()
    except Exception as e:
        logger.warning("CheatCore 插件注册失败: %s", e)


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def unlock(key: str) -> Dict:
    """用解密密钥解锁：校验 → 解密 → 释放 → 动态导入 → 持久化密钥。

    返回 {"success": bool, "reason": str}；reason 为 invalid_key / ok 等。
    """
    key = (key or "").strip()
    if not key:
        return {"success": False, "reason": "need_key"}
    key_bytes = key.encode("utf-8")
    if len(key_bytes) < KEY_MIN_LEN:
        return {"success": False, "reason": "invalid_key"}

    with _state_lock:
        blob = blob_path()
        if blob is None:
            return {"success": False, "reason": "blob_missing"}
        try:
            with open(blob, "rb") as f:
                data = f.read()
            files = _decrypt_files(data, key_bytes)
        except (ValueError, OSError) as e:
            logger.info("CheatCore 解锁失败: %s", e)
            return {"success": False, "reason": "invalid_key"}
        try:
            _write_files(files)
            _import_package()
        except Exception as e:  # 导入/写盘失败：保留现场，报解锁失败
            logger.warning("CheatCore 解锁后加载失败: %s", e)
            _log_manager.log(f"作弊工具箱: 功能加载失败（{e}）")
            return {"success": False, "reason": "load_error"}
        _state.update({"unlocked": True, "reason": "ok", "source": "blob", "key": key_bytes})
        _reload_plugins()
        try:
            ConfigManager().set(KEY_CONFIG, key)
        except Exception as e:
            logger.warning("CheatCore 密钥持久化失败: %s", e)
        _log_manager.log("作弊工具箱: 已解锁")
        return {"success": True, "reason": "ok"}


def ensure_unlocked() -> Dict:
    """查询解锁状态；已持久化密钥时自动解锁。

    返回 {"success": bool, "reason": str, "source": str|None}：
    - unlocked / dev    已解锁（dev 为开发模式）
    - need_key          需要用户输入密钥
    - blob_missing      安装不含 cheat_core.bin
    - invalid_key / load_error  自动解锁失败
    """
    with _state_lock:
        if _state["unlocked"]:
            return {"success": True, "reason": "unlocked", "source": _state["source"]}

    dev = dev_src_dir()
    if dev is not None:
        with _state_lock:
            _state.update({"unlocked": True, "reason": "dev", "source": "dev", "key": None})
        _import_package()
        _reload_plugins()
        return {"success": True, "reason": "dev", "source": "dev"}

    if blob_path() is None:
        return {"success": False, "reason": "blob_missing", "source": None}

    stored = str(ConfigManager().get(KEY_CONFIG, "") or "").strip()
    if stored:
        result = unlock(stored)
        if result["success"]:
            return {"success": True, "reason": "unlocked", "source": "blob"}
        # 持久化密钥失效（换包/换密钥）：清掉并回到需要输入
        if result["reason"] in ("invalid_key", "load_error"):
            try:
                ConfigManager().set(KEY_CONFIG, "")
            except Exception:
                pass
            return {"success": False, "reason": "need_key", "source": None}
        return {"success": False, "reason": result["reason"], "source": None}

    return {"success": False, "reason": "need_key", "source": None}


def is_unlocked() -> bool:
    """仅内存态判断（不触发自动解锁），供门面快速短路。"""
    return bool(_state["unlocked"])


def lock() -> Dict:
    """锁定：清除密钥配置、内存态、插件注册、sys.path 条目与运行时目录。"""
    with _state_lock:
        if _state.get("key"):
            _state["key"] = None
        _state["unlocked"] = False
        _state["reason"] = "need_key"
        _state["source"] = None
        _state["package"] = None
    try:
        ConfigManager().set(KEY_CONFIG, "")
    except Exception:
        pass
    try:
        from webutils.cheat_plugins import CheatPluginHost
        CheatPluginHost.clear()
    except Exception:
        pass
    for p in (runtime_dir(), dev_src_dir() or ""):
        if p and p in sys.path:
            try:
                sys.path.remove(p)
            except ValueError:
                pass
    _purge_package_modules()
    root = runtime_dir()
    if os.path.isdir(root):
        try:
            for dirpath, _dirs, filenames in os.walk(root, topdown=False):
                for name in filenames:
                    try:
                        os.remove(os.path.join(dirpath, name))
                    except OSError:
                        pass
                try:
                    os.rmdir(dirpath)
                except OSError:
                    pass
        except OSError:
            pass
    _log_manager.log("作弊工具箱: 已锁定")
    return {"success": True}


def get_package() -> object:
    """返回已解锁的 cheatcore 包；未解锁抛 RuntimeError。"""
    if not is_unlocked():
        result = ensure_unlocked()
        if not result["success"]:
            raise RuntimeError(f"作弊工具箱未解锁（{result['reason']}）")
    return _import_package()


def _read_webui_file(rel: str) -> str:
    """读取解密/开发目录中的前端文件内容（未解锁抛 RuntimeError）。"""
    if not is_unlocked() and not ensure_unlocked().get("success"):
        raise RuntimeError("作弊工具箱未解锁")
    base = dev_src_dir() or runtime_dir()
    path = os.path.join(base, *rel.replace("\\", "/").split("/"))
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def section_html(name: str) -> str:
    """工具箱页完整 HTML（如 'cheat' → webui/sections/cheat.html）。"""
    return _read_webui_file(f"webui/sections/{name}.html")


def script_js(name: str) -> str:
    """工具箱页完整 JS（如 'cheat' → webui/js/cheat.js）。"""
    return _read_webui_file(f"webui/js/{name}.js")
