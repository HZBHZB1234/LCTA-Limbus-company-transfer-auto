"""launcher/patch 多线程（threads=N）与串行等价性测试。

多线程模组准备（移植自 FaustLauncher 多线程加载器）：
- detect_lunartique_mods：各 zip 并行转换/解压
- extract_assets：并行解压展平到缓存，串行按体积降序拷贝（保持合并顺序）
- patch_assets：各 bundle 并行备份/补丁/重打包
"""
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


def _write_zip(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return path


def _tree_files(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


def _make_lunartique_zip(mods: Path, name: str) -> Path:
    # 内容随文件名变化，保证各 zip 缓存键（sha256）互不相同
    return _write_zip(mods / name, {
        "Root/Installation/__data": f"i-{name}",
        "Root/Uninstallation/__data": f"u-{name}",
    })


# ═══════════════ detect_lunartique_mods：多线程与串行等价 ═══════════════

def test_detect_threads_equivalent(tmp_path, monkeypatch):
    import launcher.patch as patch

    def fake_compress_factory(calls):
        def fake(src, dst):
            calls.append(Path(src).name)
            _write_zip(dst, {"Acc/Bundle/1.0": Path(src).stem.encode()})
        return fake

    results = {}
    for threads, local in ((1, "local-serial"), (4, "local-parallel")):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / local))
        mods = tmp_path / f"mods-{threads}"
        mods.mkdir()
        names = ["m0.zip", "m1.zip", "m2.zip", "m3.zip", "m4.zip"]
        for name in names:
            _make_lunartique_zip(mods, name)
        calls = []
        monkeypatch.setattr(patch, "compress_lunartique_mod",
                            fake_compress_factory(calls))

        done = []
        patch.detect_lunartique_mods(str(mods), threads=threads,
                                     progress_cb=lambda d, t: done.append((d, t)))

        assert sorted(calls) == sorted(names)          # 全部完成转换
        assert all(not (mods / n).exists() for n in names)  # 源 zip 已删除
        results[threads] = {
            name: (mods / name.replace(".zip", ".carra2")).read_bytes()
            for name in names
        }
        assert done and done[-1] == (len(names), len(names))  # 进度回调收尾

    # 串行与并行的转换产物逐字节一致
    assert results[1] == results[4]


def test_detect_threads_mixed_formats(tmp_path, monkeypatch):
    """并行模式下 Lunartique / 非 Lunartique / 损坏 zip 混合时行为与串行一致。"""
    import launcher.patch as patch

    results = {}
    for threads, local in ((1, "local-serial"), (4, "local-parallel")):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / local))
        mods = tmp_path / f"mods-{threads}"
        mods.mkdir()
        _make_lunartique_zip(mods, "good.zip")
        _write_zip(mods / "plain.zip", {"Acc/Bundle/2.0": b"asset"})
        bad = mods / "bad.zip"
        bad.write_bytes(b"not a zip at all")

        monkeypatch.setattr(patch, "compress_lunartique_mod",
                            lambda src, dst: _write_zip(dst, {"A/B/1.0": b"x"}))

        patch.detect_lunartique_mods(str(mods), threads=threads)

        results[threads] = _tree_files(mods)
        assert (mods / "good.carra2").is_file()
        assert (mods / "plain.zip").exists() is False
        assert bad.exists()  # 损坏 zip 保留

    assert results[1] == results[4]


# ═══════════════ extract_assets：多线程与串行等价（含合并顺序） ═══════════════

def test_extract_threads_merge_order_equivalent(tmp_path, monkeypatch):
    """同名展平目标路径的合并顺序保持旧语义：体积小者后拷贝、内容胜出。"""
    import launcher.patch as patch

    results = {}
    for threads, local in ((1, "local-serial"), (4, "local-parallel")):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / local))
        mods = tmp_path / f"mods-{threads}"
        mods.mkdir()
        # large 体积更大先拷贝，small 后拷贝覆盖 → Acc/1.0 内容应为 b"B"
        _write_zip(mods / "large.carra2",
                   {"Acc/Bundle/1.0": b"A", "Acc/Bundle/9.9": b"P" * 4096})
        _write_zip(mods / "small.carra2", {"Acc/Bundle/1.0": b"B"})
        out = tmp_path / f"out-{threads}"
        out.mkdir()

        done = []
        patch.extract_assets(str(out), str(mods), threads=threads,
                             progress_cb=lambda d, t: done.append((d, t)))

        results[threads] = _tree_files(out)
        assert done and done[-1] == (2, 2)

    assert results[1] == results[4]
    assert results[1][str(Path("Acc") / "1.0")] == b"B"


def test_extract_threads_cache_hit_skips_extract(tmp_path, monkeypatch):
    """缓存已预热时多线程直接命中，不重复解压（拷贝结果一致）。"""
    import launcher.patch as patch

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    mods = tmp_path / "mods"
    mods.mkdir()
    _write_zip(mods / "a.carra2", {"Acc/Bundle/1.0": b"x"})
    _write_zip(mods / "b.carra2", {"Acc/Bundle/2.0": b"y"})
    out_warm = tmp_path / "out-warm"
    out_warm.mkdir()
    patch.extract_assets(str(out_warm), str(mods), threads=1)

    out_fast = tmp_path / "out-fast"
    out_fast.mkdir()
    patch.extract_assets(str(out_fast), str(mods), threads=4)

    assert _tree_files(out_warm) == _tree_files(out_fast)


