"""安装插件 —— 从本地安装和管理汉化包。"""

import os

from webui.app import api_expose
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from webutils import (
    find_translation_packages,
    delete_translation_package,
    install_translation_package,
    toggle_install_package,
)


@api_expose
def get_translation_packages(framework) -> dict:
    """获取翻译包列表。"""
    try:
        target_dir = configManager.get("ui_default.install.package_directory", "")
        if not target_dir:
            target_dir = os.getcwd()
        packages = find_translation_packages(target_dir)
        logManager.info(f"找到 {len(packages)} 个翻译包")
        return {"success": True, "packages": packages}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def delete_translation_package_api(framework, package_name: str) -> dict:
    """删除指定的翻译包。"""
    try:
        target_path = configManager.get("ui_default.install.package_directory", "")
        if not target_path:
            target_path = os.getcwd()
        result = delete_translation_package(package_name, target_path, logManager)
        return result
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def install_translation(framework, package_name: str = None, modal_id: str = "false") -> dict:
    """安装翻译包。"""
    try:
        if package_name is None:
            return {"success": False, "message": "传参错误"}

        game_path = configManager.get("game_path", "")
        if not game_path:
            return {"success": False, "message": "请先设置游戏路径"}

        logManager.ModalLog(f"开始安装汉化包: {package_name}", modal_id)

        package_dir = configManager.get("ui_default.install.package_directory", "")
        if not package_dir:
            package_dir = os.getcwd()

        package_path = os.path.join(package_dir, package_name)
        success, message = install_translation_package(
            package_path, game_path,
            logger_=logManager, modal_id=modal_id
        )

        return {"success": success, "message": message}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def toggle_installed_package(framework, able) -> dict:
    """切换翻译包启用状态。"""
    try:
        changed = toggle_install_package(configManager.config, able)
        return {"success": True, "changed": changed}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}
