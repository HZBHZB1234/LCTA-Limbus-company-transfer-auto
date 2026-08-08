"""
tests/test_damage_hook.py
伤害倍率 Hook 模块单元测试。

覆盖：
- DHConfig 结构大小/字段（与 C 端 DH_CONFIG 对齐，共 16584 字节）
- parse_multiplier 钳制 [0.1, 1000] 与非法输入回退
- parse_prologue_bytes / validate_payload 校验
- build_config 偏移 → 结构字段映射
- drain_new_log_entries 环形缓冲增量抽取（回绕/溢出丢弃/重置清洗）
- resolve_offsets 缓存命中 / API 刷新 / 游戏更新后自动失效（stale 降级）
- DamageHookManager.apply() 写入共享内存后 get_status() 可读回
"""

import ctypes
import json
import sys

import pytest

import webutils.function_damage_hook

_IS_WINDOWS = sys.platform == "win32"

from globalManagers.ConfigManager import ConfigManager

from webutils.function_damage_hook import (
    DHConfig,
    DH_MAGIC,
    LOG_RING_CAP,
    MULTIPLIER_MIN,
    MULTIPLIER_MAX,
    parse_multiplier,
    parse_prologue_bytes,
    validate_payload,
    build_config,
    drain_new_log_entries,
    DamageHookManager,
    offsets_cache_path,
)

OFFSETS_2026_08 = {
    "game_version": "2026-08-06",
    "gameassembly_sha256": "E580119AB44BC1FA3C0CA0B60102BFEA6574D4F162F2B9E64067047DB8CE5A7B",
    "gameassembly_size": 139846144,
    "rva_get_take_attack_dmg_multiplier": 17105360,
    "rva_get_opponent_faction": 16982112,
    "prologue": "48 8B C4 53 55 56 57 41 54 41 55 41 56 41 57 48",
}


class TestConfigStruct:
    """DHConfig 必须是 16584 字节、与 C 端字段一一对应。"""

    def test_size_is_16584(self):
        assert ctypes.sizeof(DHConfig) == 16584

    def test_magic_roundtrip(self):
        cfg = DHConfig()
        cfg.magic = DH_MAGIC
        assert cfg.magic == DH_MAGIC

    def test_prologue_array(self):
        cfg = DHConfig()
        for i in range(16):
            cfg.prologue[i] = i
        assert list(cfg.prologue[:4]) == [0, 1, 2, 3]

    def test_field_types(self):
        cfg = DHConfig()
        cfg.multiplier = 3.0
        assert cfg.multiplier == pytest.approx(3.0)
        cfg.rva_take_attack = 17105360
        assert cfg.rva_take_attack == 17105360

    def test_log_ring_layout(self):
        """log_head 偏移在 last_log 之后；环形缓冲为 CAP×128 字节。"""
        assert DHConfig.log_head.offset == DHConfig.last_log.offset + 128
        row = next(t for t in DHConfig._fields_ if t[0] == "log_ring")[1]
        assert ctypes.sizeof(row) == LOG_RING_CAP * 128


class TestParseMultiplier:
    """parse_multiplier：[0.1, 1000] 浮点，超界钳制，非法回退默认值。"""

    def test_normal(self):
        assert parse_multiplier("3.0") == pytest.approx(3.0)

    def test_default_value(self):
        assert parse_multiplier("5", default=7.0) == pytest.approx(5.0)

    def test_below_min_clamped(self):
        assert parse_multiplier("0.01") == pytest.approx(MULTIPLIER_MIN)

    def test_above_max_clamped(self):
        assert parse_multiplier("5000") == pytest.approx(MULTIPLIER_MAX)

    def test_negative_clamped(self):
        assert parse_multiplier("-2") == pytest.approx(MULTIPLIER_MIN)

    def test_non_numeric_default(self):
        assert parse_multiplier("oops") == pytest.approx(3.0)
        assert parse_multiplier(None, default=2.0) == pytest.approx(2.0)
        assert parse_multiplier("") == pytest.approx(3.0)


class TestParsePrologue:
    """parse_prologue_bytes：16 字节 hex 字符串解析。"""

    def test_normal(self):
        raw = parse_prologue_bytes(OFFSETS_2026_08["prologue"])
        assert raw is not None
        assert len(raw) == 16
        assert raw[0] == 0x48 and raw[3] == 0x53

    def test_lowercase_hex_ok(self):
        raw = parse_prologue_bytes(OFFSETS_2026_08["prologue"].lower())
        assert raw is not None and len(raw) == 16

    def test_short_rejected(self):
        assert parse_prologue_bytes("48 8B C4") is None

    def test_invalid_hex_rejected(self):
        assert parse_prologue_bytes("ZZ 8B C4 53 55 56 57 41 54 41 55 41 56 41 57 48") is None

    def test_non_string_rejected(self):
        assert parse_prologue_bytes(None) is None
        assert parse_prologue_bytes(12345) is None


