"""launcher/modcache 工具测试：_disable 过滤 / 目录摘要 / 原子写 / LRU 清理。"""
from pathlib import Path

import pytest

from launcher import modcache


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    return modcache.cache_root()


def test_enabled_mod_files_filters_disable_file(tmp_path):
    (tmp_path / "a.bank").write_bytes(b"a")
    (tmp_path / "b.bank_disable").write_bytes(b"b")
    (tmp_path / "c.carra2_disable").write_bytes(b"c")
    result = [p.name for p in modcache.enabled_mod_files(tmp_path, "*.bank")]
    assert result == ["a.bank"]
    result2 = [p.name for p in modcache.enabled_mod_files(tmp_path, "*") if p.is_file()]
    assert result2 == ["a.bank"]


def test_enabled_mod_files_filters_disable_directory(tmp_path):
    mod = tmp_path / "MyMod_disable"
    mod.mkdir()
    (mod / "1.rebank").write_bytes(b"x")
    (tmp_path / "Other").mkdir()
    (tmp_path / "Other" / "2.rebank").write_bytes(b"y")
    result = [p.name for p in modcache.enabled_mod_files(tmp_path, "*.rebank")]
    assert result == ["2.rebank"]


def test_tree_digest_is_content_based(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "f.txt").write_text("hello")
    (b / "f.txt").write_text("hello")
    assert modcache.tree_digest(str(a)) == modcache.tree_digest(str(b))
    (a / "f.txt").write_text("world")
    assert modcache.tree_digest(str(a)) != modcache.tree_digest(str(b))


def test_atomic_write_replaces(tmp_path):
    dest = tmp_path / "sub" / "out.bin"
    modcache.atomic_write(dest, b"one")
    assert dest.read_bytes() == b"one"
    modcache.atomic_write(dest, b"two")
    assert dest.read_bytes() == b"two"
    assert not list(dest.parent.glob("*.tmp"))


def test_prune_lru_keeps_newest(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    for i in range(5):
        (cache / f"f{i}.carra2").write_bytes(b"x")
    # 手动调整 mtime 保证顺序
    import os
    base = 1_700_000_000
    for i, p in enumerate(sorted(cache.glob("*.carra2"))):
        os.utime(p, (base + i, base + i))
    removed = modcache.prune_lru(cache, 3)
    assert removed == 2
    remaining = sorted(cache.glob("*.carra2"))
    assert len(remaining) == 3
    assert remaining[0].name == "f2.carra2"  # 最旧 f0/f1 被移除
    assert not list(cache.glob("*.tmp"))


def test_prune_lru_removes_dirs_too(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    for i in range(4):
        d = cache / f"dir{i}"
        d.mkdir()
        (d / "x").write_bytes(b"x")
    removed = modcache.prune_lru(cache, 2)
    assert removed == 2
    assert len(list(cache.iterdir())) == 2


def test_sha256_file_matches_hashlib(tmp_path):
    import hashlib
    p = tmp_path / "f.bin"
    p.write_bytes(b"payload" * 1000)
    assert modcache.sha256_file(str(p)) == hashlib.sha256(b"payload" * 1000).hexdigest()