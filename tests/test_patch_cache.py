"""launcher/patch 缓存测试：carra2 转换/解压缓存、bundle 重打包缓存、LZ4 回退。"""
import shutil
import zipfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True, scope="module")
def _restore_global_log_state():
    yield
    import logging
    from globalManagers.LogManager import LogManager
    LogManager._instance = None
    LogManager._initialized = False
    logging.getLogger("LCTA").propagate = True


@pytest.fixture
def localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    return tmp_path / "local"


def _write_zip(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return path


# ═══════════════ detect_lunartique_mods（zip→carra2 转换缓存 + 删除源 zip） ═══════════════

def test_detect_converts_and_deletes_zip(localappdata, tmp_path, monkeypatch):
    import launcher.patch as patch

    mods = tmp_path / "mods"
    mods.mkdir()
    zip_path = _write_zip(mods / "m.zip", {
        "Root/Installation/__data": "i",
        "Root/Uninstallation/__data": "u",
    })

    calls = []

    def fake_compress(src, dst):
        calls.append(src)
        _write_zip(dst, {"Acc/Bundle/1.0": b"x"})

    monkeypatch.setattr(patch, "compress_lunartique_mod", fake_compress)

    patch.detect_lunartique_mods(str(mods))
    assert not zip_path.exists()  # 源 zip 已删除
    carra2 = mods / "m.carra2"
    assert carra2.is_file()  # 产物复制回模组目录
    assert calls == [str(zip_path)]

    # 再次运行（无 zip）：无事发生，carra2 保持
    patch.detect_lunartique_mods(str(mods))
    assert carra2.is_file()


def test_detect_cache_hit_skips_conversion(localappdata, tmp_path, monkeypatch):
    """同包重新放入模组目录：缓存命中跳过转换，仍产出 carra2 并删除 zip。"""
    import launcher.patch as patch

    mods = tmp_path / "mods"
    mods.mkdir()
    zip_data = {"Root/Installation/__data": "i", "Root/Uninstallation/__data": "u"}
    zip_path = _write_zip(mods / "m.zip", zip_data)

    calls = []
    monkeypatch.setattr(patch, "compress_lunartique_mod",
                        lambda src, dst: calls.append(src) or _write_zip(dst, {"A/B/1.0": b"x"}))

    patch.detect_lunartique_mods(str(mods))
    assert calls == [str(zip_path)]
    assert not zip_path.exists()

    # 重新放入同内容 zip → 命中缓存，不重复转换
    zip2 = _write_zip(mods / "m.zip", zip_data)
    patch.detect_lunartique_mods(str(mods))
    assert calls == [str(zip_path)]  # 未再次调用转换
    assert not zip2.exists()
    assert (mods / "m.carra2").is_file()


def test_detect_skips_disabled_zip(localappdata, tmp_path, monkeypatch):
    import launcher.patch as patch

    mods = tmp_path / "mods"
    mods.mkdir()
    _write_zip(mods / "m.zip", {"R/Installation/__data": "i", "R/Uninstallation/__data": "u"})
    _write_zip(mods / "n.zip_disable", {"R/Installation/__data": "i", "R/Uninstallation/__data": "u"})

    calls = []
    monkeypatch.setattr(patch, "compress_lunartique_mod",
                        lambda src, dst: calls.append(src) or _write_zip(dst, {"A/B/1.0": b"x"}))
    patch.detect_lunartique_mods(str(mods))
    assert calls == [str(mods / "m.zip")]  # 禁用的 zip 未参与
    assert not (mods / "m.zip").exists()
    assert (mods / "m.carra2").exists()
    assert (mods / "n.zip_disable").exists()  # 禁用 zip 未被删除


# ═══════════════ extract_assets（解压缓存 + 展平语义） ═══════════════

def test_extract_caches_and_flattens(localappdata, tmp_path):
    import launcher.patch as patch

    carra = _write_zip(tmp_path / "c.carra2", {"Acc/Bundle/1.0": b"x"})
    mods = tmp_path / "mods"
    mods.mkdir()
    shutil.copyfile(carra, mods / "c.carra2")
    out = tmp_path / "out"
    out.mkdir()

    patch.extract_assets(str(out), str(mods))

    # 展平：3 层条目 Acc/Bundle/1.0 → Acc/1.0（丢弃 bundle 段）
    assert (out / "Acc" / "1.0").read_bytes() == b"x"
    assert not (out / "Acc" / "Bundle").exists()

    # 缓存目录存在（carra2 内容哈希）
    from launcher import modcache
    cache_dirs = list(modcache.carra2_extract_dir().iterdir())
    assert len(cache_dirs) == 1


def test_extract_skips_disable_carra2(localappdata, tmp_path):
    import launcher.patch as patch

    mods = tmp_path / "mods"
    mods.mkdir()
    _write_zip(mods / "a.carra2", {"Acc/1.0": b"x"})
    _write_zip(mods / "b.carra2_disable", {"Acc/2.0": b"y"})
    out = tmp_path / "out"
    out.mkdir()

    patch.extract_assets(str(out), str(mods))
    assert (out / "Acc" / "1.0").exists()
    assert not (out / "Acc" / "2.0").exists()


def test_extract_carra2_only_mod_dir(localappdata, tmp_path):
    """carra2-only 模组目录（旧版转换产物、无 zip）必须正常提取（回归防护）。"""
    import launcher.patch as patch

    mods = tmp_path / "mods"
    mods.mkdir()
    _write_zip(mods / "a.carra2", {"Acc/Bundle/3.0": b"z"})
    out = tmp_path / "out"
    out.mkdir()

    patch.extract_assets(str(out), str(mods))
    assert (out / "Acc" / "3.0").read_bytes() == b"z"


# ═══════════════ patch_assets（bundle 重打包缓存 + LZ4 格式） ═══════════════

class FakeBundle:
    version_player = "vanilla"
    files = {}

    def save(self, packer=None):
        return b"LZ4DATA" if packer == "lz4" else b"ORIGDATA"


class FakeEnv:
    def __init__(self):
        self._bundle = FakeBundle()
        self.files = {}


def test_patch_assets_lz4_and_cache(localappdata, tmp_path, monkeypatch):
    import launcher.patch as patch

    bundle_root = tmp_path / "acct" / "bundle"
    bundle_root.mkdir(parents=True)
    (bundle_root / "__data").write_bytes(b"ORIGINAL_DATA")

    asset_root = tmp_path / "assetroot"
    mod_dir = asset_root / "acct"  # 目录名须等于 bundle_root.parent.name
    mod_dir.mkdir(parents=True)
    (mod_dir / "1.0").write_bytes(b"modded")

    fake_env = FakeEnv()
    monkeypatch.setattr(patch, "get_bundle_file", lambda env: env._bundle)
    monkeypatch.setattr(patch, "UnityPy",
                        type("U", (), {"load": staticmethod(lambda p: fake_env)})())

    patch.patch_assets(str(asset_root), lambda: [str(bundle_root)])
    assert (bundle_root / "__data").read_bytes() == b"LZ4DATA"  # 优先 LZ4 格式
    assert (bundle_root / "__original").exists()

    # 第二次：模拟原版恢复后重新打补丁 → 命中缓存，不重新编码
    (bundle_root / "__data").write_bytes(b"ORIGINAL_DATA")
    (bundle_root / "__original").unlink()
    save_calls = []
    orig_save = fake_env._bundle.save

    def counting_save(b, packer=None):
        save_calls.append(packer)
        return orig_save(b, packer)

    fake_env._bundle.save = counting_save
    patch.patch_assets(str(asset_root), lambda: [str(bundle_root)])
    assert save_calls == []  # 缓存命中，未调用 save
    assert (bundle_root / "__data").read_bytes() == b"LZ4DATA"


def test_patch_assets_skips_without_mod_dir(localappdata, tmp_path, monkeypatch):
    import launcher.patch as patch

    bundle_root = tmp_path / "acct" / "bundle"
    bundle_root.mkdir(parents=True)
    (bundle_root / "__data").write_bytes(b"ORIGINAL_DATA")
    asset_root = tmp_path / "assetroot"
    asset_root.mkdir()  # 无 acct 子目录

    monkeypatch.setattr(patch, "get_bundle_file", lambda env: env._bundle)
    monkeypatch.setattr(patch, "UnityPy", type("U", (), {"load": staticmethod(lambda p: None)})())

    patch.patch_assets(str(asset_root), lambda: [str(bundle_root)])
    assert (bundle_root / "__data").read_bytes() == b"ORIGINAL_DATA"  # 未动
    assert not (bundle_root / "__original").exists()


def test_save_bundle_falls_back_to_original():
    import launcher.patch as patch

    class BadBundle:
        def save(self, packer=None):
            if packer == "lz4":
                raise RuntimeError("lz4 boom")
            return b"ORIG"

    data, packer = patch._save_bundle(BadBundle())
    assert data == b"ORIG"
    assert packer == "original"