class TestValidatePayload:
    """validate_payload：字段缺失/格式错误拒绝，合法规范化返回。"""

    def test_valid_payload(self):
        result = validate_payload(OFFSETS_2026_08)
        assert result is not None
        assert result["gameassembly_sha256"] == OFFSETS_2026_08["gameassembly_sha256"]
        assert result["rva_get_take_attack_dmg_multiplier"] == 17105360

    def test_missing_key_rejected(self):
        bad = dict(OFFSETS_2026_08)
        del bad["rva_get_opponent_faction"]
        assert validate_payload(bad) is None

    def test_bad_sha256_rejected(self):
        bad = dict(OFFSETS_2026_08, gameassembly_sha256="not-a-hash")
        assert validate_payload(bad) is None

    def test_zero_rva_rejected(self):
        bad = dict(OFFSETS_2026_08, rva_get_take_attack_dmg_multiplier=0)
        assert validate_payload(bad) is None

    def test_bad_prologue_rejected(self):
        bad = dict(OFFSETS_2026_08, prologue="48 8B")
        assert validate_payload(bad) is None


class TestBuildConfig:
    """build_config：偏移与配置映射到 DHConfig。"""

    def test_field_mapping(self):
        cfg = build_config(OFFSETS_2026_08, 3.0, True, True)
        assert cfg.magic == DH_MAGIC
        assert cfg.enabled == 1
        assert cfg.log == 1
        assert cfg.retry_requested == 0
        assert cfg.multiplier == pytest.approx(3.0)
        assert cfg.rva_take_attack == 17105360
        assert cfg.rva_opponent_faction == 16982112
        assert list(cfg.prologue[:4]) == [0x48, 0x8B, 0xC4, 0x53]

    def test_disabled_flags(self):
        cfg = build_config(OFFSETS_2026_08, 3.0, False, False)
        assert cfg.enabled == 0
        assert cfg.log == 0


def _fill_ring(cfg, entries, base=0):
    """按 C 端语义写入环形缓冲：槽位 = (base + i) % CAP，head/count 单调递增。"""
    cfg.log_head = base
    cfg.log_count = base
    for i, entry in enumerate(entries):
        raw = entry.encode("utf-8")[:127]
        slot = (base + i) % LOG_RING_CAP
        cfg.log_ring[slot][: len(raw)] = raw
    cfg.log_count = base + len(entries)
    cfg.log_head = base + len(entries)


