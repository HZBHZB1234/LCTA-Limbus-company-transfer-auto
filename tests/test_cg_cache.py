# -*- coding: utf-8 -*-
"""webutils.cg.bundle 缓存测试：增量扫描（路径不可变前提）、失效驱逐、v1 迁移、去重、force、size 同步。"""
import json
import os
import threading

import pytest

from webutils.cg import bundle as cg_bundle


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """假缓存目录 + 假数据目录 + 可计数的 _scan_one（catalog 隔离为空）。"""
    cache_root = tmp_path / "unity_cache"
    data_dir = tmp_path / "cg_data"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cg_bundle, "get_cache_root", lambda: cache_root)
    monkeypatch.setattr(cg_bundle, "_cg_data_dir", lambda: data_dir)
    monkeypatch.setattr(cg_bundle, "_catalog_cg_ids", lambda: set())  # 隔离本机真实 catalog

    calls = []
    lock = threading.Lock()

    def fake_scan_one(path, is_cancelled):
        with lock:
            calls.append(path)
        name = os.path.basename(os.path.dirname(path))
        return [{
            "cg_id": f"Story_CG/fake_{name}",
            "sprite_pid": 1,
            "tex_pid": 2,
            "bundle": path,
            "container": f"Assets/Resources_moved/Story/CG/Personality/{name}.png",
        }]

    monkeypatch.setattr(cg_bundle, "_scan_one", fake_scan_one)
    return {
        "cache_root": cache_root,
        "data_dir": data_dir,
        "calls": calls,
    }


def _make_bundle(root, *parts, size=60_000, name=None):
    p = root.joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    f = p / "__data"
    f.write_bytes(b"\0" * size)
    return str(f)


def _write_cache(data_dir, cache):
    (data_dir / "cg_ids.json").write_text(
        json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _read_cache(data_dir):
    return json.loads((data_dir / "cg_ids.json").read_text(encoding="utf-8"))


def _hit(path, cg_id):
    return {"cg_id": cg_id, "sprite_pid": 1, "tex_pid": 2, "bundle": path,
            "container": "Assets/Resources_moved/Story/CG/Personality/x.png"}


class TestIncrementalScan:
    def test_full_hit_skips_all(self, env):
        b1 = _make_bundle(env["cache_root"], "h1", "h2")
        b2 = _make_bundle(env["cache_root"], "h3")
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b1: {"size": 60_000, "hits": [_hit(b1, "Story_CG/a")]},
            b2: {"size": 60_000, "hits": [_hit(b2, "Unit_CG/b")]},
        }, "catalog": []}
        _write_cache(env["data_dir"], cache)

        result = cg_bundle.scan_cg_ids()
        assert env["calls"] == []  # 零 UnityPy 打开
        assert result["count"] == 2
        assert set(result["items"]) == {"Story_CG/a", "Unit_CG/b"}

    def test_incremental_scans_only_new(self, env):
        b1 = _make_bundle(env["cache_root"], "h1", "h2")
        b2 = _make_bundle(env["cache_root"], "h3")
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b1: {"size": 60_000, "hits": [_hit(b1, "Story_CG/a")]},
        }, "catalog": []}
        _write_cache(env["data_dir"], cache)

        result = cg_bundle.scan_cg_ids()
        assert env["calls"] == [b2]
        assert result["count"] == 2
        assert "Story_CG/a" in result["items"] and "Story_CG/fake_h3" in result["items"]
        # 新结果已落盘
        saved = _read_cache(env["data_dir"])
        assert b2 in saved["bundles"]

    def test_size_change_rescans(self, env):
        b1 = _make_bundle(env["cache_root"], "h1", "h2", size=60_000)
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b1: {"size": 99_999, "hits": [_hit(b1, "Story_CG/a")]},  # 与磁盘不符
        }, "catalog": []}
        _write_cache(env["data_dir"], cache)
        result = cg_bundle.scan_cg_ids()
        assert env["calls"] == [b1]
        assert "Story_CG/fake_h2" in result["items"]
        saved = _read_cache(env["data_dir"])
        assert saved["bundles"][b1]["size"] == 60_000

    def test_force_full_rescan(self, env):
        b1 = _make_bundle(env["cache_root"], "h1", "h2")
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b1: {"size": 60_000, "hits": [_hit(b1, "Story_CG/a")]},
        }, "catalog": []}
        _write_cache(env["data_dir"], cache)
        result = cg_bundle.scan_cg_ids(force=True)
        assert env["calls"] == [b1]
        assert "Story_CG/fake_h2" in result["items"]  # 重新扫描覆盖旧 hits

    def test_dedupe_largest_bundle_wins(self, env):
        b_small = _make_bundle(env["cache_root"], "s", size=60_000)
        b_big = _make_bundle(env["cache_root"], "b", size=200_000)
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b_small: {"size": 60_000, "hits": [_hit(b_small, "Story_CG/dup")]},
            b_big: {"size": 200_000, "hits": [_hit(b_big, "Story_CG/dup")]},
        }, "catalog": []}
        _write_cache(env["data_dir"], cache)
        result = cg_bundle.scan_cg_ids()
        assert result["items"]["Story_CG/dup"]["bundle"] == b_big

    def test_catalog_ids_merged_as_uncached(self, env, monkeypatch):
        """catalog 有效但未缓存的 ID 并入视图（cached=False，仅可锁定）；Unit_ 同名并入 Story_。"""
        b1 = _make_bundle(env["cache_root"], "h1", "h2")
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b1: {"size": 60_000, "hits": [_hit(b1, "Story_CG/a")]},
        }, "catalog": []}
        _write_cache(env["data_dir"], cache)
        monkeypatch.setattr(cg_bundle, "_catalog_cg_ids",
                            lambda: {"Story_CG/a", "Story_CG/not_downloaded", "Unit_CG/not_downloaded"})

        result = cg_bundle.scan_cg_ids()
        assert result["items"]["Story_CG/a"]["cached"] is True
        assert result["items"]["Story_CG/not_downloaded"]["cached"] is False
        assert result["items"]["Story_CG/not_downloaded"]["tex_pid"] is None
        # Unit_CG/not_downloaded 与 Story_CG/not_downloaded 同名 → 合并（只保留 Story_）
        assert "Unit_CG/not_downloaded" not in result["items"]
        assert result["count"] == 2

    def test_unit_cg_merged_into_story_cg(self, env):
        """同名的 Unit_CG/ 与 Story_CG/ 是同一 CG（兜底 label）：展示名优先 Story_。"""
        b_story = _make_bundle(env["cache_root"], "s1", "s2")
        b_unit = _make_bundle(env["cache_root"], "u1", "u2")
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b_story: {"size": 60_000, "hits": [_hit(b_story, "Story_CG/10101_normal")]},
            b_unit: {"size": 200_000, "hits": [_hit(b_unit, "Unit_CG/10101_normal")]},
        }, "catalog": []}
        _write_cache(env["data_dir"], cache)

        result = cg_bundle.scan_cg_ids()
        assert "Story_CG/10101_normal" in result["items"]
        assert "Unit_CG/10101_normal" not in result["items"]

    def test_unit_only_kept_when_no_story(self, env):
        """只有 Unit_ 存在时保留 Unit_ 展示。"""
        b_unit = _make_bundle(env["cache_root"], "u1", "u2")
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b_unit: {"size": 60_000, "hits": [_hit(b_unit, "Unit_CG/only_unit")]},
        }, "catalog": []}
        _write_cache(env["data_dir"], cache)
        result = cg_bundle.scan_cg_ids()
        assert "Unit_CG/only_unit" in result["items"]


