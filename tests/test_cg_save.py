# -*- coding: utf-8 -*-
"""webutils.cg 测试：AES 加解密往返、存档 CG 模型读写、锁定列表操作、CG ID 规范化。"""
import base64
import json
import os

import pytest

from webutils.cg.save import (
    encrypt_save,
    normalize_cg_id,
    read_cg_model,
    set_forced_cg,
    aes_crypt,
)

CG_KEY = "UserLocalStoryCGSaveModel"


def _make_save(key: bytes, iv: bytes, forced=None, unlocked=None) -> str:
    """构造一条合成存档（Base64(AES-CBC(JSON))，结构与真实存档一致）。"""
    cg = {
        "_cgIdList": unlocked or ["CG/10101_normal"],
        "_forcedCharacterCgIdList": forced or [],
        "_latestCg": "",
        "_freeviewCgIdList": [],
    }
    root = {
        "_stringDic": {
            "keys": ["UserLocalTutorialSaveModel", CG_KEY, "UserLocalFancySaveModel"],
            "values": ['{"_done":1}', json.dumps(cg, ensure_ascii=False, separators=(",", ":")), '{"_x":0}'],
        }
    }
    return encrypt_save(json.dumps(root, ensure_ascii=False, separators=(",", ":")), key, iv)


class TestAesRoundTrip:
    """AES-256-CBC + PKCS7 + Base64 往返与 .NET Aes 语义对齐（自检）。"""

    def test_roundtrip(self):
        key = os.urandom(32)
        iv = os.urandom(16)
        msg = '{"_cgIdList":["BG/test"],"_forcedCharacterCgIdList":[]}'
        enc = encrypt_save(msg, key, iv)
        assert enc and isinstance(enc, str)
        plain = aes_crypt(base64.b64decode(enc), key, iv, encrypt=False)
        assert plain.decode("utf-8") == msg

    def test_detects_wrong_key(self):
        key = os.urandom(32)
        iv = os.urandom(16)
        enc = encrypt_save('{"a":1}', key, iv)
        with pytest.raises(Exception):
            aes_crypt(
                base64.b64decode(enc),
                os.urandom(32),
                iv,
                encrypt=False,
            )


class TestNormalizeCgId:
    """三态 ID 模型（上游确认）：存档形式 CG//BG/，键形式 Story_CG//Unit_CG/ 自动转换。"""

    def test_save_forms_pass_through(self):
        assert normalize_cg_id("CG/10101_normal") == "CG/10101_normal"
        assert normalize_cg_id("BG/my_custom") == "BG/my_custom"

    def test_prefix_case_normalized(self):
        assert normalize_cg_id("cg/10101_normal") == "CG/10101_normal"
        assert normalize_cg_id("  BG/xxx  ") == "BG/xxx"

    def test_key_form_converted(self):
        assert normalize_cg_id("Story_CG/10101_normal") == "CG/10101_normal"
        assert normalize_cg_id("Unit_CG/10101_normal") == "CG/10101_normal"
        assert normalize_cg_id("story_cg/10101_normal") == "CG/10101_normal"

    def test_png_suffix_stripped(self):
        assert normalize_cg_id("CG/10101_normal.png") == "CG/10101_normal"
        assert normalize_cg_id("Story_CG/10101_normal.PNG") == "CG/10101_normal"

    def test_bare_name_rejected(self):
        with pytest.raises(ValueError):
            normalize_cg_id("10101_normal")
        # 非 key 的 story_ 开头名字不应误转
        with pytest.raises(ValueError):
            normalize_cg_id("story_old photo studio")

    def test_rejects_invalid(self):
        with pytest.raises(ValueError):
            normalize_cg_id("")
        with pytest.raises(ValueError):
            normalize_cg_id("CG/")
        with pytest.raises(ValueError):
            normalize_cg_id("CG/a/b")
        with pytest.raises(ValueError):
            normalize_cg_id("BG/..")