class TestDrainLogEntries:
    """drain_new_log_entries：按 log_count 增量从环形缓冲抽取新日志。"""

    def test_no_new_entries(self):
        cfg = DHConfig()
        cfg.magic = DH_MAGIC
        _fill_ring(cfg, ["a", "b", "c"], base=0)
        result = drain_new_log_entries(cfg, 3)
        assert result == {"entries": [], "count": 3, "dropped": 0}

    def test_partial_drain_keeps_order(self):
        cfg = DHConfig()
        cfg.magic = DH_MAGIC
        _fill_ring(cfg, ["first", "second", "third", "fourth"], base=0)
        result = drain_new_log_entries(cfg, 2)
        assert result["entries"] == ["third", "fourth"]
        assert result["count"] == 4
        assert result["dropped"] == 0

    def test_wraparound_keeps_order(self):
        cfg = DHConfig()
        cfg.magic = DH_MAGIC
        _fill_ring(cfg, ["e127", "e128", "e129"], base=127)
        result = drain_new_log_entries(cfg, 127)
        # 槽位回绕：e127 在 slot 127，e128 在 slot 0，e129 在 slot 1
        assert result["entries"] == ["e127", "e128", "e129"]
        assert result["dropped"] == 0

    def test_overflow_reports_dropped_and_keeps_latest(self):
        cfg = DHConfig()
        cfg.magic = DH_MAGIC
        _fill_ring(cfg, [f"e{i}" for i in range(LOG_RING_CAP + 10)], base=0)
        result = drain_new_log_entries(cfg, 0)
        assert result["count"] == LOG_RING_CAP + 10
        assert result["dropped"] == 10
        assert len(result["entries"]) == LOG_RING_CAP
        assert result["entries"][-1] == f"e{LOG_RING_CAP + 9}"

    def test_count_reset_treated_as_full_drain(self):
        """共享内存被 apply() 重写（count 回 0）后，last_count 应重置。"""
        cfg = DHConfig()
        cfg.magic = DH_MAGIC
        _fill_ring(cfg, ["a", "b"], base=0)
        result = drain_new_log_entries(cfg, 99)
        assert result["entries"] == ["a", "b"]
        assert result["count"] == 2
        assert result["dropped"] == 0

    def test_empty_entries_filtered(self):
        cfg = DHConfig()
        cfg.magic = DH_MAGIC
        _fill_ring(cfg, ["keep"], base=0)
        cfg.log_count = 3  # 模拟两条空槽（0 填充）计入计数
        cfg.log_head = 3
        result = drain_new_log_entries(cfg, 0)
        assert result["entries"] == ["keep"]
        assert result["count"] == 3

    def test_nul_truncation_and_bad_bytes(self):
        cfg = DHConfig()
        cfg.magic = DH_MAGIC
        raw = b"target=OK\x00\xff\xfe"
        cfg.log_ring[0][: len(raw)] = raw
        cfg.log_count = 1
        cfg.log_head = 1
        result = drain_new_log_entries(cfg, 0)
        assert result["entries"] == ["target=OK"]

    def test_invalid_magic_still_parses(self):
        """纯函数不做 magic 校验（由调用方决定），结构读取即可解析。"""
        cfg = DHConfig()
        _fill_ring(cfg, ["x"], base=0)
        result = drain_new_log_entries(cfg, 0)
        assert result["entries"] == ["x"]


