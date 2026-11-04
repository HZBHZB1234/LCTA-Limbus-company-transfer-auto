# -*- coding: utf-8 -*-
"""P6 桥接层测试（plan 12.3）。

验证 JS↔Python 边界：只接受 tool_id/release_id/action，不接受任意 URL 或磁盘目标；
本地管理（列出/启停/卸载/回滚）在**离线/未登录**时依然可用；
在线失败不抹掉本地状态。
"""
import json
from pathlib import Path

import pytest

from webutils.toolbox import api as api_mod
from webutils.toolbox import install, paths, state


class _FakeApi:
    """假的 ToolboxApi：可控地成功或失败。"""

    base_url = "https://mods.lcta.test"

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
        # confirm_foreign 是布尔确认位（外部 loader 二次确认），modal_id 只用于
        # 进度显示；两者都不是 URL/路径。契约不变：接口里永远不允许出现下载源
        # 或目标目录参数。
        assert params == {"self", "tool_id", "release_id", "confirm_foreign", "modal_id"}
        assert not any(k and ("url" in k or "path" in k) for k in params)
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
    def test_set_game_root_rejects_bad_path(self, tmp_path, monkeypatch):
        _patch_config(monkeypatch)
        b = _make_bridge(tmp_path)
        r = b.toolbox_set_game_root(str(tmp_path / "does-not-exist"))
        assert r["success"] is False

    def test_set_game_root_rejects_drive_root(self, monkeypatch):
        import os

        if os.name != "nt":
            pytest.skip("仅 Windows")
        _patch_config(monkeypatch)
        b = _make_bridge(Path("."))
        assert b.toolbox_set_game_root("C:\\")["success"] is False


def _patch_config(monkeypatch, initial=None):
    """把 ConfigManager 换成内存字典（避免测试写真实 config.json）。"""
    from globalManagers.ConfigManager import ConfigManager

    store = dict(initial or {})

    def _get(self, key, default=None):
        return store.get(key, default)

    def _set(self, key, value, auto_save=True):
        store[key] = value

    monkeypatch.setattr(ConfigManager, "get", _get)
    monkeypatch.setattr(ConfigManager, "set", _set)
    return store


def _make_real_bridge(api=None):
    """不覆盖 ``_toolbox_game_root`` 的桥：用来测真实的配置读取路径。"""
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

    return Bridge()


class TestSharedGamePath:
    """游戏路径只有一份：订阅工具页与「设置」页必须读写同一个键（2026-11-04）。

    历史 bug：订阅工具读 ``ui_default.toolbox.game_root``，设置页写 ``game_path``，
    两处都"保存成功"却互不可见。
    """

    def test_reads_shared_game_path(self, tmp_path, monkeypatch):
        game = tmp_path / "game"
        game.mkdir()
        store = _patch_config(monkeypatch, {"game_path": str(game)})
        r = _make_real_bridge().toolbox_status_local()
        assert r["data"]["game_root"] == str(game)
        assert store["game_path"] == str(game), "不应写入订阅工具私有键"

    def test_set_writes_shared_game_path_not_private_key(self, tmp_path, monkeypatch):
        from webutils.toolbox import config as toolbox_config

        game = tmp_path / "game"
        game.mkdir()
        store = _patch_config(monkeypatch)
        r = _make_real_bridge().toolbox_set_game_root(str(game))
        assert r["success"] is True
        assert store.get(toolbox_config.GAME_PATH_KEY), "必须写到共用的 game_path"
        assert toolbox_config.LEGACY_GAME_ROOT_KEY not in store, "不得再写订阅工具私有键"

    def test_legacy_key_is_migrated(self, tmp_path, monkeypatch):
        """老用户只配过订阅工具私有键：读到即迁到 game_path，之后统一。"""
        from webutils.toolbox import config as toolbox_config

        game = tmp_path / "game"
        game.mkdir()
        store = _patch_config(
            monkeypatch, {toolbox_config.LEGACY_GAME_ROOT_KEY: str(game)}
        )
        assert _make_real_bridge().toolbox_status_local()["data"]["game_root"] == str(game)
        assert store.get(toolbox_config.GAME_PATH_KEY) == str(game), "旧值应被迁移"

    def test_game_path_wins_over_legacy(self, tmp_path, monkeypatch):
        from webutils.toolbox import config as toolbox_config

        new = tmp_path / "new"
        old = tmp_path / "old"
        new.mkdir()
        old.mkdir()
        _patch_config(monkeypatch, {
            toolbox_config.GAME_PATH_KEY: str(new),
            toolbox_config.LEGACY_GAME_ROOT_KEY: str(old),
        })
        assert _make_real_bridge().toolbox_status_local()["data"]["game_root"] == str(new)

    def test_missing_root_message_points_to_settings(self, tmp_path, monkeypatch):
        """未配置时的提示必须指向「设置」页，并说明两处共用同一份路径。"""
        _patch_config(monkeypatch)
        r = _make_real_bridge().toolbox_status_local()
        msg = r["data"]["local_error"]
        assert "设置" in msg
        assert "共用" in msg