class TestStalePurge:
    def test_purge_evicted_bundle_and_originals(self, env, tmp_path):
        b_live = _make_bundle(env["cache_root"], "h1", "h2")
        b_gone = str(tmp_path / "gone" / "__data")  # 缓存里记录但磁盘已不存在
        raw_bin = env["data_dir"] / "originals" / "dead.bin"
        raw_bin.parent.mkdir(parents=True, exist_ok=True)
        raw_bin.write_bytes(b"raw")
        originals = {
            "Story_CG/live": {"raw": str(env["data_dir"] / "o.bin"), "bundle": b_live,
                              "tex_pid": 2, "version_player": "5.x.x"},
            "Story_CG/gone": {"raw": str(raw_bin), "bundle": b_gone, "tex_pid": 2,
                              "version_player": "5.x.x"},
        }
        (env["data_dir"] / "originals.json").write_text(
            json.dumps(originals, ensure_ascii=False), encoding="utf-8")
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b_live: {"size": 60_000, "hits": [_hit(b_live, "Story_CG/a")]},
            b_gone: {"size": 60_000, "hits": [_hit(b_gone, "Story_CG/gone")]},
        }, "catalog": []}
        _write_cache(env["data_dir"], cache)

        result = cg_bundle.scan_cg_ids()
        saved = _read_cache(env["data_dir"])
        assert b_gone not in saved["bundles"]
        assert "Story_CG/gone" not in result["items"]
        # 还原数据已清理：raw bin 删除、store 条目移除、存活条目保留
        assert not raw_bin.exists()
        store = json.loads((env["data_dir"] / "originals.json").read_text(encoding="utf-8"))
        assert "Story_CG/gone" not in store
        assert "Story_CG/live" in store


