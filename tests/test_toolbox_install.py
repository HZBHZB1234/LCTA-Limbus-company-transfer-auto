# -*- coding: utf-8 -*-
"""P6 安装引擎测试（plan 10.2–10.5 / 16.4）。

全部在**临时目录**里操作合成 ZIP，绝不碰真实游戏目录、不执行任何 DLL。
覆盖：底座/插件安装、依赖顺序、启停（移出加载树）、更新保持启停、
回滚、卸载保留非受管文件、完整性检查、冲突检测、磁盘/游戏运行拒绝。
"""
import os
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


def _runtime_plan(stub: Path) -> install.InstallPlan:
    return install.InstallPlan(
        kind="runtime",
        release_id="rt-1",
        version="1.0.0",
        files=[("BepInEx/core/x.dll", "")],
        allowed_prefixes=["BepInEx"],
        stub_path=stub,
    )


def _plugin_plan(stub: Path, tool_id="tool-a", guid="guid-a", release="r1") -> install.InstallPlan:
    return install.InstallPlan(
        kind="plugin",
        release_id=release,
        version="2.0.0",
        tool_id=tool_id,
        guid=guid,
        main_dll="ToolA.dll",
        requires_runtime=True,
        stub_path=stub,
    )


class TestRuntimeInstall:
    def test_installs_and_records_manifest(self, game, tmp_path):
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        result = install.install_runtime(game, _runtime_plan(z))
        assert result["ok"] is True
        assert (game / "BepInEx" / "core" / "x.dll").read_bytes() == b"core"

        m = state.Manifest.load(game)
        assert m.runtime is not None and m.runtime.release_id == "rt-1"

    def test_rejects_foreign_loader_without_confirmation(self, game, tmp_path):
        """检测到非受管 BepInEx 时必须拒绝（不静默覆盖别人的框架）。"""
        (game / "BepInEx").mkdir()
        (game / "BepInEx" / "core").mkdir()
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        with pytest.raises(install.InstallError) as ei:
            install.install_runtime(game, _runtime_plan(z))
        assert ei.value.code == install.E_FOREIGN_LOADER

    def test_accepts_foreign_loader_with_confirmation(self, game, tmp_path):
        (game / "BepInEx").mkdir()
        (game / "BepInEx" / "core").mkdir()
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        result = install.install_runtime(game, _runtime_plan(z), confirm_foreign=True)
        assert result["ok"] is True

    def test_rejects_unsafe_archive(self, game, tmp_path):
        z = _zip(tmp_path / "bad.zip", [("../evil.dll", b"x")])
        with pytest.raises(install.InstallError) as ei:
            install.install_runtime(game, _runtime_plan(z))
        assert ei.value.code == install.E_MANIFEST_INVALID
        assert not (game.parent / "evil.dll").exists()

    def test_missing_stub_rejected(self, game, tmp_path):
        plan = _runtime_plan(tmp_path / "nope.zip")
        with pytest.raises(install.InstallError) as ei:
            install.install_runtime(game, plan)
        assert ei.value.code == install.E_MANIFEST_INVALID

    def test_layout_whitelist_enforced(self, game, tmp_path):
        """底座包不能往白名单外的位置写文件。"""
        z = _zip(tmp_path / "rt.zip", [("evil.txt", b"x")])
        with pytest.raises(install.InstallError):
            install.install_runtime(game, _runtime_plan(z))

    def test_second_install_backs_up_previous(self, game, tmp_path):
        """重复安装：旧文件先备份，回滚能恢复。"""
        z1 = _zip(tmp_path / "rt1.zip", [("BepInEx/core/x.dll", b"v1")])
        install.install_runtime(game, _runtime_plan(z1))
        z2 = _zip(tmp_path / "rt2.zip", [("BepInEx/core/x.dll", b"v2")])
        install.install_runtime(game, _runtime_plan(z2))
        assert (game / "BepInEx" / "core" / "x.dll").read_bytes() == b"v2"

        m = state.Manifest.load(game)
        backup = m.runtime.files[0].backup_path
        assert backup and (paths.backups_dir(game) / backup).exists()