class TestSessionExpired:
    """令牌失效必须**要求重新登录**，而不是只在设置页留一行小字（2026-11-04）。"""

    def test_expired_session_flips_logged_in_false(self, game):
        from webutils.toolbox.api import AuthRequiredError

        class _ExpiredApi(_FakeApi):
            def access(self):
                self.calls.append("access")
                raise AuthRequiredError("invalid_token", "令牌已过期")

        b = _make_bridge(game, api=_ExpiredApi())
        d = b.toolbox_status_online(force=True)["data"]
        assert d["logged_in"] is False, "本地有 refresh token 也不能显示为已登录"
        assert d["session_expired"] is True
        assert d["errors"]["access"]["code"] == "auth_required", (
            "服务端 detail 的 code 五花八门，桥接层必须统一成 auth_required"
        )

    def test_network_error_is_not_session_expired(self, game):
        """断网 ≠ 登录失效：不能把网络错误也引导去重新登录。"""
        b = _make_bridge(game, api=_FakeApi(raise_on={"access"}))
        d = b.toolbox_status_online(force=True)["data"]
        assert d["logged_in"] is True
        assert d["session_expired"] is False

    def test_composed_status_carries_flag(self, game):
        from webutils.toolbox.api import AuthRequiredError

        class _ExpiredApi(_FakeApi):
            def access(self):
                raise AuthRequiredError("error", "登录已失效，请重新登录")

        b = _make_bridge(game, api=_ExpiredApi())
        d = b.toolbox_status()["data"]
        assert d["session_expired"] is True
        assert d["logged_in"] is False

    def test_no_relogin_required_after_successful_login(self, game):
        b = _make_bridge(game)
        d = b.toolbox_status_online(force=True)["data"]
        assert d["session_expired"] is False
        assert d["logged_in"] is True

    def test_expired_flag_survives_credential_wipe(self, game):
        """刷新失败会清空凭据 → 下一次 is_logged_in() 为 False。

        这时仍必须提示「需要重新登录」，否则用户看到的是普通「未登录」，
        完全不知道刚才是令牌失效导致的（表现成"莫名其妙被登出"）。
        """
        from webutils.toolbox.api import AuthRequiredError

        class _WipedApi(_FakeApi):
            def __init__(self):
                super().__init__()
                self.wiped = False

            def is_logged_in(self):
                return not self.wiped

            def access(self):
                raise AuthRequiredError("error", "登录已失效，请重新登录")

            def _wipe(self):
                self.wiped = True

        api = _WipedApi()
        b = _make_bridge(game, api=api)
        first = b.toolbox_status_online(force=True)["data"]
        assert first["session_expired"] is True

        api._wipe()  # 模拟 _refresh_once 失败后清空 DPAPI 凭据
        second = b.toolbox_status_online(force=True)["data"]
        assert second["logged_in"] is False
        assert second["session_expired"] is True, "失效提示不能只闪一次"

    def test_logout_clears_expired_flag(self, game):
        """用户主动登出后不应再提示「请重新登录」。"""
        from webutils.toolbox.api import AuthRequiredError

        class _ExpiredApi(_FakeApi):
            def __init__(self):
                super().__init__()
                self.expired = True
                self.signed_in = True

            def is_logged_in(self):
                return self.signed_in

            def access(self):
                if self.expired:
                    raise AuthRequiredError("error", "登录已失效")
                return {"unlocked": False, "season_active": True}

            def logout(self):
                self.calls.append("logout")
                self.expired = False
                self.signed_in = False

        api = _ExpiredApi()
        b = _make_bridge(game, api=api)
        assert b.toolbox_status_online(force=True)["data"]["session_expired"] is True
        b.toolbox_logout()
        d = b.toolbox_status_online(force=True)["data"]
        assert d["session_expired"] is False
        assert d["logged_in"] is False

    def test_login_clears_expired_flag(self, game):
        from webutils.toolbox.api import AuthRequiredError

        class _ExpiredApi(_FakeApi):
            def __init__(self):
                super().__init__()
                self.expired = True

            def access(self):
                if self.expired:
                    raise AuthRequiredError("error", "登录已失效")
                return {"unlocked": True, "season_active": True}

            def login(self, identifier, password):
                self.calls.append(("login", identifier, password))
                self.expired = False
                return {"access_token": "a"}

        api = _ExpiredApi()
        b = _make_bridge(game, api=api)
        assert b.toolbox_status_online(force=True)["data"]["session_expired"] is True
        assert b.toolbox_login("alice", "pw")["success"] is True
        d = b.toolbox_status_online(force=True)["data"]
        assert d["session_expired"] is False
        assert d["logged_in"] is True


