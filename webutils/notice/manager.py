# -*- coding: utf-8 -*-
"""公告汉化后台任务管理（WebUI 侧）。

与 `resource_updater/web_api.py` 同款结构：工作线程 + 可取消事件 + 轮询状态，
页面每 500ms 拉一次 `get_status()` 刷新进度与日志。
"""
from __future__ import annotations

import threading
import time
from typing import List, Optional

from globalManagers.LogManager import LogManager

from .core import NoticeLocalizeError, NoticeLocalizer

_log_manager = LogManager()

MAX_LOGS = 200


class NoticeManager:
    def __init__(self):
        self.worker: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.status = "idle"
        self.status_text = "等待操作"
        self.done = 0
        self.total = 0
        self.logs: List[str] = []
        self.last_result: Optional[dict] = None
        self._lock = threading.Lock()

    # -- 内部 -------------------------------------------------------------
    def _log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        with self._lock:
            self.logs.append("[{}] {}".format(stamp, message))
            if len(self.logs) > MAX_LOGS:
                del self.logs[: len(self.logs) - MAX_LOGS]
        _log_manager.log("[公告汉化] {}".format(message))

    def _snapshot(self) -> dict:
        with self._lock:
            logs = list(self.logs)
            percent = int(self.done * 100 / self.total) if self.total else 0
            return {
                "running": bool(self.worker and self.worker.is_alive()),
                "status": self.status,
                "text": self.status_text,
                "done": self.done,
                "total": self.total,
                "percent": percent,
                "logs": logs,
                "last_result": self.last_result,
            }

    # -- 对外 -------------------------------------------------------------
    def get_info(self) -> dict:
        try:
            return NoticeLocalizer.from_config().info()
        except Exception as exc:  # pragma: no cover - 兜底
            _log_manager.log_error(exc)
            return {"success": False, "message": str(exc)}

    def get_status(self) -> dict:
        return {"success": True, "data": self._snapshot()}

    def start_sync(self, force: bool = False) -> dict:
        if self.worker and self.worker.is_alive():
            return {"success": False, "message": "同步任务正在运行"}

        # 服务地址固定内置（`core.NoticeLocalizer.from_config`），无需用户配置
        localizer = NoticeLocalizer.from_config()

        self.cancel_event = threading.Event()
        self.status = "running"
        self.status_text = "正在获取官方公告清单"
        self.done = 0
        self.total = 0
        self.last_result = None
        with self._lock:
            self.logs = []
        self._log("开始同步公告（强制刷新）" if force else "开始同步公告（增量）")

        def progress(done: int, total: int, message: str) -> None:
            self.done = done
            self.total = total
            self.status_text = message

        def run() -> None:
            try:
                result = localizer.sync(
                    force=force, cancel_event=self.cancel_event, progress=progress
                )
                self.last_result = result
                self.done = result.get("total", self.done)
                self.total = result.get("total", self.total)
                if result.get("cancelled"):
                    self.status = "cancelled"
                elif result.get("pending"):
                    # 服务端未命中缓存且等待预算耗尽：不是失败，剩余公告留待下次
                    self.status = "pending"
                elif result.get("timed_out"):
                    self.status = "timed_out"
                elif result.get("success"):
                    self.status = "success"
                else:
                    self.status = "error"
                self.status_text = result.get("message") or self.status_text
                self._log(self.status_text)
                for item in result.get("items") or []:
                    if item.get("status") == "failed":
                        self._log(
                            "失败 {}: {}".format(item.get("file"), item.get("message"))
                        )
                    for warning in item.get("warnings") or []:
                        self._log("提示 {}: {}".format(item.get("file"), warning))
            except NoticeLocalizeError as exc:
                self.status = "error"
                self.status_text = str(exc)
                self._log("失败: {}".format(exc))
            except Exception as exc:  # pragma: no cover - 兜底
                self.status = "error"
                self.status_text = "同步失败: {}".format(exc)
                _log_manager.log_error(exc)
            finally:
                self.worker = None

        self.worker = threading.Thread(target=run, name="notice-localize", daemon=True)
        self.worker.start()
        return {"success": True, "message": "同步任务已启动"}

    def cancel(self) -> dict:
        if not (self.worker and self.worker.is_alive()):
            return {"success": False, "message": "当前没有运行中的任务"}
        self.cancel_event.set()
        self.status_text = "正在取消"
        self._log("已请求取消")
        return {"success": True, "message": "已请求取消"}

    def restore(self, files: Optional[List[str]] = None) -> dict:
        if self.worker and self.worker.is_alive():
            return {"success": False, "message": "请先等待当前同步任务结束"}
        try:
            result = NoticeLocalizer.from_config().restore(files)
        except Exception as exc:
            _log_manager.log_error(exc)
            return {"success": False, "message": str(exc)}
        self.status = "idle"
        self.status_text = result.get("message", "")
        self._log(self.status_text)
        return result

    def test_service(self, file_name: str = "") -> dict:
        if self.worker and self.worker.is_alive():
            return {"success": False, "message": "请先等待当前同步任务结束"}
        try:
            result = NoticeLocalizer.from_config().test_service(file_name)
        except Exception as exc:
            _log_manager.log_error(exc)
            return {"success": False, "message": str(exc)}
        self._log(result.get("message", ""))
        return result

    def service_status(self) -> dict:
        """查询内置翻译服务的运行状态（页面加载时自动刷新，不进同步日志）。"""
        try:
            return NoticeLocalizer.from_config().service_status()
        except Exception as exc:  # pragma: no cover - 兜底
            _log_manager.log_error(exc)
            return {"success": False, "message": str(exc)}


_manager: Optional[NoticeManager] = None
_manager_lock = threading.Lock()


def get_notice_manager() -> NoticeManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = NoticeManager()
        return _manager