class TestPluginInstall:
    def _with_runtime(self, game, tmp_path):
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        install.install_runtime(game, _runtime_plan(z))

    def test_requires_runtime_first(self, game, tmp_path):
        z = _zip(tmp_path / "p.zip", [("ToolA.dll", b"dll")])
        with pytest.raises(install.InstallError) as ei:
            install.install_plugin(game, _plugin_plan(z))
        assert ei.value.code == install.E_DEPENDENCY_MISSING

    def test_installs_into_managed_dir(self, game, tmp_path):
        self._with_runtime(game, tmp_path)
        z = _zip(tmp_path / "p.zip", [("ToolA.dll", b"dll")])
        result = install.install_plugin(game, _plugin_plan(z))
        assert result["ok"] is True
        assert (game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "ToolA.dll").read_bytes() == b"dll"

    def test_rejects_guid_conflict(self, game, tmp_path):
        self._with_runtime(game, tmp_path)
        z1 = _zip(tmp_path / "p1.zip", [("ToolA.dll", b"a")])
        install.install_plugin(game, _plugin_plan(z1, tool_id="tool-a", guid="same-guid"))
        z2 = _zip(tmp_path / "p2.zip", [("ToolB.dll", b"b")])
        with pytest.raises(install.InstallError) as ei:
            install.install_plugin(game, _plugin_plan(z2, tool_id="tool-b", guid="same-guid"))
        assert ei.value.code == install.E_GUID_CONFLICT

    def test_update_preserves_disabled_state(self, game, tmp_path):
        """原本停用的插件，更新后**仍停用**（不能意外启用）。"""
        self._with_runtime(game, tmp_path)
        z1 = _zip(tmp_path / "p1.zip", [("ToolA.dll", b"v1")])
        install.install_plugin(game, _plugin_plan(z1))
        install.set_enabled(game, "tool-a", False)

        z2 = _zip(tmp_path / "p2.zip", [("ToolA.dll", b"v2")])
        result = install.install_plugin(game, _plugin_plan(z2, release="r2"))
        assert result["enabled"] is False
        # 新版本应落在停用目录，而不是加载树里
        assert not (game / "BepInEx" / "plugins" / "LCTA" / "tool-a").exists()
        assert (paths.disabled_dir(game, "tool-a", "r2") / "ToolA.dll").read_bytes() == b"v2"


class TestEnableDisable:
    def _setup(self, game, tmp_path):
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        install.install_runtime(game, _runtime_plan(z))
        zp = _zip(tmp_path / "p.zip", [("ToolA.dll", b"dll")])
        install.install_plugin(game, _plugin_plan(zp))

    def test_disable_moves_out_of_load_tree(self, game, tmp_path):
        """停用必须把 DLL 移出**整个** BepInEx 加载树。

        只改配置里的 enabled 布尔值是不够的 —— BepInEx 照样会加载。
        """
        self._setup(game, tmp_path)
        enabled_path = game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "ToolA.dll"
        assert enabled_path.exists()

        install.set_enabled(game, "tool-a", False)
        assert not enabled_path.exists()
        # 停用位置在加载树之外
        disabled = paths.disabled_dir(game, "tool-a", "r1") / "ToolA.dll"
        assert disabled.exists()
        assert not paths.is_within(disabled, game / "BepInEx" / "plugins")

    def test_reenable_restores_to_load_tree(self, game, tmp_path):
        self._setup(game, tmp_path)
        install.set_enabled(game, "tool-a", False)
        install.set_enabled(game, "tool-a", True)
        assert (game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "ToolA.dll").exists()

    def test_state_persisted(self, game, tmp_path):
        self._setup(game, tmp_path)
        install.set_enabled(game, "tool-a", False)
        assert state.Manifest.load(game).plugins["tool-a"].enabled is False

    def test_idempotent(self, game, tmp_path):
        self._setup(game, tmp_path)
        r = install.set_enabled(game, "tool-a", True)
        assert r["changed"] is False

    def test_unmanaged_rejected(self, game, tmp_path):
        self._setup(game, tmp_path)
        with pytest.raises(install.InstallError) as ei:
            install.set_enabled(game, "not-installed", False)
        assert ei.value.code == install.E_NOT_MANAGED


class TestIntegrity:
    def _setup(self, game, tmp_path):
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        install.install_runtime(game, _runtime_plan(z))
        zp = _zip(tmp_path / "p.zip", [("ToolA.dll", b"dll")])
        install.install_plugin(game, _plugin_plan(zp))

    def test_clean_is_ok(self, game, tmp_path):
        self._setup(game, tmp_path)
        r = install.verify_integrity(game, "tool-a")
        assert r["ok"] is True and r["needs_repair"] is False

    def test_detects_modified_file(self, game, tmp_path):
        """文件被改过（用户手改/杀毒改动）→ 需要修复，不静默放过。"""
        self._setup(game, tmp_path)
        (game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "ToolA.dll").write_bytes(b"TAMPERED")
        r = install.verify_integrity(game, "tool-a")
        assert r["ok"] is False
        assert r["modified"] == ["ToolA.dll"]

    def test_detects_missing_file(self, game, tmp_path):
        """被杀毒隔离 → 报「缺失」而不是「正常」。"""
        self._setup(game, tmp_path)
        (game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "ToolA.dll").unlink()
        r = install.verify_integrity(game, "tool-a")
        assert r["ok"] is False
        assert r["missing"] == ["ToolA.dll"]


