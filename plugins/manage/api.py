"""管理插件 —— 管理已安装的汉化包和模组。"""

from webui.app import api_expose
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from webutils import (
    find_installed_packages,
    use_translation_package,
    delete_installed_package,
    check_lang_enabled,
    fing_mod,
    toggle_mod,
    delete_mod,
    open_mod_path,
    check_symlink,
)


@api_expose
def get_installed_packages(framework) -> dict:
    """获取已安装的翻译包列表。"""
    try:
        game_path = configManager.get("game_path", "")
        enable = check_lang_enabled(game_path)
        if not enable:
            return {"success": True, "enable": False}
        packages, selected = find_installed_packages(configManager.config)
        logManager.info(f"找到 {len(packages)} 个翻译包")
        return {"success": True, "packages": packages, "selected": selected, "enable": True}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def delete_installed_package_api(framework, package_name: str) -> dict:
    """删除已安装的翻译包。"""
    try:
        return delete_installed_package(package_name, configManager.config)
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def use_translation(framework, package_name: str = None, modal_id: str = "false") -> dict:
    """切换使用的汉化包。"""
    try:
        logManager.ModalLog(f"开始切换汉化包: {package_name}", modal_id)
        success = use_translation_package(package_name, configManager.config)
        if success:
            return {"success": True, "message": "成功切换汉化包"}
        return {"success": False, "message": "切换汉化包失败"}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def find_installed_mod(framework) -> dict:
    """查找已安装的模组。"""
    try:
        able, disable = fing_mod(configManager.config)
        return {"success": True, "able": able, "disable": disable}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def toggle_mod_api(framework, mod_name: str, enable: bool) -> dict:
    """切换模组启用状态。"""
    try:
        logManager.info(f"修改mod可用性 {mod_name} 为 {enable}")
        changed = toggle_mod(configManager.config, mod_name, enable)
        return {"success": True, "changed": changed}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def delete_mod_api(framework, mod_name: str, enable: bool) -> dict:
    """删除模组。"""
    try:
        logManager.info(f"删除mod {mod_name} 状态 {enable}")
        success = delete_mod(configManager.config, mod_name, enable)
        return {"success": success, "message": ""}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def open_mod_path_api(framework) -> dict:
    """打开模组文件夹。"""
    try:
        logManager.info("打开mod文件夹")
        open_mod_path(configManager.config)
        return {"success": True, "message": ""}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def get_symlink_status(framework) -> dict:
    """获取软链接状态。"""
    try:
        result = check_symlink()
        return {"success": True, "status": result}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}
