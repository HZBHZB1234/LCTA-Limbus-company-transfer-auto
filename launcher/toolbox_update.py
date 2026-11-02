# -*- coding: utf-8 -*-
"""启动器阶段的订阅工具自动更新（2026-11-02）。

## 为什么放在启动器

自动更新必须在**游戏没运行**时写文件（DLL 被占用、替换会失败），而启动器
的 ``PHASE_TOOLBOX_UPDATE`` 正好在 ``subprocess.Popen(游戏)`` 之前，且用户
本来就在等待 —— 不需要常驻定时器，也不会在 WebUI 挂一整天时反复打站点。

阶段顺序：``… → PREPARE_MOD → TOOLBOX_UPDATE → LAUNCH``。放在 ``PREPARE_MOD``
之后是为了让模组/挂载准备先完成（文件所有权确定之后再动工具文件）。

## 无人值守的四条底线

1. **不装新工具**：只升级已安装的（装什么是用户的决定）；
2. **不碰底座**：``runtime_zip_root`` 由用户手动更新（doorstop 原生层更新
   失败 = 游戏起不来），``deps.plan_updates`` 会把它归入 ``runtime_manual``；
3. **不降级**：目标版本序必须高于已装，否则跳过；
4. **失败不阻塞启动**：任何异常只记录 + 标记阶段失败，游戏照常启动。

依赖处理：已装工具的**硬依赖缺失**会被补装（这是修复而不是新增功能），
更新顺序按拓扑序（被依赖者先），否则新插件配旧依赖可能启动即崩。

节流：默认 6 小时一次；某工具连续失败后 1 小时内不再重试，避免每次开局都
打站点。状态与报告落在 ``<游戏目录>/.lcta-toolbox/``，供 WebUI 展示"上次
开局前自动更新了什么"。
"""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from globalManagers.ConfigManager import ConfigManager
from globalManagers.LogManager import LogManager

_log_manager = LogManager()

TOOLBOX_CONFIG_KEY = "ui_default.toolbox"
STATE_DIR_NAME = ".lcta-toolbox"
STATE_FILE_NAME = "update-state.json"
REPORT_FILE_NAME = "last-update.json"
DEFAULT_INTERVAL_HOURS = 6.0
FAILURE_BACKOFF_HOURS = 1.0
# 单次启动最多更新多少个工具：一次装太多会让开局等待变得不可接受
MAX_UPDATES_PER_RUN = 8


def _log(message: str, *args) -> None:
    _log_manager.log(message, *args)


def _now() -> float:
    return time.time()


def _iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts or _now(), tz=timezone.utc).isoformat(timespec="seconds")


def _network_ok(timeout: float = 3.0) -> bool:
    """轻量联网探测：只判断"有没有网"，不关心站点可达性。"""
    try:
        socket.create_connection(("223.5.5.5", 53), timeout=timeout).close()
        return True
    except OSError:
        return False


def _state_path(game_root) -> Path:
    return Path(game_root) / STATE_DIR_NAME / STATE_FILE_NAME


