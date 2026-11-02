# -*- coding: utf-8 -*-
"""启动器阶段的订阅工具自动更新（2026-11-02）。

这里测的是**编排**，不是安装本身（安装由 webutils/toolbox 的测试覆盖）：
什么时候跳过、按什么顺序执行、失败怎么退避、报告落到哪里。

关键语义（无人值守阶段的底线）：

- 未登录/无资格/断网/游戏运行中 → 跳过，且**不产生任何写入**；
- 节流：默认 6 小时；失败退避 1 小时；
- 只升级已装工具；底座跳过；绝不降级（由 ``deps.plan_updates`` 保证）；
- 单个工具失败不影响其余，且不抛出（不能阻塞游戏启动）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from launcher import toolbox_update
from webutils.toolbox import state


class FakeApi:
    """替代 ToolboxMixin 适配器：只保留本模块用到的接口。"""

    def __init__(self, *, logged_in=True, season_active=True, unlocked=True,
                 items=None, install_ok=True, install_error=None):
        self.logged_in = logged_in
        self.season_active = season_active
        self.unlocked = unlocked
        self.items = items or []
        self.install_ok = install_ok
        self.install_error = install_error
        self.calls = []

    def is_logged_in(self):
        return self.logged_in

    def season(self):
        return {"season_active": self.season_active}

    def access(self):
        return {"unlocked": self.unlocked}

    def catalog(self):
        return {"items": self.items}

    def toolbox_install_any(self, tool_id, release_id):
        self.calls.append((str(tool_id), str(release_id)))
        if self.install_error is not None:
            raise self.install_error
        if not self.install_ok:
            return {"success": False, "code": "install_failed", "message": "安装失败"}
        return {"success": True, "message": "安装完成"}


@pytest.fixture()
def game(tmp_path, monkeypatch):
    root = tmp_path / "game"
    root.mkdir()
    monkeypatch.setattr(toolbox_update, "_resolve_game_root", lambda: str(root))
    monkeypatch.setattr(toolbox_update, "_network_ok", lambda *a, **k: True)
    # 测试不碰真实进程检测
    import webutils.toolbox.runtime as toolbox_runtime
    monkeypatch.setattr(toolbox_runtime, "is_game_running", lambda *a, **k: False)
    return root


def _install_manifest(root: Path, entries=("1",)) -> None:
    manifest = state.Manifest(root)
    for tool_id in entries:
        manifest.plugins[tool_id] = state.PluginEntry(
            tool_id=tool_id,
            release_id=f"old-{tool_id}",
            version="1.0.0",
            version_sort="0001.0000.0000~",
            main_dll="A.dll",
            files=[],
        )
    manifest.save()


def _catalog_item(tool_id="1", *, release="new-1", version_sort="0001.0001.0000~",
                  install_kind="bepinex_plugin_dll", downloadable=True, dependencies=()):
    return {
        "tool_id": int(tool_id),
        "tool_name": f"T{tool_id}",
        "release_id": release,
        "version": "1.1.0",
        "version_sort": version_sort,
        "is_latest": True,
        "install_kind": install_kind,
        "access_kind": "original",
        "downloadable": downloadable,
        "dependencies": list(dependencies),
    }


def _use_api(monkeypatch, api) -> None:
    monkeypatch.setattr(toolbox_update, "_make_bridge", lambda: api)


def _state(root: Path) -> dict:
    return json.loads((root / ".lcta-toolbox" / "update-state.json").read_text(encoding="utf-8"))


def _report(root: Path) -> dict:
    return json.loads((root / ".lcta-toolbox" / "last-update.json").read_text(encoding="utf-8"))


class TestPreconditions:
    def test_no_game_root_skips(self, monkeypatch):
        monkeypatch.setattr(toolbox_update, "_resolve_game_root", lambda: None)
        report = toolbox_update.run_toolbox_update(force=True)
        assert report["skipped"] == "no_game_root"

    def test_throttled_without_force(self, game, monkeypatch):
        _install_manifest(game)
        (game / ".lcta-toolbox" / "update-state.json").write_text(
            json.dumps({"last_check_at": time.time()}), encoding="utf-8"
        )
        api = FakeApi(items=[_catalog_item()])
        _use_api(monkeypatch, api)
        report = toolbox_update.run_toolbox_update()
        assert report["skipped"] == "throttled"
        assert api.calls == []

    def test_force_bypasses_throttle(self, game, monkeypatch):
        _install_manifest(game)
        (game / ".lcta-toolbox" / "update-state.json").write_text(
            json.dumps({"last_check_at": time.time()}), encoding="utf-8"
        )
        api = FakeApi(items=[_catalog_item()])
        _use_api(monkeypatch, api)
        report = toolbox_update.run_toolbox_update(force=True)
        assert report["skipped"] is None
        assert api.calls == [("1", "new-1")]

    def test_offline_skips(self, game, monkeypatch):
        monkeypatch.setattr(toolbox_update, "_network_ok", lambda *a, **k: False)
        api = FakeApi(items=[_catalog_item()])
        _use_api(monkeypatch, api)
        assert toolbox_update.run_toolbox_update(force=True)["skipped"] == "offline"
        assert api.calls == []

    def test_game_running_skips(self, game, monkeypatch):
        import webutils.toolbox.runtime as toolbox_runtime

        monkeypatch.setattr(toolbox_runtime, "is_game_running", lambda *a, **k: True)
        api = FakeApi(items=[_catalog_item()])
        _use_api(monkeypatch, api)
        assert toolbox_update.run_toolbox_update(force=True)["skipped"] == "game_running"
        assert api.calls == []

    @pytest.mark.parametrize("kwargs,reason", [
        ({"logged_in": False}, "not_logged_in"),
        ({"season_active": False}, "season_inactive"),
        ({"unlocked": False}, "no_entitlement"),
    ])
    def test_account_gates(self, game, monkeypatch, kwargs, reason):
        _install_manifest(game)
        api = FakeApi(items=[_catalog_item()], **kwargs)
        _use_api(monkeypatch, api)
        report = toolbox_update.run_toolbox_update(force=True)
        assert report["skipped"] == reason
        assert api.calls == []


class TestApply:
    def test_updates_installed_tool_and_writes_report(self, game, monkeypatch):
        _install_manifest(game)
        api = FakeApi(items=[_catalog_item()])
        _use_api(monkeypatch, api)

        report = toolbox_update.run_toolbox_update(force=True)
        assert report["ok"] is True
        assert [u["tool_id"] for u in report["updated"]] == ["1"]
        assert api.calls == [("1", "new-1")]
        assert _report(game)["updated"][0]["tool_id"] == "1"
        assert _state(game)["last_result"]["updated"] == 1

    def test_no_update_is_clean_noop(self, game, monkeypatch):
        _install_manifest(game)
        api = FakeApi(items=[])  # 目录里没有该工具
        _use_api(monkeypatch, api)
        report = toolbox_update.run_toolbox_update(force=True)
        assert report["updated"] == [] and report["failed"] == []
        assert api.calls == []

    def test_does_not_install_unmanaged_tools(self, game, monkeypatch):
        """自动更新只升级已装工具：目录里有新工具也不装。"""
        _install_manifest(game, entries=())
        api = FakeApi(items=[_catalog_item(tool_id="9")])
        _use_api(monkeypatch, api)
        report = toolbox_update.run_toolbox_update(force=True)
        assert report["updated"] == []
        assert api.calls == []

    def test_runtime_never_auto_updated(self, game, monkeypatch):
        _install_manifest(game)
        api = FakeApi(items=[_catalog_item(install_kind="runtime_zip_root")])
        _use_api(monkeypatch, api)
        report = toolbox_update.run_toolbox_update(force=True)
        assert report["updated"] == []
        assert api.calls == []
        skipped = [s["reason"] for s in report["details"]["skipped_items"]]
        assert "runtime_manual" in skipped

    def test_failure_recorded_and_backed_off(self, game, monkeypatch):
        _install_manifest(game)
        api = FakeApi(items=[_catalog_item()], install_ok=False)
        _use_api(monkeypatch, api)

        report = toolbox_update.run_toolbox_update(force=True)
        assert report["ok"] is False
        assert [f["tool_id"] for f in report["failed"]] == ["1"]
        assert _state(game)["failures"]["1"] > 0

        # 1 小时内不再重试（避免每次开局都打站点）
        api2 = FakeApi(items=[_catalog_item()])
        _use_api(monkeypatch, api2)
        report2 = toolbox_update.run_toolbox_update(force=True)
        assert api2.calls == []
        assert report2["updated"] == []

    def test_exception_never_escapes(self, game, monkeypatch):
        """单个工具抛异常不能让阶段炸掉（会阻塞游戏启动）。"""
        _install_manifest(game)
        api = FakeApi(items=[_catalog_item()], install_error=RuntimeError("boom"))
        _use_api(monkeypatch, api)
        report = toolbox_update.run_toolbox_update(force=True)
        assert report["ok"] is False
        assert report["failed"][0]["tool_id"] == "1"

    def test_cancel_stops_between_tools(self, game, monkeypatch):
        import threading

        _install_manifest(game, entries=("1", "2"))
        catalog = [_catalog_item(tool_id="1"), _catalog_item(tool_id="2")]
        api = FakeApi(items=catalog)
        _use_api(monkeypatch, api)

        cancel = threading.Event()
        cancel.set()  # 一开始就取消：一个都不装
        report = toolbox_update.run_toolbox_update(force=True, cancel_event=cancel)
        assert api.calls == []
        assert report["failed"][0].get("cancelled") is True

    def test_dependency_repaired_when_missing(self, game, monkeypatch):
        """已装工具的硬依赖缺失 → 补装（修复而不是新增功能）。"""
        _install_manifest(game)
        catalog = [
            _catalog_item(tool_id="1", release="old-1", version_sort="0001.0000.0000~",
                          dependencies=[{"tool_id": 2, "optional": False}]),
            _catalog_item(tool_id="2"),
        ]
        api = FakeApi(items=catalog)
        _use_api(monkeypatch, api)
        report = toolbox_update.run_toolbox_update(force=True)
        assert [r["tool_id"] for r in report["repaired"]] == ["2"]


class TestReportReader:
    def test_reads_last_report(self, game):
        (game / ".lcta-toolbox").mkdir()
        (game / ".lcta-toolbox" / "last-update.json").write_text(
            json.dumps({"ok": True, "updated": [{"tool_id": "1"}]}), encoding="utf-8"
        )
        assert toolbox_update.read_last_report()["updated"][0]["tool_id"] == "1"

    def test_missing_report_is_empty(self, game):
        assert toolbox_update.read_last_report() == {}
