# -*- coding: utf-8 -*-
"""P6 manifest / journal / 崩溃恢复测试（plan 10.5 / 16.4）。

核心不变量：

1. manifest 写入是**原子**的（临时文件 + os.replace），不会留下截断 JSON；
2. 多文件提交中断后，journal 能把磁盘恢复到事务前状态；
3. manifest **不含任何凭据**（它是本地明文文件）；
4. 游戏目录被移动后，旧 manifest 不套用到新路径。
"""
import json
import os
from pathlib import Path

import pytest

from webutils.toolbox import paths, state


class TestAtomicWrite:
    def test_writes_and_reads_back(self, tmp_path):
        p = tmp_path / "m.json"
        state.atomic_write_json(p, {"a": 1})
        assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1}

    def test_no_temp_file_left_behind(self, tmp_path):
        p = tmp_path / "m.json"
        state.atomic_write_json(p, {"a": 1})
        leftovers = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
        assert leftovers == []

    def test_overwrite_is_atomic(self, tmp_path):
        p = tmp_path / "m.json"
        state.atomic_write_json(p, {"v": 1})
        state.atomic_write_json(p, {"v": 2})
        assert json.loads(p.read_text(encoding="utf-8")) == {"v": 2}

    def test_read_json_tolerates_corruption(self, tmp_path):
        """损坏的 JSON 不能让读取抛错（否则整个工具箱打不开）。"""
        p = tmp_path / "bad.json"
        p.write_text("{ truncated", encoding="utf-8")
        assert state.read_json(p, default={"fallback": True}) == {"fallback": True}

    def test_read_json_missing_returns_default(self, tmp_path):
        assert state.read_json(tmp_path / "nope.json", default=None) is None


class TestManifest:
    def test_roundtrip(self, tmp_path):
        game = tmp_path / "game"
        game.mkdir()
        m = state.Manifest(game)
        m.runtime = state.RuntimeEntry(release_id="rt-1", version="1.0.0")
        m.plugins["tool-a"] = state.PluginEntry(
            tool_id="tool-a", release_id="r1", version="2.0", guid="guid-a",
            main_dll="ToolA.dll", installed_at=state._utcnow_iso(),
        )
        m.save()

        loaded = state.Manifest.load(game)
        assert loaded.runtime is not None and loaded.runtime.release_id == "rt-1"
        assert loaded.is_managed("tool-a")
        assert loaded.plugins["tool-a"].guid == "guid-a"

    def test_missing_manifest_is_empty(self, tmp_path):
        game = tmp_path / "game"
        game.mkdir()
        m = state.Manifest.load(game)
        assert m.runtime is None and m.plugins == {}

    def test_manifest_contains_no_credentials(self, tmp_path):
        """manifest 是本地明文文件，绝不能写进任何凭据（plan 10.5）。"""
        game = tmp_path / "game"
        game.mkdir()
        m = state.Manifest(game)
        m.plugins["tool-a"] = state.PluginEntry(tool_id="tool-a", release_id="r1")
        m.save()

        raw = (paths.manifest_path(game)).read_text(encoding="utf-8").lower()
        for forbidden in ("access_token", "refresh_token", "ticket", "secret",
                          "password", "email_code", "pepper", "private_key"):
            assert forbidden not in raw, f"manifest 泄露了 {forbidden}"

    def test_game_root_move_invalidates_manifest(self, tmp_path):
        """游戏目录被移动后，旧 manifest 不得套用到新路径。"""
        g1 = tmp_path / "game1"
        g1.mkdir()
        m = state.Manifest(g1)
        m.plugins["tool-a"] = state.PluginEntry(tool_id="tool-a", release_id="r1")
        m.save()
        data = json.loads(paths.manifest_path(g1).read_text(encoding="utf-8"))

        g2 = tmp_path / "game2"
        g2.mkdir()
        # 把旧 manifest 内容放到新目录（模拟「目录整体移动但 manifest 一起搬走」）
        paths.toolbox_dir(g2).mkdir(parents=True, exist_ok=True)
        paths.manifest_path(g2).write_text(json.dumps(data), encoding="utf-8")

        m2 = state.Manifest.load(g2)
        assert not m2.is_managed("tool-a"), "移动后不应沿用旧路径的受管清单"
        assert m2.runtime is None

    def test_guid_conflict_detection(self, tmp_path):
        game = tmp_path / "game"
        game.mkdir()
        m = state.Manifest(game)
        m.plugins["a"] = state.PluginEntry(tool_id="a", release_id="r1", guid="same", enabled=True)
        assert m.has_guid_conflict("same") == "a"
        assert m.has_guid_conflict("same", exclude_tool="a") is None
        assert m.has_guid_conflict("other") is None

    def test_disabled_plugin_does_not_conflict(self, tmp_path):
        """停用的插件不占用加载树，不应造成 GUID 冲突。"""
        game = tmp_path / "game"
        game.mkdir()
        m = state.Manifest(game)
        m.plugins["a"] = state.PluginEntry(tool_id="a", release_id="r1", guid="same", enabled=False)
        assert m.has_guid_conflict("same") is None