class TestForcedEntries:
    """forced 对象解析：仅人格 CG（<人格ID>_normal|_gacksung）。"""

    def test_parse_normal(self):
        from webutils.cg.save import parse_forced_entry

        assert parse_forced_entry("CG/10101_normal") == {"id": 10101, "gacksung": False}
        assert parse_forced_entry("CG/10101_gacksung") == {"id": 10101, "gacksung": True}
        assert parse_forced_entry("Story_CG/10101_normal") == {"id": 10101, "gacksung": False}

    def test_non_personality_rejected(self):
        from webutils.cg.save import parse_forced_entry

        with pytest.raises(ValueError, match="解锁池注入"):
            parse_forced_entry("CG/Dummy")
        with pytest.raises(ValueError, match="解锁池注入"):
            parse_forced_entry("BG/my_custom")

    def test_is_personality_name(self):
        from webutils.cg.save import is_personality_name

        assert is_personality_name("10101_normal") is True
        assert is_personality_name("10101_gacksung") is True
        assert is_personality_name("Dummy") is False
        assert is_personality_name("story_old photo studio") is False


class TestSaveModelIO:
    """存档 CG 模型读取与锁定写入（monkeypatch 注册表与路径，不触碰真实存档）。"""

    def _patch_env(self, monkeypatch, tmp_path, key, iv, slot="0"):
        save_file = tmp_path / f"save_slot_{slot}.json"
        save_file.write_text(_make_save(key, iv), encoding="utf-8")

        # 注入密钥（真实环境从注册表读取，测试环境直接替换）
        import webutils.cg.save as save_mod

        monkeypatch.setattr(
            save_mod,
            "get_credential",
            lambda: (key, iv),
        )
        return str(save_file)

    def test_read_model(self, monkeypatch, tmp_path):
        key, iv = os.urandom(32), os.urandom(16)
        path = self._patch_env(monkeypatch, tmp_path, key, iv)
        model = read_cg_model(path)
        assert model["cg_id_list"] == ["CG/10101_normal"]
        assert model["forced_ids"] == []

    def test_set_forced_then_read_back(self, monkeypatch, tmp_path):
        key, iv = os.urandom(32), os.urandom(16)
        path = self._patch_env(monkeypatch, tmp_path, key, iv)

        model = set_forced_cg(path, ["Story_CG/10102_normal", "CG/10103_gacksung"])
        # 写盘为对象数组，读取回显为可读存档 ID
        assert model["forced_ids"] == ["CG/10102_normal", "CG/10103_gacksung"]
        assert model["forced_list"] == [{"id": 10102, "gacksung": False},
                                        {"id": 10103, "gacksung": True}]
        # 其余模型字段保留
        assert model["cg_id_list"] == ["CG/10101_normal"]

        model2 = read_cg_model(path)
        assert model2["forced_ids"] == ["CG/10102_normal", "CG/10103_gacksung"]

    def test_clear_forced(self, monkeypatch, tmp_path):
        key, iv = os.urandom(32), os.urandom(16)
        path = self._patch_env(monkeypatch, tmp_path, key, iv)
        set_forced_cg(path, ["CG/10101_normal"])
        model = set_forced_cg(path, [])
        assert model["forced_ids"] == []

    def test_non_personality_rejected_on_apply(self, monkeypatch, tmp_path):
        """非人格资源（BG/ 自定义、Dummy 类）写入锁定列表报错并引导方案 B。"""
        key, iv = os.urandom(32), os.urandom(16)
        path = self._patch_env(monkeypatch, tmp_path, key, iv)
        with pytest.raises(ValueError, match="解锁池注入"):
            set_forced_cg(path, ["BG/my_custom"])
        with pytest.raises(ValueError, match="解锁池注入"):
            set_forced_cg(path, ["CG/Dummy"])

    def test_bg_valid_in_pool(self, monkeypatch, tmp_path):
        """方案 B：BG/ 自定义与任意字符串资源可注入解锁池（幂等）。"""
        from webutils.cg.save import remove_cg_id_list, set_cg_id_list

        key, iv = os.urandom(32), os.urandom(16)
        path = self._patch_env(monkeypatch, tmp_path, key, iv)

        model = set_cg_id_list(path, "BG/my_custom")
        assert model["cg_id_list"] == ["CG/10101_normal", "BG/my_custom"]
        assert model.get("pool_unstable") is True
        # 幂等：重复注入不重复
        model = set_cg_id_list(path, "CG/10101_normal")  # 已存在
        assert model["cg_id_list"].count("CG/10101_normal") == 1
        # 移除
        model = remove_cg_id_list(path, "BG/my_custom")
        assert model["cg_id_list"] == ["CG/10101_normal"]

    def test_other_models_preserved(self, monkeypatch, tmp_path):
        key, iv = os.urandom(32), os.urandom(16)
        path = self._patch_env(monkeypatch, tmp_path, key, iv)
        set_forced_cg(path, ["CG/10101_normal"])

        # 校验 TutorialSaveModel 的原始值未被破坏
        import webutils.cg.save as save_mod

        root = save_mod.load_root(path)
        keys = root["_stringDic"]["keys"]
        vals = root["_stringDic"]["values"]
        i = keys.index("UserLocalTutorialSaveModel")
        assert json.loads(vals[i]) == {"_done": 1}


