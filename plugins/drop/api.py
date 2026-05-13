"""拖拽插件 —— 支持拖拽汉化包文件到窗口进行安装。"""

from webui.app import api_expose
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from webutils import evalFile, makeMessage, evalFiles


@api_expose
def handle_dropped_files(framework, files_data: list) -> dict:
    """处理前端拖拽的文件数据。"""
    file_info = {file: evalFile(file) for file in files_data}
    message = makeMessage(file_info)
    if message == 'invalid':
        return {"success": False, "message": "禁止同时进行更新与其他操作"}
    if message == 'none':
        return {"success": False, "message": "无文件"}
    return {"success": True, "message": message, "file_info": file_info}


@api_expose
def eval_dropped_files(framework, files_data: list, modal_id: str = "false") -> dict:
    """从拖拽的文件安装汉化包。"""
    evalFiles(files_data, configManager.config, logManager, modal_id)
    return {"success": True, "message": "安装完成"}
