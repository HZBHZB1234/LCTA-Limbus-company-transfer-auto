"""专有词汇插件 —— 从 Wiki 抓取专有词汇。"""

from webui.app import api_expose, CancelRunning
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from webutils import function_fetch_main


@api_expose
def fetch_proper_nouns(framework, modal_id: str = "false") -> dict:
    """抓取专有词汇。"""
    try:
        logManager.ModalLog("开始抓取专有词汇...", modal_id)
        proper_config = configManager.get("ui_default.proper", {})
        function_fetch_main(modal_id, logManager, **proper_config)
        return {"success": True, "message": "专有词汇抓取成功"}
    except CancelRunning:
        return {"success": False, "message": "已取消"}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}
