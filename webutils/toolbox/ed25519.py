# -*- coding: utf-8 -*-
"""Ed25519 验签（纯 Python，无第三方依赖）。

## 为什么不用 cryptography / PyNaCl

客户端运行在 **Python 3.9.6** 且 requirements 里**没有** ``cryptography``
或 ``PyNaCl``。为一个「验签一次」的动作引入编译型依赖，会显著增加打包与
离线安装成本（还要处理 wheel 平台匹配）。

Ed25519 **验签**是一个定义明确、可完整测试的操作，因此这里用 RFC 8032 的
标准参考算法实现，并以「服务端用 cryptography 生成的真实签名」做交叉验证
（见 ``tests/test_toolbox_manifest.py``）——不是自签自验那种自洽测试。

## 诚实边界

- 本实现**只做验签**，不生成签名（客户端不需要私钥，也不该有私钥）；
- 签名私钥永远不下发到客户端；
- 若将来引入 ``cryptography``，应优先用它并删除本模块。
"""
from __future__ import annotations

import hashlib

# Curve25519 参数（RFC 8032 §5.1）
P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I = pow(2, (P - 1) // 4, P)   # sqrt(-1)

BYTE_LEN = 32
SIG_LEN = 64


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _recover_x(y: int, sign: int) -> int:
    """由 y 与符号位恢复 x（RFC 8032 §5.1.3）。"""
    if y >= P:
        raise ValueError("y 超出域")
    x2 = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
    if x2 == 0:
        if sign:
            raise ValueError("x=0 但符号位为 1")
        return 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * I % P
    if (x * x - x2) % P != 0:
        raise ValueError("点不在曲线上")
    if (x & 1) != sign:
        x = P - x
    return x


# 仿射坐标下的点运算（验签只做几十次运算，性能足够）


def _edwards_add(p1, p2):
    x1, y1 = p1
    x2, y2 = p2
    denom = D * x1 * x2 * y1 * y2 % P
    x3 = (x1 * y2 + x2 * y1) * pow(1 + denom, P - 2, P) % P
    y3 = (y1 * y2 + x1 * x2) * pow(1 - denom, P - 2, P) % P
    return (x3, y3)


def _scalar_mult(point, scalar: int):
    """双倍-加法标量乘（从高位到低位）。"""
    result = (0, 1)   # 单位元
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _edwards_add(result, addend)
        addend = _edwards_add(addend, addend)
        scalar >>= 1
    return result


def _decompress(data: bytes):
    if len(data) != BYTE_LEN:
        raise ValueError("编码点长度错误")
    value = int.from_bytes(data, "little")
    sign = value >> 255
    y = value & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return (x, y)


def _compress(point) -> bytes:
    x, y = point
    value = y | ((x & 1) << 255)
    return value.to_bytes(BYTE_LEN, "little")


_BASE_POINT = None


def _base_point():
    """基点的解压结果（延迟计算并缓存）。"""
    global _BASE_POINT
    if _BASE_POINT is None:
        # B 的 y 坐标 = 4/5
        by = 4 * pow(5, P - 2, P) % P
        _BASE_POINT = (_recover_x(by, 0), by)
    return _BASE_POINT


def verify(public_key: bytes, signature: bytes, message: bytes) -> bool:
    """校验 Ed25519 签名。

    ``public_key`` 是 32 字节原始公钥，``signature`` 是 64 字节签名。
    任何格式/曲线错误一律返回 False（**不**抛异常）——
    调用方的语义是「验签不通过就拒绝安装」，不该因畸形输入而崩溃。

    ## 为什么必须拒绝「小阶点」

    全零公钥 ``00..00`` 解压后是**单位元**（阶为 1）。若不做检查，
    攻击者可以用「R = 单位元、S = 0」伪造出对**任意**消息都通过的签名
    （因为 ``S*B = 0 = R + k*A`` 恒成立）。这是 Ed25519 实现最经典的
    验证漏洞之一，且仅靠「验签返回 True/False」的自洽测试**发现不了**。

    这里拒绝两类点：``A``/``R`` 为单位元，以及 ``R`` 落在小阶子群中
    （阶 1/2/4/8 的点，共 8 个）。RFC 8032 要求 A 为素阶子群元素。
    """
    try:
        if len(public_key) != BYTE_LEN or len(signature) != SIG_LEN:
            return False

        r_bytes = signature[:BYTE_LEN]
        s_bytes = signature[BYTE_LEN:]

        # S 必须 < L（否则签名可延展）
        s = int.from_bytes(s_bytes, "little")
        if s >= L:
            return False

        a = _decompress(public_key)
        r = _decompress(r_bytes)

        # 小阶点检查：单位元与 8 个低阶点一律拒绝
        if _is_small_order(a) or _is_small_order(r):
            return False

        k = int.from_bytes(_sha512(r_bytes + public_key + message), "little") % L

        left = _scalar_mult(_base_point(), s)
        right = _edwards_add(r, _scalar_mult(a, k))
        return _compress(left) == _compress(right)
    except (ValueError, TypeError, ArithmeticError):
        return False


# 小阶点的压缩编码（阶 1/2/4/8 共 8 个）。Ed25519 的 8-torsion 子群元素
# 数量固定且可枚举，直接比对编码是最稳妥的做法。
def _small_order_encodings() -> frozenset:
    """枚举 8-torsion 子群的所有点编码（延迟计算并缓存）。"""
    global _SMALL_ORDER
    if _SMALL_ORDER is None:
        identity = (0, 1)
        # 二阶点：(0, -1)
        order2 = (0, P - 1)
        points = {identity, order2}
        # 四阶与八阶点由二阶点与一个四阶点生成
        # (x, y) 满足 x^2 = -1 的解给出四阶点
        x4 = I
        y4 = 0
        order4 = (x4, y4)
        points.add(order4)
        points.add((P - x4, y4))
        # 用 2*order4 得到二阶点已在集合中；再用 order4 + order2 得到八阶点
        for p in list(points):
            points.add(_edwards_add(p, order4))
            points.add(_edwards_add(p, order2))
        _SMALL_ORDER = frozenset(_compress(p) for p in points)
    return _SMALL_ORDER


_SMALL_ORDER = None


def _is_small_order(point) -> bool:
    """点是否落在小阶子群（单位元/二阶/四阶/八阶）。"""
    try:
        return _compress(point) in _small_order_encodings()
    except (ValueError, TypeError):
        return True


def verify_from_der_public_key(der: bytes, signature: bytes, message: bytes) -> bool:
    """从 DER/PEM 公钥验签。

    服务端用 ``cryptography`` 输出 PEM（``SubjectPublicKeyInfo``）。
    Ed25519 的 SPKI 结构固定：前缀 12 字节 + 32 字节原始公钥。
    这里做**严格前缀校验**，不猜测结构 —— 结构不符直接 False。
    """
    raw = _extract_ed25519_raw(der)
    if raw is None:
        return False
    return verify(raw, signature, message)


# Ed25519 SubjectPublicKeyInfo 的固定前缀（RFC 8410）
_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


def _extract_ed25519_raw(der: bytes) -> bytes | None:
    """从 PEM 或 DER 中提取 32 字节原始 Ed25519 公钥。"""
    data = der
    if b"-----BEGIN" in data:
        import base64
        import re

        m = re.search(rb"-----BEGIN PUBLIC KEY-----(.+?)-----END PUBLIC KEY-----", data, re.S)
        if not m:
            return None
        try:
            data = base64.b64decode(re.sub(rb"\s+", b"", m.group(1)))
        except Exception:  # noqa: BLE001
            return None

    if len(data) == 32:
        # 已经是原始公钥
        return data
    if len(data) == len(_SPKI_PREFIX) + 32 and data.startswith(_SPKI_PREFIX):
        return data[len(_SPKI_PREFIX):]
    return None


def canonical_bytes(manifest: dict) -> bytes:
    """清单的规范字节串。

    必须与服务端 ``tool_releases.manifest_canonical_bytes`` **逐字节一致**：
    排序键 + 紧凑分隔符 + ``ensure_ascii=False``。任何一处不同都会导致
    验签永久失败（且现象是「所有包都装不上」，很难排查）。
    """
    import json

    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")