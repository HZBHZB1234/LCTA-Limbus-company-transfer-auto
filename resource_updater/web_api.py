import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import webview

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager

from .core import DownloadCancelled, GameInfo, ResourceUpdater, resolve_aria2_binary
from .service import (
    get_resource_update_config,
    record_successful_update,
    selected_languages,
)


_log_manager = LogManager()


class ResourceUpdaterAPI:
    def __init__(self):
        self._window = None
        self.worker = None
        self.cancel_event = threading.Event()
        self.updater = None
        self.status = "idle"
        self.status_text = "等待操作"

    def set_window(self, window) -> None:
        self._window = window

    def _emit(self, event: Dict[str, Any]) -> None:
        if not self._window:
            return
        payload = json.dumps(event, ensure_ascii=False)
        try:
            self._window.evaluate_js(
                "window.onResourceUpdaterEvent && window.onResourceUpdaterEvent({});".format(
                    payload
                )
            )
        except Exception as exc:
            _log_manager.debug(
                "[游戏资源更新/UI] 推送事件失败: {} ({})".format(event.get("type"), exc)
            )

    def get_initial_state(self) -> Dict[str, Any]:
        config = get_resource_update_config()
        _log_manager.debug("[游戏资源更新/UI] 读取页面初始状态")
        return {
            "success": True,
            "game_path": ConfigManager().get("game_path", ""),
            "config": config,
            "aria2_available": bool(resolve_aria2_binary()),
            "status": self.status,
            "status_text": self.status_text,
        }

    def select_game_folder(self) -> str:
        if not self._window:
            return ""
        selected = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return selected[0] if selected else ""

    def probe_game_dir(self, game_dir: str) -> Dict[str, Any]:
        try:
            _log_manager.log("[游戏资源更新/UI] 检测游戏目录: {}".format(game_dir))
            game = GameInfo(Path(game_dir))
            game.validate()
            tokens = game.extract_tokens()
            return {
                "success": True,
                "message": "游戏目录有效，已识别当前 CDN 令牌",
                "tokens": tokens,
            }
        except Exception as exc:
            _log_manager.log("[游戏资源更新/UI] 游戏目录检测失败: {}".format(exc))
            return {"success": False, "message": str(exc)}

    def save_options(self, options: Dict[str, Any]) -> Dict[str, Any]:
        updates = {
            "launcher.resource_update.enabled": bool(options.get("enabled", False)),
            "launcher.resource_update.localize": bool(options.get("localize", True)),
            "launcher.resource_update.bundle": bool(options.get("bundle", True)),
            "launcher.resource_update.lang_jp": bool(options.get("lang_jp", True)),
            "launcher.resource_update.lang_en": bool(options.get("lang_en", True)),
            "launcher.resource_update.lang_kr": bool(options.get("lang_kr", True)),
            "launcher.resource_update.jobs": max(1, min(int(options.get("jobs", 8)), 32)),
            "launcher.resource_update.engine": options.get("engine", "auto"),
        }
        game_path = str(options.get("game_path", "")).strip()
        if game_path:
            updates["game_path"] = game_path
        count = ConfigManager().set_batch(updates)
        _log_manager.debug(
            "[游戏资源更新/UI] 已保存页面配置: {}".format(updates)
        )
        return {"success": count == len(updates), "updated": count}

    def start_update(self, options: Dict[str, Any]) -> Dict[str, Any]:
        if self.worker and self.worker.is_alive():
            return {"success": False, "message": "更新任务正在运行"}
        game_path = Path(str(options.get("game_path", "")).strip())
        update_localize = bool(options.get("localize", True))
        update_bundle = bool(options.get("bundle", True))
        languages = selected_languages(options)
        if not update_localize and not update_bundle:
            return {"success": False, "message": "请至少选择 localize 或 bundle"}
        if update_localize and not languages:
            return {"success": False, "message": "更新 localize 时请至少选择一种语言"}
        try:
            GameInfo(game_path).validate()
        except Exception as exc:
            _log_manager.log("[游戏资源更新/UI] 启动前校验失败: {}".format(exc))
            return {"success": False, "message": str(exc)}

        self.save_options(options)
        self.cancel_event = threading.Event()
        self.status = "running"
        self.status_text = "正在准备更新"
        _log_manager.log(
            "[游戏资源更新/UI] 手动任务已提交: game_dir={}, localize={}, bundle={}, languages={}".format(
                game_path, update_localize, update_bundle, languages
            )
        )

        def progress(channel: str, message: str, fraction: Optional[float]) -> None:
            self.status_text = message
            self._emit({
                "type": "progress",
                "channel": channel,
                "message": message,
                "fraction": fraction,
            })

        def run() -> None:
            try:
                self.updater = ResourceUpdater(
                    game_path,
                    jobs=options.get("jobs", 8),
                    engine=options.get("engine", "auto"),
                    progress_callback=progress,
                    cancel_event=self.cancel_event,
                )
                result = self.updater.run(
                    update_localize=update_localize,
                    update_bundle=update_bundle,
                    languages=languages,
                )
                if result["success"]:
                    record_successful_update(
                        game_path,
                        result,
                        update_localize,
                        update_bundle,
                        languages,
                    )
                    self.status = "success"
                    self.status_text = "资源更新完成"
                else:
                    self.status = "error"
                    self.status_text = "资源更新完成，但存在失败项"
                _log_manager.log(
                    "[游戏资源更新/UI] 手动任务完成，状态 {}".format(self.status)
                )
                self._emit({
                    "type": "complete",
                    "status": self.status,
                    "message": self.status_text,
                    "result": result,
                })
            except DownloadCancelled:
                self.status = "cancelled"
                self.status_text = "更新已取消"
                _log_manager.log("[游戏资源更新/UI] 手动任务已取消")
                self._emit({"type": "complete", "status": self.status, "message": self.status_text})
            except Exception as exc:
                self.status = "error"
                self.status_text = str(exc)
                _log_manager.log_error(exc)
                self._emit({
                    "type": "complete",
                    "status": self.status,
                    "message": str(exc),
                })
            finally:
                self.updater = None

        self.worker = threading.Thread(target=run, name="resource-updater", daemon=True)
        self.worker.start()
        return {"success": True, "message": "更新任务已启动"}

    def cancel_update(self) -> Dict[str, Any]:
        if not self.worker or not self.worker.is_alive():
            return {"success": False, "message": "当前没有运行中的任务"}
        self.cancel_event.set()
        if self.updater:
            self.updater.cancel()
        self.status_text = "正在取消"
        _log_manager.log("[游戏资源更新/UI] 已请求取消手动任务")
        return {"success": True, "message": "已请求取消"}
