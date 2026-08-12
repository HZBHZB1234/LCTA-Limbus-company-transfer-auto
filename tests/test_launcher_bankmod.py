"""launcher/bankmod.py：启动期 .rebank 补丁与哈希缓存测试"""
import hashlib
import json
import os
import time
import zipfile

import pytest

from launcher import bankmod


@pytest.fixture(autouse=True, scope="module")
def _restore_global_log_state():
    """bankmod 导入时会实例化 LogManager 单例并把 LCTA logger 设为
    propagate=False，破坏后续测试模块的 caplog 捕获，模块结束后还原。"""
    yield
    import logging
    from globalManagers.LogManager import LogManager
    LogManager._instance = None
    LogManager._initialized = False
    logging.getLogger("LCTA").propagate = True


def _make_rebank(tmp_path, name="mod.rebank", base_bank="Weapon.bank"):
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("rebank.json", json.dumps({"format": "rebank", "base_bank": "Weapon"}))
        z.writestr("0/voice.wav", b"wavdata")
    return str(p)


def test_rebank_files_in(tmp_path):
    _make_rebank(tmp_path, "a.rebank")
    _make_rebank(tmp_path, "b.rebank")
    (tmp_path / "c.rebank_disable").write_bytes(b"x")
    got = bankmod.rebank_files_in(str(tmp_path))
    assert sorted(os.path.basename(g) for g in got) == ["a.rebank", "b.rebank"]


def test_cache_dir_and_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    monkeypatch.setattr(bankmod, "cache_dir", lambda: str(tmp_path / "la" / "LCTA" / "bank-cache"))
    a = _make_rebank(tmp_path, "a.rebank")
    b = _make_rebank(tmp_path, "b.rebank")
    d1 = bankmod.mod_digest([a, b])
    d2 = bankmod.mod_digest([a, b])
    assert d1 == d2
    assert len(d1) == 64


def test_apply_rebanks_cache_hit(tmp_path, monkeypatch):
    _make_rebank(tmp_path, "a.rebank")
    sound_dir = tmp_path / "sound"
    sound_dir.mkdir()
    (sound_dir / "Weapon.bank").write_bytes(b"original")
    cache = tmp_path / "cache"
    cache.mkdir()

    calls = {"patch": 0}
    fake_digest = "d" * 64

    def fake_cache_dir():
        return str(cache)

    def fake_patch_into(target_bank, rebanks, log=None):
        calls["patch"] += 1
        with open(target_bank, "wb") as fh:
            fh.write(b"patched")

    monkeypatch.setattr(bankmod, "cache_dir", fake_cache_dir)
    monkeypatch.setattr(bankmod, "_patch_into", fake_patch_into)
    monkeypatch.setattr(bankmod, "mod_digest", lambda paths: fake_digest)
    monkeypatch.setattr("launcher.sound.sound_folder", lambda: str(sound_dir))

    r = bankmod.apply_rebanks(str(tmp_path))
    assert calls["patch"] == 1
    assert r["patched"] == ["Weapon.bank"]
    assert r["cache_miss"] == 1

    # 第二次运行：缓存命中，不再补丁
    (sound_dir / "Weapon.bank").write_bytes(b"original")
    r2 = bankmod.apply_rebanks(str(tmp_path))
    assert calls["patch"] == 1
    assert r2["cache_hit"] == 1


def test_apply_rebanks_rollback_on_failure(tmp_path, monkeypatch):
    """补丁失败时恢复 .bak 原版，且不写缓存。"""
    _make_rebank(tmp_path, "a.rebank")
    sound_dir = tmp_path / "sound"
    sound_dir.mkdir()
    (sound_dir / "Weapon.bank").write_bytes(b"original")
    cache = tmp_path / "cache"
    cache.mkdir()

    def fake_patch_into(target_bank, rebanks, log=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(bankmod, "cache_dir", lambda: str(cache))
    monkeypatch.setattr(bankmod, "_patch_into", fake_patch_into)
    monkeypatch.setattr("launcher.sound.sound_folder", lambda: str(sound_dir))

    r = bankmod.apply_rebanks(str(tmp_path))
    assert r["patched"] == []
    assert r["skipped"] == [("Weapon.bank", "boom")]
    assert (sound_dir / "Weapon.bank").read_bytes() == b"original"
    assert not (sound_dir / "Weapon.bank.bak").exists()
    assert list(cache.iterdir()) == []


def test_prune_cache(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    for i in range(5):
        (cache / ("%d.bank" % i)).write_bytes(b"x")
        (cache / ("%d.bank.json" % i)).write_text("{}", encoding="utf-8")
        os.utime(cache / ("%d.bank" % i), (time.time(), time.time() + i * 10))
        os.utime(cache / ("%d.bank.json" % i), (time.time(), time.time() + i * 10))
    monkeypatch.setattr(bankmod, "cache_dir", lambda: str(cache))

    removed = bankmod.prune_cache(max_entries=2)
    assert removed == 3
    remaining = sorted(p.name for p in cache.glob("*.bank"))
    assert remaining == ["3.bank", "4.bank"]
    assert sorted(p.name for p in cache.glob("*.json")) == ["3.bank.json", "4.bank.json"]