class TestLegacyCacheInvalidation:
    def test_v2_wrong_format_discarded(self, env):
        """v1/v2 缓存含错误 BG/ ID 格式，直接作废重建（不迁移）。"""
        b1 = _make_bundle(env["cache_root"], "h1", "h2")
        legacy = {
            "version": 2,
            "scanned_at": 42,
            "bundles": {
                b1: {"size": 60_000, "hits": [_hit(b1, "BG/legacy")]},
            },
        }
        _write_cache(env["data_dir"], legacy)

        result = cg_bundle.load_index()
        assert result["count"] == 0

        result = cg_bundle.scan_cg_ids()
        assert env["calls"] == [b1]  # 全量重扫
        assert "BG/legacy" not in result["items"]
        assert "Story_CG/fake_h2" in result["items"]
        saved = _read_cache(env["data_dir"])
        assert saved["version"] == 3


class TestSizeSync:
    def test_update_bundle_size(self, env):
        b1 = _make_bundle(env["cache_root"], "h1", "h2", size=60_000)
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b1: {"size": 60_000, "hits": [_hit(b1, "Story_CG/a")]},
        }, "catalog": []}
        _write_cache(env["data_dir"], cache)
        # 模拟替换写回：文件变大
        os.utime(b1)
        with open(b1, "ab") as f:
            f.write(b"\0" * 5_000)
        cg_bundle._update_bundle_size(b1)
        saved = _read_cache(env["data_dir"])
        assert saved["bundles"][b1]["size"] == 65_000

    def test_scan_after_replace_no_rescan(self, env):
        b1 = _make_bundle(env["cache_root"], "h1", "h2", size=60_000)
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b1: {"size": 60_000, "hits": [_hit(b1, "Story_CG/a")]},
        }, "catalog": []}
        _write_cache(env["data_dir"], cache)
        with open(b1, "ab") as f:
            f.write(b"\0" * 5_000)
        cg_bundle._update_bundle_size(b1)  # replace 后同步 size

        cg_bundle.scan_cg_ids()
        assert env["calls"] == []  # size 已同步 → 无重扫


class TestEntryResolution:
    """索引条目解析：预览/替换接受存档形式（CG/<名>）与键形式，键统一为 Story_ 优先。"""

    def _setup(self, env):
        b_story = _make_bundle(env["cache_root"], "s1", "s2")
        b_unit = _make_bundle(env["cache_root"], "u1", "u2")
        cache = {"version": 3, "scanned_at": 1, "bundles": {
            b_story: {"size": 60_000, "hits": [_hit(b_story, "Story_CG/a")]},
            b_unit: {"size": 60_000, "hits": [_hit(b_unit, "Unit_CG/only_unit")]},
        }, "catalog": ["Story_CG/not_downloaded"]}
        _write_cache(env["data_dir"], cache)
        return b_story

    def test_save_form_resolves_story(self, env):
        self._setup(env)
        entry, key = cg_bundle._get_texture_entry("CG/a")
        assert key == "Story_CG/a"
        assert entry["cached"] is True

    def test_key_form_resolves(self, env):
        self._setup(env)
        entry, key = cg_bundle._get_texture_entry("Story_CG/a")
        assert key == "Story_CG/a"
        assert entry["tex_pid"] == 2

    def test_save_form_falls_back_to_unit(self, env):
        self._setup(env)
        entry, key = cg_bundle._get_texture_entry("CG/only_unit")
        assert key == "Unit_CG/only_unit"

    def test_unknown_raises(self, env):
        self._setup(env)
        with pytest.raises(LookupError, match="索引中未找到"):
            cg_bundle._get_texture_entry("CG/zzz")

    def test_catalog_only_not_local(self, env):
        self._setup(env)
        with pytest.raises(LookupError, match="未在本地缓存中下载"):
            cg_bundle._get_texture_entry("CG/not_downloaded")

    def test_restore_store_key_resolution(self, env):
        """originals store 以键形式为规范键：存档形式/键形式输入均可命中。"""
        import json as _json
        from webutils.cg.bundle import _originals_path, _original_store, _resolve_entry_key

        store = {"Story_CG/a": {"raw": "x", "bundle": "b", "tex_pid": 1}}
        _originals_path().write_text(
            _json.dumps(store, ensure_ascii=False), encoding="utf-8")
        assert _resolve_entry_key("CG/a", _original_store()) == "Story_CG/a"
        assert _resolve_entry_key("Story_CG/a", _original_store()) == "Story_CG/a"
        # 历史 BG/ 键原样命中
        store2 = {"BG/Dark_Forest": {"raw": "x"}}
        _originals_path().write_text(
            _json.dumps(store2, ensure_ascii=False), encoding="utf-8")
        assert _resolve_entry_key("BG/Dark_Forest", _original_store()) == "BG/Dark_Forest"
