"""
拖拽文件处理 Handler
处理前端拖放文件的评估和安装
"""

from . import BaseHandler


class DragDropHandler(BaseHandler):
    """拖拽文件处理器"""

    def handle_dropped(self, files_data: list) -> dict:
        """处理拖拽文件数据，返回文件信息"""
        from webutils.function_drop import evalFile, makeMessage

        file_info = {file: evalFile(file) for file in files_data}
        message = makeMessage(file_info)

        if message == 'invalid':
            return {"success": False, "message": "禁止同时进行更新与其他操作"}
        if message == 'none':
            return {"success": False, "message": "无文件"}

        return {"success": True, "message": message, "file_info": file_info}

    def eval_dropped(self, files_data: list, modal_id: str, current_files: list = None) -> dict:
        """评估并安装拖拽文件"""
        from webutils.function_drop import evalFiles

        evalFiles(files_data, self.config.raw, self.log, modal_id)
        return {"success": True, "message": "安装完成"}
