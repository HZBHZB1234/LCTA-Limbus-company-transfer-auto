"""
tests/test_config_api_coerce.py
webui/app_api/config.py 前端同步通道的类型转换测试。

前端通用同步通道（bindConfigAutoSave / collectConfigFromUI → update_config_batch）
对非 checkbox/radio 控件一律提交字符串。后端必须按 config_check.json 声明的类型
转换，否则 int 键会被以 "8" 落盘，下次启动 validate() 报错并被 fix() 重置为默认值。

覆盖：
- int 键："8" → 8；非法数字串保留原值
- bool 键：字符串 "true"/"false"/"1"/"0" 兜底转换；已传 bool 不受影响
- str 键：传数字不误转（如 proper.max_length 声明为 str）
- 未声明键（cheat 插件动态键等）：原样保留
- update_config_batch 批量写入前逐键转换，未声明键仍原样传入 set_batch
- schema 加载失败（path_ 未设置）时降级为原样返回
"""
from unittest.mock import MagicMock, patch

import pytest

import webui.app_api.config as config_mod
from webui.app_api.config import _coerce_config_value

TRUE_CASES = ["true", "TRUE", "1", "on", "yes", " true "]
FALSE_CASES = ["false", "0", "off", "no"]


def _make_api():
    api = object.__new__(config_mod.ConfigMixin)
    api.log = MagicMock()
    api.log_error = MagicMock()
    api.log_manager = MagicMock()
    return api


@pytest.fixture
def schema():
    return {
        "ui_default": {
            "aria2_dl": {"jobs": "int", "connection_limit": "int", "seed_time": "int"},
            "bank": {"quality": "int", "threads": "int"},
            "proper": {"max_length": "str", "min_length": "str"},
        },
        "launcher": {
            "resource_update": {
                "jobs": "int", "retry_max": "int",
                "retry_delay": "int", "connection_limit": "int",
            },
            "work": {"gui_mode": "bool", "crash_popup": "bool"},
        },
    }


class TestCoerceInt:
    def test_numeric_string_to_int(self, schema):
        with patch.object(config_mod, "load_config_types", return_value=schema):
            assert _coerce_config_value("ui_default.bank.quality", "90") == 90
            assert _coerce_config_value("launcher.resource_update.jobs", "8") == 8
            assert _coerce_config_value("ui_default.aria2_dl.seed_time", "0") == 0

    def test_already_int_untouched(self, schema):
        with patch.object(config_mod, "load_config_types", return_value=schema):
            assert _coerce_config_value("ui_default.bank.quality", 92) == 92

    def test_invalid_string_kept(self, schema):
        with patch.object(config_mod, "load_config_types", return_value=schema):
            assert _coerce_config_value("ui_default.bank.quality", "abc") == "abc"
            assert _coerce_config_value("ui_default.bank.quality", "") == ""


class TestCoerceBool:
    @pytest.mark.parametrize("raw", TRUE_CASES)
    def test_true_strings(self, schema, raw):
        with patch.object(config_mod, "load_config_types", return_value=schema):
            assert _coerce_config_value("launcher.work.gui_mode", raw) is True

    @pytest.mark.parametrize("raw", FALSE_CASES)
    def test_false_strings(self, schema, raw):
        with patch.object(config_mod, "load_config_types", return_value=schema):
            assert _coerce_config_value("launcher.work.crash_popup", raw) is False

    def test_already_bool_untouched(self, schema):
        with patch.object(config_mod, "load_config_types", return_value=schema):
            assert _coerce_config_value("launcher.work.gui_mode", True) is True

    def test_other_string_kept(self, schema):
        with patch.object(config_mod, "load_config_types", return_value=schema):
            assert _coerce_config_value("launcher.work.gui_mode", "maybe") == "maybe"


class TestCoerceStrAndUnknown:
    def test_str_key_number_not_coerced(self, schema):
        with patch.object(config_mod, "load_config_types", return_value=schema):
            assert _coerce_config_value("ui_default.proper.max_length", "100") == "100"

    def test_unknown_key_untouched(self, schema):
        with patch.object(config_mod, "load_config_types", return_value=schema):
            assert _coerce_config_value("cheat_plugins.foo", "8") == "8"
            assert _coerce_config_value("damage_hook_multiplier", "3.0") == "3.0"

    def test_non_string_value_untouched(self, schema):
        with patch.object(config_mod, "load_config_types", return_value=schema):
            assert _coerce_config_value("ui_default.bank.quality", 8) == 8
            assert _coerce_config_value("ui_default.bank.quality", None) is None

    def test_schema_load_failure_returns_original(self):
        with patch.object(config_mod, "load_config_types", side_effect=OSError):
            assert _coerce_config_value("ui_default.bank.quality", "90") == "90"


class TestUpdateConfigBatchCoerces:
    @patch("webui.app_api.config.ConfigManager")
    def test_int_keys_coerced_before_set_batch(self, mock_cm):
        api = _make_api()
        instance = mock_cm.return_value
        instance.set_batch.return_value = 2
        schema = {"launcher": {"resource_update": {"jobs": "int"}}}
        with patch.object(config_mod, "load_config_types", return_value=schema):
            result = api.update_config_batch(
                {"launcher.resource_update.jobs": "8", "cheat.unknown": "9"})
        instance.set_batch.assert_called_once_with(
            {"launcher.resource_update.jobs": 8, "cheat.unknown": "9"})
        assert result == {"success": True, "updated": 2, "total": 2}

    @patch("webui.app_api.config.ConfigManager")
    def test_update_config_value_coerces(self, mock_cm):
        api = _make_api()
        schema = {"ui_default": {"bank": {"quality": "int"}}}
        with patch.object(config_mod, "load_config_types", return_value=schema):
            assert api.update_config_value("ui_default.bank.quality", "90") is True
        mock_cm.return_value.set.assert_called_once_with("ui_default.bank.quality", 90)
