from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from globalManagers.ConfigManager import ConfigManager
from webui.app_api.exceptions import CancelRunning

from .models import ActionPlan, OperationResult
from .tasks import TaskRegistry


class ActionPlanService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._plans: Dict[str, ActionPlan] = {}

    def build(self, action_id: str, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        inputs = dict(inputs or {})
        if action_id != "install-recommended-localization":
            raise ValueError(f"Unsupported action: {action_id}")

        configured_path = ConfigManager().get("game_path", "") or ""
        game_path = Path(configured_path) if configured_path else None
        game_ready = bool(game_path and (game_path / "LimbusCompany.exe").is_file())
        inputs.setdefault("provider", "llc")
        inputs.setdefault("download_source", "github")
        inputs.setdefault("zip_type", "zip")
        blockers = [] if game_ready else ["请先设置有效的 Limbus Company 游戏目录"]
        plan = ActionPlan(
            id=uuid.uuid4().hex,
            action_id=action_id,
            title="安装推荐汉化",
            inputs=inputs,
            steps=[
                {"id": "preflight", "title": "检查游戏目录与写入权限"},
                {"id": "download", "title": "下载并准备零协汉化包"},
                {"id": "install", "title": "安装到游戏语言目录"},
                {"id": "verify", "title": "确认汉化包已可用"},
            ],
            changes=["下载目录将保存一份可复用的汉化包", "游戏语言目录将写入 LLC_zh-CN"],
            warnings=blockers,
            requirements=["可访问汉化下载源", "游戏目录可写"],
            can_execute=not blockers,
        )
        with self._lock:
            self._plans[plan.id] = plan
        return plan.to_dict()

    def get(self, plan_id: str) -> Optional[ActionPlan]:
        with self._lock:
            return self._plans.get(plan_id)

    def execute(self, plan_id: str, api, tasks: TaskRegistry) -> Dict[str, Any]:
        plan = self.get(plan_id)
        if plan is None:
            raise ValueError("Action plan not found")
        if not plan.can_execute:
            raise ValueError("Action plan has unresolved blockers")

        task = tasks.create("localization-install", plan.title, can_cancel=True)
        threading.Thread(
            target=self._run_install,
            args=(plan, task["id"], api, tasks),
            name=f"lcta-task-{task['id'][:8]}",
            daemon=True,
        ).start()
        return task

    def _run_install(self, plan: ActionPlan, task_id: str, api, tasks: TaskRegistry) -> None:
        from webutils.function_llc import function_llc_main
        from webutils.packages.install import install_translation_package
        from webutils.utils import get_cache_font

        api.add_modal_id(task_id)
        tasks.update(task_id, state="running", stage="preflight", progress=3, message="正在检查游戏目录")
        try:
            game_path = Path(ConfigManager().get("game_path", "") or "")
            if not (game_path / "LimbusCompany.exe").is_file():
                raise RuntimeError("游戏目录无效，请重新选择 Limbus Company 安装目录")

            package_dir = Path(ConfigManager().get("ui_default.install.package_directory", "") or Path.cwd())
            package_dir.mkdir(parents=True, exist_ok=True)
            cache_path = get_cache_font()
            use_cache = bool(cache_path and Path(cache_path).is_file())

            tasks.update(task_id, stage="download", progress=8, message="正在下载推荐汉化")
            api.init_github()
            package_path = function_llc_main(
                task_id,
                dump_default=False,
                download_source=plan.inputs.get("download_source", "github"),
                from_proxy=ConfigManager().get("ui_default.zero.use_proxy", True),
                zip_type=plan.inputs.get("zip_type", "zip"),
                use_cache=use_cache,
                cache_path=cache_path,
                output_dir=str(package_dir),
            )
            api.check_modal_running(task_id, log=False)
            if not package_path:
                raise RuntimeError("汉化包准备完成，但未返回可安装文件")

            tasks.update(task_id, stage="install", progress=92, message="正在写入游戏目录")
            success, message = install_translation_package(str(package_path), str(game_path), modal_id=task_id)
            if not success:
                raise RuntimeError(message)

            result = OperationResult(
                success=True,
                summary="推荐汉化已安装",
                changed_items=[str(package_path), str(game_path / "LimbusCompany_Data" / "Lang" / "LLC_zh-CN")],
                next_actions=[
                    {"id": "open-launcher", "title": "启动游戏"},
                    {"id": "open-library", "title": "查看已安装内容"},
                ],
            )
            tasks.update(
                task_id,
                state="succeeded",
                stage="complete",
                progress=100,
                message=result.summary,
                can_cancel=False,
                result=result.to_dict(),
            )
        except CancelRunning:
            tasks.update(task_id, state="cancelled", stage="cancelled", message="安装已取消", can_cancel=False)
        except Exception as exc:
            tasks.append_log(task_id, str(exc))
            tasks.update(
                task_id,
                state="failed",
                stage="failed",
                message=str(exc),
                can_cancel=False,
                can_retry=True,
                errors=[str(exc)],
                result=OperationResult(
                    success=False,
                    summary="推荐汉化安装失败",
                    failed_items=[str(exc)],
                    recovery="检查网络、游戏目录权限后重试；也可打开旧版界面使用自定义来源。",
                ).to_dict(),
            )
        finally:
            api.del_modal_list(task_id)
