"""
tests/test_plugin_window.py
通用插件独立窗口（pw_open / PluginWindowAPI / CheatPluginHost.find_window）测试。

覆盖：
- find_window：命中 / 未知 id / 未解锁（空注册）短路
- PluginWindowAPI.pw_get_bootstrap：正常返回 {title, theme, js}、未解锁、文件缺失
- PluginWindowAPI.pw_invoke：白名单分发信封、锁定与非法动作区分
- pw_open：解锁 + 同意门控 + 窗口创建/跟踪/关闭清理（webview 打桩）
"""

import re
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from webutils.cheat_plugins import CheatPluginHost
import webui.plugin_window_api as pwa
import webui.app_api.cheat_core as cheat_core_api


FAKE_PLUGIN = {
    "id": "cheat",
    "name": "作弊工具箱",
    "entry": "cheat_damage_hook",
    "manager": "CheatDamageHookManager",
    "api": ["get_status"],
    "managers": [],
    "webui": {"section": "cheat", "js": "cheat"},
    "windows": [{
        "id": "staticmod-editor",
        "title": "LCTA - 静态数据编辑器",
        "js": "windows/staticmod-editor.js",
        "width": 1360,
        "height": 860,
    }],
    "launcher": {"consent": "cheat", "enabled_key": "launcher.work.cheat_damage"},
}


@pytest.fixture()
def registered_plugin():
    """注入已注册插件快照，结束后还原。"""
    old = list(CheatPluginHost._plugins)
    CheatPluginHost._plugins = [dict(FAKE_PLUGIN)]
    yield
    CheatPluginHost._plugins = old


@pytest.fixture()
def empty_registry():
    old = list(CheatPluginHost._plugins)
    CheatPluginHost._plugins = []
    yield
    CheatPluginHost._plugins = old


class FakeCM:
    store = {}

    def get(self, key, default=None):
        return FakeCM.store.get(key, default)

    def set(self, key, value, auto_save=True):
        FakeCM.store[key] = value


class _ClosedEvent:
    """模拟 pywebview 事件的 += 订阅语法。"""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def __isub__(self, fn):
        if fn in self.handlers:
            self.handlers.remove(fn)
        return self


class FakeWindow:
    def __init__(self):
        self.js_calls = []
        self.events = types.SimpleNamespace(closed=_ClosedEvent())

    def evaluate_js(self, js):
        self.js_calls.append(js)


class TestFindWindow:
    def test_found_and_defaults(self, registered_plugin):
        desc = CheatPluginHost.find_window("staticmod-editor")
        assert desc["title"] == "LCTA - 静态数据编辑器"
        assert desc["js"] == "windows/staticmod-editor.js"  # 相对解密目录 webui/
        assert desc["consent"] == "cheat"  # 从 launcher.consent 兜底

    def test_unknown_id_raises(self, registered_plugin):
        with pytest.raises(RuntimeError, match="未知插件窗口"):
            CheatPluginHost.find_window("no-such-window")

    def test_locked_short_circuit(self, empty_registry):
        with pytest.raises(RuntimeError, match="未解锁"):
            CheatPluginHost.find_window("staticmod-editor")


class TestBootstrapBridge:
    def test_bootstrap_ok(self, registered_plugin, monkeypatch, tmp_path):
        monkeypatch.setattr(pwa, "ConfigManager", FakeCM)
        FakeCM.store["theme"] = "dark"
        monkeypatch.setattr("webutils.cheat_core._read_webui_file",
                            lambda rel: "// feature js: " + rel)
        api = pwa.PluginWindowAPI("staticmod-editor")
        res = api.pw_get_bootstrap()
        assert res["success"]
        assert res["data"]["theme"] == "dark"
        assert res["data"]["title"].startswith("LCTA")
        assert "staticmod-editor" in res["data"]["js"]

    def test_bootstrap_locked(self, empty_registry, monkeypatch):
        monkeypatch.setattr(pwa, "ConfigManager", FakeCM)
        api = pwa.PluginWindowAPI("staticmod-editor")
        res = api.pw_get_bootstrap()
        assert not res["success"] and res["reason"] == "locked"

    def test_invoke_envelope(self, registered_plugin, monkeypatch):
        class FakeMgr:
            @classmethod
            def get_status(cls):
                return {"available": True}

        monkeypatch.setattr(CheatPluginHost, "_manager_specs",
                            classmethod(lambda cls, plugin: [("e", "m", ["get_status"])]))
        monkeypatch.setattr(CheatPluginHost, "_manager_class",
                            classmethod(lambda cls, plugin, entry=None, manager=None: FakeMgr))
        api = pwa.PluginWindowAPI("staticmod-editor")
        res = api.pw_invoke("get_status", [])
        assert res == {"success": True, "data": {"available": True}}

        bad = api.pw_invoke("not_in_whitelist", [])
        assert not bad["success"] and bad["reason"] == "invalid_action"

    def test_invoke_locked_reason(self, empty_registry):
        api = pwa.PluginWindowAPI("staticmod-editor")
        res = api.pw_invoke("get_status", [])
        assert not res["success"] and res["reason"] == "locked"


