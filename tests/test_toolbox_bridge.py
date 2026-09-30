# -*- coding: utf-8 -*-
"""P6 桥接层测试（plan 12.3）。

验证 JS↔Python 边界：只接受 tool_id/release_id/action，不接受任意 URL 或磁盘目标；
本地管理（列出/启停/卸载/回滚）在**离线/未登录**时依然可用；
在线失败不抹掉本地状态。
"""
import json
from pathlib import Path

import pytest

from webutils.toolbox import install, paths, state


class _FakeApi:
    """假的 ToolboxApi：可控地成功或失败。"""

    def __init__(self, *, access_ok=True, raise_on=None):
        self.access_ok = access_ok
        self.raise_on = raise_on or set()
        self.calls = []

    def _maybe_raise(self, name):
        if name in self.raise_on:
            raise RuntimeError(f"{name} 失败（模拟网络错误）")

    def is_logged_in(self):
        return True

    def access(self):
        self.calls.append("access")
        self._maybe_raise("access")
        return {"unlocked": self.access_ok, "season_active": True}

    def season(self):
        self.calls.append("season")
        self._maybe_raise("season")
        return {"season_active": True, "name": "S1"}

    def current_user(self):
        return {"id": 1, "username": "alice"}

    def login(self, identifier, password):
        self.calls.append(("login", identifier, password))
        self._maybe_raise("login")
        return {"access_token": "a"}

    def logout(self):
        self.calls.append("logout")

    def new_challenge(self):
        return {"challenge_id": "c" * 16, "material": "题面"}

    def solve(self, cid, answer):
        self.calls.append(("solve", cid, answer))
        return {"unlocked": True}

    def afdian_status(self):
        return {"configured": False, "bound": False}

    def verify_order(self, order_no):
        return {"unlocked": True}

    def catalog(self):
        self.calls.append("catalog")
        return {"items": []}

    def manifest(self, tool_id, release_id):
        return {"manifest": {"files": []}, "signature": None}

    def download_ticket(self, *a, **k):
        raise AssertionError("不应走到下载")


def _make_bridge(tmp_path, *, api=None, game_root=True):
    """构造一个带 ToolboxMixin 的最小对象（避开 pywebview 依赖）。"""
    from webui.app_api.toolbox import ToolboxMixin

    class Bridge(ToolboxMixin):
        def __init__(self):
            self.errors = []
            self.ui = []

        def log_error(self, exc):
            self.errors.append(repr(exc))

        def log_ui(self, msg):
            self.ui.append(msg)

        def _toolbox_api(self):
            return api or _FakeApi()

        def _toolbox_game_root(self):
            if not game_root:
                raise ValueError("尚未配置游戏目录")
            return str(tmp_path)

    return Bridge()


@pytest.fixture()
def game(tmp_path):
    g = tmp_path / "game"
    g.mkdir()
    return g


class TestStatusBridge:
    def test_local_available_when_offline(self, game):
        """在线查询失败**不能**让本地状态消失（过季/断网仍要能停用卸载）。"""
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        r = b.toolbox_status()
        assert r["success"] is True
        d = r["data"]
        assert d["local"] is not None, "本地状态必须仍然返回"
        assert d["online"] is None
        assert d["online_error"], "在线失败应如实上报，而不是静默"

    def test_reports_missing_game_root(self, tmp_path):
        b = _make_bridge(tmp_path, game_root=False)
        r = b.toolbox_status()
        assert r["success"] is True
        assert "game_root" in r["data"] or "local_error" in r["data"]

    def test_includes_protocol_version(self, game):
        b = _make_bridge(game)
        assert b.toolbox_status()["data"]["protocol_version"] >= 2