class TestOffsetsCache:
    """resolve_offsets：缓存命中 / API 刷新 / 游戏更新自动失效（stale 降级）。"""

    @pytest.fixture(autouse=True)
    def _isolation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LCTA_DAMAGE_HOOK_CACHE", str(tmp_path))
        monkeypatch.setattr(
            ConfigManager, "get",
            staticmethod(lambda key, default=None: {
                "game_path": str(tmp_path / "game"),
            }.get(key, default)),
        )
        yield
        with DamageHookManager._offsets_lock:
            DamageHookManager._offsets = None

    def _write_cache(self, local_hash, offsets=OFFSETS_2026_08):
        with open(offsets_cache_path(), "w", encoding="utf-8") as f:
            json.dump({"local_sha256": local_hash, "offsets": offsets}, f)

    def test_cache_hit_no_api_call(self, monkeypatch, tmp_path):
        local = {"sha256": OFFSETS_2026_08["gameassembly_sha256"], "size": 1}
        monkeypatch.setattr(webutils.function_damage_hook, "local_gameassembly_hash",
                            lambda: local)
        self._write_cache(OFFSETS_2026_08["gameassembly_sha256"])

        called = []
        monkeypatch.setattr(DamageHookManager, "_fetch_from_api",
                            staticmethod(lambda: called.append(1) or None))

        result = DamageHookManager.resolve_offsets()
        assert result["success"] is True
        assert result["source"] == "cache"
        assert result["stale"] is False
        assert called == []  # 未发网络请求

    def test_miss_fetches_and_caches(self, monkeypatch, tmp_path):
        local = {"sha256": OFFSETS_2026_08["gameassembly_sha256"], "size": 1}
        monkeypatch.setattr(webutils.function_damage_hook, "local_gameassembly_hash",
                            lambda: local)
        self._write_cache("OLD-HASH-DIFFERENT")

        monkeypatch.setattr(DamageHookManager, "_fetch_from_api",
                            staticmethod(lambda: dict(OFFSETS_2026_08)))

        result = DamageHookManager.resolve_offsets()
        assert result["success"] is True
        assert result["source"] == "api"
        assert result["stale"] is False
        # 缓存已更新为 API 数据
        with open(offsets_cache_path(), "r", encoding="utf-8") as f:
            cached = json.load(f)
        assert cached["local_sha256"] == OFFSETS_2026_08["gameassembly_sha256"]

    def test_update_not_published_keeps_old_cache_stale(self, monkeypatch, tmp_path):
        """游戏已更新但 API 尚未发布新版偏移 → 保留旧缓存并标记 stale（降级）。"""
        local = {"sha256": "NEW-GAME-HASH", "size": 2}
        monkeypatch.setattr(webutils.function_damage_hook, "local_gameassembly_hash",
                            lambda: local)
        self._write_cache(OFFSETS_2026_08["gameassembly_sha256"])

        monkeypatch.setattr(DamageHookManager, "_fetch_from_api",
                            staticmethod(lambda: dict(OFFSETS_2026_08)))

        result = DamageHookManager.resolve_offsets()
        assert result["success"] is True
        assert result["stale"] is True
        assert result["offsets"]["gameassembly_sha256"] == OFFSETS_2026_08["gameassembly_sha256"]
        # 缓存未被污染（仍是旧版本条目）
        with open(offsets_cache_path(), "r", encoding="utf-8") as f:
            cached = json.load(f)
        assert cached["local_sha256"] == OFFSETS_2026_08["gameassembly_sha256"]

    def test_fetch_failure_falls_back_stale(self, monkeypatch, tmp_path):
        """网络失败但有旧缓存 → 降级使用并标记 stale。"""
        local = {"sha256": "NEW-GAME-HASH", "size": 2}
        monkeypatch.setattr(webutils.function_damage_hook, "local_gameassembly_hash",
                            lambda: local)
        self._write_cache(OFFSETS_2026_08["gameassembly_sha256"])

        monkeypatch.setattr(DamageHookManager, "_fetch_from_api",
                            staticmethod(lambda: None))

        result = DamageHookManager.resolve_offsets()
        assert result["success"] is True
        assert result["stale"] is True
        assert result["offsets"] is not None

    def test_fetch_failure_no_cache_fails(self, monkeypatch, tmp_path):
        local = {"sha256": "NEW-GAME-HASH", "size": 2}
        monkeypatch.setattr(webutils.function_damage_hook, "local_gameassembly_hash",
                            lambda: local)
        monkeypatch.setattr(DamageHookManager, "_fetch_from_api",
                            staticmethod(lambda: None))

        result = DamageHookManager.resolve_offsets()
        assert result["success"] is False

    def test_game_missing_fails(self, monkeypatch):
        monkeypatch.setattr(webutils.function_damage_hook, "local_gameassembly_hash",
                            lambda: None)
        result = DamageHookManager.resolve_offsets()
        assert result["success"] is False
        assert result["reason"] == "game_missing"

    def test_force_refresh_ignores_cache(self, monkeypatch, tmp_path):
        local = {"sha256": OFFSETS_2026_08["gameassembly_sha256"], "size": 1}
        monkeypatch.setattr(webutils.function_damage_hook, "local_gameassembly_hash",
                            lambda: local)
        self._write_cache(OFFSETS_2026_08["gameassembly_sha256"])

        monkeypatch.setattr(DamageHookManager, "_fetch_from_api",
                            staticmethod(lambda: dict(OFFSETS_2026_08)))

        result = DamageHookManager.resolve_offsets(force_refresh=True)
        assert result["source"] == "api"


class TestManagerMap:
    """apply()（显式 offsets）写入共享内存后 get_status() 能读回（Windows）。"""

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        DamageHookManager.close()
        with DamageHookManager._offsets_lock:
            DamageHookManager._offsets = None

    @pytest.mark.skipif(not _IS_WINDOWS, reason="共享内存仅 Windows")
    def test_apply_writes_and_reads(self, monkeypatch):
        def fake_get(key, default=None):
            return {
                "launcher.work.damage_hook": True,
                "launcher.work.damage_hook_multiplier": "3.0",
                "launcher.work.damage_hook_log": True,
            }.get(key, default)

        monkeypatch.setattr(
            ConfigManager, "get",
            staticmethod(lambda key, default=None: fake_get(key, default)),
        )
        result = DamageHookManager.apply(offsets=OFFSETS_2026_08)
        assert result["success"] is True
        assert result["enabled"] is True

        status = DamageHookManager.get_status()
        # apply 未走 resolve，来源标记保持 None；共享内存已写入偏移
        assert status["offsets_source"] is None
        assert status["last_error_text"] == "正常"
        assert status["verified"] is False
        assert status["installed"] is False

    @pytest.mark.skipif(not _IS_WINDOWS, reason="共享内存仅 Windows")
    def test_apply_disabled(self, monkeypatch):
        monkeypatch.setattr(
            ConfigManager, "get",
            staticmethod(lambda key, default=None: {
                "launcher.work.damage_hook": False,
                "launcher.work.damage_hook_multiplier": "3.0",
            }.get(key, default)),
        )
        result = DamageHookManager.apply(offsets=OFFSETS_2026_08)
        assert result["enabled"] is False
