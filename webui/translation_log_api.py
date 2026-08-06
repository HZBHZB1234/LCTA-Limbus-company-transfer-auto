# -*- coding: utf-8 -*-
"""翻译诊断日志查看器的 JS-API 桥接。"""
from pathlib import Path
import webview

from globalManagers.ConfigManager import ConfigManager
from webutils.packages import open_explorer

class TranslationLogViewerAPI:
    """翻译诊断日志查看器的只读 JS-API 桥接。"""

    def __init__(self):
        from webutils.function_translation_logs import TranslationLogService

        self._service_class = TranslationLogService
        self._service = None
        self._file_id = None
        self._window = None

    def set_window(self, window):
        self._window = window

    def get_config_value(self, key_path, default_value=None):
        return ConfigManager().get(key_path, default_value)

    def choose_dump(self):
        if self._window is None:
            return {"success": False, "message": "日志窗口尚未初始化"}
        try:
            default_dir = Path.cwd() / "logs" / "translation_dump"
            if not default_dir.is_dir():
                default_dir = Path.cwd()
            selected = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                directory=str(default_dir),
                allow_multiple=False,
                file_types=("Translation Dump (*.jsonl)",),
            )
            if not selected:
                return {"success": False, "cancelled": True, "message": "已取消选择"}
            path = Path(selected[0]).resolve()
            service = self._service_class(path.parent)
            data = service.get_file_info(path.name, force_refresh=True)
            self._service = service
            self._file_id = path.name
            return {"success": True, "data": data}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def query_records(self, filters=None, page=1, page_size=50, force_refresh=False):
        if self._service is None or self._file_id is None:
            return {"success": False, "message": "请先选择要打开的 Dump 文件"}
        try:
            data = self._service.query_records(
                self._file_id,
                filters or {},
                page,
                page_size,
                bool(force_refresh),
            )
            return {"success": True, "data": data}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def get_record(self, line_number):
        if self._service is None or self._file_id is None:
            return {"success": False, "message": "请先选择要打开的 Dump 文件"}
        try:
            return {
                "success": True,
                "data": self._service.get_record(self._file_id, line_number),
            }
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def export_filtered(self, filters=None):
        if self._window is None:
            return {"success": False, "message": "日志窗口尚未初始化"}
        if self._service is None or self._file_id is None:
            return {"success": False, "message": "请先选择要打开的 Dump 文件"}
        try:
            from datetime import datetime

            stem = Path(self._file_id).stem
            default_name = f"{stem}_filtered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
            selected = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                directory=str(Path.cwd()),
                save_filename=default_name,
                file_types=("JSON Lines (*.jsonl)",),
            )
            if not selected:
                return {"success": False, "cancelled": True, "message": "已取消导出"}
            destination = selected[0]
            if Path(destination).suffix.lower() != ".jsonl":
                destination = f"{destination}.jsonl"
            data = self._service.export_filtered(self._file_id, filters or {}, destination)
            return {"success": True, "data": data}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def open_selected_folder(self):
        if self._service is None:
            return {"success": False, "message": "请先选择要打开的 Dump 文件"}
        try:
            open_explorer(self._service.log_dir)
            return {"success": True}
        except Exception as exc:
            return {"success": False, "message": str(exc)}
