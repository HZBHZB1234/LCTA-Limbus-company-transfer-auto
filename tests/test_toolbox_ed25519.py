# -*- coding: utf-8 -*-
"""客户端 Ed25519 验签测试（P6 / plan 16.3）。

**关键点：测试向量来自服务端的真实 ``cryptography`` 签名**，而不是用本模块
自己签、自己验。后者是自洽测试 —— 算法写错了照样「通过」。

向量生成方式（见 ``tests/data/ed25519_vectors.json`` 的 note）：
``site/.venv``（装有 cryptography）用 Ed25519PrivateKey 对 8 个含中文/emoji
的清单规范字节串签名，公钥同时导出 raw 与 PEM 两种形态。

客户端**只验签、不签名**：私钥永不下发。
"""
import json
from pathlib import Path

import pytest

from webutils.toolbox import ed25519

VECTORS_PATH = Path(__file__).parent / "data" / "ed25519_vectors.json"


@pytest.fixture(scope="module")
def vectors():
    if not VECTORS_PATH.exists():
        pytest.skip("缺少测试向量文件")
    return json.loads(VECTORS_PATH.read_text(encoding="utf-8"))


class TestVerifyRealSignatures:
    def test_all_real_signatures_verify(self, vectors):
        """服务端真实签名必须全部验证通过（这是互通性的核心断言）。"""
        pub = bytes.fromhex(vectors["pub_raw"])
        for i, v in enumerate(vectors["vectors"]):
            sig = bytes.fromhex(v["signature"])
            msg = bytes.fromhex(v["message"])
            assert ed25519.verify(pub, sig, msg) is True, f"向量 {i} 验签失败"

    def test_pem_public_key_also_works(self, vectors):
        """PEM（SubjectPublicKeyInfo）形态也要能解析。"""
        pem = vectors["pub_pem"].encode("utf-8")
        for i, v in enumerate(vectors["vectors"]):
            sig = bytes.fromhex(v["signature"])
            msg = bytes.fromhex(v["message"])
            assert ed25519.verify_from_der_public_key(pem, sig, msg) is True, f"向量 {i} PEM 验签失败"

    def test_vectors_include_non_ascii(self, vectors):
        """向量必须含非 ASCII，确保规范字节串编码一致（否则中文清单永远验不过）。

        注意：``message`` 字段是 **hex 编码**的，所以非 ASCII 要看解码后的内容，
        不能直接对 JSON 文本做子串匹配。
        """
        found_non_ascii = False
        for v in vectors["vectors"]:
            text = bytes.fromhex(v["message"]).decode("utf-8")
            if any(ord(ch) > 127 for ch in text):
                found_non_ascii = True
                break
        assert found_non_ascii, "测试向量未覆盖非 ASCII 清单内容"


class TestRejectsBadInput:
    def test_tampered_message_rejected(self, vectors):
        pub = bytes.fromhex(vectors["pub_raw"])
        v = vectors["vectors"][0]
        sig = bytes.fromhex(v["signature"])
        msg = bytes.fromhex(v["message"])
        tampered = bytearray(msg)
        tampered[-1] ^= 0x01
        assert ed25519.verify(pub, sig, bytes(tampered)) is False

    def test_tampered_signature_rejected(self, vectors):
        pub = bytes.fromhex(vectors["pub_raw"])
        v = vectors["vectors"][0]
        sig = bytearray(bytes.fromhex(v["signature"]))
        msg = bytes.fromhex(v["message"])
        sig[0] ^= 0x01
        assert ed25519.verify(pub, bytes(sig), msg) is False

    def test_wrong_public_key_rejected(self, vectors):
        v = vectors["vectors"][0]
        pub = bytearray(bytes.fromhex(vectors["pub_raw"]))
        pub[0] ^= 0x01
        assert ed25519.verify(bytes(pub), bytes.fromhex(v["signature"]),
                              bytes.fromhex(v["message"])) is False

    def test_wrong_length_rejected(self, vectors):
        pub = bytes.fromhex(vectors["pub_raw"])
        v = vectors["vectors"][0]
        sig = bytes.fromhex(v["signature"])
        msg = bytes.fromhex(v["message"])
        assert ed25519.verify(pub[:31], sig, msg) is False
        assert ed25519.verify(pub + b"\x00", sig, msg) is False
        assert ed25519.verify(pub, sig[:63], msg) is False

    def test_malleable_signature_rejected(self, vectors):
        """S >= L 的签名必须拒绝（否则同一消息有多个「有效」签名）。"""
        pub = bytes.fromhex(vectors["pub_raw"])
        v = vectors["vectors"][0]
        msg = bytes.fromhex(v["message"])
        r_part = bytes.fromhex(v["signature"])[:32]
        bad = r_part + bytes([0xFF] * 32)
        assert ed25519.verify(pub, bad, msg) is False

    def test_garbage_public_key_returns_false_not_raise(self):
        """畸形公钥必须返回 False，而不是抛异常。

        调用方语义是「验签不过就拒绝安装」；抛异常会让畸形输入变成
        未处理错误，界面显示「崩溃」而不是「包不可信」。
        """
        assert ed25519.verify(b"\x00" * 32, b"\x00" * 64, b"msg") is False
        assert ed25519.verify(b"\xff" * 32, b"\xff" * 64, b"msg") is False

    def test_empty_inputs_return_false(self):
        assert ed25519.verify(b"", b"", b"") is False


class TestCanonicalBytes:
    def test_matches_server_convention(self):
        """规范字节串必须与服务端逐字节一致（排序键 + 紧凑分隔符 + 非 ASCII 原样）。

        任何差异都会导致**所有包都装不上**，且现象极难排查。
        """
        manifest = {"b": 2, "a": 1, "zh": "中文"}
        got = ed25519.canonical_bytes(manifest)
        # 手写期望值（不调用被测代码）
        assert got == b'{"a":1,"b":2,"zh":"\xe4\xb8\xad\xe6\x96\x87"}'

    def test_key_order_does_not_matter(self):
        m1 = {"a": 1, "b": {"y": 2, "x": 3}}
        m2 = {"b": {"x": 3, "y": 2}, "a": 1}
        assert ed25519.canonical_bytes(m1) == ed25519.canonical_bytes(m2)

    def test_no_spaces_in_output(self):
        assert b" " not in ed25519.canonical_bytes({"a": 1, "b": [1, 2]})

    def test_canonical_bytes_used_for_verification(self, vectors):
        """端到端：用规范字节串验签，证明签名覆盖的是清单本身。"""
        pub = bytes.fromhex(vectors["pub_raw"])
        v = vectors["vectors"][0]
        manifest = json.loads(bytes.fromhex(v["message"]).decode("utf-8"))
        assert ed25519.canonical_bytes(manifest) == bytes.fromhex(v["message"])
        assert ed25519.verify(pub, bytes.fromhex(v["signature"]),
                              ed25519.canonical_bytes(manifest)) is True