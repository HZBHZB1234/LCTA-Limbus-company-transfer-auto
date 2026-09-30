# -*- coding: utf-8 -*-
"""客户端凭据安全存储（Windows DPAPI，当前用户范围）。

## 为什么必须加密

refresh token 是长期凭据：明文写进 config.json 后，任何能读该文件的进程
（其他软件、误上传的日志、备份、同步盘）都等于拿到了账号。
plan 16.4 明确要求「DPAPI 当前用户隔离、旧明文迁移删除」。

## 实现选择

用 Windows DPAPI（``CryptProtectData``）通过 ctypes 调用，
**不引入** ``pywin32``/``win32crypt`` —— 客户端 requirements 里没有它们，
为一个存令牌的动作加依赖不划算。

DPAPI 的 ``CRYPTPROTECT_LOCAL_MACHINE`` **不**使用：必须绑定当前用户，
否则同机其他用户也能解密（plan 16.4「当前用户隔离」）。

## 非 Windows 行为

非 Windows 平台没有 DPAPI。此时**明确拒绝存储**而不是降级成明文 ——
静默明文落盘是最糟的选择：用户以为令牌被加密了。
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MAGIC = b"LCTADP01"   # 便于识别「这是我们写的密文」，而不是猜


class CredentialStoreError(RuntimeError):
    """凭据存储失败（无 DPAPI、密文损坏等）。"""


def _dpapi_available() -> bool:
    return os.name == "nt" and hasattr(ctypes, "windll")


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob_from(data: bytes) -> _DataBlob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _blob_to(blob: _DataBlob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def protect(data: bytes, *, entropy: bytes = b"") -> bytes:
    """用当前用户的 DPAPI 加密。"""
    if not _dpapi_available():
        raise CredentialStoreError("当前平台不支持 DPAPI，拒绝以明文保存凭据")

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    blob_in = _blob_from(data)
    blob_entropy = _blob_from(entropy) if entropy else None
    blob_out = _DataBlob()

    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None,
        ctypes.byref(blob_entropy) if blob_entropy else None,
        None,
        None,
        0,   # 不加 CRYPTPROTECT_LOCAL_MACHINE：必须绑定当前用户
        ctypes.byref(blob_out),
    )
    if not ok:
        raise CredentialStoreError(f"DPAPI 加密失败（错误码 {kernel32.GetLastError()}）")
    try:
        return _blob_to(blob_out)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def unprotect(data: bytes, *, entropy: bytes = b"") -> bytes:
    """用当前用户的 DPAPI 解密。"""
    if not _dpapi_available():
        raise CredentialStoreError("当前平台不支持 DPAPI")

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    blob_in = _blob_from(data)
    blob_entropy = _blob_from(entropy) if entropy else None
    blob_out = _DataBlob()

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        ctypes.byref(blob_entropy) if blob_entropy else None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
        # 常见原因：换了 Windows 用户、文件被拷到别的机器、密文损坏
        raise CredentialStoreError(f"DPAPI 解密失败（错误码 {kernel32.GetLastError()}）")
    try:
        return _blob_to(blob_out)
    finally:
        kernel32.LocalFree(blob_out.pbData)


# ---------------------------------------------------------------------------
# 凭据存储
# ---------------------------------------------------------------------------


class CredentialStore:
    """按 key 保存少量凭据（加密落盘）。

    文件格式：``MAGIC + DPAPI(JSON)``。JSON 里只放凭据本身，
    **不放**任何可读的账号信息（避免文件被看到时泄露用户名/邮箱）。
    """

    def __init__(self, path: Optional[os.PathLike | str] = None) -> None:
        self.path = Path(path) if path else self.default_path()

    @staticmethod
    def default_path() -> Path:
        local = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return local / "LCTA" / "toolbox" / "credentials.bin"

    # -- 读写 ---------------------------------------------------------------

    def _load_all(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = self.path.read_bytes()
        except OSError:
            logger.warning("读取凭据文件失败", exc_info=True)
            return {}
        if not raw.startswith(MAGIC):
            # 旧格式/被破坏：不猜测内容，按空处理（用户重新登录即可）
            logger.warning("凭据文件格式不认识，按空处理：%s", self.path)
            return {}
        try:
            plain = unprotect(raw[len(MAGIC):], entropy=b"LCTA-toolbox")
        except CredentialStoreError:
            # 换用户/换机器后解不开是正常的，不是错误
            logger.info("凭据无法解密（可能更换了 Windows 用户或机器），按空处理")
            return {}
        try:
            data = json.loads(plain.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("凭据内容损坏，按空处理")
            return {}
        return data if isinstance(data, dict) else {}

    def _save_all(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        plain = json.dumps(data, ensure_ascii=False).encode("utf-8")
        blob = MAGIC + protect(plain, entropy=b"LCTA-toolbox")

        # 原子写：临时文件 + os.replace
        tmp = self.path.with_suffix(".tmp")
        with open(str(tmp), "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(self.path))

        # 收紧权限（同机其他用户不可读）
        try:
            os.chmod(str(self.path), 0o600)
        except OSError:
            pass

    # -- 对外 API -----------------------------------------------------------

    def get(self, key: str) -> Optional[str]:
        return self._load_all().get(key)

    def set(self, key: str, value: str) -> None:
        if not value:
            self.delete(key)
            return
        data = self._load_all()
        data[key] = value
        self._save_all(data)

    def delete(self, key: str) -> None:
        data = self._load_all()
        if key in data:
            del data[key]
            self._save_all(data)

    def clear(self) -> None:
        """清除全部凭据（登出时调用）。

        删除整个文件而不是写空对象：写空对象仍保留「这个用户用过工具箱」的痕迹。
        """
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def has(self, key: str) -> bool:
        return bool(self._load_all().get(key))

    # -- 迁移 ---------------------------------------------------------------

    def migrate_from_plaintext(self, plaintext_path: os.PathLike | str) -> bool:
        """把旧明文凭据迁入加密存储，并**删除**明文文件。

        plan 16.4 要求「旧明文迁移删除」。只迁不删等于没做迁移 ——
        明文仍然躺在那儿。
        """
        src = Path(plaintext_path)
        if not src.exists():
            return False
        try:
            raw = src.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("旧明文凭据无法解析，跳过迁移：%s", src)
            return False
        if not isinstance(data, dict):
            return False

        merged = self._load_all()
        for k, v in data.items():
            if isinstance(v, str) and v:
                merged[k] = v
        if merged:
            self._save_all(merged)

        # 明文必须删除；删不掉就明确报错，不能静默留一份明文
        try:
            src.unlink()
        except OSError as exc:
            raise CredentialStoreError(
                f"旧明文凭据迁移后无法删除 {src}：{exc}（请手动删除）"
            ) from exc
        logger.info("已把明文凭据迁入 DPAPI 存储并删除原文件")
        return True