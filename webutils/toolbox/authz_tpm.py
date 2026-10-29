# -*- coding: utf-8 -*-
"""TPM 设备身份（Windows Platform Crypto Provider，2026-10-27）。

## 为什么用 TPM 而不是 DPAPI 存密钥

DPAPI 只防「别的 Windows 用户」，**不防以当前用户身份运行的恶意软件**：
信息窃取木马能直接调 ``CryptUnprotectData`` 解出明文。TPM 则不同 ——
私钥由芯片生成且**不可导出**，文件被拷走、备份泄漏、内存 dump 都拿不到
可用的东西；换台机器也完全无效。

## 算法选择

TPM 2.0 标准只保证 **ECDSA P-256**，Ed25519 不是标准算法（多数 TPM 不支持）。
因此设备签名用 P-256；票据（服务端签发）仍用 Ed25519，由 doorstop 内嵌公钥验。

## 本地只存公开信息

``%LOCALAPPDATA%\\LCTA\\device.json``:
    { "device_id": "...", "api_base": "https://mods.lcta.top",
      "tpm_key_name": "LCTA-Authz-Device" }

``device_id`` 是随机公开标识；私钥在 TPM 里，文件里没有任何秘密。
"""
from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import secrets
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MS_PLATFORM_KEY_STORAGE_PROVIDER = "Microsoft Platform Crypto Provider"
NCRYPT_SILENT_FLAG = 0x00000040
NCRYPT_UI_PROTECT_KEY_FLAG = 0x00000010
BCRYPT_ECDSA_P256_ALGORITHM = "ECDSA_P256"
NCRYPT_ECDSA_P256_ALGORITHM = "ECDSA_P256"

DEFAULT_KEY_NAME = "LCTA-Authz-Device"
DEFAULT_API_BASE = "https://mods.lcta.top"


class TpmUnavailable(RuntimeError):
    """本机没有可用 TPM 或调用失败 —— 明确失败，不静默降级成软密钥。"""


def _is_windows() -> bool:
    return os.name == "nt"


def device_file_path() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "LCTA" / "device.json"


def _ncrypt():
    if not _is_windows():
        raise TpmUnavailable("TPM 仅支持 Windows")
    try:
        return ctypes.windll.ncrypt
    except Exception as exc:  # noqa: BLE001
        raise TpmUnavailable(f"无法加载 ncrypt.dll：{exc}") from exc


def _bcrypt():
    return ctypes.windll.bcrypt


def tpm_available() -> bool:
    """粗检：能否打开 Microsoft Platform Crypto Provider。"""
    if not _is_windows():
        return False
    try:
        prov = ctypes.c_void_p()
        status = _ncrypt().NCryptOpenStorageProvider(
            ctypes.byref(prov), MS_PLATFORM_KEY_STORAGE_PROVIDER, 0
        )
        if status != 0:
            return False
        _ncrypt().NCryptFreeObject(prov)
        return True
    except Exception:  # noqa: BLE001
        return False


