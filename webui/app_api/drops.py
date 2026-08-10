# -*- coding: utf-8 -*-
"""LCTA_API 拖拽文件：分析/回调/安装。"""
import json
from webutils.drop import evalFile, makeMessage, evalFiles
from webui.app_api.exceptions import CancelRunning

class DropMixin:

    def handle_dropped_files(self, files_data):
        """处理前端拖拽的文件数据"""
        try:
            if not files_data:
                return {"success": False, "message": "无文件"}
            file_info = {file: evalFile(file) for file in files_data}
            message = makeMessage(file_info)
            if message == 'invalid':
                return {"success": False, "message": "禁止同时进行更新与其他操作"}
            if message == 'none':
                return {"success": False, "message": "无有效文件"}
            return {"success": True, "message": message, "file_info": file_info}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": f"分析拖入文件时出错: {str(e)}"}

    def on_drop(self, e):
        files = e['dataTransfer']['files']
        file_paths = [file['pywebviewFullPath'] for file in files if file.get('pywebviewFullPath')]
        file_paths_json = json.dumps(file_paths)
        self._window.evaluate_js(f"dragDropManager.hideMaskImmediate();dragDropManager.onFileDropCallback({file_paths_json})")

        print(f'Event: {e["type"]}. Dropped files:')

        for file in files:
            print(file.get('pywebviewFullPath'))

    def eval_dropped_files(self, files_data, modal_id="false"):
        """从拖拽的文件安装汉化包"""
        try:
            result = evalFiles(files_data, modal_id)
            return result
        except CancelRunning:
            self.log('文件安装任务已取消')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}
