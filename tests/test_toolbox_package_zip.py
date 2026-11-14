# -*- coding: utf-8 -*-
"""解压型文件包 ``game_relative_zip`` 安装（2026-11-06）。

站点新增 ``game_relative_zip``：清单只声明**一个 .zip**，客户端下载校验后
自己解压到签名清单里的 ``target_dir``。本文件守住：

1. 正常路径：解压到 target_dir、manifest 记录每个文件的哈希；
2. **与逐文件包完全一致的落盘语义**：卸载、完整性、回滚、重叠检测、
   更新时清理旧文件（因为两者共享 ``_apply_package``）；
3. 解压安全：Zip Slip / 敏感 target_dir / 布局白名单；
4. 更新时旧文件清理只删哈希仍匹配的；
5. 游戏运行中拒绝。

全部在临时目录里操作合成 ZIP，绝不碰真实游戏目录、不执行任何 DLL。
"""
import os
import zipfile
from pathlib import Path

import pytest

from webutils.toolbox import archive, install, paths, state


def _zip(path: Path, members) -> Path:
    with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return path


@pytest.fixture()
def game(tmp_path):
    g = tmp_path / "game"
    g.mkdir()
    (g / "LimbusCompany.exe").write_bytes(b"fake")
    return g


def _zip_plan(stub: Path, *, target_dir="BepInEx/plugins/ZipPack", tool_id="zip-a",
              release="rz1", prefixes=()) -> install.InstallPlan:
    return install.InstallPlan(
        kind="package_zip",
        release_id=release,
        version="1.0.0",
        tool_id=tool_id,
        target_dir=target_dir,
        requires_runtime=False,
        stub_path=stub,
        archive_prefixes=tuple(prefixes),
    )


class TestInstall:
    def test_extracts_to_target_dir(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [
            ("a.dll", b"AAA"),
            ("sub/b.txt", b"BBB"),
            ("sub/deep/c.json", b'{"k":1}'),
        ])
        r = install.install_package_zip(game, _zip_plan(z))
        assert r["ok"] is True
        assert r["kind"] == "package_zip"
        assert r["files"] == 3
        root = game / "BepInEx" / "plugins" / "ZipPack"
        assert (root / "a.dll").read_bytes() == b"AAA"
        assert (root / "sub" / "b.txt").read_bytes() == b"BBB"
        assert (root / "sub" / "deep" / "c.json").read_bytes() == b'{"k":1}'

    def test_records_manifest_hashes(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [("a.dll", b"AAA"), ("sub/b.txt", b"BBB")])
        install.install_package_zip(game, _zip_plan(z))
        entry = state.Manifest.load(game).packages["zip-a"]
        assert entry.target_dir == "BepInEx/plugins/ZipPack"
        assert entry.release_id == "rz1"
        assert {f.relative_path for f in entry.files} == {"a.dll", "sub/b.txt"}
        assert all(f.sha256 for f in entry.files), "每个落盘文件都要记哈希（供完整性/卸载）"

    def test_staging_cleaned_up(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [("a.dll", b"AAA")])
        install.install_package_zip(game, _zip_plan(z))
        staging = paths.staging_dir(game)
        leftovers = [p for p in staging.glob("pz-*")] if staging.is_dir() else []
        assert leftovers == [], "解压暂存目录必须清理（成功/失败都不留半成品）"

    def test_empty_archive_rejected(self, game, tmp_path):
        z = _zip(tmp_path / "empty.zip", [])
        with pytest.raises(install.InstallError) as ei:
            install.install_package_zip(game, _zip_plan(z))
        assert ei.value.code == install.E_MANIFEST_INVALID

    def test_missing_stub_rejected(self, game, tmp_path):
        with pytest.raises(install.InstallError) as ei:
            install.install_package_zip(
                game, _zip_plan(tmp_path / "nope.zip")
            )
        assert ei.value.code == install.E_MANIFEST_INVALID

    def test_missing_target_dir_rejected(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [("a.dll", b"AAA")])
        with pytest.raises(install.InstallError) as ei:
            install.install_package_zip(game, _zip_plan(z, target_dir=""))
        assert ei.value.code == install.E_MANIFEST_INVALID

    def test_no_runtime_required_by_default(self, game, tmp_path):
        """文件包不强制要求底座（与 install_package 一致）。"""
        z = _zip(tmp_path / "pack.zip", [("a.dll", b"AAA")])
        r = install.install_package_zip(game, _zip_plan(z))
        assert r["ok"] is True
        assert state.Manifest.load(game).runtime is None

    def test_requires_runtime_enforced(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [("a.dll", b"AAA")])
        plan = _zip_plan(z)
        plan.requires_runtime = True
        with pytest.raises(install.InstallError) as ei:
            install.install_package_zip(game, plan)
        assert ei.value.code == install.E_DEPENDENCY_MISSING


