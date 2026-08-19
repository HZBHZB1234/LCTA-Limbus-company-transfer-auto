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

    def set_main_window(self, window) -> None:
        """绑定 LCTA 主窗口 webview 对象（下载请求转发目标）。"""
        self._main_window = window

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

    def modMirrorRequest(self, msg) -> dict:
        """校验来源后转发到主窗口（evaluate_js 派发自定义事件）。"""
        try:
            if not isinstance(msg, dict) or msg.get("source") != "lcta-mod-mirror":
                return {"ok": False, "message": "无效的请求来源"}
            if self._main_window is None:
                return {"ok": False, "message": "主窗口不可用"}
            detail = json.dumps({"payload": msg.get("payload") or {}}, ensure_ascii=False)
            js = (
                "window.dispatchEvent(new CustomEvent('lcta-mod-download', "
                f"{{detail: {detail}}}));"
            )
            self._main_window.evaluate_js(js)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}
