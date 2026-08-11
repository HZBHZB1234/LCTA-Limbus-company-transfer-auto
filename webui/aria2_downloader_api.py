# -*- coding: utf-8 -*-
"""高速下载器独立窗口的 JS-API 桥接。

后端逻辑位于 webutils/function_aria2_downloader.py（模块级单例 aria2_manager）。
进度快照由后台轮询线程经 _push 分发到窗口 JS 的 __aria2DlDispatch 事件。
"""
import json
import os
from pathlib import Path

import webview

from globalManagers.ConfigManager import ConfigManager


def resolve_default_save_dir() -> str:
    """解析默认保存目录：优先系统真实「下载」目录（支持迁移后的已知文件夹）。"""
    try:
        from webutils.utils.shell import get_downloads_dir
        return get_downloads_dir()
    except Exception:
        return str(Path.home() / "Downloads")


class Aria2DownloaderAPI:
    """高速下载器窗口的 JS-API 桥接。"""

    def __init__(self):
        self._window = None
        self._snapshot_bound = False

    def set_window(self, window):
        self._window = window

    def get_config_value(self, key_path, default_value=None):
        return ConfigManager().get(key_path, default_value)

    def _push(self, payload: dict):
        if self._window is None:
            return
        try:
            serialized = json.dumps(payload, ensure_ascii=False)
            self._window.evaluate_js(
                f"window.__aria2DlDispatch && window.__aria2DlDispatch({serialized})"
            )
        except Exception:
            pass

    def log_error(self, exc):
        try:
            from globalManagers.LogManager import LogManager
            LogManager().log_error(exc)
        except Exception:
            pass

    def _bind_snapshot(self):
        from webutils import aria2_manager
        if self._snapshot_bound:
            return
        self._snapshot_bound = True
        aria2_manager.set_snapshot_callback(self._push_snapshot)

    def _push_snapshot(self, snapshot: dict):
        self._push({"type": "snapshot", "payload": snapshot})

    # ---- 初始状态 ----

    def get_state(self):
        """窗口初始数据：aria2c 可用性、服务状态、持久化配置。"""
        try:
            from webutils import aria2_manager
            from resource_updater.core import resolve_aria2_binary
            self._bind_snapshot()
            mgr = ConfigManager()
            cfg = mgr.get('ui_default.aria2_dl', {}) or {}
            save_dir = cfg.get('save_dir') or resolve_default_save_dir()
            return {
                "success": True,
                "available": resolve_aria2_binary() is not None,
                "server_running": aria2_manager.is_running(),
                "config": {
                    "save_dir": save_dir,
                    "save_dir_exists": bool(save_dir) and Path(save_dir).is_dir(),
                    "jobs": int(cfg.get('jobs') or 8),
                    "connection_limit": int(cfg.get('connection_limit') or 16),
                    "seed_time": int(cfg.get('seed_time') or 0),
                },
            }
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    # ---- 目录/文件选择 ----

    def browse_folder(self):
        if self._window is None:
            return {"success": False, "message": "窗口尚未初始化"}
        try:
            selected = self._window.create_file_dialog(webview.FileDialog.FOLDER)
            if not selected:
                return {"success": False, "cancelled": True, "message": "已取消选择"}
            return {"success": True, "path": str(Path(selected[0]).resolve())}
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    def browse_torrent(self):
        if self._window is None:
            return {"success": False, "message": "窗口尚未初始化"}
        try:
            selected = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=("BitTorrent (*.torrent)",),
            )
            if not selected:
                return {"success": False, "cancelled": True, "message": "已取消选择"}
            return {"success": True, "path": str(Path(selected[0]).resolve())}
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    # ---- 服务与任务 ----

    def start_server(self):
        from webutils import aria2_manager
        try:
            self._bind_snapshot()
            result = aria2_manager.start_server()
            if result["success"]:
                self._push({"type": "server", "payload": {"running": True}})
            return result
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    def add_urls(self, payload: dict):
        from webutils import aria2_manager
        try:
            urls = payload.get("urls") or []
            save_dir = str(payload.get("save_dir") or "").strip()
            if not save_dir:
                return {"success": False, "message": "请先选择保存目录"}
            if not urls:
                return {"success": False, "message": "没有可添加的链接"}
            result = aria2_manager.add_urls(urls, save_dir)
            if result.get("added"):
                self._persist_save_dir(save_dir)
            return result
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    def add_torrent(self, payload: dict):
        from webutils import aria2_manager
        try:
            torrent_path = payload.get("path") or ""
            save_dir = str(payload.get("save_dir") or "").strip()
            if not save_dir:
                return {"success": False, "message": "请先选择保存目录"}
            result = aria2_manager.add_torrent(torrent_path, save_dir)
            if result.get("success"):
                self._persist_save_dir(save_dir)
            return result
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    def pause_task(self, gid):
        from webutils import aria2_manager
        try:
            return aria2_manager.pause(gid)
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    def resume_task(self, gid):
        from webutils import aria2_manager
        try:
            return aria2_manager.resume(gid)
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    def remove_task(self, gid):
        from webutils import aria2_manager
        try:
            return aria2_manager.remove(gid)
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    def pause_all(self):
        from webutils import aria2_manager
        try:
            return aria2_manager.pause_all()
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    def resume_all(self):
        from webutils import aria2_manager
        try:
            return aria2_manager.resume_all()
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    def purge_completed(self):
        from webutils import aria2_manager
        try:
            return aria2_manager.purge_completed()
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}

    # ---- 配置持久化 ----

    def _persist_save_dir(self, save_dir: str):
        try:
            ConfigManager().set('ui_default.aria2_dl.save_dir', save_dir)
        except Exception:
            pass

    def save_window_config(self, payload: dict):
        """保存 并发任务数/每文件连接数/做种时间；下次启动下载服务时生效。"""
        try:
            cfg = ConfigManager()
            current = cfg.get('ui_default.aria2_dl', {}) or {}
            jobs = int(payload.get('jobs') or current.get('jobs') or 8)
            connection_limit = int(
                payload.get('connection_limit') or current.get('connection_limit') or 16
            )
            seed_time = int(payload.get('seed_time') or current.get('seed_time') or 0)
            cfg.set('ui_default.aria2_dl', {
                "save_dir": payload.get('save_dir') or current.get('save_dir') or resolve_default_save_dir(),
                "jobs": max(1, jobs),
                "connection_limit": max(1, min(16, connection_limit)),
                "seed_time": max(0, seed_time),
            })
            return {"success": True}
        except Exception as exc:
            self.log_error(exc)
            return {"success": False, "message": str(exc)}