class TestExtractionSafety:
    def test_sensitive_target_dir_rejected(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [("x.dll", b"X")])
        with pytest.raises(paths.UnsafePathError):
            install.install_package_zip(
                game, _zip_plan(z, target_dir="BepInEx/core")
            )

    def test_traversal_target_dir_rejected(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [("x.dll", b"X")])
        with pytest.raises(paths.UnsafePathError):
            install.install_package_zip(
                game, _zip_plan(z, target_dir="../escape")
            )

    @pytest.mark.parametrize("member", ["../escape.dll", "/abs.dll", "a/../../b.dll"])
    def test_zip_slip_rejected(self, game, tmp_path, member):
        z = _zip(tmp_path / "evil.zip", [(member, b"X")])
        with pytest.raises(install.InstallError) as ei:
            install.install_package_zip(game, _zip_plan(z))
        assert ei.value.code == install.E_MANIFEST_INVALID
        assert not (game.parent / "escape.dll").exists()

    def test_layout_whitelist_enforced(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [("a.dll", b"AAA"), ("elsewhere/b.dll", b"B")])
        with pytest.raises(install.InstallError) as ei:
            install.install_package_zip(game, _zip_plan(z, prefixes=["sub"]))
        assert ei.value.code == install.E_MANIFEST_INVALID

    def test_layout_whitelist_allows_matching(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [("sub/a.dll", b"AAA")])
        r = install.install_package_zip(game, _zip_plan(z, prefixes=["sub"]))
        assert r["ok"] is True