class DummyApi(cheat_core_api.CheatCoreMixin):
    def __init__(self):
        self.errors = []

    def log_error(self, e):  # CoreMixin 最小桩
        self.errors.append(e)


class TestPwOpen:
    @pytest.fixture()
    def shell_html(self, tmp_path, monkeypatch):
        webui_dir = tmp_path / "webui"
        webui_dir.mkdir()
        (webui_dir / "plugin-window.html").write_text("<html></html>", encoding="utf-8")
        monkeypatch.setenv("path_", str(tmp_path))

    @pytest.fixture()
    def unlocked(self, monkeypatch):
        from webutils import cheat_core
        monkeypatch.setattr(cheat_core, "ensure_unlocked",
                            lambda: {"success": True, "reason": "unlocked"})
        monkeypatch.setattr(cheat_core_api, "ConfigManager", FakeCM)
        FakeCM.store["cheat.disclaimer_accepted"] = True
        yield
        FakeCM.store.clear()

    @pytest.fixture()
    def fake_webview(self, monkeypatch):
        created = []

        import types
        fake = types.SimpleNamespace(
            FileDialog=types.SimpleNamespace(FOLDER=3, OPEN=1, SAVE=2),
            create_window=lambda *a, **k: created.append(FakeWindow()) or created[-1],
        )
        monkeypatch.setitem(sys.modules, "webview", fake)
        return created

    def test_open_creates_and_tracks_window(self, registered_plugin, unlocked,
                                            shell_html, fake_webview):
        dummy = DummyApi()
        res = dummy.pw_open("staticmod-editor")
        assert res["success"]
        assert len(fake_webview) == 1
        assert len(dummy._plugin_windows) == 1

        # 主题注入已执行
        win = fake_webview[0]
        if not any("applyTheme" in js or "theme-" in js for js in win.js_calls):
            print("DEBUG errors:", dummy.errors, "js_calls:", win.js_calls)
        assert any("applyTheme" in js or "theme-" in js for js in win.js_calls)

        # 关闭回调清理跟踪
        for handler in win.events.closed.handlers:
            handler()
        assert dummy._plugin_windows == []

    def test_open_requires_consent(self, registered_plugin, shell_html, fake_webview,
                                   monkeypatch):
        from webutils import cheat_core
        monkeypatch.setattr(cheat_core, "ensure_unlocked",
                            lambda: {"success": True, "reason": "unlocked"})
        monkeypatch.setattr(cheat_core_api, "ConfigManager", FakeCM)
        FakeCM.store.clear()  # 未同意
        dummy = DummyApi()
        res = dummy.pw_open("staticmod-editor")
        assert not res["success"] and res["reason"] == "consent_required"
        assert not fake_webview

    def test_open_requires_unlock(self, registered_plugin, monkeypatch, tmp_path):
        from webutils import cheat_core
        monkeypatch.setattr(cheat_core, "ensure_unlocked",
                            lambda: {"success": False, "reason": "need_key"})
        dummy = DummyApi()
        res = dummy.pw_open("staticmod-editor")
        assert not res["success"] and res["reason"] == "need_key"

    def test_open_unknown_window(self, registered_plugin, unlocked, shell_html, fake_webview):
        dummy = DummyApi()
        res = dummy.pw_open("nope")
        assert not res["success"] and res["reason"] == "unknown_window"

    def test_sync_theme_pushes_to_windows(self, registered_plugin, unlocked,
                                          shell_html, fake_webview):
        dummy = DummyApi()
        assert dummy.pw_open("staticmod-editor")["success"]
        dummy.sync_theme_to_plugin_windows("purple")
        assert any("applyTheme('purple')" in js for js in fake_webview[0].js_calls)


class TestShellLayoutContract:
    """壳样式回归：#pw-root 必须是占满视口的 flex 列容器。

    功能页（rule-editor.css）约定 .rule-editor-container{flex:1} 直接挂在 body
    下；插件窗口壳多包了一层 #pw-root，若它不是 flex 容器，内部 flex:1 高度链
    全部失效 → 内容按 auto 高度溢出且 body overflow:hidden 截断，整窗无法滚动。
    """

    SHELL = Path(__file__).resolve().parents[1] / "webui" / "plugin-window.html"

    def test_pw_root_is_flex_column(self):
        html = self.SHELL.read_text(encoding="utf-8")
        m = re.search(r"#pw-root\s*\{([^}]*)\}", html)
        assert m, "plugin-window.html 缺少 #pw-root 规则"
        style = m.group(1)
        assert re.search(r"display:\s*flex", style), "#pw-root 须为 flex 容器"
        assert re.search(r"flex-direction:\s*column", style)
        assert re.search(r"min-height:\s*0", style)

    def test_body_clips_overflow(self):
        html = self.SHELL.read_text(encoding="utf-8")
        body_rules = re.findall(r"\bbody\s*\{([^}]*)\}", html)
        assert any("overflow: hidden" in r for r in body_rules), \
            "body 须 overflow:hidden（配合 #pw-root flex 链裁剪溢出内容）"
