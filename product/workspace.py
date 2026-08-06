from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from globalManagers.ConfigManager import ConfigManager

from .launcher_session import LaunchSessionStore
from .models import ActionDescriptor, Issue, SCHEMA_VERSION, utc_now_iso


class WorkspaceService:
    def __init__(self, launcher_store: Optional[LaunchSessionStore] = None) -> None:
        self.launcher_store = launcher_store or LaunchSessionStore()

    def get_snapshot(self) -> Dict[str, Any]:
        config = ConfigManager()
        configured_path = config.get("game_path", "") or ""
        game_path = Path(configured_path) if configured_path else None
        game_executable = game_path / "LimbusCompany.exe" if game_path else None
        game_ready = bool(game_executable and game_executable.is_file())
        packages = self._installed_packages(game_path) if game_ready and game_path else []
        issues: List[Issue] = []

        if not game_ready:
            issues.append(Issue(
                id="game-path-missing",
                severity="blocking",
                title="尚未找到游戏目录",
                summary="设置 Limbus Company 安装目录后，LCTA 才能安装汉化并启动游戏。",
                action_id="configure-game-path",
            ))
        elif not packages:
            issues.append(Issue(
                id="localization-missing",
                severity="recommended",
                title="尚未安装汉化",
                summary="可以直接安装推荐汉化方案，默认选项已为新用户准备好。",
                action_id="install-recommended-localization",
            ))

        health = "blocked" if any(issue.severity == "blocking" for issue in issues) else (
            "attention" if issues else "healthy"
        )
        actions = self._actions(game_ready, bool(packages))
        launcher_session = self.launcher_store.load()
        config_payload = json.dumps(config.raw, sort_keys=True, ensure_ascii=False, default=str)
        revision_source = config_payload + json.dumps(launcher_session or {}, sort_keys=True, ensure_ascii=False)

        return {
            "schema_version": SCHEMA_VERSION,
            "revision": hashlib.sha256(revision_source.encode("utf-8")).hexdigest()[:16],
            "generated_at": utc_now_iso(),
            "health": health,
            "headline": self._headline(health, bool(packages)),
            "game": {
                "path": str(game_path) if game_path else "",
                "executable": str(game_executable) if game_executable else "",
                "ready": game_ready,
            },
            "localization": {
                "installed": bool(packages),
                "packages": packages,
                "count": len(packages),
            },
            "issues": [issue.__dict__ for issue in issues],
            "recommended_actions": [action.__dict__ for action in actions],
            "launcher_session": launcher_session,
            "theme": config.get("theme", "dark"),
            "legacy_ui_available": (Path(os.getenv("path_", "") or os.getcwd()) / "webui" / "index.html").is_file(),
        }

    @staticmethod
    def _headline(health: str, has_packages: bool) -> str:
        if health == "blocked":
            return "先完成一项设置，就可以开始使用"
        if not has_packages:
            return "游戏已找到，下一步安装推荐汉化"
        return "环境状态良好，可以直接开始工作"

    @staticmethod
    def _actions(game_ready: bool, has_packages: bool) -> List[ActionDescriptor]:
        return [
            ActionDescriptor(
                id="configure-game-path",
                title="设置游戏目录",
                summary="定位 Limbus Company 安装目录",
                intent="settings/game-path",
                availability="available" if not game_ready else "completed",
                recommended=not game_ready,
            ),
            ActionDescriptor(
                id="install-recommended-localization",
                title="安装推荐汉化",
                summary="下载、校验并安装零协汉化包",
                intent="workbench/localization",
                availability="available" if game_ready else "blocked",
                blockers=[] if game_ready else ["请先设置有效的游戏目录"],
                recommended=game_ready and not has_packages,
            ),
            ActionDescriptor(
                id="open-launcher",
                title="启动游戏",
                summary="打开 Launcher GUI 并查看本次启动计划",
                intent="launcher/start",
                availability="available" if game_ready else "blocked",
                blockers=[] if game_ready else ["请先设置有效的游戏目录"],
                recommended=game_ready and has_packages,
            ),
        ]

    @staticmethod
    def _installed_packages(game_path: Path) -> List[Dict[str, Any]]:
        candidates = [
            game_path / "LimbusCompany_Data" / "Lang",
            game_path / "LimbusCompany_Data" / "lang",
        ]
        package_root = next((path for path in candidates if path.is_dir()), None)
        if package_root is None:
            return []
        return [
            {"id": child.name, "name": child.name, "path": str(child)}
            for child in sorted(package_root.iterdir(), key=lambda path: path.name.lower())
            if child.is_dir()
        ]
