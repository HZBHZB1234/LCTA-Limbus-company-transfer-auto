# -*- coding: utf-8 -*-
"""Mod 镜像站独立窗口桥（js_api）。

站点页面（https://mods.lcta.top/?embed=lcta）内嵌于 pywebview 独立窗口，
页面 JS 通过 `window.pywebview.api` 调用本类：

- modMirrorBridge(action, data)：登录态持久化 —— 站点 localStorage 的
  access_token / refresh_token / user 经此桥写入 LCTA config.json
  （ui_default.mod_mirror.auth），页面加载时再经 get-auth 恢复，
  实现登录状态跨窗口/跨程序会话持久化。
- modMirrorRequest(msg)：下载请求转发 —— 经主窗口 evaluate_js 派发
  `lcta-mod-download` 事件，由主窗口 SPA 弹出进度模态窗并执行 aria2 下载+安装。
"""
from __future__ import annotations

import json


class ModMirrorWindowAPI:

    def __init__(self):
        self._main_window = None
        self._main_api = None

    def set_main_window(self, window) -> None:
        """绑定 LCTA 主窗口 webview 对象（下载请求转发目标）。"""
        self._main_window = window

    def set_main_api(self, api) -> None:
        """绑定 LCTA_API（同进程），供订阅工具状态/登录同步复用。"""
        self._main_api = api

    # ==================== 站点 → 宿主：登录态持久化 ====================

    def modMirrorBridge(self, action: str, data: dict | None = None) -> dict:
        """get-auth / save-auth / clear-auth。"""
        from webutils.function_mod_mirror import (
            mod_mirror_get_auth,
            mod_mirror_save_auth,
        )
        if action == "get-auth":
            return mod_mirror_get_auth() or {}
        if action in ("save-auth", "clear-auth"):
            mod_mirror_save_auth(data if action == "save-auth" else None)
            return {"ok": True}
        return {"ok": False, "message": f"未知操作: {action}"}

    # ==================== 站点 → 宿主：下载/安装 ====================

    def _forward_event(self, event_name: str, payload: dict) -> dict:
        if self._main_window is None:
            return {"ok": False, "message": "主窗口不可用"}
        detail = json.dumps({"payload": payload}, ensure_ascii=False)
        js = (
            f"window.dispatchEvent(new CustomEvent({json.dumps(event_name)}, "
            f"{{detail: {detail}}}));"
        )
        self._main_window.evaluate_js(js)
        return {"ok": True}

    def modMirrorRequest(self, msg) -> dict:
        """校验来源后转发到主窗口（evaluate_js 派发自定义事件）。"""
        try:
            if not isinstance(msg, dict) or msg.get("source") != "lcta-mod-mirror":
                return {"ok": False, "message": "无效的请求来源"}
            return self._forward_event("lcta-mod-download", msg.get("payload") or {})
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}

    # ==================== 订阅工具：状态 / 登录 / 安装 ====================

    def toolboxStatus(self) -> dict:
        """返回订阅工具在 LCTA 宿主侧的登录/游戏目录/运行状态。"""
        try:
            from globalManagers.ConfigManager import ConfigManager
            from webutils.toolbox import api as toolbox_api
            from webutils.toolbox import runtime

            cfg = ConfigManager().get("ui_default.toolbox", {}) or {}
            game_root = (cfg.get("game_root") if isinstance(cfg, dict) else "") or ""
            game_running = None
            if game_root:
                try:
                    game_running = runtime.is_game_running(game_root)
                except Exception:  # noqa: BLE001
                    game_running = None
            api = toolbox_api.ToolboxApi()
            return {
                "success": True,
                "data": {
                    "logged_in": api.is_logged_in(),
                    "game_root": game_root,
                    "game_running": game_running,
                    "base_url": api.base_url,
                },
            }
        except Exception as e:  # noqa: BLE001
            return {"success": False, "message": str(e)}

    def toolboxSyncLogin(self, force=False) -> dict:
        """把镜像站当前登录态同步为 LCTA 订阅工具会话（仅 access token）。"""
        try:
            if self._main_api is not None and hasattr(self._main_api, "toolbox_sync_mirror_login"):
                return self._main_api.toolbox_sync_mirror_login(force=bool(force))
            return {"success": False, "message": "主程序未就绪"}
        except Exception as e:  # noqa: BLE001
            return {"success": False, "message": str(e)}

    def toolboxInstallRequest(self, msg) -> dict:
        """站点请求安装/下载订阅工具：只接受 id 与动作，转发主窗口执行。

        网页不传 URL、目标路径或命令；主窗口会重新走签名清单/票据/哈希校验。
        """
        try:
            if not isinstance(msg, dict) or msg.get("source") != "lcta-mod-mirror":
                return {"ok": False, "message": "无效的请求来源"}
            payload = msg.get("payload") or {}
            if not isinstance(payload, dict):
                return {"ok": False, "message": "无效的请求参数"}
            action = str(payload.get("action") or "install")
            if action not in ("install", "download-file"):
                return {"ok": False, "message": f"不支持的订阅工具操作: {action}"}
            try:
                tool_id = int(payload.get("tool_id"))
            except (TypeError, ValueError):
                return {"ok": False, "message": "无效的工具 ID"}
            release_id = str(payload.get("release_id") or "")
            if not release_id or len(release_id) > 64 or not all(
                ch.isalnum() or ch in "._-" for ch in release_id
            ):
                return {"ok": False, "message": "无效的发布 ID"}
            clean = {
                "action": action,
                "tool_id": tool_id,
                "release_id": release_id,
                "tool_name": str(payload.get("tool_name") or "")[:255],
                "install_kind": str(payload.get("install_kind") or "")[:64],
                "modal_id": str(payload.get("modal_id") or "false")[:128],
            }
            if action == "download-file":
                clean["file_name"] = str(payload.get("file_name") or "")[:256]
                clean["sha256"] = str(payload.get("sha256") or "").lower()[:64]
            return self._forward_event("lcta-toolbox-install", clean)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}

    def toolboxOpenToolbox(self) -> dict:
        """把主窗口切到「订阅工具」页（未登录时引导用户登录）。"""
        try:
            if self._main_window is None:
                return {"ok": False, "message": "主窗口不可用"}
            self._main_window.evaluate_js("goAndShow('toolbox')")
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}

    def toolboxOpenDownloads(self) -> dict:
        """打开系统下载目录。"""
        try:
            if self._main_api is not None and hasattr(self._main_api, "toolbox_open_downloads"):
                return self._main_api.toolbox_open_downloads()
            return {"success": False, "message": "主程序未就绪"}
        except Exception as e:  # noqa: BLE001
            return {"success": False, "message": str(e)}