class TestLocalManagementOffline:
    """本地管理必须**不依赖**在线资格。"""

    def _install_one(self, game, tmp_path):
        import zipfile

        rt = tmp_path / "rt.zip"
        with zipfile.ZipFile(str(rt), "w") as zf:
            zf.writestr("BepInEx/core/x.dll", b"core")
        install.install_runtime(game, install.InstallPlan(
            kind="runtime", release_id="rt-1", files=[], allowed_prefixes=["BepInEx"], stub_path=rt,
        ))
        pl = tmp_path / "p.zip"
        with zipfile.ZipFile(str(pl), "w") as zf:
            zf.writestr("ToolA.dll", b"dll")
        install.install_plugin(game, install.InstallPlan(
            kind="plugin", release_id="r1", tool_id="tool-a", guid="g",
            main_dll="ToolA.dll", requires_runtime=True, stub_path=pl,
        ))

    def test_list_works_offline(self, game, tmp_path):
        self._install_one(game, tmp_path)
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        r = b.toolbox_list_installed()
        assert r["success"] is True
        assert [p["tool_id"] for p in r["data"]["plugins"]] == ["tool-a"]

    def test_disable_works_offline(self, game, tmp_path):
        """停用必须能在离线/过季时完成。"""
        self._install_one(game, tmp_path)
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        r = b.toolbox_set_enabled("tool-a", False)
        assert r["success"] is True, r
        assert not (game / "BepInEx" / "plugins" / "LCTA" / "tool-a" / "ToolA.dll").exists()

    def test_uninstall_works_offline(self, game, tmp_path):
        self._install_one(game, tmp_path)
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        assert b.toolbox_uninstall("tool-a")["success"] is True
        assert "tool-a" not in state.Manifest.load(game).plugins

    def test_rollback_works_offline(self, game, tmp_path):
        self._install_one(game, tmp_path)
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        assert b.toolbox_rollback("tool-a")["success"] is True

    def test_integrity_works_offline(self, game, tmp_path):
        self._install_one(game, tmp_path)
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        r = b.toolbox_verify_integrity("tool-a")
        assert r["success"] is True and r["data"]["ok"] is True


class TestInstallBoundary:
    def test_unsigned_manifest_refused(self, game, tmp_path):
        """未签名清单必须拒绝安装（不能只靠客户端「约定」）。"""
        b = _make_bridge(game, api=_FakeApi())
        r = b.toolbox_install(1, "r1")
        assert r["success"] is False
        assert "签名" in r["message"]

    def test_missing_public_key_refused(self, game, tmp_path, monkeypatch):
        """本地没有配置验签公钥 → fail-closed，不安装。"""
        api = _FakeApi()
        api.manifest = lambda t, r: {
            "manifest": {"files": [{"path": "A.dll", "sha256": "a" * 64}]},
            "signature": "c2ln",
        }
        b = _make_bridge(game, api=api)
        r = b.toolbox_install(1, "r1")
        assert r["success"] is False
        assert "签名" in r["message"]

    def test_no_arbitrary_url_accepted(self, game):
        """桥接口签名里**没有** URL/路径参数 —— 网页无法指定下载源或目标目录。"""
        import inspect

        from webui.app_api.toolbox import ToolboxMixin

        params = set(inspect.signature(ToolboxMixin.toolbox_install).parameters)
        assert params == {"self", "tool_id", "release_id"}
        for name in ("url", "path", "target", "command", "script"):
            assert name not in params

    def test_concurrent_install_rejected(self, game, monkeypatch):
        """并发安装必须被拒（否则两个任务互相覆盖文件）。"""
        from webui.app_api import toolbox as tb

        # 占住锁
        assert tb._task_lock.acquire(blocking=False)
        try:
            b = _make_bridge(game)
            r = b.toolbox_install(1, "r1")
            assert r["success"] is False
            assert "进行中" in r["message"]
        finally:
            tb._task_lock.release()


class TestGameRootValidation:
    def test_set_game_root_rejects_bad_path(self, tmp_path):
        b = _make_bridge(tmp_path)
        r = b.toolbox_set_game_root(str(tmp_path / "does-not-exist"))
        assert r["success"] is False

    def test_set_game_root_rejects_drive_root(self):
        import os

        if os.name != "nt":
            pytest.skip("仅 Windows")
        b = _make_bridge(Path("."))
        assert b.toolbox_set_game_root("C:\\")["success"] is False


class TestUnlockBridge:
    def test_challenge_response_has_no_answer(self, game):
        """桥返回的挑战里**不能**含答案。"""
        b = _make_bridge(game)
        data = b.toolbox_new_challenge()["data"]
        assert "answer" not in data
        assert data["challenge_id"]

    def test_solve_passes_through(self, game):
        b = _make_bridge(game)
        assert b.toolbox_solve("c" * 16, "deadbeef")["success"] is True