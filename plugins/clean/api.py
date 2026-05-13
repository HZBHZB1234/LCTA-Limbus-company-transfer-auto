"""清理插件 —— 清除游戏缓存和临时文件。"""

from pathlib import Path

from webui.app import api_expose, CancelRunning
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from webutils import clean_config_main


@api_expose
def clean_cache(framework, modal_id: str = "false", custom_files=None,
                clean_progress=None, clean_notice=None, clean_mods=None) -> dict:
    """清理缓存。"""
    try:
        if custom_files is None:
            custom_files = []
        if clean_progress is None:
            clean_progress = configManager.get("ui_default.clean.clean_progress", False)
        if clean_notice is None:
            clean_notice = configManager.get("ui_default.clean.clean_notice", False)
        if clean_mods is None:
            clean_mods = configManager.get("ui_default.clean.clean_mods", False)

        if clean_mods:
            roaming_path = Path.home() / "AppData" / "Roaming"
            mods_path = roaming_path / "LimbusCompanyMods"
            custom_files.append(mods_path)

        logManager.ModalLog("开始清除缓存...", modal_id)
        clean_config_main(
            modal_id=modal_id, logger_=logManager,
            clean_progress=clean_progress, clean_notice=clean_notice,
            custom_files=custom_files
        )
        return {"success": True, "message": "缓存清除成功"}
    except CancelRunning:
        return {"success": False, "message": "已取消"}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}
