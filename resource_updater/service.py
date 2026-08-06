import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager

from .core import ResourceUpdater, build_game_fingerprint, default_work_dir


_log_manager = LogManager()


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _state_path() -> Path:
    return default_work_dir() / "launcher-state.json"


def _load_state(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        _log_manager.log(
            "[游戏资源更新/Launcher] 读取状态失败，将重新检查: {}".format(exc)
        )
        return {}


def _save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temp_path.replace(path)
    _log_manager.debug("[游戏资源更新/Launcher] 状态已保存: {}".format(path))


def get_resource_update_config() -> Dict[str, Any]:
    manager = ConfigManager()
    return {
        "enabled": manager.get("launcher.resource_update.enabled", False),
        "localize": manager.get("launcher.resource_update.localize", True),
        "bundle": manager.get("launcher.resource_update.bundle", True),
        "lang_jp": manager.get("launcher.resource_update.lang_jp", True),
        "lang_en": manager.get("launcher.resource_update.lang_en", True),
        "lang_kr": manager.get("launcher.resource_update.lang_kr", True),
        "jobs": max(1, _as_int(manager.get("launcher.resource_update.jobs", 8), 8)),
        "engine": manager.get("launcher.resource_update.engine", "auto"),
        "retry_max": max(0, _as_int(manager.get("launcher.resource_update.retry_max", 2), 2)),
        "retry_delay": max(5, _as_int(manager.get("launcher.resource_update.retry_delay", 30), 30)),
        "connection_limit": max(
            1, min(16, _as_int(manager.get("launcher.resource_update.connection_limit", 8), 8))
        ),
    }


def selected_languages(config: Dict[str, Any]):
    return [
        language
        for language in ("jp", "en", "kr")
        if config.get("lang_" + language, False)
    ]


def record_update_result(
    game_path: Path,
    result: Dict[str, Any],
    update_localize: bool,
    update_bundle: bool,
    languages,
) -> None:
    """无论成败都记录更新结果；已完整完成的 scope 会标记，失败 scope 保持未完成（下次启动重试）。"""
    state_path = _state_path()
    fingerprint = build_game_fingerprint(game_path)
    previous = _load_state(state_path)
    resources = (
        previous.get("resources", {})
        if previous.get("fingerprint") == fingerprint
        else {}
    )
    completed_languages = set(resources.get("languages", []))
    if update_localize:
        localize_result = (result.get("results") or {}).get("localize") or {}
        if not localize_result.get("failed"):
            resources["localize"] = True
            completed_languages.update(languages)
    if update_bundle:
        bundle_result = (result.get("results") or {}).get("bundle") or {}
        if not bundle_result.get("failed"):
            resources["bundle"] = True
    resources["languages"] = sorted(completed_languages)
    failed_items = []
    for item in (result.get("results") or {}).values():
        failed_items.extend(item.get("failed_items") or [])
    last_result = {
        "success": bool(result.get("success")),
        "failed": result.get("failed", 0),
        "retried": result.get("retried", 0),
        "failed_items": [
            {"name": item.get("name"), "reason": item.get("reason")}
            for item in failed_items
        ],
    }
    _save_state(state_path, {
        "game_dir": str(game_path),
        "fingerprint": fingerprint,
        "tokens": result.get("tokens", {}),
        "resources": resources,
        "last_result": last_result,
    })
    _log_manager.log(
        "[游戏资源更新/Launcher] 已记录更新结果: {}".format(last_result)
    )


def record_successful_update(
    game_path: Path,
    result: Dict[str, Any],
    update_localize: bool,
    update_bundle: bool,
    languages,
) -> None:
    record_update_result(game_path, result, update_localize, update_bundle, languages)


def get_last_update_result() -> Optional[Dict[str, Any]]:
    state = _load_state(_state_path())
    return state.get("last_result")


def _state_covers_config(
    state: Dict[str, Any], fingerprint: Dict[str, Any], config: Dict[str, Any]
) -> bool:
    if state.get("fingerprint") != fingerprint:
        return False
    resources = state.get("resources", {})
    if config["bundle"] and not resources.get("bundle"):
        return False
    if config["localize"]:
        completed_languages = set(resources.get("languages", []))
        if not resources.get("localize") or not set(selected_languages(config)).issubset(completed_languages):
            return False
    return True


def run_launcher_resource_update(
    game_dir: Optional[Path] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    config = get_resource_update_config()
    if not config["enabled"]:
        _log_manager.debug("[游戏资源更新/Launcher] 自动预下载未启用")
        return {"success": True, "skipped": True, "reason": "disabled"}
    if not config["localize"] and not config["bundle"]:
        _log_manager.log("[游戏资源更新/Launcher] 未选择更新范围，跳过")
        return {"success": True, "skipped": True, "reason": "no_targets"}
    game_path = Path(game_dir or ConfigManager().get("game_path", ""))
    fingerprint = build_game_fingerprint(game_path)
    state_path = _state_path()
    state = _load_state(state_path)
    if _state_covers_config(state, fingerprint, config):
        _log_manager.log("[游戏资源更新/Launcher] 游戏 EXE 未变化，跳过预下载")
        return {"success": True, "skipped": True, "reason": "unchanged"}

    _log_manager.log(
        "[游戏资源更新/Launcher] 检测到游戏 EXE 指纹或资源范围变化，开始预下载"
    )

    updater = ResourceUpdater(
        game_path,
        jobs=config["jobs"],
        engine=config["engine"],
        cancel_event=cancel_event,
        retry_max=config["retry_max"],
        retry_delay=config["retry_delay"],
        connection_limit=config["connection_limit"],
    )
    result = updater.run(
        update_localize=config["localize"],
        update_bundle=config["bundle"],
        languages=selected_languages(config),
    )
    record_update_result(
        game_path,
        result,
        config["localize"],
        config["bundle"],
        selected_languages(config),
    )
    if result["success"]:
        _log_manager.log("[游戏资源更新/Launcher] 预下载完成: {}".format(result))
    else:
        _log_manager.log(
            "[游戏资源更新/Launcher] 预下载存在失败项（已完成范围已记录，下次启动将自动重试失败范围）: {}".format(
                result
            )
        )
    return result
