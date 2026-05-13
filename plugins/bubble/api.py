"""气泡插件 —— 气泡文本模组。"""

from webui.app import api_expose
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from webutils import function_bubble_main


@api_expose
def download_bubble(framework, modal_id: str = "false") -> dict:
    """下载气泡模组。"""
    try:
        logManager.ModalLog("开始下载...", modal_id)
        function_bubble_main(modal_id, logManager, configManager.config)
        return {"success": True, "message": "下载完成"}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}