class TestUninstall:
    def _setup(self, game, tmp_path):
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        install.install_runtime(game, _runtime_plan(z))
        zp = _zip(tmp_path / "p.zip", [("ToolA.dll", b"dll")])
        install.install_plugin(game, _plugin_plan(zp))

    def test_removes_managed_files(self, game, tmp_path):
        self._setup(game, tmp_path)
        r = install.uninstall_plugin(game, "tool-a")
        assert r["removed"] >= 1
        assert not (game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "ToolA.dll").exists()
        assert "tool-a" not in state.Manifest.load(game).plugins

    def test_preserves_unmanaged_files(self, game, tmp_path):
        """卸载只删受管文件；用户放进同目录的其他文件必须保留。"""
        self._setup(game, tmp_path)
        user_file = game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "my-notes.txt"
        user_file.write_text("mine", encoding="utf-8")
        install.uninstall_plugin(game, "tool-a")
        assert user_file.exists(), "不得删除用户自己的文件"

    def test_preserves_user_modified_file(self, game, tmp_path):
        """受管文件被用户改过 → 不自动删，交给用户决定。"""
        self._setup(game, tmp_path)
        dll = game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "ToolA.dll"
        dll.write_bytes(b"USER-EDITED")
        r = install.uninstall_plugin(game, "tool-a")
        assert dll.exists()
        assert str(dll) in r["skipped"]

    def test_runtime_survives_plugin_uninstall(self, game, tmp_path):
        """卸载插件不能动底座。"""
        self._setup(game, tmp_path)
        install.uninstall_plugin(game, "tool-a")
        assert (game / "BepInEx" / "core" / "x.dll").exists()
        assert state.Manifest.load(game).runtime is not None


class TestRollback:
    def test_rollback_restores_backup(self, game, tmp_path):
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        install.install_runtime(game, _runtime_plan(z))
        z1 = _zip(tmp_path / "p1.zip", [("ToolA.dll", b"v1")])
        install.install_plugin(game, _plugin_plan(z1))
        z2 = _zip(tmp_path / "p2.zip", [("ToolA.dll", b"v2")])
        install.install_plugin(game, _plugin_plan(z2, release="r2"))

        r = install.rollback_plugin(game, "tool-a")
        assert r["ok"] is True
        assert (game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "ToolA.dll").read_bytes() == b"v1"

    def test_rollback_works_while_disabled(self, game, tmp_path):
        """离线/停用状态下也能回滚（本地维护不依赖在线资格）。"""
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        install.install_runtime(game, _runtime_plan(z))
        z1 = _zip(tmp_path / "p1.zip", [("ToolA.dll", b"v1")])
        install.install_plugin(game, _plugin_plan(z1))
        z2 = _zip(tmp_path / "p2.zip", [("ToolA.dll", b"v2")])
        install.install_plugin(game, _plugin_plan(z2, release="r2"))
        install.set_enabled(game, "tool-a", False)

        r = install.rollback_plugin(game, "tool-a")
        assert r["ok"] is True
        assert (paths.disabled_dir(game, "tool-a", "r2") / "ToolA.dll").read_bytes() == b"v1"


class TestConflictDetection:
    def test_detects_foreign_loader(self, game):
        (game / "BepInEx").mkdir()
        c = install.detect_conflicts(game)
        assert c["foreign_loader"] is True
        assert c["managed_runtime"] is False

    def test_managed_loader_not_foreign(self, game, tmp_path):
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        install.install_runtime(game, _runtime_plan(z))
        c = install.detect_conflicts(game)
        assert c["foreign_loader"] is False
        assert c["managed_runtime"] is True


class TestListing:
    def test_lists_managed_and_unmanaged(self, game, tmp_path):
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        install.install_runtime(game, _runtime_plan(z))
        zp = _zip(tmp_path / "p.zip", [("ToolA.dll", b"dll")])
        install.install_plugin(game, _plugin_plan(zp))

        # 用户自己放了一个插件
        manual = game / "BepInEx" / "plugins" / "OtherMod.dll"
        manual.write_bytes(b"other")

        r = install.list_installed(game)
        assert r["runtime"]["release_id"] == "rt-1"
        assert [p["tool_id"] for p in r["plugins"]] == ["tool-a"]
        assert any("OtherMod.dll" in u for u in r["unmanaged"])

    def test_works_without_manifest(self, game):
        r = install.list_installed(game)
        assert r["runtime"] is None and r["plugins"] == []


class TestGameRunningGuard:
    def test_install_refused_while_game_running(self, game, tmp_path, monkeypatch):
        """游戏运行中必须拒绝安装（文件被锁，写进去会损坏安装）。"""
        monkeypatch.setattr(install.runtime, "is_game_running", lambda *a, **k: True)
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        with pytest.raises(RuntimeError) as ei:
            install.install_runtime(game, _runtime_plan(z))
        assert "游戏正在运行" in str(ei.value)

    def test_set_enabled_refused_while_game_running(self, game, tmp_path, monkeypatch):
        z = _zip(tmp_path / "rt.zip", [("BepInEx/core/x.dll", b"core")])
        install.install_runtime(game, _runtime_plan(z))
        zp = _zip(tmp_path / "p.zip", [("ToolA.dll", b"dll")])
        install.install_plugin(game, _plugin_plan(zp))

        monkeypatch.setattr(install.runtime, "is_game_running", lambda *a, **k: True)
        with pytest.raises(RuntimeError):
            install.set_enabled(game, "tool-a", False)