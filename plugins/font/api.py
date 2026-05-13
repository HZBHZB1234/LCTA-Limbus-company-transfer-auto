"""字体插件 —— 管理系统字体，为汉化包更换字体。"""

from webui.app import api_expose
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from webutils import (
    get_system_fonts,
    export_system_font,
    change_font_for_package,
)


@api_expose
def get_system_fonts_list(framework) -> dict:
    """获取系统字体列表。"""
    try:
        result = get_system_fonts()
        if result.get("success"):
            logManager.info(f"成功获取系统字体列表，共 {len(result.get('fonts', []))} 个字体")
        return result
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def export_selected_font(framework, font_name: str, destination_path: str) -> dict:
    """导出选定的字体。"""
    try:
        logManager.info(f"开始导出字体 {font_name} 到 {destination_path}")
        result = export_system_font(font_name, destination_path, logManager)
        return result
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def change_font_for_package_api(framework, package_name: str, font_path: str,
                                modal_id: str = "false") -> dict:
    """为翻译包更换字体。"""
    try:
        logManager.info(f"开始为翻译包 {package_name} 更换字体")
        result = change_font_for_package(package_name, font_path, logManager, modal_id)
        if result[0]:
            return {"success": True, "message": result[1]}
        return {"success": False, "message": result[1]}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}
