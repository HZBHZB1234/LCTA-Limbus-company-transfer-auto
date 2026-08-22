# -*- coding: utf-8 -*-
"""staticmod 核心单元测试。

覆盖:
  - catalog 动态定位（用真实当前 catalog 副本 + 临时副本）
  - jsonpatch / pathset 补丁应用
  - full → diff 转换往返
  - bundle 内 TextAsset 按名匹配 + 重打包 + 解压后 CRC
  - 双写 catalog 字段（临时 catalog 副本）与缓存条目（临时根）
  - 无 .staticmod 时 apply 返回跳过
"""
import io
import json
import os
import shutil
import struct
import zipfile
from pathlib import Path

import pytest

import UnityPy.config

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.12f1"

from launcher import staticmod


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_catalog(tmp_path_factory):
    """真实当前 catalog 的副本（避免污染游戏目录）。"""
    src = (Path(os.environ.get("LOCALAPPDATA", "")) / ".." / "LocalLow" / "ProjectMoon"
           / "LimbusCompany" / "com.unity.addressables" / "catalog_S1.bin")
    dst = tmp_path_factory.mktemp("cat") / "catalog_S1.bin"
    shutil.copyfile(src, dst)
    return dst


@pytest.fixture(scope="module")
def real_bundle(tmp_path_factory):
    """真实当前 static bundle 缓存副本。"""
    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / ".." / "LocalLow" / "Unity" / "ProjectMoon_LimbusCompany",
        Path("D:/Unity/ProjectMoon_LimbusCompany"),
    ]
    for root in roots:
        outer = root / "64bd0105e9544bef32ddae650b8bcb26"
        if not outer.is_dir():
            continue
        for inner in outer.iterdir():
            data = inner / "__data"
            if data.is_file():
                dst = tmp_path_factory.mktemp("bundle") / "static.bundle"
                shutil.copyfile(data, dst)
                return dst
    pytest.skip("未找到 static bundle 缓存")


