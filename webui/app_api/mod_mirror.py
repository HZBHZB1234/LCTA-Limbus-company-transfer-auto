# -*- coding: utf-8 -*-
"""LCTA_API Mod 镜像站域：独立窗口打开 / 下载安装桥 / 状态查询。"""
from __future__ import annotations

import webview

from globalManagers.ConfigManager import ConfigManager
from webutils.function_mod_mirror import base_url, mod_mirror_request
from webui.app_api.exceptions import CancelRunning


class ModMirrorMixin:

    def open_mod_mirror(self):
        """打开 Mod 镜像站独立窗口（内嵌线上站点，登录态经桥持久化）。"""
        existing = getattr(self, "_mod_mirror_window", None)
        if existing is not None:
            try:
                existing.restore()
                existing.show()
                return {"success": True, "message": "Mod 镜像站已打开"}
            except Exception:
                self._mod_mirror_window = None

        from webui.mod_mirror_api import ModMirrorWindowAPI

        api = ModMirrorWindowAPI()
        window = webview.create_window(
            "LCTA - Mod 镜像站",
            url=f"{base_url()}/?embed=lcta",
            width=1280, height=860, resizable=True, text_select=True,
            js_api=api,
        )
        api.set_main_window(self._window)

        self._mod_mirror_window = window

        def clear_window_reference(*_args):
            if getattr(self, "_mod_mirror_window", None) is window:
                self._mod_mirror_window = None

        window.events.closed += clear_window_reference
        return {"success": True, "message": "Mod 镜像站已打开"}

    def mod_mirror_request(self, payload, modal_id="false"):
        """下载并安装镜像站标准版 / 下载普通文件到「下载」目录。"""
        try:
            return mod_mirror_request(payload, modal_id)
        except CancelRunning:
            self.log("mod 镜像站下载任务已取消")
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def mod_mirror_status(self):
        """前端初始化信息：站点地址 / mod 目录 / aria2c 可用性 / 已安装目录。"""
        from resource_updater.core import resolve_aria2_binary
        from webutils.packages.manage import get_mod_path

        return {
            "base_url": base_url(),
            "mod_path": str(get_mod_path()),
            "aria2_available": resolve_aria2_binary() is not None,
            "base_url_configurable": True,
        }

    def mod_mirror_set_base_url(self, url):
        """更新镜像站地址（空白恢复默认值）。"""
        url = (url or "").strip().rstrip("/")
        if not url:
            url = "https://mods.lcta.top"
        if not url.startswith(("http://", "https://")):
            return {"success": False, "message": "站点地址需以 http(s):// 开头"}
        cfg = ConfigManager().get("ui_default.mod_mirror", {}) or {}
        cfg["base_url"] = url
        ConfigManager().set("ui_default.mod_mirror", cfg)
        return {"success": True, "message": f"站点地址已更新为 {url}"}

    def mod_mirror_open_folder(self):
        """打开 mod 安装目录。"""
        from webutils.packages.manage import open_mod_path

        try:
            open_mod_path()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}