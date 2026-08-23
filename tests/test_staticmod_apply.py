# -*- coding: utf-8 -*-
"""launcher/staticmod._read_textasset_json 的 TextAsset 定位测试。

覆盖 .staticmod manifest 可选 container 字段引入的精确寻址：
  - 同名不同目录文件（实测 event-mission/ 与 mission/ 下 walpu8/9-mission）
    按 container 各自命中；
  - 指定 container 但目标不存在 → 显式失败（不静默回退名字首命中）；
  - 旧包（无 container）保持 m_Name / dataClass+file 名字匹配行为。
"""

import types

import pytest
from UnityPy.enums import ClassIDType
from UnityPy.files import SerializedFile

from launcher.staticmod import _read_textasset_json


class FakeReader:
    """最小 ObjectReader 替身：type/path_id/read_typetree/container。"""

    def __init__(self, name, script, path_id, container=None):
        self.type = ClassIDType.TextAsset
        self.path_id = path_id
        self.container = container
        self._tt = {"m_Name": name, "m_Script": script}

    def read_typetree(self):
        return dict(self._tt)


class FakeSerializedFile(SerializedFile):
    """仅借 isinstance 判定；对象表直接注入，绕过真实解析。"""

    def __init__(self, objects):
        self.objects = objects


def make_bundle(readers):
    ser = FakeSerializedFile({r.path_id: r for r in readers})
    return types.SimpleNamespace(files={"0.bundle": ser})


A_CONT = "Assets/Resources_moved/StaticData/static-data/event-mission/w8.json"
B_CONT = "Assets/Resources_moved/StaticData/static-data/mission/w8.json"


@pytest.fixture()
def dup_bundle():
    """同名不同目录两文件 + 一个无关文件。"""
    return make_bundle([
        FakeReader("w8", '{"which":"event"}', 301, container=A_CONT),
        FakeReader("w8", '{"which":"mission"}', 302, container=B_CONT),
        FakeReader("other", "{}", 303,
                   container="Assets/Resources_moved/StaticData/static-data/misc/o.json"),
    ])


class TestContainerMatching:
    def test_precise_hit_each_side(self, dup_bundle):
        _, name_a, script_a = _read_textasset_json(dup_bundle, "x", "w8", A_CONT)
        _, name_b, script_b = _read_textasset_json(dup_bundle, "x", "w8", B_CONT)
        assert (name_a, script_a) == ("w8", '{"which":"event"}')
        assert (name_b, script_b) == ("w8", '{"which":"mission"}')

    def test_container_case_insensitive(self, dup_bundle):
        obj, name, script = _read_textasset_json(
            dup_bundle, "x", "w8", B_CONT.replace("Assets", "assets"))
        assert obj.path_id == 302 and script == '{"which":"mission"}'

    def test_missing_container_fails_loudly(self, dup_bundle):
        """container 指定了却找不到 → 返回 None（宁可失败不静默补错文件）。"""
        ghost = "Assets/Resources_moved/StaticData/static-data/ghost/w8.json"
        assert _read_textasset_json(dup_bundle, "x", "w8", ghost) == (None, None, None)

    def test_legacy_name_match_without_container(self, dup_bundle):
        """旧包兼容：不给 container 时按 m_Name 首命中（历史行为）。"""
        obj, name, script = _read_textasset_json(dup_bundle, "x", "w8")
        assert name == "w8" and script == '{"which":"event"}'

    def test_legacy_dataclass_prefixed_name(self):
        """旧包兼容：dataClass/file 组合名可命中（名字自带路径的形态）。"""
        bundle = make_bundle([FakeReader("Skill/SkillData", '{"v":1}', 401)])
        obj, name, script = _read_textasset_json(bundle, "Skill", "SkillData")
        assert name == "Skill/SkillData" and script == '{"v":1}'

    def test_non_textasset_objects_skipped(self):
        class Other(FakeReader):
            def __init__(self):
                super().__init__("t", "{}", 501)
                self.type = ClassIDType.GameObject

        bundle = make_bundle([Other(),
                              FakeReader("t", '{"ok":1}', 502)])
        obj, name, script = _read_textasset_json(bundle, "", "t")
        assert obj.path_id == 502 and script == '{"ok":1}'
