# -*- coding: utf-8 -*-
"""底座生命周期（2026-11-02）：卸载 / 回滚 / 旧文件清理 / LimiNex 遗留识别。

## 为什么补这些

订阅工具底座（Zylarnex）取代了 cheat core 里的 LimiNex 挂载。旧实现有
``unmount``，新实现**只有安装没有卸载** —— 用户装上就回不到裸跑。这里补齐：

- ``uninstall_runtime``：只动登记过且哈希匹配的文件；安装时覆盖过的原始文件
  还原回去；``BepInEx/plugins`` 里的用户插件一律保留；
- ``rollback_runtime``：按备份还原；
- 插件更新清理旧版本残留（不清理会让 BepInEx 同时加载新旧两个 DLL）；
- ``detect_conflicts`` 识别 LimiNex 遗留痕迹（只上报，不擅自删）。
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from webutils.toolbox import install, paths, state


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


def _runtime_plan(stub: Path, release="rt-1") -> install.InstallPlan:
    return install.InstallPlan(
        kind="runtime",
        release_id=release,
        version="1.0.0",
        files=[],
        allowed_prefixes=(),
        stub_path=stub,
    )


def _plugin_plan(stub: Path, *, tool_id="tool-a", release="r1", main="A.dll") -> install.InstallPlan:
    return install.InstallPlan(
        kind="plugin",
        release_id=release,
        version="1.0.0",
        tool_id=tool_id,
        guid=None,
        main_dll=main,
        requires_runtime=False,
        stub_path=stub,
    )


class TestRuntimeUninstall:
    def test_restores_original_and_removes_ours(self, game, tmp_path):
        (game / "winhttp.dll").write_bytes(b"original")
        stub = _zip(tmp_path / "rt.zip", [
            ("winhttp.dll", b"zylarnex"),
            ("BepInEx/core/x.dll", b"core"),
        ])
        install.install_runtime(game, _runtime_plan(stub))
        assert (game / "winhttp.dll").read_bytes() == b"zylarnex"

        result = install.uninstall_runtime(game)
        assert result["ok"] is True
        # 覆盖过的原始文件还原（不是删掉）
        assert (game / "winhttp.dll").read_bytes() == b"original"
        # 我们新增的文件删除
        assert not (game / "BepInEx" / "core" / "x.dll").exists()
        assert state.Manifest.load(game).runtime is None

    def test_keeps_user_plugins(self, game, tmp_path):
        """卸载底座不能连带删用户的 BepInEx/plugins（旧 LimiNex 的整目录删是反例）。"""
        stub = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        install.install_runtime(game, _runtime_plan(stub))
        user_plugin = game / "BepInEx" / "plugins" / "user" / "Other.dll"
        user_plugin.parent.mkdir(parents=True)
        user_plugin.write_bytes(b"user")

        install.uninstall_runtime(game)
        assert user_plugin.read_bytes() == b"user"

    def test_skips_user_modified_runtime_file(self, game, tmp_path):
        stub = _zip(tmp_path / "rt.zip", [
            ("winhttp.dll", b"zylarnex"),
        ])
        install.install_runtime(game, _runtime_plan(stub))
        (game / "winhttp.dll").write_bytes(b"user-patched")

        result = install.uninstall_runtime(game)
        assert (game / "winhttp.dll").read_bytes() == b"user-patched"
        assert "winhttp.dll" in result["skipped"]

    def test_rejects_when_never_installed(self, game):
        with pytest.raises(install.InstallError) as ei:
            install.uninstall_runtime(game)
        assert ei.value.code == install.E_NOT_MANAGED

    def test_never_touches_game_own_files(self, game, tmp_path):
        """即便清单被篡改，也不允许删游戏本体。"""
        exe = game / "LimbusCompany.exe"
        with pytest.raises(paths.UnsafePathError):
            paths.assert_runtime_target(game, exe)
        with pytest.raises(paths.UnsafePathError):
            paths.assert_runtime_target(game, game / "GameAssembly.dll")

    def test_rollback_restores_from_backup(self, game, tmp_path):
        (game / "winhttp.dll").write_bytes(b"original")
        stub = _zip(tmp_path / "rt.zip", [("winhttp.dll", b"zylarnex")])
        install.install_runtime(game, _runtime_plan(stub))
        result = install.rollback_runtime(game)
        assert result["restored"] == ["winhttp.dll"]
        assert (game / "winhttp.dll").read_bytes() == b"original"
        # 回滚不改受管记录，卸载负责清空
        assert state.Manifest.load(game).runtime is not None


class TestRuntimeTargetAssertion:
    def test_allows_base_files_at_root(self, game):
        paths.assert_runtime_target(game, game / "winhttp.dll")
        paths.assert_runtime_target(game, game / "doorstop_config.ini")
        paths.assert_runtime_target(game, game / "BepInEx" / "core" / "x.dll")

    def test_rejects_outside_game_root(self, game, tmp_path):
        with pytest.raises(paths.UnsafePathError):
            paths.assert_runtime_target(game, tmp_path / "elsewhere.dll")

    def test_rejects_game_root_itself(self, game):
        with pytest.raises(paths.UnsafePathError):
            paths.assert_runtime_target(game, game)


class TestPluginStaleCleanup:
    def test_update_removes_dropped_file(self, game, tmp_path):
        """旧版本多出来的 DLL 必须删掉：留着会被 BepInEx 一起加载。"""
        install.install_plugin(game, _plugin_plan(_zip(tmp_path / "v1.zip", [
            ("A.dll", b"a1"), ("B.dll", b"b1"),
        ])))
        install.install_plugin(game, _plugin_plan(_zip(tmp_path / "v2.zip", [
            ("A.dll", b"a2"),
        ]), release="r2"))

        plugin_dir = paths.plugin_dir(game, "tool-a")
        assert (plugin_dir / "A.dll").read_bytes() == b"a2"
        assert not (plugin_dir / "B.dll").exists()

    def test_update_keeps_user_modified_stale_file(self, game, tmp_path):
        install.install_plugin(game, _plugin_plan(_zip(tmp_path / "v1.zip", [
            ("A.dll", b"a1"), ("B.dll", b"b1"),
        ])))
        plugin_dir = paths.plugin_dir(game, "tool-a")
        (plugin_dir / "B.dll").write_bytes(b"user-hacked")

        install.install_plugin(game, _plugin_plan(_zip(tmp_path / "v2.zip", [
            ("A.dll", b"a2"),
        ]), release="r2"))
        assert (plugin_dir / "B.dll").read_bytes() == b"user-hacked"


class TestLiminexLegacyDetection:
    def test_detects_marker(self, game):
        (game / "BepInEx").mkdir()
        (game / "BepInEx" / "lcta-liminex.json").write_text("{}", encoding="utf-8")
        assert install.detect_conflicts(game)["liminex_legacy"] is True

    def test_detects_mapping_artifacts(self, game):
        (game / "BepInEx").mkdir()
        (game / "il2cpp_mappings.txt").write_text("il2cpp_init=x\n", encoding="utf-8")
        assert install.detect_conflicts(game)["liminex_legacy"] is True

    def test_plain_bepinex_is_not_liminex(self, game):
        (game / "BepInEx" / "core").mkdir(parents=True)
        out = install.detect_conflicts(game)
        assert out["liminex_legacy"] is False
        assert out["foreign_loader"] is True
