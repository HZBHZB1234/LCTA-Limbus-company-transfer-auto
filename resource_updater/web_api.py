import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager

from .core import DownloadCancelled, GameInfo, ResourceUpdater, resolve_aria2_binary
from .server_sync import (
    _s_token_from_settings,
    create_lethe_shortcut,
    detect_lethe_dir_candidates,
    get_server_switch_config,
    save_server_switch_options,
)
from .service import (
    get_last_update_result,
    get_resource_update_config,
    record_update_result,
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
            "last_result": get_last_update_result(),
        }

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
        def as_int(value, default):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        updates = {
            "launcher.resource_update.enabled": bool(options.get("enabled", False)),
            "launcher.resource_update.localize": bool(options.get("localize", True)),
            "launcher.resource_update.bundle": bool(options.get("bundle", True)),
            "launcher.resource_update.lang_jp": bool(options.get("lang_jp", True)),
            "launcher.resource_update.lang_en": bool(options.get("lang_en", True)),
            "launcher.resource_update.lang_kr": bool(options.get("lang_kr", True)),
            "launcher.resource_update.jobs": max(1, min(as_int(options.get("jobs", 8), 8), 32)),
            "launcher.resource_update.engine": options.get("engine", "auto"),
            "launcher.resource_update.retry_max": max(0, as_int(options.get("retry_max", 2), 2)),
            "launcher.resource_update.retry_delay": max(5, as_int(options.get("retry_delay", 30), 30)),
            "launcher.resource_update.connection_limit": max(
                1, min(as_int(options.get("connection_limit", 8), 8), 16)
            ),
        }
        count = ConfigManager().set_batch(updates)
        _log_manager.debug(
            "[游戏资源更新/UI] 已保存页面配置: {}".format(updates)
        )
        return {"success": count == len(updates), "updated": count}

    def start_update(self, options: Dict[str, Any]) -> Dict[str, Any]:
        if self.worker and self.worker.is_alive():
            return {"success": False, "message": "更新任务正在运行"}
        game_path_str = str(options.get("game_path", "")).strip()
        if not game_path_str:
            game_path_str = str(ConfigManager().get("game_path", "")).strip()
        game_path = Path(game_path_str)
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
                    retry_max=options.get("retry_max", 2),
                    retry_delay=options.get("retry_delay", 30),
                    connection_limit=options.get("connection_limit", 8),
                )
                result = self.updater.run(
                    update_localize=update_localize,
                    update_bundle=update_bundle,
                    languages=languages,
                )
                record_update_result(
                    game_path,
                    result,
                    update_localize,
                    update_bundle,
                    languages,
                )
                if result["success"]:
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


class ServerSwitchAPI:
    """官服 ⇄ lethe 私服资源切换的页面控制器（目录校验、选项持久化、快捷方式）。"""

    def __init__(self):
        self._window = None

    def set_window(self, window) -> None:
        self._window = window

    def get_initial_state(self) -> Dict[str, Any]:
        config = get_server_switch_config()
        official = ConfigManager().get("game_path", "")
        candidates = [str(path) for path in detect_lethe_dir_candidates()]
        return {
            "success": True,
            "official_dir": official,
            "config": config,
            "lethe_candidates": candidates,
            "aria2_available": bool(resolve_aria2_binary()),
        }

    def probe_lethe_dir(self, lethe_dir: str) -> Dict[str, Any]:
        try:
            path = Path(lethe_dir)
            catalog = path / "LimbusCompany_Data" / "StreamingAssets" / "aa" / "catalog.bin"
            settings = path / "LimbusCompany_Data" / "StreamingAssets" / "aa" / "settings.json"
            exe = path / "LimbusCompany.exe"
            if not catalog.is_file():
                return {"success": False, "message": "目录缺少 catalog.bin，不是有效的 lethe 分发包: {}".format(path)}
            if not settings.is_file():
                return {"success": False, "message": "目录缺少 settings.json，不是有效的 lethe 分发包: {}".format(path)}
            token = _s_token_from_settings(settings)
            return {
                "success": True,
                "message": "lethe 目录有效，已识别 CDN 令牌",
                "tokens": {"s": token},
                "has_exe": exe.is_file(),
                "exe_path": str(exe) if exe.is_file() else "",
            }
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def save_options(self, options: Dict[str, Any]) -> Dict[str, Any]:
        result = save_server_switch_options(options)
        _log_manager.debug("[服务器切换/UI] 已保存页面配置: {}".format(options))
        return result

    def create_shortcut(self, lethe_dir: str) -> Dict[str, Any]:
        """创建「开启 lethe 私服」桌面快捷方式。"""
        if not lethe_dir.strip():
            return {"success": False, "message": "lethe 目录为空，请先选择 lethe 分发包目录"}
        return create_lethe_shortcut(Path(lethe_dir.strip()))