class TestSharedSemantics:
    """解压包与逐文件包共享 ``_apply_package``：这些行为必须一模一样。"""

    def test_uninstall_removes_files(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [("a.dll", b"AAA"), ("sub/b.txt", b"BBB")])
        install.install_package_zip(game, _zip_plan(z))
        r = install.uninstall_package(game, "zip-a")
        assert r["removed"] == 2
        assert not (game / "BepInEx" / "plugins" / "ZipPack" / "a.dll").exists()
        assert "zip-a" not in state.Manifest.load(game).packages

    def test_verify_integrity_detects_modification(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [("a.dll", b"AAA")])
        install.install_package_zip(game, _zip_plan(z))
        target = game / "BepInEx" / "plugins" / "ZipPack" / "a.dll"
        target.write_bytes(b"MODIFIED")
        v = install.verify_integrity_package(game, "zip-a")
        assert v["ok"] is False
        assert "a.dll" in v["modified"]

    def test_update_removes_stale_files(self, game, tmp_path):
        z1 = _zip(tmp_path / "v1.zip", [("a.dll", b"AAA"), ("old.txt", b"OLD")])
        install.install_package_zip(game, _zip_plan(z1, release="rz1"))
        stale = game / "BepInEx" / "plugins" / "ZipPack" / "old.txt"
        assert stale.exists()

        z2 = _zip(tmp_path / "v2.zip", [("a.dll", b"NEW")])
        install.install_package_zip(game, _zip_plan(z2, release="rz2"))
        assert not stale.exists(), "新版本不再包含的旧受管文件应被清理"
        assert (game / "BepInEx" / "plugins" / "ZipPack" / "a.dll").read_bytes() == b"NEW"

    def test_update_keeps_user_modified_file(self, game, tmp_path):
        z1 = _zip(tmp_path / "v1.zip", [("a.dll", b"AAA"), ("cfg.txt", b"OLD")])
        install.install_package_zip(game, _zip_plan(z1, release="rz1"))
        cfg = game / "BepInEx" / "plugins" / "ZipPack" / "cfg.txt"
        cfg.write_bytes(b"USER-EDITED")

        z2 = _zip(tmp_path / "v2.zip", [("a.dll", b"NEW")])
        install.install_package_zip(game, _zip_plan(z2, release="rz2"))
        assert cfg.read_bytes() == b"USER-EDITED", "用户改过的文件不得静默删除"

    def test_overlapping_target_dirs_rejected(self, game, tmp_path):
        za = _zip(tmp_path / "a.zip", [("a.dll", b"A")])
        install.install_package_zip(game, _zip_plan(za, tool_id="zip-a",
                                                    target_dir="BepInEx/plugins/Pack"))
        zb = _zip(tmp_path / "b.zip", [("b.dll", b"B")])
        with pytest.raises(install.InstallError) as ei:
            install.install_package_zip(
                game, _zip_plan(zb, tool_id="zip-b",
                                target_dir="BepInEx/plugins/Pack/inner")
            )
        assert ei.value.code == install.E_PATH_UNSAFE

    def test_rollback_restores_backup(self, game, tmp_path):
        z1 = _zip(tmp_path / "v1.zip", [("a.dll", b"ORIGINAL")])
        install.install_package_zip(game, _zip_plan(z1, release="rz1"))
        target = game / "BepInEx" / "plugins" / "ZipPack" / "a.dll"

        z2 = _zip(tmp_path / "v2.zip", [("a.dll", b"UPDATED")])
        install.install_package_zip(game, _zip_plan(z2, release="rz2"))
        assert target.read_bytes() == b"UPDATED"

        r = install.rollback_package(game, "zip-a")
        assert r["ok"] is True
        assert target.read_bytes() == b"ORIGINAL", "回滚应还原安装前的旧文件"

    def test_listed_as_package(self, game, tmp_path):
        z = _zip(tmp_path / "pack.zip", [("a.dll", b"AAA")])
        install.install_package_zip(game, _zip_plan(z))
        r = install.list_installed(game)
        assert "zip-a" in [p["tool_id"] for p in r["packages"]]


class TestGameRunningGuard:
    def test_refused_while_game_running(self, game, tmp_path, monkeypatch):
        z = _zip(tmp_path / "pack.zip", [("a.dll", b"AAA")])
        monkeypatch.setattr(install.runtime, "is_game_running", lambda *a, **k: True)
        with pytest.raises(RuntimeError) as ei:
            install.install_package_zip(game, _zip_plan(z))
        assert "游戏正在运行" in str(ei.value)
        assert not (game / "BepInEx" / "plugins" / "ZipPack" / "a.dll").exists()


class TestArchiveBombGuard:
    def test_ratio_guard_applies(self, game, tmp_path, monkeypatch):
        """把阈值压到 1，断言解压型包确实经过 ``inspect_archive`` 的炸弹防护。"""
        z = _zip(tmp_path / "bomb.zip", [("big.bin", b"A" * (64 * 1024))])
        real = archive.inspect_archive

        def _strict(path, **kw):
            kw.setdefault("max_ratio", 1)
            return real(path, **kw)

        monkeypatch.setattr(install.archive, "inspect_archive", _strict)
        with pytest.raises(install.InstallError) as ei:
            install.install_package_zip(game, _zip_plan(z))
        assert ei.value.code == install.E_MANIFEST_INVALID
        assert "压缩比" in ei.value.message
