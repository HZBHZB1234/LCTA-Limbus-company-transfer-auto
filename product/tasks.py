from __future__ import annotations

import copy
import threading
import uuid
from typing import Any, Dict, List, Optional

from .models import SCHEMA_VERSION, utc_now_iso


TERMINAL_STATES = {"succeeded", "failed", "cancelled"}


class TaskRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: Dict[str, Dict[str, Any]] = {}

    def create(self, kind: str, title: str, can_cancel: bool = True) -> Dict[str, Any]:
        task_id = uuid.uuid4().hex
        task = {
            "schema_version": SCHEMA_VERSION,
            "id": task_id,
            "kind": kind,
            "title": title,
            "state": "queued",
            "stage": "queued",
            "progress": 0,
            "message": "等待执行",
            "can_cancel": can_cancel,
            "can_retry": False,
            "cancel_requested": False,
            "result": None,
            "errors": [],
            "logs": [],
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        with self._lock:
            self._tasks[task_id] = task
        return copy.deepcopy(task)

    def update(self, task_id: str, **changes: Any) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            if "progress" in changes:
                changes["progress"] = max(0, min(100, int(changes["progress"])))
            task.update(changes)
            task["updated_at"] = utc_now_iso()
            return copy.deepcopy(task)

    def append_log(self, task_id: str, message: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["logs"].append({"time": utc_now_iso(), "message": str(message)})
            task["logs"] = task["logs"][-200:]
            task["updated_at"] = utc_now_iso()

    def request_cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task["state"] in TERMINAL_STATES or not task["can_cancel"]:
                return False
            task.update({
                "cancel_requested": True,
                "state": "cancelling",
                "message": "正在取消",
                "updated_at": utc_now_iso(),
            })
            return True

    def is_cancel_requested(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            return bool(task and task.get("cancel_requested"))

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            return copy.deepcopy(task) if task else None

    def list(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            tasks = sorted(
                self._tasks.values(),
                key=lambda item: item["updated_at"],
                reverse=True,
            )
            return copy.deepcopy(tasks[:limit])
