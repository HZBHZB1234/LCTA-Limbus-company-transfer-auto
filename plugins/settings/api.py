"""设置插件 —— 基础配置管理。"""

import os

from webui.app import api_expose
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager


@api_expose
def save_settings(framework, game_path: str, debug_mode: bool,
                  auto_update: bool) -> dict:
    """保存基础设置。"""
    try:
        configManager.set("game_path", game_path)
        configManager.set("debug", debug_mode)
        configManager.set("auto_check_update", auto_update)
        logManager.info(f"设置已保存: 游戏路径={game_path}, 调试模式={debug_mode}")
        return {"success": True, "message": "设置保存成功"}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def use_default_config(framework) -> dict:
    """使用默认配置。"""
    try:
        configManager.load_config_default()
        configManager.config = configManager._default
        logManager.info("已重置为默认配置")
        return {"success": True, "message": "已重置为默认配置"}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def reset_config(framework) -> dict:
    """重置配置。"""
    try:
        config_path = "config.json"
        if os.path.exists(config_path):
            os.remove(config_path)
        configManager.load_config_default()
        configManager.config = configManager._default
        logManager.info("配置已重置")
        return {"success": True, "message": "配置已重置"}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}
