import json
import time
from pathlib import Path

import pytest

from globalManagers.ConfigManager import ConfigManager
from launcher.pipeline import LaunchPipeline, PHASE_INIT, PHASE_LAUNCH, PHASE_RUNNING
from product.actions import ActionPlanService
from product.launcher_session import LaunchSessionService, LaunchSessionStore
from product.tasks import TaskRegistry
from product.workspace import WorkspaceService


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    default_path = tmp_path / "config_default.json"
    schema_path = tmp_path / "config_check.json"
    default_data = {
        "game_path": "",
        "theme": "dark",
        "launcher": {
            "work": {
                "update": "no",
                "mod": False,
                "cdn_optimize": False,
                "ui_mode": "webview",
            },
            "resource_update": {"enabled": False},
        },
        "ui_default": {
            "install": {"package_directory": ""},
            "zero": {"use_proxy": True},
        },
    }
    config_path.write_text(json.dumps(default_data), encoding="utf-8")
    default_path.write_text(json.dumps(default_data), encoding="utf-8")
    schema_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("path_", str(tmp_path))

    ConfigManager._instance = None
    ConfigManager._initialized = False
    manager = ConfigManager(str(config_path), str(default_path), str(schema_path))
    yield manager
    ConfigManager._instance = None
    ConfigManager._initialized = False


def test_workspace_snapshot_blocks_when_game_path_missing(isolated_config, tmp_path):
    service = WorkspaceService(LaunchSessionStore(tmp_path / "launcher.json"))

    snapshot = service.get_snapshot()

    assert snapshot["health"] == "blocked"
    assert snapshot["game"]["ready"] is False
    assert snapshot["recommended_actions"][0]["id"] == "configure-game-path"
    assert snapshot["recommended_actions"][0]["recommended"] is True


def test_workspace_snapshot_recommends_install_for_clean_game(isolated_config, tmp_path):
    game_path = tmp_path / "Limbus Company"
    game_path.mkdir()
    (game_path / "LimbusCompany.exe").write_bytes(b"game")
    isolated_config.set("game_path", str(game_path))

    snapshot = WorkspaceService(LaunchSessionStore(tmp_path / "launcher.json")).get_snapshot()

    assert snapshot["health"] == "attention"
    install_action = next(action for action in snapshot["recommended_actions"] if action["id"] == "install-recommended-localization")
    assert install_action["recommended"] is True
    assert install_action["availability"] == "available"


def test_workspace_snapshot_lists_installed_packages(isolated_config, tmp_path):
    game_path = tmp_path / "Limbus Company"
    package_path = game_path / "LimbusCompany_Data" / "Lang" / "LLC_zh-CN"
    package_path.mkdir(parents=True)
    (game_path / "LimbusCompany.exe").write_bytes(b"game")
    isolated_config.set("game_path", str(game_path))

    snapshot = WorkspaceService(LaunchSessionStore(tmp_path / "launcher.json")).get_snapshot()

    assert snapshot["health"] == "healthy"
    assert snapshot["localization"]["installed"] is True
    assert snapshot["localization"]["packages"][0]["name"] == "LLC_zh-CN"


def test_action_plan_has_blocker_without_game_path(isolated_config):
    plan = ActionPlanService().build("install-recommended-localization")

    assert plan["can_execute"] is False
    assert plan["warnings"]


def test_action_plan_is_executable_for_valid_game(isolated_config, tmp_path):
    game_path = tmp_path / "game"
    game_path.mkdir()
    (game_path / "LimbusCompany.exe").write_bytes(b"game")
    isolated_config.set("game_path", str(game_path))

    plan = ActionPlanService().build("install-recommended-localization")

    assert plan["can_execute"] is True
    assert [step["id"] for step in plan["steps"]] == ["preflight", "download", "install", "verify"]


def test_task_registry_tracks_progress_logs_and_cancel():
    registry = TaskRegistry()
    task = registry.create("demo", "演示任务")

    registry.update(task["id"], state="running", progress=140, message="执行中")
    registry.append_log(task["id"], "第一条日志")

    updated = registry.get(task["id"])
    assert updated["progress"] == 100
    assert updated["logs"][-1]["message"] == "第一条日志"
    assert registry.request_cancel(task["id"]) is True
    assert registry.get(task["id"])["state"] == "cancelling"


def test_launcher_session_maps_pipeline_phases(isolated_config, tmp_path):
    store = LaunchSessionStore(tmp_path / "launcher.json")
    service = LaunchSessionService(store)

    def run(progress):
        pipeline = LaunchPipeline()
        progress.register_to_pipeline(pipeline)
        pipeline.emit(PHASE_INIT)
        pipeline.emit(PHASE_LAUNCH)
        pipeline.context["game_pid"] = 1234
        pipeline.emit(PHASE_RUNNING)

    service.start(run)
    for _ in range(100):
        snapshot = service.get_snapshot()
        if snapshot["state"] == "succeeded":
            break
        time.sleep(0.01)

    snapshot = service.get_snapshot()
    assert snapshot["state"] == "succeeded"
    assert snapshot["game_process"]["pid"] == 1234
    assert store.load()["id"] == snapshot["id"]


def test_default_launcher_mode_is_webview():
    config = json.loads(Path("config_default.json").read_text(encoding="utf-8"))
    assert config["launcher"]["work"]["ui_mode"] == "webview"
