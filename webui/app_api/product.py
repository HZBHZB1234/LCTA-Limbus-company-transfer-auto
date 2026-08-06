# -*- coding: utf-8 -*-
"""Product-level APIs used by the redesigned main WebView."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from globalManagers.ConfigManager import ConfigManager
from product import ActionPlanService, TaskRegistry, WorkspaceService


class _ProductContext:
    def __init__(self) -> None:
        self.tasks = TaskRegistry()
        self.actions = ActionPlanService()
        self.workspace = WorkspaceService()


class ProductMixin:
    @property
    def product_context(self) -> _ProductContext:
        context = getattr(self, "_product_context", None)
        if context is None:
            context = _ProductContext()
            self._product_context = context
        return context

    def get_product_bootstrap(self):
        return {
            "workspace": self.product_context.workspace.get_snapshot(),
            "tasks": self.product_context.tasks.list(),
            "start_context": {
                "target": os.getenv("LCTA_START_TARGET", "home"),
                "payload": os.getenv("LCTA_START_CONTEXT", ""),
            },
        }

    def get_workspace_snapshot(self):
        return self.product_context.workspace.get_snapshot()

    def build_action_plan(self, action_id, inputs=None):
        return self.product_context.actions.build(action_id, inputs)

    def execute_action_plan(self, plan_id):
        return self.product_context.actions.execute(plan_id, self, self.product_context.tasks)

    def list_tasks(self, filters=None):
        limit = 20
        if isinstance(filters, dict):
            try:
                limit = int(filters.get("limit", limit))
            except (TypeError, ValueError):
                pass
        return self.product_context.tasks.list(limit=max(1, min(limit, 100)))

    def get_task(self, task_id):
        return self.product_context.tasks.get(task_id)

    def cancel_task(self, task_id):
        if not self.product_context.tasks.request_cancel(task_id):
            return {"success": False, "message": "任务当前不可取消"}
        self.set_modal_running(task_id, "cancel")
        return {"success": True, "task": self.product_context.tasks.get(task_id)}

    def open_launcher_window(self):
        root = Path(os.getenv("path_", "") or Path(__file__).resolve().parents[2])
        script = root / "start_webui.py"
        subprocess.Popen([sys.executable, str(script), "-launcher"], cwd=str(root), env=os.environ.copy())
        return {"success": True}

    def set_product_theme(self, theme):
        if theme not in {"light", "dark"}:
            return {"success": False, "message": "未知主题"}
        ConfigManager().set("theme", theme)
        return {"success": True, "theme": theme}

    def _update_product_task_from_modal(self, modal_id, **changes):
        if modal_id in {None, "false"} or not hasattr(self, "_product_context"):
            return
        if self.product_context.tasks.get(modal_id) is None:
            return
        message = changes.pop("log", None)
        if message:
            self.product_context.tasks.append_log(modal_id, message)
        if changes:
            self.product_context.tasks.update(modal_id, **changes)
