from __future__ import annotations

from typing import Any

from ..context import FileExecutionContext
from ..handler import DropFileHandler
from globalManagers.LogManager import LogManager

_log_manager = LogManager()


class InvalidHandler(DropFileHandler):
    """无效文件：跳过。"""

    file_type = 'invalid'
    label = '无效的文件'

    def detect(self, item: Any) -> str | None:
        return None

    def execute(self, context: FileExecutionContext) -> str:
        _log_manager.log_modal_process(
            f"跳过无效文件: {context.file_name}", context.modal_id)
        return 'skipped'