# ═══════════════ patch_assets：多线程与串行等价 + 失败回滚 ═══════════════

class FakeBundle:
    files = {}  # patch_bundle_asset 遍历用；空集 = 无可补丁对象

    def __init__(self, tag):
        self.tag = tag
        self.version_player = "vanilla"

    def save(self, packer=None):
        return (b"LZ4:" + self.tag.encode() if packer == "lz4"
                else b"ORIG:" + self.tag.encode())


class FakeEnv:
    def __init__(self, tag):
        self._bundle = FakeBundle(tag)


def _make_bundle_tree(root: Path, count: int):
    """生成 count 个独立 bundle（含原版 __data 与对应模组资源目录）。"""
    bundle_roots = []
    for i in range(count):
        bundle_root = root / "acct" / f"b{i}"
        bundle_root.mkdir(parents=True)
        (bundle_root / "__data").write_bytes(f"ORIGINAL_{i}".encode())
        mod_dir = root / "assets" / "acct"
        mod_dir.mkdir(parents=True, exist_ok=True)
        (mod_dir / f"{i}.0").write_bytes(b"modded")
        bundle_roots.append(str(bundle_root))
    return bundle_roots


def _install_fake_unitypy(patch, monkeypatch):
    monkeypatch.setattr(
        patch, "UnityPy",
        type("U", (), {"load": staticmethod(
            lambda p: FakeEnv(Path(p).parent.name))})())
    monkeypatch.setattr(patch, "get_bundle_file", lambda env: env._bundle)


def test_patch_assets_threads_equivalent(tmp_path, monkeypatch):
    import launcher.patch as patch

    _install_fake_unitypy(patch, monkeypatch)
    results = {}
    for threads, local in ((1, "local-serial"), (4, "local-parallel")):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / local))
        tree = tmp_path / f"tree-{threads}"
        roots = _make_bundle_tree(tree, 6)

        done = []
        patch.patch_assets(str(tree / "assets"), threads=threads,
                           bundle_data=lambda: roots,
                           progress_cb=lambda d, t: done.append((d, t)))

        # 以 bundle 目录名为键（两次运行在不同树中，绝对路径不可比）
        data_files = {Path(r).name: (Path(r) / "__data").read_bytes()
                      for r in roots}
        originals = {Path(r).name: (Path(r) / "__original").exists()
                     for r in roots}
        results[threads] = (data_files, originals)
        assert done and done[-1] == (len(roots), len(roots))

    data_1, orig_1 = results[1]
    data_4, orig_4 = results[4]
    assert data_1 == data_4
    assert orig_1 == orig_4 == {r: True for r in data_1}
    assert set(data_1.values()) == {
        b"LZ4:" + f"b{i}".encode() for i in range(6)}


def test_patch_assets_threads_error_rolls_back_and_raises(tmp_path, monkeypatch):
    """并行下一个 bundle 失败：全部任务跑完后重抛异常，失败者回滚、其余正常。"""
    import launcher.patch as patch

    _install_fake_unitypy(patch, monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    tree = tmp_path / "tree"
    roots = _make_bundle_tree(tree, 3)

    real_get_env = patch.UnityPy.load

    def load_with_bad(path):
        env = real_get_env(path)
        if Path(path).parent.name == "b1":
            env._bundle.save = lambda packer=None: (_ for _ in ()).throw(
                RuntimeError("boom"))
        return env

    # 注意：patch.UnityPy 是实例，实例属性不参与描述符绑定；此处必须直接赋
    # 函数对象——赋 staticmethod 对象在 Python 3.9 下不可调用（3.10+ 才可调用）。
    monkeypatch.setattr(patch.UnityPy, "load", load_with_bad)

    with pytest.raises(RuntimeError, match="boom"):
        patch.patch_assets(str(tree / "assets"), threads=2,
                           bundle_data=lambda: roots)

    # 失败的 b1 已回滚为原版数据；成功的 b0/b2 正常打补丁并保留备份
    assert (Path(roots[1]) / "__data").read_bytes() == b"ORIGINAL_1"
    assert not (Path(roots[1]) / "__original").exists()
    assert (Path(roots[0]) / "__data").read_bytes() == b"LZ4:b0"
    assert (Path(roots[2]) / "__data").read_bytes() == b"LZ4:b2"
    assert (Path(roots[0]) / "__original").exists()
    assert (Path(roots[2]) / "__original").exists()


def test_modstatus_registry_order_and_removal():
    """任务注册表：按开始顺序输出、finish 移除、快照为独立副本。"""
    from launcher import modstatus

    modstatus.clear()
    try:
        modstatus.begin("k1", "任务一", "转换", "处理中")
        modstatus.begin("k2", "任务二", "解压", "排队中",
                        status=modstatus.STATUS_WAITING)
        modstatus.update("k2", stage="解压展平", description="开始解压",
                         status=modstatus.STATUS_RUNNING)

        snap = modstatus.snapshot()
        assert [t["key"] for t in snap] == ["k1", "k2"]
        assert snap[1]["stage"] == "解压展平"
        assert snap[1]["status"] == "running"

        snap[0]["name"] = "改动不影响内部"
        assert modstatus.snapshot()[0]["name"] == "任务一"

        modstatus.finish("k1")
        assert [t["key"] for t in modstatus.snapshot()] == ["k2"]
    finally:
        modstatus.clear()
