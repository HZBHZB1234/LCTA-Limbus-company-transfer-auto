from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import webview

from globalManagers.ConfigManager import ConfigManager
from product.launcher_session import LaunchSessionService


class LauncherWindowAPI:
    def __init__(self, service: LaunchSessionService, run_callable) -> None:
        self.service = service
        self.run_callable = run_callable
        self.window = None

    def set_window(self, window) -> None:
        self.window = window

    def get_launcher_session(self, session_id=None):
        return self.service.get_snapshot()

    def start_launcher_session(self, options=None):
        return self.service.start(self.run_callable)

    def cancel_launcher_session(self, session_id=None):
        return self.service.cancel()

    def close_launcher_window(self, mode="close"):
        if mode == "stop-game":
            self.service.terminate_game()
            self.service.cancel()
        elif mode == "cancel":
            self.service.cancel()
        if self.window is not None:
            self.window.destroy()
        return {"success": True}

    def open_main_window(self, target="home", context=None):
        root = Path(os.getenv("path_", "") or Path(__file__).resolve().parents[1])
        script = root / "start_webui.py"
        env = os.environ.copy()
        env["LCTA_START_TARGET"] = str(target or "home")
        if context:
            env["LCTA_START_CONTEXT"] = json.dumps(context, ensure_ascii=False)
        subprocess.Popen(
            [sys.executable, str(script), "--target", str(target or "home")],
            cwd=str(root),
            env=env,
        )
        return {"success": True}

    def get_theme(self):
        return ConfigManager().get("theme", "dark")


def run_launcher_webview(run_callable):
    root = Path(os.getenv("path_", "") or Path(__file__).resolve().parents[1])
    html_path = root / "webui" / "product" / "launcher.html"
    if not html_path.is_file():
        raise FileNotFoundError(f"Launcher WebView entry not found: {html_path}")

    service = LaunchSessionService()
    api = LauncherWindowAPI(service, run_callable)
    window = webview.create_window(
        "LCTA Launcher",
        url=str(html_path),
        width=920,
        height=680,
        min_size=(760, 560),
        resizable=True,
        text_select=True,
        js_api=api,
    )
    api.set_window(window)

    def dispatch(snapshot: Dict[str, Any]) -> None:
        if api.window is None:
            return
        payload = json.dumps(snapshot, ensure_ascii=False)
        try:
            api.window.run_js(
                "window.dispatchEvent(new CustomEvent('lcta:launcher-session-changed', "
                f"{{ detail: {payload} }}));"
            )
        except Exception:
            pass

    def on_closed(*_args) -> None:
        snapshot = service.get_snapshot()
        if snapshot["state"] in {"running", "cancelling"}:
            service.cancel()

    service.set_listener(dispatch)
    window.events.closed += on_closed
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    webview.start(debug=ConfigManager().get("debug", False), http_server=True)
