"""
tests/test_input_bypass.py
输入反检测模块单元测试。

覆盖：
- RHConfig 结构大小/字段（与 C 端 RH_CONFIG 对齐，共 80 字节）
- parse_count / parse_ratio / parse_percent 的钳制与非法输入回退
- auto_ratio 自动计算（synth/(real+synth)，分母为 0 取 0）
- build_config 的模式 → 结构字段映射（含钳制与自动比例）
- InputBypassManager.apply() 写入共享内存后 get_status() 可读回
"""

import ctypes
import sys

import pytest

_IS_WINDOWS = sys.platform == "win32"

from globalManagers.ConfigManager import ConfigManager

from webutils.function_input_bypass import (
    RHConfig,
    RATIO_MAX,
    RATIO_CLAMP,
    VOLATILITY_MAX,
    RH_MAGIC,
    parse_count,
    parse_ratio,
    parse_percent,
    auto_ratio,
    build_config,
    InputBypassManager,
)


class TestConfigStruct:
    """RHConfig 必须是 80 字节、与 C 端字段一一对应。"""

    def test_size_is_80(self):
        assert ctypes.sizeof(RHConfig) == 80

    def test_magic_roundtrip(self):
        cfg = RHConfig()
        cfg.magic = RH_MAGIC
        assert cfg.magic == RH_MAGIC

    def test_field_types(self):
        cfg = RHConfig()
        cfg.mouse_real = 5
        assert cfg.mouse_real == 5
        cfg.volatility = 10
        assert cfg.volatility == 10


class TestParseCount:
    """parse_count：≥0 整数，非法输入回退默认值。"""

    def test_normal(self):
        assert parse_count("42", "x") == 42

    def test_float_string_truncates(self):
        assert parse_count("3.9", "x") == 3

    def test_negative_clamped(self):
        assert parse_count("-5", "x") == 0

    def test_non_numeric_default(self):
        assert parse_count("abc", "x", default=7) == 7
        assert parse_count(None, "x") == 0
        assert parse_count("", "x") == 0


class TestParsePercent:
    """parse_percent：[0, VOLATILITY_MAX] 浮点，超上限钳制。"""

    def test_normal(self):
        assert parse_percent("10", "x") == 10.0

    def test_float_string(self):
        assert parse_percent("3.5", "x") == pytest.approx(3.5)

    def test_zero_means_off(self):
        assert parse_percent("0", "x") == 0.0

    def test_above_max_clamped(self):
        assert parse_percent("99", "x") == pytest.approx(VOLATILITY_MAX)
        assert parse_percent("50.1", "x") == pytest.approx(VOLATILITY_MAX)

    def test_negative_clamped(self):
        assert parse_percent("-5", "x") == 0.0

    def test_non_numeric_default(self):
        assert parse_percent("oops", "x") == 0.0
        assert parse_percent(None, "x") == 0.0


class TestParseRatio:
    """parse_ratio：[0, RATIO_MAX) 浮点，高于/等于阈值钳制到 RATIO_CLAMP（严格其下）。"""

    def test_normal(self):
        assert parse_ratio("0.3", "x") == pytest.approx(0.3)

    def test_greater_equal_max_clamped(self):
        assert parse_ratio("0.9", "x") == pytest.approx(RATIO_CLAMP)
        assert parse_ratio("1", "x") == pytest.approx(RATIO_CLAMP)
        assert RATIO_CLAMP < RATIO_MAX

    def test_negative_clamped(self):
        assert parse_ratio("-0.2", "x") == 0.0

    def test_non_numeric_default(self):
        assert parse_ratio("oops", "x") == 0.0
        assert parse_ratio(None, "x") == 0.0


class TestAutoRatio:
    """auto_ratio：synth/(real+synth)，分母为 0 取 0，超阈值钳制。"""

    def test_normal(self):
        assert auto_ratio(8, 2) == pytest.approx(2 / 10)

    def test_synth_only(self):
        assert auto_ratio(0, 5) == pytest.approx(RATIO_CLAMP)

    def test_zero_denominator(self):
        assert auto_ratio(0, 0) == 0.0

    def test_negative_counts_clamped(self):
        assert auto_ratio(-3, 2) == pytest.approx(0.0)

    def test_over_max_clamped(self):
        assert auto_ratio(1, 100) == pytest.approx(RATIO_CLAMP)


class TestBuildConfig:
    """build_config：模式与已钳制字段映射到 RHConfig。"""

    def test_auto_mode(self):
        cfg = build_config("auto", True, {})
        assert cfg.mode == 0
        assert cfg.armed == 1
        assert cfg.mouse_synth == 0
        assert cfg.volatility == 0

    def test_manual_mode(self):
        cfg = build_config("manual", False, {
            "mouse_real": 12,
            "key_real": 3,
            "mouse_synth": 7,
            "key_synth": 1,
        })
        assert cfg.mode == 1
        assert cfg.armed == 0
        assert cfg.mouse_real == 12
        assert cfg.key_real == 3
        assert cfg.mouse_synth == 7
        assert cfg.key_synth == 1
        # 比例自动计算：synth/(real+synth)
        assert cfg.mouse_ratio == pytest.approx(7 / 19)
        assert cfg.key_ratio == pytest.approx(1 / 4)

    def test_volatility_mapped(self):
        cfg = build_config("manual", True, {"volatility": "15"})
        assert cfg.volatility == 15

    def test_unknown_mode_falls_back_auto(self):
        cfg = build_config("weird", False, {})
        assert cfg.mode == 0

    def test_values_are_clamped(self):
        cfg = build_config("manual", False, {
            "mouse_real": -1,
            "volatility": 99,
        })
        assert cfg.mouse_real == 0
        assert cfg.volatility == VOLATILITY_MAX

    def test_armed_flag(self):
        assert build_config("auto", True, {}).armed == 1
        assert build_config("auto", False, {}).armed == 0


class TestManagerMap:
    """apply() 写入共享内存后 get_status() 能读回（Windows）。"""

    BASE = {
        "launcher.work.input_bypass": True,
        "launcher.work.input_bypass_mode": "manual",
        "launcher.work.input_bypass_mouse_real": "8",
        "launcher.work.input_bypass_key_real": "2",
        "launcher.work.input_bypass_mouse_synth": "1",
        "launcher.work.input_bypass_key_synth": "0",
        "launcher.work.input_bypass_volatility": "5",
    }

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        InputBypassManager.close()

    def test_apply_writes_and_reads(self, monkeypatch):
        monkeypatch.setattr(
            ConfigManager, "get",
            staticmethod(lambda key, default=None: self.BASE.get(key, default)),
        )
        result = InputBypassManager.apply()
        assert result["success"] is True
        assert result["armed"] is True
        assert result["mode"] == "manual"

        status = InputBypassManager.get_status()
        assert status["armed"] is True
        assert status["mode"] == "manual"

    def test_apply_auto_by_default(self, monkeypatch):
        def fake_get(key, default=None):
            return {
                "launcher.work.input_bypass": False,
                "launcher.work.input_bypass_mode": "auto",
            }.get(key, default)

        monkeypatch.setattr(
            ConfigManager, "get",
            staticmethod(lambda key, default=None: fake_get(key, default)),
        )
        InputBypassManager.apply()
        status = InputBypassManager.get_status()
        assert status["armed"] is False
        assert status["mode"] == "auto"