def _report_path(game_root) -> Path:
    return Path(game_root) / STATE_DIR_NAME / REPORT_FILE_NAME


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    """原子写（同目录临时文件 + replace）：断电不会留下截断 JSON。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except OSError:
        logging.getLogger(__name__).warning("写入 %s 失败", path, exc_info=True)


def _resolve_game_root() -> Optional[str]:
    """游戏目录：订阅工具配置优先，回退启动器的 ``game_path``。"""
    try:
        cfg = ConfigManager().get(TOOLBOX_CONFIG_KEY, {}) or {}
        root = (cfg.get("game_root") if isinstance(cfg, dict) else "") or ""
        root = str(root or "").strip()
        if root:
            return root
        fallback = str(ConfigManager().get("game_path", "") or "").strip()
        return fallback or None
    except Exception:  # noqa: BLE001 - 配置异常按"未配置"处理
        return None


def _interval_seconds() -> float:
    try:
        hours = float(ConfigManager().get("launcher.toolbox_update.interval_hours",
                                         DEFAULT_INTERVAL_HOURS))
    except (TypeError, ValueError):
        hours = DEFAULT_INTERVAL_HOURS
    return max(0.5, min(168.0, hours)) * 3600.0


def _make_bridge():
    """启动器侧的桥接适配器：复用订阅工具的安装/验签路径。

    刻意**不复制**验签、取票据、下载、按 install_kind 派发的任何逻辑 ——
    两条路径一旦各写一份必然漂移。这里只补启动器缺的日志与游戏目录回退。
    """
    from webui.app_api.toolbox import ToolboxBridgeError, ToolboxMixin

    class _LauncherToolbox(ToolboxMixin):
        def log_ui(self, message):
            _log("订阅工具：%s", message)

        def log_error(self, exc):
            _log_manager.log_error(exc)

        def _toolbox_game_root(self):
            root = _resolve_game_root()
            if not root:
                raise ToolboxBridgeError(
                    "no_game_root", "尚未配置游戏目录，跳过订阅工具更新"
                )
            return root

    return _LauncherToolbox()


def _preconditions(api) -> Optional[str]:
    """返回跳过原因（None 表示可以继续）。全部**只读**，不改任何状态。"""
    try:
        if not api.is_logged_in():
            return "not_logged_in"
        season = api.season() or {}
        if not season.get("season_active"):
            return "season_inactive"
        access = api.access() or {}
        if not access.get("unlocked"):
            return "no_entitlement"
    except Exception as exc:  # noqa: BLE001 - 断网/服务端异常都按"跳过"处理
        _log("订阅工具更新：在线状态检查失败，跳过（%s）", exc)
        return "online_unavailable"
    return None


def _apply_one(api, update: dict, progress: Optional[Callable[[int, str], None]],
               cancel_event) -> dict:
    """装一个更新（或补装一个缺失依赖），返回结果字典。"""
    tool_id = str(update.get("tool_id") or "")
    release_id = str(update.get("release_id") or "")
    if cancel_event is not None and cancel_event.is_set():
        return {"tool_id": tool_id, "ok": False, "message": "已取消", "cancelled": True}
    try:
        result = api.toolbox_install_any(tool_id, release_id) or {}
    except Exception as exc:  # noqa: BLE001 - 单个工具失败不影响其余
        _log_manager.log_error(exc)
        return {"tool_id": tool_id, "ok": False, "message": str(exc)}
    ok = bool(result.get("success"))
    message = str(result.get("message") or result.get("code") or "")
    return {
        "tool_id": tool_id,
        "release_id": release_id,
        "ok": ok,
        "code": result.get("code"),
        "message": message,
        "to_version": update.get("to_version"),
        "from_version": update.get("from_version"),
    }


def run_toolbox_update(
    *,
    cancel_event=None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    force: bool = False,
) -> dict:
    """执行一次订阅工具更新（启动器阶段回调）。

    返回报告字典（同时落盘 ``last-update.json``）。**永不抛出**：本函数是
    启动管线的一个阶段，任何异常都只能降级为"本次不更新"。
    """
    report: dict = {
        "checked_at": _iso(),
        "ok": True,
        "skipped": None,
        "updated": [],
        "failed": [],
        "repaired": [],
        "details": {},
    }

    def progress(percent: int, text: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(max(0, min(100, int(percent))), text)
        except Exception:  # noqa: BLE001 - 进度展示失败不影响更新
            pass

    game_root = _resolve_game_root()
    if not game_root:
        report["skipped"] = "no_game_root"
        return report

    state = _read_json(_state_path(game_root))
    if not force:
        last = float(state.get("last_check_at") or 0)
        if last and (_now() - last) < _interval_seconds():
            report["skipped"] = "throttled"
            return report

    if not _network_ok():
        report["skipped"] = "offline"
        return report

    # 上次中断的事务先回滚，再谈更新（否则写入会踩在半成品上）
    try:
        from webutils.toolbox import state as toolbox_state

        recovered = toolbox_state.recover_if_needed(game_root)
        if recovered:
            report["details"]["recovered"] = recovered
            _log("订阅工具更新：已回滚上次未完成的事务")
    except Exception as exc:  # noqa: BLE001
        _log_manager.log_error(exc)

    # 游戏在跑就不动文件（文件被锁，替换半途失败会留下混合状态）
    try:
        from webutils.toolbox import runtime as toolbox_runtime

        if toolbox_runtime.is_game_running(game_root):
            report["skipped"] = "game_running"
            return report
    except Exception:  # noqa: BLE001 - 检测失败不当作"在运行"
        pass

    try:
        from webutils.toolbox import deps
        from webutils.toolbox import state as toolbox_state
    except Exception as exc:  # noqa: BLE001
        _log_manager.log_error(exc)
        report["skipped"] = "toolbox_unavailable"
        return report

    api = _make_bridge()
    progress(5, "正在检查订阅工具更新…")
    reason = _preconditions(api)
    if reason is not None:
        report["skipped"] = reason
        state["last_check_at"] = _now()
        _write_json(_state_path(game_root), state)
        _write_json(_report_path(game_root), report)
        _log("订阅工具更新：跳过（%s）", reason)
        return report

    try:
        catalog = api.catalog() or {}
        items = catalog.get("items") or []
        manifest = toolbox_state.Manifest.load(game_root)
        plan = deps.plan_updates(manifest, items)
        repairs = deps.missing_installed_dependencies(manifest, items)
    except Exception as exc:  # noqa: BLE001
        _log_manager.log_error(exc)
        report["skipped"] = "catalog_failed"
        state["last_check_at"] = _now()
        _write_json(_state_path(game_root), state)
        return report

    state["last_check_at"] = _now()
    report["details"]["skipped_items"] = plan.get("skipped") or []
    updates = list(plan.get("updates") or [])
    failures: dict = state.get("failures") or {}
    now = _now()

    # 失败退避：同一工具 1 小时内不反复重试（否则每次开局都打站点）
    def _in_backoff(tool_id: str) -> bool:
        last_fail = float(failures.get(tool_id) or 0)
        return bool(last_fail) and (now - last_fail) < FAILURE_BACKOFF_HOURS * 3600

    updates = [u for u in updates if not _in_backoff(str(u.get("tool_id")))]
    if len(updates) > MAX_UPDATES_PER_RUN:
        _log("订阅工具更新：本次只处理 %d 个（其余下次启动继续）", MAX_UPDATES_PER_RUN)
        updates = updates[:MAX_UPDATES_PER_RUN]

    total = max(len(updates) + len(repairs), 1)
    done = 0

    for repair in repairs:
        progress(int(10 + 70 * done / total), f"补装依赖 {repair.get('tool_id')}…")
        result = _apply_one(api, repair, progress, cancel_event)
        done += 1
        if result.get("ok"):
            report["repaired"].append(result)
        else:
            report["failed"].append(result)
            failures[str(repair.get("tool_id"))] = _now()

    for update in updates:
        progress(int(10 + 70 * done / total), f"更新 {update.get('tool_id')}…")
        result = _apply_one(api, update, progress, cancel_event)
        done += 1
        if result.get("cancelled"):
            report["failed"].append(result)
            break
        if result.get("ok"):
            report["updated"].append(result)
            failures.pop(str(update.get("tool_id")), None)
            _log(
                "订阅工具更新：%s %s → %s",
                update.get("tool_id"), update.get("from_version"), update.get("to_version"),
            )
        else:
            report["failed"].append(result)
            failures[str(update.get("tool_id"))] = _now()
            _log(
                "订阅工具更新：%s 失败（%s）",
                update.get("tool_id"), result.get("message") or result.get("code"),
            )

    state["failures"] = failures
    state["last_result"] = {
        "checked_at": report["checked_at"],
        "updated": len(report["updated"]),
        "failed": len(report["failed"]),
        "repaired": len(report["repaired"]),
    }
    report["ok"] = not report["failed"]
    _write_json(_state_path(game_root), state)
    _write_json(_report_path(game_root), report)

    progress(100, "订阅工具已是最新" if not (updates or repairs) else "订阅工具更新完成")
    if not updates and not repairs:
        _log("订阅工具更新：全部已是最新")
    return report


def read_last_report() -> dict:
    """给 WebUI 用：读上次启动器更新的结果（读不到返回空）。"""
    root = _resolve_game_root()
    if not root:
        return {}
    return _read_json(_report_path(root))
