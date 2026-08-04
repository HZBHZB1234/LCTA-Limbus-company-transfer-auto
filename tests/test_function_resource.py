"""webutils/function_resource.py 资源提取健壮性测试

覆盖：
- load_text_assets / extract_files_from_resource 遇到 container 为 None
  （UnityPy 中不在容器映射表中的对象）时不崩溃并跳过
- container 为非字符串类型时同样安全跳过
- 正常 TextAsset 对象仍能被提取
"""
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from UnityPy.enums import ClassIDType

from webutils.function_resource import (
    extract_files_from_resource,
    get_limbus_resource_files,
    load_text_assets,
)


class FakeObj:
    def __init__(self, container=None, type_=None, script=None):
        self.container = container
        self.type = type_
        self._script = script

    def read(self):
        return SimpleNamespace(script=self._script)


class FakeEnv:
    def __init__(self, objects):
        self.objects = objects


def _make_text_asset(container_name):
    payload = json.dumps({"list": [{"id": 1}]}).encode("utf-8")
    return FakeObj(container=f"assets/limbus/personality/{container_name}",
                   type_=ClassIDType.TextAsset, script=payload)


class TestLoadTextAssets:
    def test_none_container_objects_are_skipped(self, tmp_path):
        """container 为 None 的对象不应导致崩溃"""
        resource_file = tmp_path / "resources.assets"
        resource_file.write_bytes(b"fake")
        env = FakeEnv(objects=[FakeObj(container=None), FakeObj(container=None)])
        with patch("webutils.function_resource.UnityPy.load", return_value=env):
            loaded, missing = load_text_assets(
                ["personality-skill-01.json"],
                logger=logging.getLogger("test_resource"),
                resource_files=[resource_file],
            )
        assert loaded == {}
        assert missing == ["personality-skill-01.json"]

    def test_non_string_container_is_skipped(self, tmp_path):
        resource_file = tmp_path / "resources.assets"
        resource_file.write_bytes(b"fake")
        env = FakeEnv(objects=[FakeObj(container=["not", "a", "string"])])
        with patch("webutils.function_resource.UnityPy.load", return_value=env):
            loaded, missing = load_text_assets(
                ["personality-skill-01.json"],
                logger=logging.getLogger("test_resource"),
                resource_files=[resource_file],
            )
        assert loaded == {}
        assert missing == ["personality-skill-01.json"]

    def test_mixed_objects_extract_matching_text_asset(self, tmp_path):
        """正常 TextAsset（container 为 str 且后缀匹配）仍能提取"""
        resource_file = tmp_path / "resources.assets"
        resource_file.write_bytes(b"fake")
        target = _make_text_asset("personality-skill-01.json")
        env = FakeEnv(objects=[FakeObj(container=None), target])
        with patch("webutils.function_resource.UnityPy.load", return_value=env):
            loaded, missing = load_text_assets(
                ["personality-skill-01.json", "personality-skill-02.json"],
                logger=logging.getLogger("test_resource"),
                resource_files=[resource_file],
            )
        assert "personality-skill-01.json" in loaded
        assert json.loads(loaded["personality-skill-01.json"]) == {"list": [{"id": 1}]}
        assert missing == ["personality-skill-02.json"]

    def test_memoryview_script_is_converted_to_bytes(self, tmp_path):
        """UnityPy 的 TextAsset.script 返回 memoryview，应转换为 bytes 后返回"""
        resource_file = tmp_path / "resources.assets"
        resource_file.write_bytes(b"fake")
        payload = json.dumps({"list": [{"id": 1}]}).encode("utf-8")
        target = FakeObj(container="assets/limbus/personality/personality-skill-01.json",
                         type_=ClassIDType.TextAsset, script=memoryview(payload))
        env = FakeEnv(objects=[target])
        with patch("webutils.function_resource.UnityPy.load", return_value=env):
            loaded, missing = load_text_assets(
                ["personality-skill-01.json"],
                logger=logging.getLogger("test_resource"),
                resource_files=[resource_file],
            )
        assert isinstance(loaded["personality-skill-01.json"], bytes)
        assert json.loads(loaded["personality-skill-01.json"]) == {"list": [{"id": 1}]}
        assert missing == []


class TestGetLimbusResourceFiles:
    def test_only_top_level_folders_are_scanned(self, monkeypatch, tmp_path):
        """只发现顶层文件夹下一层内的 __data 文件，忽略更深层级与无关文件"""
        base = tmp_path / "AppData" / "LocalLow" / "Unity" / "ProjectMoon_LimbusCompany"
        (base / "a" / "sub").mkdir(parents=True)
        (base / "a" / "sub" / "__data").write_bytes(b"x")
        (base / "b" / "sub").mkdir(parents=True)
        (base / "b" / "sub" / "__data").write_bytes(b"x")
        (base / "c" / "deep" / "even").mkdir(parents=True)
        (base / "c" / "deep" / "even" / "__data").write_bytes(b"x")
        (base / "no_data" / "sub").mkdir(parents=True)
        (base / "plain_file").write_text("x")

        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        found = get_limbus_resource_files()

        assert sorted(path.parent.parent.name for path in found) == ["a", "b"]

    def test_missing_root_returns_empty(self, monkeypatch, tmp_path):
        root = tmp_path / "nonexistent"
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: root))
        assert get_limbus_resource_files() == []


class TestExtractFilesFromResource:
    def test_none_container_objects_do_not_crash(self, tmp_path):
        resource_path = tmp_path / "resources.assets"
        resource_path.write_bytes(b"fake")
        output_dir = tmp_path / "out"
        env = FakeEnv(objects=[FakeObj(container=None), FakeObj(container=None)])
        with patch("webutils.function_resource.UnityPy.load", return_value=env):
            found = extract_files_from_resource(
                str(resource_path),
                ["personality-skill-01.json"],
                str(output_dir),
            )
        assert found == []

    def test_matching_text_asset_is_extracted(self, tmp_path):
        resource_path = tmp_path / "resources.assets"
        resource_path.write_bytes(b"fake")
        output_dir = tmp_path / "out"
        target = _make_text_asset("personality-skill-01.json")
        env = FakeEnv(objects=[target])
        with patch("webutils.function_resource.UnityPy.load", return_value=env):
            found = extract_files_from_resource(
                str(resource_path),
                ["personality-skill-01.json"],
                str(output_dir),
            )
        assert found == ["personality-skill-01.json"]
        assert (output_dir / "personality-skill-01.json").exists()