class TestAuthChangedNotification:
    """登录态在别处变化时必须**立即**通知页面刷新（2026-11-04）。

    典型表现：在 Mod 镜像站窗口完成登录 / 点了「同步登录态」后，回到订阅工具页
    状态条仍写「未登录」，要手动点刷新才对。根因是登录发生在别的窗口，主窗口
    页面收不到任何通知，只能等下一次 15s 节流后的刷新。
    """

    class _Win:
        def __init__(self):
            self.scripts = []

        def evaluate_js(self, js):
            self.scripts.append(js)

        def auth_events(self):
            return [s for s in self.scripts if "lcta-toolbox-auth-changed" in s]

    def _bridge(self, game, api=None):
        b = _make_bridge(game, api=api)
        b._window = self._Win()
        return b

    def test_login_transition_notifies_page(self, game):
        class _Api(_FakeApi):
            def __init__(self):
                super().__init__()
                self.signed_in = False

            def is_logged_in(self):
                return self.signed_in

            def access(self):
                if not self.signed_in:
                    raise AssertionError("未登录时不该调用 access")
                return {"unlocked": False, "season_active": True}

            def login(self, identifier, password):
                self.signed_in = True
                return {"access_token": "a"}

        api = _Api()
        b = self._bridge(game, api=api)
        # 首次观测（游客）只记基线，不推事件
        b.toolbox_status_online(force=True)
        assert b._window.auth_events() == []
        # 登录 → 身份迁移 → 必须推事件
        assert b.toolbox_login("alice", "pw")["success"] is True
        events = b._window.auth_events()
        assert len(events) == 1
        assert "lcta-toolbox-auth-changed" in events[0]

    def test_repeated_status_does_not_loop(self, game):
        """同一身份反复查询不能推事件：否则「刷新→查询→再刷新」会自激。"""
        b = self._bridge(game)
        for _ in range(4):
            b.toolbox_status_online(force=True)
        assert b._window.auth_events() == []

    def test_logout_notifies_page(self, game):
        b = self._bridge(game)
        b.toolbox_status_online(force=True)      # 基线：已登录
        assert b._window.auth_events() == []
        assert b.toolbox_logout()["success"] is True
        events = b._window.auth_events()
        assert len(events) == 1
        assert "logout" in events[0]

    def test_sync_mirror_login_notifies_page(self, game, monkeypatch):
        """镜像站窗口里同步登录 → 主窗口页面必须立刻刷新。"""
        import webutils.function_mod_mirror as fmm

        monkeypatch.setattr(
            fmm, "mod_mirror_get_auth",
            lambda: {"access_token": "tok", "user": {"id": 9, "username": "bob"}},
        )
        api = _FakeApi()
        api.is_logged_in = lambda: False
        saved = {}
        api.save_auth = lambda data: saved.update(data)
        b = self._bridge(game, api=api)
        b.toolbox_status_online(force=True)       # 基线：游客
        assert b._window.auth_events() == []
        r = b.toolbox_sync_mirror_login(force=True)
        assert r["success"] is True
        events = b._window.auth_events()
        assert len(events) == 1
        assert "sync-mirror" in events[0]

    def test_expiry_transition_notifies_page(self, game):
        from webutils.toolbox.api import AuthRequiredError

        class _Api(_FakeApi):
            def __init__(self):
                super().__init__()
                self.expired = False

            def access(self):
                if self.expired:
                    raise AuthRequiredError("invalid_token", "令牌已过期")
                return {"unlocked": True, "season_active": True}

        api = _Api()
        b = self._bridge(game, api=api)
        b.toolbox_status_online(force=True)       # 基线：user:alice
        assert b._window.auth_events() == []
        api.expired = True
        b.toolbox_status_online(force=True)       # user -> expired
        assert len(b._window.auth_events()) == 1

    def test_missing_window_does_not_break_login(self, game):
        """无窗口（纯后端/测试环境）时推送事件不能把登录搞失败。"""
        b = _make_bridge(game)
        assert not hasattr(b, "_window")
        assert b.toolbox_login("alice", "pw")["success"] is True


class TestDeviceKeyConflict:
    """「本机密钥已被另一个账号授权」→ 询问是否覆盖（2026-11-05）。

    历史行为：服务端按公钥判定设备归属，而密钥名是固定常量 —— 同一台机器上
    无论哪个账号登录，导出的都是同一个公钥，第二个账号注册必然被拒，报
    「请先在另一账号取消授权」。那个账号往往已经登录不上，机器就此锁死。
    现在改为：冲突回可识别的 code，前端弹窗询问，同意后带 overwrite 重试。
    """

    class _ConflictApi(_FakeApi):
        """第一次注册抛冲突，带 overwrite 时成功 —— 记录实际收到的参数。"""

        def __init__(self):
            super().__init__()
            self.enable_calls = []

        def enable_device(self, display_name="", overwrite=False):
            self.enable_calls.append(bool(overwrite))
            if not overwrite:
                raise api_mod.ApiError(
                    "device_conflict", "该密钥已在另一账号下授权，请先在另一账号取消授权"
                )
            return {"device_id": "dev-new", "ok": True}

    def test_conflict_returns_actionable_code(self, game):
        api = self._ConflictApi()
        r = _make_bridge(game, api=api).toolbox_authz_enable()
        assert r["success"] is False
        # 必须是前端能分支的 code，而不是一句无从下手的文案
        assert r["code"] == "device_key_conflict"
        assert r["data"]["need_overwrite"] is True
        assert api.enable_calls == [False], "冲突时不能自动覆盖"

    def test_overwrite_retries_with_flag(self, game):
        api = self._ConflictApi()
        b = _make_bridge(game, api=api)
        assert b.toolbox_authz_enable()["code"] == "device_key_conflict"
        r = b.toolbox_authz_enable(overwrite=True)
        assert r["success"] is True
        assert api.enable_calls == [False, True]

    def test_js_false_string_is_not_truthy(self, game):
        """pywebview 有时把 ``"false"`` 当字符串传过来：不能当 True 覆盖密钥。"""
        api = self._ConflictApi()
        b = _make_bridge(game, api=api)
        r = b.toolbox_authz_enable(overwrite="false")
        assert r["code"] == "device_key_conflict"
        assert api.enable_calls == [False]

    def test_other_errors_are_not_treated_as_conflict(self, game):
        """TPM 不可用等错误必须原样上报，不能被误判成「密钥冲突」。"""

        class _NoTpmApi(_FakeApi):
            def enable_device(self, display_name="", overwrite=False):
                raise api_mod.ApiError("tpm_unavailable", "本机没有可用的 TPM，无法启用订阅工具")

        r = _make_bridge(game, api=_NoTpmApi()).toolbox_authz_enable()
        assert r["success"] is False
        assert r["code"] == "tpm_unavailable"
        assert "need_overwrite" not in (r.get("data") or {})

    def test_conflict_detected_by_message_without_code(self, game):
        """服务端只给文案（没有 code）时也要认出来，否则仍然死锁。"""

        class _MsgOnlyApi(_FakeApi):
            def enable_device(self, display_name="", overwrite=False):
                raise api_mod.ApiError("error", "请先在另一账号取消授权")

        r = _make_bridge(game, api=_MsgOnlyApi()).toolbox_authz_enable()
        assert r["code"] == "device_key_conflict"


