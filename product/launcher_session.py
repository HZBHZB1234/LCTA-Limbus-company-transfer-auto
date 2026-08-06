from __future__ import annotations

import copy
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from globalManagers.ConfigManager import ConfigManager
from launcher.pipeline import (
    PHASE_CDN,
    PHASE_CHECK_UPDATE,
    PHASE_EXIT,
    PHASE_INIT,
    PHASE_LAUNCH,
    PHASE_PREPARE_MOD,
    PHASE_RESOURCE_UPDATE,
    PHASE_RUNNING,
)

from .models import SCHEMA_VERSION, utc_now_iso


PHASES = [
    (PHASE_INIT, "准备启动", lambda cfg: True),
    (PHASE_CHECK_UPDATE, "检查工具与汉化更新", lambda cfg: cfg.get("launcher.work.update", "no") != "no"),
    (PHASE_RESOURCE_UPDATE, "预下载游戏资源", lambda cfg: cfg.get("launcher.resource_update.enabled", False)),
    (PHASE_CDN, "优化下载网络", lambda cfg: cfg.get("launcher.work.cdn_optimize", False)),
    (PHASE_PREPARE_MOD, "准备模组与文本", lambda cfg: cfg.get("launcher.work.mod", False)),
    (PHASE_LAUNCH, "启动游戏", lambda cfg: True),
    (PHASE_RUNNING, "游戏运行中", lambda cfg: True),
    (PHASE_EXIT, "结束与清理", lambda cfg: True),
]


class LaunchSessionStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        root = Path(os.getenv("path_", "") or os.getcwd())
        self.path = path or root / "tmp" / "launcher" / "last-session.json"

    def load(self) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def save(self, snapshot: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)


class LauncherSessionProgressAdapter:
    def __init__(self, service: "LaunchSessionService") -> None:
        self.service = service

    def register_to_pipeline(self, pipeline) -> None:
        self.service.attach_pipeline(pipeline)

    def is_alive(self) -> bool:
        return True

    def set_progress_marquee(self) -> None:
        self.service.update_progress(None)

    def set_progress(self, percent: int) -> None:
        self.service.update_progress(percent)

    def update_status(self, message: str) -> None:
        self.service.update_status(message)

    def mark_phase_failed(self, phase: str) -> None:
        self.service.mark_phase_failed(phase)

    def close(self) -> None:
        self.service.finish_from_pipeline()


class LauncherSessionLogHandler(logging.Handler):
    def __init__(self, service: "LaunchSessionService") -> None:
        super().__init__()
        self.service = service
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.service.append_log(self.format(record))
        except Exception:
            pass


