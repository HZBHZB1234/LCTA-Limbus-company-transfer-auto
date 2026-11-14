"""
tests/test_start_webui_clr_guard.py
start_webui 启动期 CLR 初始化失败门禁回归测试。

历史 bug：ensure_clr() 失败后只打印/落盘便继续 main()，而 webview.start()
必然在 winforms 后端再崩一次，抛出的
"Failed to resolve Python.Runtime.Loader.Initialize"
把上面的真实原因（MOTW / 0x80131515 探针输出）盖住——用户与开发者
在日志里看到的都是这条无信息量报错，且打包版（无控制台）连界面都没有。

覆盖：
- CLR 失败：真实异常落盘、弹原生错误框、**不再**继续启动 WebUI
- CLR 成功：正常进入 webui.app.main()
- _append_app_log 写入 logs/app.log 失败时静默不抛错
"""
import sys
import types
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import start_webui


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


@pytest.fixture()
def fake_webui_app(monkeypatch):
    """注入假的 webui.app（避免真实 pywebview / CLR 导入链）。"""
    module = types.ModuleType("webui.app")
    recorder = _Recorder()
    module.main = recorder
    monkeypatch.setitem(sys.modules, "webui.app", module)
    return recorder


@pytest.fixture()
def startup_env(monkeypatch):
    """存档点：init_env / WebView2 预检 / 日志与弹窗副作用全部打桩。"""
    monkeypatch.setattr(start_webui, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(start_webui, "check_webview2_environment", lambda: True)
    log = _Recorder()
    dialog = _Recorder()
    monkeypatch.setattr(start_webui, "_append_app_log", log)
    monkeypatch.setattr(start_webui, "_fatal_startup_dialog", dialog)
    return {"log": log, "dialog": dialog}


def _install_fake_clr_bootstrap(monkeypatch, ensure_clr):
    """把 webutils.clr_bootstrap.ensure_clr 换成给定实现（不导入真实包）。"""
    parent = types.ModuleType("webutils")
    parent.__path__ = []
    bootstrap = types.ModuleType("webutils.clr_bootstrap")
    bootstrap.ensure_clr = ensure_clr
    monkeypatch.setitem(sys.modules, "webutils", parent)
    monkeypatch.setitem(sys.modules, "webutils.clr_bootstrap", bootstrap)


def test_clr_failure_aborts_startup(monkeypatch, startup_env, fake_webui_app):
    """CLR 初始化失败：落盘 + 弹框 + 直接返回，不再进入 webui.app.main。"""
    error = RuntimeError("pythonnet(netfx) 初始化失败: 0x80131515 不支持操作")

    def _ensure():
        raise error

    _install_fake_clr_bootstrap(monkeypatch, _ensure)

    assert start_webui.start_webui() is None

    assert fake_webui_app.calls == []
    assert startup_env["dialog"].calls, "CLR 失败必须给出可见提示"
    title, text = startup_env["dialog"].calls[0][0]
    assert "LCTA 启动失败" in title
    assert "logs/app.log" in text
    logged = "".join(call[0][0] for call in startup_env["log"].calls)
    assert "clr 初始化失败" in logged
    assert "0x80131515" in logged


def test_clr_success_continues_to_webui(monkeypatch, startup_env, fake_webui_app):
    """CLR 正常：继续启动 WebUI，不弹错误框。"""
    _install_fake_clr_bootstrap(monkeypatch, lambda: object())

    start_webui.start_webui()

    assert len(fake_webui_app.calls) == 1
    assert startup_env["dialog"].calls == []


def test_append_app_log_writes_file(tmp_path, monkeypatch):
    """真实日志写入：落到 cwd/logs/app.log。"""
    monkeypatch.chdir(tmp_path)
    assert start_webui._append_app_log("hello\n") is True
    target = tmp_path / "logs" / "app.log"
    assert target.read_text(encoding="utf-8") == "hello\n"
    # 追加而非覆盖
    assert start_webui._append_app_log("world\n") is True
    assert target.read_text(encoding="utf-8") == "hello\nworld\n"


def test_append_app_log_failure_is_silent(monkeypatch, tmp_path):
    """写入失败（如目录被占位文件挡住）返回 False 且不抛错。"""
    blocker = tmp_path / "logs"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert start_webui._append_app_log("x") is False
