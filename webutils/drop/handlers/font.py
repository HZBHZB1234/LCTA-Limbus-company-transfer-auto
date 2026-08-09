from __future__ import annotations

import os
from typing import Any

from ..context import FileExecutionContext
from ..handler import DropFileHandler
from ...utils.font import save_cache_font
from globalManagers.LogManager import LogManager

_log_manager = LogManager()

FONT_SUFFIXES = ('.ttf', '.otf')


class FontHandler(DropFileHandler):
    """自定义缓存字体：拖入 .ttf/.otf 替换缓存中的 ChineseFont.ttf。"""

    file_type = 'font'
    label = '缓存字体'

    def detect(self, item: Any) -> str | None:
        if isinstance(item, str) and os.path.splitext(item)[1].lower() in FONT_SUFFIXES:
            return self.file_type
        return None

    def execute(self, context: FileExecutionContext) -> str:
        _log_manager.log_modal_process(
            f"正在替换缓存字体: {context.file_name}", context.modal_id)
        save_cache_font(context.file_path)
        _log_manager.log_modal_process(
            f"缓存字体已替换: {context.file_name}", context.modal_id)
        return 'fonts'