def _make_mod(tmp_path, patches=None, full_files=None, name="testmod"):
    """构造 .staticmod 包。"""
    mod = tmp_path / (name + ".staticmod")
    # 分离 manifest 描述与真实源文件（manifest 不能含 Path 对象）
    manifest_patches = []
    file_specs = []
    for p in patches or []:
        manifest_patches.append({
            "dataClass": p["dataClass"], "file": p["file"],
            "opType": p["opType"], "source": p["source"],
        })
        file_specs.append((p["source"], p["src"]))
    manifest_full = []
    for ff in full_files or []:
        manifest_full.append({
            "dataClass": ff["dataClass"], "file": ff["file"], "source": ff["source"],
        })
        file_specs.append((ff["source"], ff["src"]))
    manifest = {
        "format": staticmod.FORMAT,
        "name": name,
        "version": "1.0.0",
        "description": "test",
        "patches": manifest_patches,
        "fullFiles": manifest_full,
    }
    with zipfile.ZipFile(mod, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        for dest, src in file_specs:
            z.write(str(src), dest)
    return mod


# ---------------------------------------------------------------------------
# catalog 动态定位
# ---------------------------------------------------------------------------

def test_locate_static_entry(real_catalog):
    entry = staticmod.locate_static_entry(str(real_catalog))
    assert entry is not None
    assert entry.inner_hash and len(entry.inner_hash) == 32
    assert entry.outer_key and len(entry.outer_key) == 32
    assert entry.crc_offset > 0 and entry.size_offset > 0
    assert 100_000 < entry.size < 50_000_000
    # 校验读出的 crc/size 与记录一致（重读文件对应偏移）
    data = real_catalog.read_bytes()
    crc = struct.unpack_from("<I", data, entry.crc_offset)[0]
    size = struct.unpack_from("<I", data, entry.size_offset)[0]
    assert crc == entry.crc
    assert size == entry.size


def test_locate_static_entry_bad_file(tmp_path):
    bad = tmp_path / "empty.bin"
    bad.write_bytes(b"")
    assert staticmod.locate_static_entry(str(bad)) is None


# ---------------------------------------------------------------------------
# 补丁应用
# ---------------------------------------------------------------------------

def test_pathset_to_jsonpatch():
    ops = staticmod._pathset_to_jsonpatch({
        "dataList[0].targetNum": 5,
        "info.name": "X",
    })
    assert ops == [
        {"op": "add", "path": "/dataList/0/targetNum", "value": 5},
        {"op": "add", "path": "/info/name", "value": "X"},
    ]


def test_apply_patch_jsonpatch():
    doc = {"dataList": [{"targetNum": 1, "x": 2}]}
    out = staticmod.apply_patch_to_json(doc, [{"op": "replace", "path": "/dataList/0/targetNum", "value": 5}], "jsonpatch")
    assert out["dataList"][0]["targetNum"] == 5
    assert out["dataList"][0]["x"] == 2


def test_apply_patch_pathset():
    doc = {"dataList": [{"targetNum": 1}]}
    out = staticmod.apply_patch_to_json(doc, {"dataList[0].targetNum": 7}, "pathset")
    assert out["dataList"][0]["targetNum"] == 7


def test_full_diff_roundtrip():
    official = {"list": [{"id": 1, "v": 10}, {"id": 2, "v": 20}]}
    mod = {"list": [{"id": 1, "v": 99}, {"id": 2, "v": 20}]}
    diff = staticmod.make_full_diff(official, mod)
    assert diff  # 非空
    import jsonpatch as jp
    out = jp.apply_patch(official, diff)
    assert out == mod


# ---------------------------------------------------------------------------
# bundle 内 TextAsset 匹配 + CRC
# ---------------------------------------------------------------------------

def test_read_textasset_and_crc(real_bundle):
    raw = real_bundle.read_bytes()
    crc, size = staticmod.bundle_decompressed_crc(raw)
    assert size == len(raw)
    assert 0 < crc < 0xFFFFFFFF

    env = UnityPy.load(io.BytesIO(raw))
    bundle = staticmod.get_bundle_file(env)
    # 找任意一个 TextAsset 验证读取
    from UnityPy.enums import ClassIDType
    found = 0
    for f in bundle.files.values():
        for obj in f.objects.values():
            if obj.type == ClassIDType.TextAsset:
                found += 1
                break
        if found:
            break
    assert found > 0


# ---------------------------------------------------------------------------
# 端到端：apply 一个真实补丁（写临时 catalog + 临时缓存根）
# ---------------------------------------------------------------------------

def test_end_to_end_apply(tmp_path, monkeypatch, real_catalog, real_bundle):
    """真实官方 bundle + 临时 catalog 副本 + 临时缓存根，跑完整应用流程。"""
    # 找到官方 bundle 里一个真实 TextAsset 名，构造 pathset 补丁
    raw = real_bundle.read_bytes()
    env = UnityPy.load(io.BytesIO(raw))
    bundle = staticmod.get_bundle_file(env)
    from UnityPy.enums import ClassIDType
    target_name = None
    for f in bundle.files.values():
        for obj in f.objects.values():
            if obj.type == ClassIDType.TextAsset:
                tt = obj.read_typetree()
                target_name = str(tt.get("m_Name", ""))
                script = tt.get("m_Script", "")
                if script and "targetNum" in script:
                    break
                target_name = None
        if target_name:
            break
    if not target_name:
        pytest.skip("官方 bundle 中无含 targetNum 的 TextAsset")

    # 构造 mod：pathset 补丁（用真实 JSON 路径：list[0].skillData[0].targetNum -> 5）
    patch_data = {"list[0].skillData[0].targetNum": 5}
    patch_src = tmp_path / "patch.json"
    patch_src.write_text(json.dumps(patch_data), encoding="utf-8")
    mod = _make_mod(tmp_path, patches=[{
        "dataClass": "skill", "file": target_name,
        "opType": "pathset", "source": "patches/skill.json", "src": patch_src,
    }])

    # 隔离：catalog 用副本，缓存根用临时目录
    test_catalog_dir = tmp_path / "cat"
    test_catalog_dir.mkdir(parents=True, exist_ok=True)
    test_catalog = test_catalog_dir / "catalog_S1.bin"
    shutil.copyfile(real_catalog, test_catalog)
    test_cache = tmp_path / "cache"
    (test_cache / "64bd0105e9544bef32ddae650b8bcb26" / "972e5bc3080c7b0e5cac18a32305e758").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(real_bundle, test_cache / "64bd0105e9544bef32ddae650b8bcb26" / "972e5bc3080c7b0e5cac18a32305e758" / "__data")

    monkeypatch.setattr(staticmod, "_catalog_path", lambda: str(test_catalog))
    monkeypatch.setattr(staticmod, "_cache_roots", lambda: [test_cache])
    monkeypatch.setattr(staticmod, "find_staticmods", lambda root: [mod])

    result = staticmod.apply_staticmods(str(tmp_path), catalog_path=str(test_catalog))
    assert result["applied"] == 1, result
    assert not result["failed"]

    # 验证：catalog 副本的 crc/size 已更新为补丁包的值
    entry = staticmod.locate_static_entry(str(test_catalog))
    data = test_catalog.read_bytes()
    new_crc = struct.unpack_from("<I", data, entry.crc_offset)[0]
    new_size = struct.unpack_from("<I", data, entry.size_offset)[0]
    patched = (test_cache / entry.outer_key / entry.inner_hash / "__data").read_bytes()
    calc_crc, calc_size = staticmod.bundle_decompressed_crc(patched)
    assert new_crc == calc_crc
    assert new_size == calc_size == len(patched)


# ---------------------------------------------------------------------------
# 无 mod 跳过
# ---------------------------------------------------------------------------

def test_no_staticmods_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(staticmod, "find_staticmods", lambda root: [])
    result = staticmod.apply_staticmods(str(tmp_path))
    assert result["applied"] == 0
    assert result.get("reason") == "no-staticmods"