def ensure_device_key(key_name: str = DEFAULT_KEY_NAME) -> bytes:
    """确保 TPM 中存在该名称的 P-256 密钥，返回**公钥 DER**。

    幂等：已存在则直接导出公钥。私钥永不出芯片。
    """
    ncrypt = _ncrypt()
    prov = ctypes.c_void_p()
    status = ncrypt.NCryptOpenStorageProvider(
        ctypes.byref(prov), MS_PLATFORM_KEY_STORAGE_PROVIDER, 0
    )
    if status != 0:
        raise TpmUnavailable(f"打开 TPM 提供程序失败（0x{status & 0xFFFFFFFF:08x}）")

    key = ctypes.c_void_p()
    try:
        # 先尝试打开已有密钥
        status = ncrypt.NCryptOpenKey(prov, ctypes.byref(key), key_name, 0, 0)
        if status != 0:
            # 不存在则创建（不可导出、可签名）
            status = ncrypt.NCryptCreatePersistedKey(
                prov, ctypes.byref(key), NCRYPT_ECDSA_P256_ALGORITHM, key_name, 0, 0
            )
            if status != 0:
                raise TpmUnavailable(f"创建 TPM 密钥失败（0x{status & 0xFFFFFFFF:08x}）")
            # 禁止导出私钥：这是本方案的核心保证
            export_policy = wintypes.DWORD(0)
            ncrypt.NCryptSetProperty(
                key, "Export Policy", ctypes.byref(export_policy),
                ctypes.sizeof(export_policy), 0
            )
            status = ncrypt.NCryptFinalizeKey(key, 0)
            if status != 0:
                raise TpmUnavailable(f"完成 TPM 密钥创建失败（0x{status & 0xFFFFFFFF:08x}）")

        # 导出公钥
        #
        # ⚠️ 必须用 **ECCPUBLICBLOB**，不能用 PUBLICKEYBLOB（2026-10-29 实测修正）
        #
        # 对 Microsoft Platform Crypto Provider（TPM）的 ECDSA 密钥，
        # NCryptExportKey(..., "PUBLICKEYBLOB") 返回 **0x8009000A
        # (NTE_NOT_SUPPORTED)** —— TPM 只支持 ECC 专用 blob 类型。
        # 原实现用 PUBLICKEYBLOB，导致「授权本机」在真实 TPM 上必然失败
        # （软件模拟 TPM 的测试覆盖不到这一点，所以一直没暴露）。
        #
        # ECCPUBLICBLOB 布局（实测 72 字节）：
        #   DWORD dwMagic  'ECS1' (0x31435345)
        #   DWORD cbKey    32
        #   BYTE  X[32]
        #   BYTE  Y[32]
        size = wintypes.DWORD(0)
        status = ncrypt.NCryptExportKey(key, None, "ECCPUBLICBLOB", None, None, 0, ctypes.byref(size), 0)
        if status != 0 or size.value == 0:
            raise TpmUnavailable(
                f"导出 TPM 公钥失败（ECCPUBLICBLOB 查询，0x{status & 0xFFFFFFFF:08x}）"
            )
        buf = ctypes.create_string_buffer(size.value)
        status = ncrypt.NCryptExportKey(
            key, None, "ECCPUBLICBLOB", None, buf, size.value, ctypes.byref(size), 0
        )
        if status != 0:
            raise TpmUnavailable(f"读取 TPM 公钥失败（0x{status & 0xFFFFFFFF:08x}）")

        return bytes(buf.raw[: size.value])
    finally:
        if key:
            ncrypt.NCryptFreeObject(key)
        if prov:
            ncrypt.NCryptFreeObject(prov)


def export_public_key_der(key_name: str = DEFAULT_KEY_NAME) -> str:
    """导出 P-256 公钥为 base64(DER)。

    站点用 cryptography 的 ``load_der_public_key`` 解析，因此这里需要标准 DER。
    CNG 的 PUBLICKEYBLOB 不是 DER —— 用 BCrypt 的 ``BCryptExportKey``
    + ``BCRYPT_ECCPUBLIC_BLOB`` 并手工封装成 SPKI。
    """
    raw = ensure_device_key(key_name)
    der = _cng_blob_to_spki_der(raw)
    return base64.b64encode(der).decode("ascii")


def _cng_blob_to_spki_der(blob: bytes) -> bytes:
    """CNG BCRYPT_ECCPUBLIC_BLOB → DER SubjectPublicKeyInfo。

    BCRYPT_ECCPUBLIC_BLOB 结构：
        DWORD dwMagic ('ECK1')
        DWORD cbKey (32)
        BYTE  X[cbKey]
        BYTE  Y[cbKey]
    """
    if len(blob) < 8:
        raise TpmUnavailable("TPM 公钥 blob 过短")
    magic = int.from_bytes(blob[0:4], "little")
    cb_key = int.from_bytes(blob[4:8], "little")
    if cb_key not in (32, 48, 64):
        raise TpmUnavailable(f"TPM 公钥长度异常：{cb_key}")
    if len(blob) < 8 + cb_key * 2:
        raise TpmUnavailable("TPM 公钥数据不完整")
    x = blob[8: 8 + cb_key]
    y = blob[8 + cb_key: 8 + 2 * cb_key]

    # 未压缩点：0x04 || X || Y
    point = b"\x04" + x + y

    # SPKI: SEQUENCE { SEQUENCE { OID ecPublicKey, OID prime256v1 }, BIT STRING point }
    oid_ec = bytes.fromhex("2a8648ce3d0201")          # 1.2.840.10045.2.1
    oid_p256 = bytes.fromhex("2a8648ce3d030107")      # 1.2.840.10045.3.1.7

    def der_len(n: int) -> bytes:
        if n < 0x80:
            return bytes([n])
        out = []
        while n:
            out.insert(0, n & 0xFF)
            n >>= 8
        return bytes([0x80 | len(out)]) + bytes(out)

    alg = b"\x30" + der_len(len(oid_ec) + 2 + len(oid_p256) + 2) + \
          b"\x06" + der_len(len(oid_ec)) + oid_ec + \
          b"\x06" + der_len(len(oid_p256)) + oid_p256
    bitstring = b"\x03" + der_len(len(point) + 1) + b"\x00" + point
    body = alg + bitstring
    return b"\x30" + der_len(len(body)) + body


