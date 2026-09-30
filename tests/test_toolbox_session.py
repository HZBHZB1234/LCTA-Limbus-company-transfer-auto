# -*- coding: utf-8 -*-
"""P6 凭据存储测试（plan 16.4：DPAPI 当前用户隔离、旧明文迁移删除）。

真实调用 DPAPI（Windows），但全部在**临时路径**上，不碰用户真实凭据文件。
非 Windows 平台跳过 DPAPI 相关用例。
"""
import json
import os
from pathlib import Path

import pytest

from webutils.toolbox import session

IS_WINDOWS = os.name == "nt"
dpapi = pytest.mark.skipif(not IS_WINDOWS, reason="DPAPI 仅 Windows")


@pytest.fixture()
def store(tmp_path):
    return session.CredentialStore(tmp_path / "cred.bin")


class TestDpapiRoundtrip:
    @dpapi
    def test_protect_unprotect_roundtrip(self):
        secret = b"refresh-token-abc123"
        blob = session.protect(secret, entropy=b"LCTAtest")
        assert blob != secret
        assert secret not in blob
        assert session.unprotect(blob, entropy=b"LCTAtest") == secret

    @dpapi
    def test_entropy_mismatch_fails(self):
        blob = session.protect(b"data", entropy=b"one")
        with pytest.raises(session.CredentialStoreError):
            session.unprotect(blob, entropy=b"two")

    @dpapi
    def test_tampered_blob_fails(self):
        blob = bytearray(session.protect(b"data", entropy=b"e"))
        blob[len(blob) // 2] ^= 0xFF
        with pytest.raises(session.CredentialStoreError):
            session.unprotect(bytes(blob), entropy=b"e")


class TestStore:
    @dpapi
    def test_set_get_roundtrip(self, store):
        store.set("refresh_token", "secret-value")
        assert store.get("refresh_token") == "secret-value"
        assert store.has("refresh_token") is True

    @dpapi
    def test_file_is_not_plaintext(self, store):
        """落盘内容里绝不能出现明文令牌。"""
        store.set("refresh_token", "super-secret-token")
        raw = store.path.read_bytes()
        assert b"super-secret-token" not in raw
        assert raw.startswith(session.MAGIC)

    @dpapi
    def test_multiple_keys(self, store):
        store.set("a", "1")
        store.set("b", "2")
        assert store.get("a") == "1"
        assert store.get("b") == "2"

    @dpapi
    def test_delete_one_key(self, store):
        store.set("a", "1")
        store.set("b", "2")
        store.delete("a")
        assert store.get("a") is None
        assert store.get("b") == "2"

    @dpapi
    def test_clear_removes_file(self, store):
        store.set("refresh_token", "x")
        assert store.path.exists()
        store.clear()
        assert not store.path.exists()
        assert store.get("refresh_token") is None

    @dpapi
    def test_missing_file_is_empty(self, store):
        assert store.get("nope") is None
        assert store.has("nope") is False

    @dpapi
    def test_corrupt_file_does_not_crash(self, store):
        """凭据文件损坏不能让工具箱打不开（按空处理，用户重新登录即可）。"""
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_bytes(b"garbage-not-ours")
        assert store.get("x") is None

    @dpapi
    def test_truncated_magic_prefix(self, store):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_bytes(session.MAGIC + b"short")
        assert store.get("x") is None

    @dpapi
    def test_empty_value_deletes_key(self, store):
        store.set("a", "1")
        store.set("a", "")
        assert store.get("a") is None

    @dpapi
    def test_survives_reload(self, tmp_path):
        """新实例能读到同一文件（进程重启后登录态不丢）。"""
        path = tmp_path / "cred.bin"
        s1 = session.CredentialStore(path)
        s1.set("refresh_token", "persisted")
        s2 = session.CredentialStore(path)
        assert s2.get("refresh_token") == "persisted"


class TestPlaintextMigration:
    @dpapi
    def test_migrates_and_deletes_plaintext(self, store, tmp_path):
        """迁移后**必须删除**明文文件 —— 只迁不删等于没做迁移。"""
        plain = tmp_path / "auth.json"
        plain.write_text(json.dumps({"refresh_token": "old-plain"}), encoding="utf-8")

        assert store.migrate_from_plaintext(plain) is True
        assert store.get("refresh_token") == "old-plain"
        assert not plain.exists(), "旧明文凭据必须被删除"

    @dpapi
    def test_merges_with_existing(self, store, tmp_path):
        store.set("access_token", "existing")
        plain = tmp_path / "auth.json"
        plain.write_text(json.dumps({"refresh_token": "new"}), encoding="utf-8")
        store.migrate_from_plaintext(plain)
        assert store.get("access_token") == "existing"
        assert store.get("refresh_token") == "new"

    @dpapi
    def test_missing_file_returns_false(self, store, tmp_path):
        assert store.migrate_from_plaintext(tmp_path / "nope.json") is False

    @dpapi
    def test_invalid_json_is_skipped(self, store, tmp_path):
        plain = tmp_path / "auth.json"
        plain.write_text("{ not json", encoding="utf-8")
        assert store.migrate_from_plaintext(plain) is False

    @dpapi
    def test_non_dict_is_skipped(self, store, tmp_path):
        plain = tmp_path / "auth.json"
        plain.write_text("[1,2,3]", encoding="utf-8")
        assert store.migrate_from_plaintext(plain) is False


class TestNoDpapiFallback:
    def test_refuses_to_store_without_dpapi(self, monkeypatch):
        """非 Windows 必须**拒绝**存储，而不是降级成明文。

        静默明文落盘是最糟的选择：用户以为令牌被加密了。
        """
        monkeypatch.setattr(session, "_dpapi_available", lambda: False)
        with pytest.raises(session.CredentialStoreError):
            session.protect(b"secret")

    def test_refuses_unprotect_without_dpapi(self, monkeypatch):
        monkeypatch.setattr(session, "_dpapi_available", lambda: False)
        with pytest.raises(session.CredentialStoreError):
            session.unprotect(b"blob")