class TestJournalRollback:
    def _setup(self, tmp_path):
        game = tmp_path / "game"
        game.mkdir()
        return game

    def test_rollback_restores_modified_file(self, tmp_path):
        """被覆盖的文件回滚后恢复原内容。"""
        game = self._setup(tmp_path)
        target = game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "A.dll"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"ORIGINAL")

        j = state.Journal(game)
        j.begin("install", "tool-a")
        backup_rel = "tool-a/A.dll"
        state.backup_file(game, target, backup_rel)
        j.add_entry(target, backup_rel=backup_rel, existed=True)

        # 提交阶段：写入新内容
        target.write_bytes(b"NEW")

        result = state.restore_from_journal(game, j)
        assert target.read_bytes() == b"ORIGINAL"
        assert str(target) in result["restored"]

    def test_rollback_deletes_newly_created_file(self, tmp_path):
        """事务中新建的文件回滚后应被删除。"""
        game = self._setup(tmp_path)
        target = game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "New.dll"
        target.parent.mkdir(parents=True)

        j = state.Journal(game)
        j.begin("install", "tool-a")
        j.add_entry(target, backup_rel=None, existed=False)
        target.write_bytes(b"NEW")

        result = state.restore_from_journal(game, j)
        assert not target.exists()
        assert str(target) in result["deleted"]

    def test_rollback_is_reverse_order(self, tmp_path):
        """逆序回滚：同一路径被多次改动时顺序不能乱。"""
        game = self._setup(tmp_path)
        t1 = game / "a.txt"
        t1.write_text("v1", encoding="utf-8")

        j = state.Journal(game)
        j.begin("install")
        state.backup_file(game, t1, "a1.txt")
        j.add_entry(t1, backup_rel="a1.txt", existed=True)
        t1.write_text("v2", encoding="utf-8")
        state.backup_file(game, t1, "a2.txt")
        j.add_entry(t1, backup_rel="a2.txt", existed=True)
        t1.write_text("v3", encoding="utf-8")

        state.restore_from_journal(game, j)
        # 逆序 → 先恢复 a2（v2），再恢复 a1（v1）→ 最终应为 v1
        assert t1.read_text(encoding="utf-8") == "v1"

    def test_missing_backup_is_reported_not_silent(self, tmp_path):
        """备份缺失必须如实上报，不能静默「回滚成功」。"""
        game = self._setup(tmp_path)
        target = game / "x.txt"
        target.write_text("now", encoding="utf-8")

        j = state.Journal(game)
        j.begin("install")
        j.add_entry(target, backup_rel="nonexistent.bak", existed=True)

        result = state.restore_from_journal(game, j)
        assert str(target) in result["missing_backup"]
        assert result["restored"] == []

    def test_rollback_refuses_outside_managed_area(self, tmp_path):
        """journal 被篡改指向受管区外时，回滚必须拒绝而不是删用户文件。"""
        game = self._setup(tmp_path)
        outside = tmp_path / "precious.txt"
        outside.write_text("important", encoding="utf-8")

        j = state.Journal(game)
        j.begin("install")
        j.add_entry(outside, backup_rel=None, existed=False)

        result = state.restore_from_journal(game, j)
        assert outside.exists(), "不得删除受管区外的文件"
        assert str(outside) in result["missing_backup"]


class TestCrashRecovery:
    def test_incomplete_journal_triggers_rollback(self, tmp_path):
        """模拟「提交到一半进程被杀」：下次启动应自动回滚。"""
        game = tmp_path / "game"
        game.mkdir()
        target = game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "A.dll"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"ORIGINAL")

        # 事务进行中：已备份、已登记、已写入新内容，但还没写 manifest
        j = state.Journal(game)
        j.begin("install", "tool-a")
        state.backup_file(game, target, "tool-a/A.dll")
        j.add_entry(target, backup_rel="tool-a/A.dll", existed=True)
        j.set_state(state.STATE_COMMITTING)
        target.write_bytes(b"HALF-WRITTEN")

        # 模拟进程重启
        result = state.recover_if_needed(game)
        assert result is not None
        assert target.read_bytes() == b"ORIGINAL"

    def test_no_incomplete_journal_is_noop(self, tmp_path):
        game = tmp_path / "game"
        game.mkdir()
        assert state.recover_if_needed(game) is None

    def test_completed_journal_is_not_recovered(self, tmp_path):
        """已完成的事务不应被回滚（否则每次启动都会撤销刚装好的东西）。"""
        game = tmp_path / "game"
        game.mkdir()
        j = state.Journal(game)
        j.begin("install", "tool-a")
        j.set_state(state.STATE_DONE)
        assert state.recover_if_needed(game) is None

    def test_journal_cleared_after_recovery(self, tmp_path):
        game = tmp_path / "game"
        game.mkdir()
        target = game / "a.txt"
        target.write_text("orig", encoding="utf-8")

        j = state.Journal(game)
        j.begin("install")
        state.backup_file(game, target, "a.bak")
        j.add_entry(target, backup_rel="a.bak", existed=True)
        j.set_state(state.STATE_COMMITTING)
        target.write_text("new", encoding="utf-8")

        state.recover_if_needed(game)
        assert state.Journal.load(game) is None, "恢复后 journal 应被清除"
        # 再次调用不应重复回滚
        assert state.recover_if_needed(game) is None
        assert target.read_text(encoding="utf-8") == "orig"