class LaunchSessionService:
    def __init__(self, store: Optional[LaunchSessionStore] = None) -> None:
        self._lock = threading.RLock()
        self._store = store or LaunchSessionStore()
        self._listener: Optional[Callable[[Dict[str, Any]], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._pipeline = None
        self._run_callable: Optional[Callable[..., Any]] = None
        self._log_handler: Optional[LauncherSessionLogHandler] = None
        self._snapshot = self._new_snapshot()
        self._persist()

    def _new_snapshot(self) -> Dict[str, Any]:
        config = ConfigManager()
        phases = []
        enabled_features = []
        for phase_id, title, predicate in PHASES:
            enabled = bool(predicate(config))
            phases.append({
                "id": phase_id,
                "title": title,
                "state": "pending" if enabled else "skipped",
                "progress": None,
                "message": "",
            })
            if enabled and phase_id not in {PHASE_INIT, PHASE_LAUNCH, PHASE_RUNNING, PHASE_EXIT}:
                enabled_features.append(title)
        return {
            "schema_version": SCHEMA_VERSION,
            "revision": 1,
            "id": uuid.uuid4().hex,
            "state": "ready",
            "current_phase": None,
            "message": "已生成本次启动计划",
            "progress": None,
            "phases": phases,
            "launch_plan": {
                "title": "启动 Limbus Company",
                "steps": [phase["title"] for phase in phases if phase["state"] != "skipped"],
            },
            "game_process": None,
            "enabled_features": enabled_features,
            "started_at": None,
            "finished_at": None,
            "can_cancel": False,
            "can_close_without_stopping_game": False,
            "issues": [],
            "logs": [],
            "result": None,
        }

    def set_listener(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        self._listener = listener

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._snapshot)

    def start(self, run_callable: Callable[..., Any]) -> Dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return copy.deepcopy(self._snapshot)
            if self._snapshot["state"] != "ready":
                self._snapshot = self._new_snapshot()
            self._run_callable = run_callable
            self._snapshot.update({
                "state": "running",
                "message": "正在准备启动",
                "started_at": utc_now_iso(),
                "finished_at": None,
                "can_cancel": True,
                "result": None,
            })
            self._changed()
            self._thread = threading.Thread(target=self._run, name="lcta-launch-session", daemon=False)
            self._thread.start()
            return copy.deepcopy(self._snapshot)

    def _run(self) -> None:
        from globalManagers.LogManager import LogManager

        adapter = LauncherSessionProgressAdapter(self)
        logger = getattr(LogManager(), "_logger", None)
        self._log_handler = LauncherSessionLogHandler(self)
        if logger is not None:
            logger.addHandler(self._log_handler)
        try:
            self._run_callable(progress=adapter)
            self.finish_from_pipeline()
        except Exception as exc:
            self.fail(str(exc))
        finally:
            if logger is not None and self._log_handler is not None:
                try:
                    logger.removeHandler(self._log_handler)
                except Exception:
                    pass

    def attach_pipeline(self, pipeline) -> None:
        self._pipeline = pipeline
        for phase_id, _, _ in PHASES:
            pipeline.on(phase_id, lambda _phase=phase_id, **_: self.phase_started(_phase))

    def phase_started(self, phase_id: str) -> None:
        with self._lock:
            for phase in self._snapshot["phases"]:
                if phase["state"] == "running" and phase["id"] != phase_id:
                    phase["state"] = "completed"
                    phase["progress"] = 100
                if phase["id"] == phase_id and phase["state"] != "skipped":
                    phase["state"] = "running"
                    phase["progress"] = None
            self._snapshot["current_phase"] = phase_id
            self._snapshot["state"] = "game_running" if phase_id == PHASE_RUNNING else "running"
            self._snapshot["can_close_without_stopping_game"] = phase_id == PHASE_RUNNING
            self._sync_game_process()
            self._changed()

    def update_status(self, message: str) -> None:
        with self._lock:
            self._snapshot["message"] = str(message)
            current = self._phase(self._snapshot.get("current_phase"))
            if current:
                current["message"] = str(message)
            self._sync_game_process()
            self._changed()

    def update_progress(self, percent: Optional[int]) -> None:
        with self._lock:
            value = None if percent is None else max(0, min(100, int(percent)))
            self._snapshot["progress"] = value
            current = self._phase(self._snapshot.get("current_phase"))
            if current:
                current["progress"] = value
            self._changed()

    def mark_phase_failed(self, phase_id: str) -> None:
        with self._lock:
            phase = self._phase(phase_id)
            if phase:
                phase["state"] = "failed"
            self._snapshot["issues"].append({
                "id": f"phase:{phase_id}",
                "severity": "warning",
                "title": "启动步骤未完全成功",
                "summary": phase["message"] if phase else phase_id,
            })
            self._changed()

    def append_log(self, message: str) -> None:
        with self._lock:
            self._snapshot["logs"].append({"time": utc_now_iso(), "message": str(message)})
            self._snapshot["logs"] = self._snapshot["logs"][-300:]
            self._changed()

    def cancel(self) -> Dict[str, Any]:
        with self._lock:
            if self._pipeline is not None:
                self._pipeline.cancel()
            self._snapshot.update({"state": "cancelling", "message": "正在停止启动流程", "can_cancel": False})
            self._changed()
            return copy.deepcopy(self._snapshot)

    def terminate_game(self) -> bool:
        process = self._pipeline.context.get("game_process") if self._pipeline else None
        if process is None or process.poll() is not None:
            return False
        process.terminate()
        return True

    def finish_from_pipeline(self) -> None:
        with self._lock:
            if self._snapshot["state"] in {"succeeded", "failed", "cancelled"}:
                return
            cancelled = bool(self._pipeline and self._pipeline.cancel_event.is_set())
            for phase in self._snapshot["phases"]:
                if phase["state"] == "running":
                    phase["state"] = "completed"
                    phase["progress"] = 100
            self._sync_game_process()
            self._snapshot.update({
                "state": "cancelled" if cancelled else "succeeded",
                "message": "启动已取消" if cancelled else "本次启动会话已结束",
                "finished_at": utc_now_iso(),
                "can_cancel": False,
                "can_close_without_stopping_game": False,
                "result": {
                    "success": not cancelled,
                    "summary": "启动已取消" if cancelled else "游戏进程已结束，清理完成",
                    "changed_items": self._snapshot["enabled_features"],
                    "failed_items": [],
                },
            })
            self._changed()

    def fail(self, message: str) -> None:
        with self._lock:
            current = self._phase(self._snapshot.get("current_phase"))
            if current:
                current["state"] = "failed"
                current["message"] = str(message)
            self._snapshot.update({
                "state": "failed",
                "message": str(message),
                "finished_at": utc_now_iso(),
                "can_cancel": False,
                "result": {
                    "success": False,
                    "summary": "启动流程失败",
                    "changed_items": [],
                    "failed_items": [str(message)],
                },
            })
            self._changed()

    def _phase(self, phase_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not phase_id:
            return None
        return next((phase for phase in self._snapshot["phases"] if phase["id"] == phase_id), None)

    def _sync_game_process(self) -> None:
        if self._pipeline is None:
            return
        process = self._pipeline.context.get("game_process")
        pid = self._pipeline.context.get("game_pid")
        if process is None and pid is None:
            return
        self._snapshot["game_process"] = {
            "pid": pid,
            "running": bool(process is not None and process.poll() is None),
            "exit_code": None if process is None or process.poll() is None else process.returncode,
        }

    def _changed(self) -> None:
        self._snapshot["revision"] += 1
        self._persist()
        if self._listener:
            try:
                self._listener(copy.deepcopy(self._snapshot))
            except Exception:
                pass

    def _persist(self) -> None:
        try:
            self._store.save(self._snapshot)
        except OSError:
            pass