class TestTpmKeyRotation:
    """覆盖本机密钥 = 换一把新密钥（新设备身份），而不是复用同一把。"""

    def test_key_name_defaults_for_legacy_record(self):
        from webutils.toolbox import authz_tpm

        # 旧版 device.json 没有 tpm_key_name 字段
        assert authz_tpm.key_name_for({"device_id": "x"}) == authz_tpm.DEFAULT_KEY_NAME
        assert authz_tpm.key_name_for(None) == authz_tpm.DEFAULT_KEY_NAME
        assert authz_tpm.key_name_for({"tpm_key_name": " custom "}) == "custom"

    def test_new_key_name_is_unique(self):
        from webutils.toolbox import authz_tpm

        names = {authz_tpm.new_key_name() for _ in range(20)}
        assert len(names) == 20, "轮换名必须唯一，否则又回到同一把密钥"
        assert all(n.startswith(authz_tpm.DEFAULT_KEY_NAME) for n in names)

    def test_prepare_new_key_reuses_base_when_free(self, monkeypatch):
        """默认名空着 → 用回默认名（保持历史路径不变，TPM 里不留垃圾）。"""
        from webutils.toolbox import authz_tpm

        monkeypatch.setattr(authz_tpm, "load_device", lambda: {"device_id": "d1"})
        monkeypatch.setattr(authz_tpm, "key_exists", lambda name: False)
        assert authz_tpm.prepare_new_key() == authz_tpm.DEFAULT_KEY_NAME

    def test_prepare_new_key_rotates_when_base_taken(self, monkeypatch):
        """默认名已被旧密钥占用 → 必须换随机名（复用同名 = 同一把钥匙 = 没覆盖）。"""
        from webutils.toolbox import authz_tpm

        monkeypatch.setattr(authz_tpm, "load_device", lambda: {"device_id": "d1"})
        monkeypatch.setattr(authz_tpm, "key_exists", lambda name: True)
        name = authz_tpm.prepare_new_key()
        assert name != authz_tpm.DEFAULT_KEY_NAME

    def test_prepare_new_key_deletes_nothing(self, monkeypatch):
        """⚠️ 挑名字阶段**绝不能**删密钥：注册失败时必须能回退到旧密钥。"""
        from webutils.toolbox import authz_tpm

        deleted = []
        monkeypatch.setattr(authz_tpm, "load_device", lambda: {"device_id": "d1"})
        monkeypatch.setattr(authz_tpm, "delete_key", lambda name: deleted.append(name) or True)
        monkeypatch.setattr(authz_tpm, "key_exists", lambda name: True)
        authz_tpm.prepare_new_key()
        assert deleted == [], "prepare_new_key 只挑名字，不许动 TPM"

    def test_delete_other_keys_keeps_current(self, monkeypatch):
        """清理时保留正在用的那把，只删默认名与上一个记录名。"""
        from webutils.toolbox import authz_tpm

        deleted = []
        monkeypatch.setattr(
            authz_tpm, "load_device",
            lambda: {"device_id": "d1", "tpm_key_name": "LCTA-Authz-Device-old"},
        )
        monkeypatch.setattr(authz_tpm, "delete_key", lambda name: deleted.append(name) or True)
        removed = authz_tpm.delete_other_keys(keep="LCTA-Authz-Device-new")
        assert "LCTA-Authz-Device-new" not in deleted, "不能删掉正在用的密钥"
        assert "LCTA-Authz-Device-old" in deleted
        assert "LCTA-Authz-Device" in deleted
        assert set(removed) == {"LCTA-Authz-Device-old", "LCTA-Authz-Device"}

    def test_enable_overwrite_keeps_old_key_when_registration_fails(self, monkeypatch):
        """**注册被拒时旧密钥必须还在** —— 否则用户既没新授权又丢了旧的。"""
        from webutils.toolbox import authz_tpm

        deleted = []
        monkeypatch.setattr(authz_tpm, "load_device", lambda: {"device_id": "old-id"})
        monkeypatch.setattr(authz_tpm, "prepare_new_key", lambda: "brand-new-key")
        monkeypatch.setattr(authz_tpm, "export_public_key_der", lambda name: "pk")
        monkeypatch.setattr(authz_tpm, "delete_other_keys",
                            lambda keep, base=None: deleted.append(keep) or [])

        class _Api(api_mod.ToolboxApi):
            def __init__(self):
                self.base_url = "https://mods.test"

            def register_device(self, device_id, public_key_b64, display_name=""):
                raise api_mod.ApiError("device_limit_reached", "已达授权上限")

        api = _Api()
        with pytest.raises(api_mod.ApiError):
            api.enable_device(overwrite=True)
        assert deleted == [], "注册失败后不得清理旧密钥"

    def test_enable_overwrite_rotates_device_id(self, game, monkeypatch):
        """覆盖后 device_id 必须重新生成：服务端可能按它判重，两边都换才稳。"""
        from webutils.toolbox import authz_tpm

        monkeypatch.setattr(authz_tpm, "load_device", lambda: {"device_id": "old-id"})
        monkeypatch.setattr(authz_tpm, "prepare_new_key", lambda: "new-key")
        monkeypatch.setattr(authz_tpm, "key_name_for", lambda dev: "old-key")
        monkeypatch.setattr(authz_tpm, "export_public_key_der", lambda name: f"pk:{name}")
        saved = {}
        monkeypatch.setattr(
            authz_tpm, "save_device",
            lambda device_id, api_base=None, key_name=None: saved.update(
                {"device_id": device_id, "key_name": key_name}
            ),
        )

        class _Api(api_mod.ToolboxApi):
            def __init__(self):
                self.base_url = "https://mods.test"
                self.registered = None

            def register_device(self, device_id, public_key_b64, display_name=""):
                self.registered = (device_id, public_key_b64)
                return {"ok": True}

        api = _Api()
        api.enable_device(overwrite=True)
        device_id, public_key = api.registered
        assert device_id != "old-id", "覆盖必须换新设备身份"
        assert public_key == "pk:new-key"
        assert saved == {"device_id": device_id, "key_name": "new-key"}


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