class TestGameRunning:
    def test_detection_api(self):
        import webutils.cg.save as save_mod

        assert callable(save_mod.is_game_running)


class TestApiMixin:
    """CgMixin 层回归：cg_status 全链路（含密钥检测），防止门面缺名类错误。"""

    def _make_mixin(self):
        import webutils.cg as cg_mod
        from webui.app_api.cg import CgMixin

        mixin = CgMixin()
        mixin.log = mixin.log_error = mixin.log_ui = lambda *a, **k: None
        mixin.add_modal_log = mixin.del_modal_list = lambda *a, **k: None
        mixin.check_modal_running = lambda *a, **k: None
        return mixin, cg_mod

    def test_cg_status_success(self, monkeypatch, tmp_path):
        mixin, cg_mod = self._make_mixin()
        slot = tmp_path / "save_slot_1.json"
        slot.write_text("dummy", encoding="utf-8")

        monkeypatch.setattr(cg_mod, "list_save_slots",
                            lambda: [{"slot": "1", "path": str(slot), "mtime": "x", "size": 1}])
        monkeypatch.setattr(cg_mod, "get_credential", lambda: (b"k" * 32, b"i" * 16))
        monkeypatch.setattr(cg_mod, "is_game_running", lambda: False)
        monkeypatch.setattr(cg_mod, "cg_bundle_status", lambda: {"cache_root": "", "cache_count": 0})

        result = mixin.cg_status()
        assert result["success"] is True
        assert result["data"]["key_available"] is True
        assert result["data"]["game_running"] is False

    def test_cg_status_key_unavailable_is_not_error(self, monkeypatch, tmp_path):
        """密钥缺失应作为状态字段返回，而不是 success=false。"""
        mixin, cg_mod = self._make_mixin()

        monkeypatch.setattr(cg_mod, "list_save_slots", lambda: [])
        monkeypatch.setattr(cg_mod, "is_game_running", lambda: False)
        monkeypatch.setattr(cg_mod, "cg_bundle_status", lambda: {"cache_root": "", "cache_count": 0})

        def bad_cred():
            raise RuntimeError("注册表未找到 LocalGameOptionData（请先运行一次游戏生成密钥）")

        monkeypatch.setattr(cg_mod, "get_credential", bad_cred)

        result = mixin.cg_status()
        assert result["success"] is True
        assert result["data"]["key_available"] is False
        assert "LocalGameOptionData" in result["data"]["key_error"]

    def test_facade_exports_match_mixin_usage(self):
        """app_api/cg.py 用到的每个 cg.X 属性必须存在于 webutils.cg 门面。"""
        import webutils.cg as cg_mod
        from webui.app_api import cg as api_mod

        source = open(api_mod.__file__, encoding="utf-8").read()
        import re

        used = set(re.findall(r"\bcg\.([a-z_][a-z_0-9]*)\(", source))
        missing = [n for n in used if not hasattr(cg_mod, n)]
        assert not missing, f"webutils.cg 门面缺少属性：{missing}"

    def test_app_api_imports_clean(self):
        from webui.app_api.cg import CgMixin

        assert callable(CgMixin.cg_status)
        assert callable(CgMixin.cg_apply)
