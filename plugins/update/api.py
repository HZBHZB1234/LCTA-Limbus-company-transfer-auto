"""更新插件 —— 检查并安装 LCTA 工具箱更新。"""

import os

from webui.app import api_expose
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from webutils.update import Updater, get_app_version


@api_expose
def auto_check_update(framework) -> dict:
    """自动检查更新。"""
    try:
        if not configManager.get("auto_check_update", True):
            return {"has_update": False}

        current_version = get_app_version()
        logManager.info(f"当前版本: {current_version}")

        updater = Updater(
            "HZBHZB1234", "LCTA-Limbus-company-transfer-auto",
            delete_old_files=configManager.get("delete_updating", True),
            logger_=logManager,
            use_proxy=configManager.get("update_use_proxy", True),
            only_stable=configManager.get("update_only_stable", False)
        )
        return updater.check_for_updates(current_version)
    except Exception as e:
        logManager.exception(e)
        return {"has_update": False}


@api_expose
def manual_check_update(framework) -> dict:
    """手动检查更新。"""
    try:
        current_version = get_app_version()
        logManager.info(f"当前版本: {current_version}")

        updater = Updater(
            "HZBHZB1234", "LCTA-Limbus-company-transfer-auto",
            delete_old_files=configManager.get("delete_updating", True),
            logger_=logManager,
            use_proxy=configManager.get("update_use_proxy", True),
            only_stable=configManager.get("update_only_stable", False)
        )
        return updater.check_for_updates(current_version)
    except Exception as e:
        logManager.exception(e)
        return {"has_update": False}


@api_expose
def perform_update_in_modal(framework, modal_id: str) -> dict:
    """在模态窗口中执行更新。"""
    try:
        logManager.ModalLog("开始执行更新...", modal_id)

        if os.getenv('update') == 'False':
            logManager.ModalLog("当前处于打包环境，跳过更新", modal_id)
            return {"success": False, "message": "打包环境无法更新"}

        current_version = get_app_version()
        updater = Updater(
            "HZBHZB1234", "LCTA-Limbus-company-transfer-auto",
            delete_old_files=configManager.get("delete_updating", True),
            logger_=logManager,
            use_proxy=configManager.get("update_use_proxy", True),
            only_stable=configManager.get("update_only_stable", False)
        )
        return updater.check_and_update(current_version)
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}