def sign_with_tpm(message: bytes, key_name: str = DEFAULT_KEY_NAME) -> str:
    """用 TPM 私钥做 SHA-256 + ECDSA 签名，返回 base64(DER)。"""
    ncrypt = _ncrypt()
    bcrypt = _bcrypt()

    # SHA-256
    h_alg = ctypes.c_void_p()
    if bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(h_alg), "SHA256", None, 0) != 0:
        raise TpmUnavailable("无法打开 SHA-256 算法")
    digest = ctypes.create_string_buffer(32)
    try:
        status = bcrypt.BCryptHash(h_alg, None, 0, message, len(message), digest, 32)
        if status != 0:
            raise TpmUnavailable("SHA-256 计算失败")
    finally:
        bcrypt.BCryptCloseAlgorithmProvider(h_alg, 0)

    prov = ctypes.c_void_p()
    if ncrypt.NCryptOpenStorageProvider(
            ctypes.byref(prov), MS_PLATFORM_KEY_STORAGE_PROVIDER, 0) != 0:
        raise TpmUnavailable("打开 TPM 提供程序失败")
    key = ctypes.c_void_p()
    try:
        if ncrypt.NCryptOpenKey(prov, ctypes.byref(key), key_name, 0, 0) != 0:
            raise TpmUnavailable("TPM 密钥不存在，请先授权设备")

        size = wintypes.DWORD(0)
        if ncrypt.NCryptSignHash(key, None, digest, 32, None, 0,
                                 ctypes.byref(size), NCRYPT_SILENT_FLAG) != 0:
            raise TpmUnavailable("TPM 签名失败（查询长度）")
        sig = ctypes.create_string_buffer(size.value)
        if ncrypt.NCryptSignHash(key, None, digest, 32, sig, size.value,
                                 ctypes.byref(size), NCRYPT_SILENT_FLAG) != 0:
            raise TpmUnavailable("TPM 签名失败")

        raw = sig.raw[: size.value]
        # CNG 返回 r||s（64 字节）→ 转 DER（站点端 cryptography 需要 DER）
        if len(raw) == 64:
            der = _raw_sig_to_der(raw[:32], raw[32:])
        else:
            der = raw
        return base64.b64encode(der).decode("ascii")
    finally:
        if key:
            ncrypt.NCryptFreeObject(key)
        if prov:
            ncrypt.NCryptFreeObject(prov)


def _der_int(v: bytes) -> bytes:
    v = v.lstrip(b"\x00") or b"\x00"
    if v[0] & 0x80:
        v = b"\x00" + v
    return b"\x02" + bytes([len(v)]) + v


def _raw_sig_to_der(r: bytes, s: bytes) -> bytes:
    body = _der_int(r) + _der_int(s)
    return b"\x30" + bytes([len(body)]) + body


# ---------------------------------------------------------------------------
# 设备凭据文件
# ---------------------------------------------------------------------------


def load_device() -> Optional[dict]:
    p = device_file_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("device_id"):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def save_device(device_id: str, *, api_base: str = DEFAULT_API_BASE,
                key_name: str = DEFAULT_KEY_NAME) -> Path:
    """写入设备凭据（**不含任何秘密**：私钥在 TPM 里）。"""
    p = device_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "device_id": device_id,
        "api_base": api_base,
        "tpm_key_name": key_name,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def clear_device() -> None:
    """删除本机设备凭据（不删 TPM 密钥 —— 需用户显式在系统里清理）。"""
    p = device_file_path()
    try:
        p.unlink()
    except OSError:
        pass


def new_device_id() -> str:
    """生成设备标识：随机 32 字符（公开标识，非秘密）。"""
    return secrets.token_hex(16)