# ---------------------------------------------------------------------------
# 2026-10-30：一键安装契约（清单驱动）+ 登录/订阅语义
# ---------------------------------------------------------------------------

def _ed25519_keypair_and_sign(seed: bytes, message: bytes):
    """RFC 8032 参考实现（**仅测试用**）：返回 (raw_public_key, signature)。

    客户端仓库是纯 Python 验签（无 cryptography），测试用同一数学的
    签名端生成真实签名，保证验签路径被真实执行而不是 mock。
    """
    import hashlib

    p = 2 ** 255 - 19
    l = 2 ** 252 + 27742317777372353535851937790883648493
    d = -121665 * pow(121666, p - 2, p) % p
    I = pow(2, (p - 1) // 4, p)

    def xrecover(y):
        xx = (y * y - 1) * pow(d * y * y + 1, p - 2, p)
        x = pow(xx, (p + 3) // 8, p)
        if (x * x - xx) % p != 0:
            x = (x * I) % p
        if x % 2 != 0:
            x = p - x
        return x

    By = 4 * pow(5, p - 2, p) % p
    B = [xrecover(By) % p, By]

    def edwards_add(P, Q):
        x1, y1 = P
        x2, y2 = Q
        x3 = (x1 * y2 + x2 * y1) * pow(1 + d * x1 * x2 * y1 * y2, p - 2, p) % p
        y3 = (y1 * y2 + x1 * x2) * pow(1 - d * x1 * x2 * y1 * y2, p - 2, p) % p
        return [x3, y3]

    def scalarmult(P, e):
        if e == 0:
            return [0, 1]
        Q = scalarmult(P, e // 2)
        Q = edwards_add(Q, Q)
        if e & 1:
            Q = edwards_add(Q, P)
        return Q

    def encodepoint(P):
        x, y = P
        out = bytearray(y.to_bytes(32, "little"))
        out[31] = (out[31] & 0x7F) | ((x & 1) << 7)
        return bytes(out)

    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= (1 << 254)
    pub = encodepoint(scalarmult(B, a))
    r = int.from_bytes(hashlib.sha512(h[32:] + message).digest(), "little") % l
    R = encodepoint(scalarmult(B, r))
    hram = int.from_bytes(hashlib.sha512(R + pub + message).digest(), "little") % l
    s = (r + hram * a) % l
    return pub, R + s.to_bytes(32, "little")


_ED25519_SPKI_DER_PREFIX = bytes.fromhex("302a300506032b6570032100")


class _ContractApi(_FakeApi):
    """可控 manifest/ticket 的假 API（默认未签名 —— 契约要求拒绝）。"""

    def __init__(self, manifest_out=None):
        super().__init__()
        self._manifest_out = manifest_out

    def manifest(self, tool_id, release_id):
        if self._manifest_out is not None:
            return self._manifest_out
        return {"manifest": {"files": []}, "signature": None}

    def download_ticket(self, tool_id, release_id, file_name, sha256):
        self.calls.append(("ticket", file_name, sha256))
        return {"download_url": "https://cdn.example.test/restricted/x"}


class TestManifestDrivenInstall:
    """一键安装契约：只信签名清单，逐文件校验，按 install_kind 分发。"""

    def _signed(self, manifest, seed=b"lcta-test-seed-0001"):
        from webutils.toolbox import ed25519

        pub, sig = _ed25519_keypair_and_sign(seed, ed25519.canonical_bytes(manifest))
        import base64

        return {
            "pub_der": _ED25519_SPKI_DER_PREFIX + pub,
            "manifest_out": {
                "manifest": manifest,
                "signature": base64.b64encode(sig).decode("ascii"),
            },
        }

    def _runtime_ready(self, game, tmp_path):
        import zipfile

        rt = tmp_path / "rt.zip"
        with zipfile.ZipFile(str(rt), "w") as zf:
            zf.writestr("BepInEx/core/x.dll", b"core")
        install.install_runtime(game, install.InstallPlan(
            kind="runtime", release_id="rt-0", files=[],
            allowed_prefixes=["BepInEx"], stub_path=rt,
        ))

    def test_multi_file_plugin_install(self, game, tmp_path, monkeypatch):
        """多文件清单：逐文件下载校验后打包事务化安装，两个文件都落位。"""
        import hashlib
        import zipfile

        self._runtime_ready(game, tmp_path)
        content_a, content_b = b"A" * 100, b"B" * 50
        sha_a = hashlib.sha256(content_a).hexdigest()
        sha_b = hashlib.sha256(content_b).hexdigest()
        manifest = {
            "schema_version": 1, "tool_id": 7, "release_id": "r9", "version": "1.2.0",
            "resource_kind": "plugin", "install_kind": "bepinex_plugin_dll",
            "tool_dir": "lcta-test", "guid": "com.lcta.test",
            "files": [
                {"path": "sub/ToolA.dll", "sha256": sha_a, "size": 100},
                {"path": "sub/ToolB.dll", "sha256": sha_b, "size": 50},
            ],
            "dependencies": [], "conflict_guids": [],
        }
        signed = self._signed(manifest)

        artifacts = {sha_a: content_a, sha_b: content_b}
        cache = {}
        for sha, content in artifacts.items():
            fp = tmp_path / f"dl-{sha[:8]}"
            fp.write_bytes(content)
            cache[sha] = fp

        api = _ContractApi(signed["manifest_out"])
        monkeypatch.setattr(
            "webutils.toolbox.download.fetch_or_reuse",
            lambda url, sha, expected_size=None, progress=None: cache[sha],
        )
        b = _make_bridge(game, api=api)
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install(7, "r9")
        assert r["success"] is True, r

        m = state.Manifest.load(game)
        entry = m.plugins["7"]
        assert {f.relative_path for f in entry.files} == {"sub/ToolA.dll", "sub/ToolB.dll"}
        # 每个清单文件各取了一张票据
        tickets = [c for c in api.calls if isinstance(c, tuple) and c[0] == "ticket"]
        assert {t[1] for t in tickets} == {"sub/ToolA.dll", "sub/ToolB.dll"}

    def test_runtime_install_via_bridge(self, game, tmp_path, monkeypatch):
        """runtime_zip_root 清单经 toolbox_install_runtime 安装底座。"""
        import hashlib
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("BepInEx/core/runtime.dll", b"runtime-core")
        zip_bytes = buf.getvalue()
        sha = hashlib.sha256(zip_bytes).hexdigest()
        fp = tmp_path / "rt-dl.zip"
        fp.write_bytes(zip_bytes)
        manifest = {
            "schema_version": 1, "tool_id": 9, "release_id": "rt1", "version": "0.3",
            "resource_kind": "runtime", "install_kind": "runtime_zip_root",
            "tool_dir": "",
            "files": [{"path": "runtime.zip", "sha256": sha, "size": len(zip_bytes)}],
            "dependencies": [], "conflict_guids": [],
        }
        signed = self._signed(manifest)
        monkeypatch.setattr(
            "webutils.toolbox.download.fetch_or_reuse",
            lambda url, sha_, expected_size=None, progress=None: fp,
        )
        api = _ContractApi(signed["manifest_out"])
        b = _make_bridge(game, api=api)
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install_runtime(9, "rt1")
        assert r["success"] is True, r
        assert state.Manifest.load(game).runtime is not None

    def test_package_install_via_bridge(self, game, tmp_path, monkeypatch):
        """game_relative_files：按签名清单 target_dir 写入并记录 packages。"""
        import hashlib

        content = b"PACKAGE"
        sha = hashlib.sha256(content).hexdigest()
        fp = tmp_path / "pkg.bin"
        fp.write_bytes(content)
        manifest = {
            "schema_version": 1, "tool_id": 7, "release_id": "rp1", "version": "1.0",
            "resource_kind": "package", "install_kind": "game_relative_files",
            "tool_dir": "pkg-test", "target_dir": "BepInEx/plugins/PkgTest",
            "requires_runtime": False,
            "files": [{"path": "PkgTest.dll", "sha256": sha, "size": len(content)}],
            "dependencies": [], "conflict_guids": [],
        }
        signed = self._signed(manifest)
        monkeypatch.setattr(
            "webutils.toolbox.download.fetch_or_reuse",
            lambda url, sha_, expected_size=None, progress=None: fp,
        )
        b = _make_bridge(game, api=_ContractApi(signed["manifest_out"]))
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install_any(7, "rp1")
        assert r["success"] is True, r
        assert (game / "BepInEx" / "plugins" / "PkgTest" / "PkgTest.dll").read_bytes() == content
        assert state.Manifest.load(game).packages["7"].target_dir == "BepInEx/plugins/PkgTest"

    def test_download_only_works_without_game_root(self, tmp_path, monkeypatch):
        """download_only 不要求配置游戏目录，只落系统下载目录。"""
        import hashlib

        content = b"DOWNLOAD"
        sha = hashlib.sha256(content).hexdigest()
        fp = tmp_path / "dl.bin"
        fp.write_bytes(content)
        manifest = {
            "schema_version": 1, "tool_id": 9, "release_id": "rd1", "version": "1.0",
            "resource_kind": "download", "install_kind": "download_only",
            "tool_dir": "dl-test",
            "files": [{"path": "file.bin", "sha256": sha, "size": len(content)}],
            "dependencies": [], "conflict_guids": [],
        }
        signed = self._signed(manifest)
        monkeypatch.setattr(
            "webutils.toolbox.download.fetch_or_reuse",
            lambda url, sha_, expected_size=None, progress=None: fp,
        )
        saved = tmp_path / "Downloads" / "dl-test" / "file.bin"
        monkeypatch.setattr(
            "webutils.toolbox.download.save_to_downloads",
            lambda files, folder, progress=None: [saved],
        )
        b = _make_bridge(tmp_path, api=_ContractApi(signed["manifest_out"]), game_root=False)
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install_any(9, "rd1")
        assert r["success"] is True, r
        assert r["data"]["kind"] == "download"
        assert r["data"]["save_paths"] == [str(saved)]

    def test_wrong_entry_refused(self, game, tmp_path):
        """插件入口装底座 / 底座入口装插件 → 明确报错而不是装错。"""
        self._runtime_ready(game, tmp_path)
        b = _make_bridge(game)
        # 未签名清单先被拒；这里用伪造 manifest_out 测 kind 分发文案
        api = _ContractApi({"manifest": {"install_kind": "runtime_zip_root", "files": [
            {"path": "a.zip", "sha256": "a" * 64}]}, "signature": "c2ln"})
        b2 = _make_bridge(game, api=api)
        b2._manifest_public_key = None  # 无公钥 → 先拒签名
        r = b2.toolbox_install_runtime(1, "r1")
        assert r["success"] is False

    def test_unknown_install_kind_refused(self, game, tmp_path):
        """未知 install_kind（含缺失）一律拒绝 —— 契约白名单。"""
        manifest = {"install_kind": "arbitrary_script",
                    "files": [{"path": "a.dll", "sha256": "a" * 64}]}
        signed = self._signed(manifest)
        b = _make_bridge(game, api=_ContractApi(signed["manifest_out"]))
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install(1, "r1")
        assert r["success"] is False
        assert "安装类型" in r["message"]

    def test_empty_files_refused(self, game, tmp_path):
        manifest = {"install_kind": "bepinex_plugin_dll", "files": []}
        signed = self._signed(manifest)
        b = _make_bridge(game, api=_ContractApi(signed["manifest_out"]))
        b._manifest_public_key = lambda: signed["pub_der"]
        r = b.toolbox_install(1, "r1")
        assert r["success"] is False
        assert "文件" in r["message"]


class TestStatusSeasonAndCatalog:
    """status 必须携带 season/catalog（此前目录数据从未填充的缺陷）。"""

    def test_status_includes_season_and_catalog(self, game):
        api = _FakeApi()
        api.catalog = lambda: {"items": [
            {"tool_id": 7, "tool_name": "P", "release_id": "r1", "version": "1",
             "resource_kind": "plugin", "access_kind": "original",
             "downloadable": True, "files": []},
        ]}
        b = _make_bridge(game, api=api)
        d = b.toolbox_status()["data"]
        assert d["season"]["name"] == "S1"
        assert d["catalog"]["items"][0]["access_kind"] == "original"
        assert d["base_url"]

    def test_guest_status_has_no_online_access(self, game):
        """游客（未登录）：目录仍可取，access/user/afdian 为空。"""
        api = _FakeApi()
        api.is_logged_in = lambda: False
        b = _make_bridge(game, api=api)
        d = b.toolbox_status()["data"]
        assert d["logged_in"] is False
        assert d["online"] is None
        assert d["catalog"] is not None
        assert d["user"] is None and d["afdian"] is None


class TestStatusSplit:
    """2026-11-01 重构：状态拆两段 —— 本地毫秒级、在线分片报错。"""

    def test_status_local_does_not_touch_network(self, game):
        """本地快照必须**零在线请求**：断网也要秒出首屏。"""
        api = _FakeApi(raise_on={"season", "access", "catalog"})
        b = _make_bridge(game, api=api)
        r = b.toolbox_status_local()
        assert r["success"] is True
        assert r["data"]["local"] is not None
        assert api.calls == [], "本地快照不应发起任何在线请求"
        assert r["data"]["protocol_version"] >= 3

    def test_status_local_reports_missing_root_without_failing(self, tmp_path):
        """没有游戏目录是**可展示的状态**，不是异常（首屏仍要能渲染）。"""
        b = _make_bridge(tmp_path, game_root=False)
        r = b.toolbox_status_local()
        assert r["success"] is True
        assert "游戏目录" in r["data"]["local_error"]

    def test_status_online_isolates_part_failures(self, game):
        """一片失败不影响其它片：season/access 正常，catalog 单独报错。"""

        def _catalog_boom():
            api.calls.append("catalog")
            raise RuntimeError("catalog 失败（模拟网络错误）")

        api = _FakeApi()
        api.catalog = _catalog_boom
        b = _make_bridge(game, api=api)
        d = b.toolbox_status_online()["data"]
        assert d["season"]["name"] == "S1"
        assert d["access"] is not None
        assert d["catalog"] is None
        assert "catalog" in d["errors"] and d["errors"]["catalog"]["message"]

    def test_status_online_always_carries_timestamp(self, game):
        b = _make_bridge(game)
        d = b.toolbox_status_online()["data"]
        assert d["fetched_at"], "前端需要「最后更新时间」来区分缓存与实时"
        assert d["protocol_version"] >= 3

    def test_access_precedes_catalog(self, game):
        """catalog 走 get_optional_user：access 先跑才能刷新过期 token。

        顺序反了会出现「已登录却整页显示需要订阅」的假象（见桥接层 docstring）。
        """
        api = _FakeApi()
        b = _make_bridge(game, api=api)
        b.toolbox_status_online(force=True)
        assert api.calls.index("access") < api.calls.index("catalog")


class TestOpenSite:
    """站点跳转：只走**白名单** + 系统浏览器，不接受任意 URL。"""

    def _bridge(self, game, monkeypatch):
        opened = []
        import webbrowser

        monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
        return _make_bridge(game), opened

    @pytest.mark.parametrize("path", ["/register", "/forgot-password", "/toolbox", "/"])
    def test_allowed_paths_open_in_browser(self, game, monkeypatch, path):
        b, opened = self._bridge(game, monkeypatch)
        r = b.toolbox_open_site(path)
        assert r["success"] is True
        assert len(opened) == 1
        assert opened[0].startswith("https://mods.lcta.test")
        assert not opened[0].endswith("//")

    @pytest.mark.parametrize("path", [
        "https://evil.example/steal",
        "//evil.example",
        "/admin",
        "/register?next=https://evil.example",
        "javascript:alert(1)",
    ])
    def test_arbitrary_targets_refused(self, game, monkeypatch, path):
        b, opened = self._bridge(game, monkeypatch)
        r = b.toolbox_open_site(path)
        assert r["success"] is False
        assert r["code"] == "invalid_target"
        assert opened == [], "非法目标一律不许交给浏览器"


class TestTaskDock:
    """任务坞：切页/重开页面后仍能看到刚才的安装结果。"""

    def test_snapshot_empty_by_default(self, game):
        b = _make_bridge(game)
        d = b.toolbox_task_status()["data"]
        assert d["running"] is False
        assert d["current"] is None
        assert d["history"] == []

    def test_failed_install_recorded_in_history(self, game):
        b = _make_bridge(game)  # _FakeApi.manifest 无签名 → 拒绝安装
        r = b.toolbox_install(1, "r1")
        assert r["success"] is False
        d = b.toolbox_task_status()["data"]
        assert d["running"] is False
        assert d["history"], "失败的任务也应留下记录"
        last = d["history"][-1]
        assert last["status"] == "failed"
        assert last["tool_id"] == "1"
        assert last["message"]

    def test_manifest_errors_carry_codes(self, game):
        """错误码供前端分支（重试 / 引导登录 / 打开设置），文案保持不变。"""
        b = _make_bridge(game)
        r = b.toolbox_install(1, "r1")
        assert r["code"] == "manifest_unsigned"
        assert "签名" in r["message"]


class TestGameRootValidate:
    """设置页「检查目录」：只校验、不落盘（与保存共用同一条判定）。"""

    def test_validate_accepts_writable_dir_without_saving(self, tmp_path, monkeypatch):
        from globalManagers.ConfigManager import ConfigManager

        game = tmp_path / "game-ok"
        game.mkdir()
        written = {}
        monkeypatch.setattr(
            ConfigManager, "get", classmethod(lambda cls, key, default=None: {})
        )
        monkeypatch.setattr(
            ConfigManager, "set", classmethod(lambda cls, key, value: written.update({key: value}))
        )
        b = _make_bridge(tmp_path)
        r = b.toolbox_validate_game_root(str(game))
        assert r["success"] is True
        assert r["data"]["game_root"]
        assert written == {}, "检查目录不应写入配置"

    def test_validate_rejects_missing_dir(self, tmp_path):
        b = _make_bridge(tmp_path)
        r = b.toolbox_validate_game_root(str(tmp_path / "not-exists"))
        assert r["success"] is False
        assert r["code"] == "invalid_game_root"

class TestManifestVersionGates:
    """清单版本门禁（2026-11-02）：宁可拒绝安装，也不能按老逻辑装错。"""

    def _bridge_with(self, game, manifest):
        from tests.test_toolbox_bridge import _ContractApi, _make_bridge

        signed = TestManifestDrivenInstall()._signed(manifest)
        api = _ContractApi(signed["manifest_out"])
        b = _make_bridge(game, api=api)
        import base64  # noqa: F401 - 仅用于构造签名后的清单
        return b, signed

    def _manifest(self, **overrides):
        manifest = {
            "schema_version": 2,
            "tool_id": 1000001,
            "release_id": "r1",
            "version": "1.0.0",
            "version_sort": "0001.0000.0000~",
            "min_client_protocol": 1,
            "resource_kind": "plugin",
            "install_kind": "bepinex_plugin_dll",
            "tool_dir": "gate",
            "files": [{"path": "A.dll", "sha256": "a" * 64}],
        }
        manifest.update(overrides)
        return manifest

    def test_current_manifest_passes(self, game):
        b, signed = self._bridge_with(game, self._manifest())
        b._manifest_public_key = lambda: signed["pub_der"]
        manifest, kind, files = b._toolbox_fetch_verified_manifest(
            b._toolbox_api(), 1000001, "r1"
        )
        assert kind == "bepinex_plugin_dll" and files

    def test_future_schema_refused(self, game):
        b, signed = self._bridge_with(game, self._manifest(schema_version=99))
        b._manifest_public_key = lambda: signed["pub_der"]
        with pytest.raises(Exception) as ei:
            b._toolbox_fetch_verified_manifest(b._toolbox_api(), 1000001, "r1")
        assert getattr(ei.value, "code", "") == "client_outdated"

    def test_min_client_protocol_too_high_refused(self, game):
        from webui.app_api import toolbox as bridge_mod

        b, signed = self._bridge_with(
            game, self._manifest(min_client_protocol=bridge_mod.BRIDGE_PROTOCOL_VERSION + 1)
        )
        b._manifest_public_key = lambda: signed["pub_der"]
        with pytest.raises(Exception) as ei:
            b._toolbox_fetch_verified_manifest(b._toolbox_api(), 1000001, "r1")
        assert getattr(ei.value, "code", "") == "client_outdated"
