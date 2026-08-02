from __future__ import annotations

import os
import shutil
from typing import Any

from ..context import FileExecutionContext
from ..handler import DropFileHandler, remove_existing
from ..inspect import JsonFormatInspection
from ...packages.manage import safe_join_path
from globalManagers.LogManager import LogManager

_log_manager = LogManager()


class CopyToModsBase(DropFileHandler):
    """单文件复制类分支共用实现：复制到 mod 目录。"""

    def execute(self, context: FileExecutionContext) -> str:
        _log_manager.log_modal_process(
            f"正在安装{self.label}: {context.file_name}", context.modal_id)

        target_path = safe_join_path(str(context.mod_path), context.file_name)
        remove_existing(target_path)
        shutil.copy2(context.file_path, str(context.mod_path))

        _log_manager.log_modal_process(
            f"{self.label}安装完成: {context.file_name}", context.modal_id)
        return 'modded'


class CarraHandler(CopyToModsBase):
    """贴图模组。"""

    file_type = 'carra'
    label = '贴图模组'

    def detect(self, item: Any) -> str | None:
        if isinstance(item, str) and os.path.splitext(item)[1].lower() == '.carra2':
            return self.file_type
        return None


class BankHandler(CopyToModsBase):
    """音效模组。"""

    file_type = 'bank'
    label = '音效模组'

    def detect(self, item: Any) -> str | None:
        if isinstance(item, str) and os.path.splitext(item)[1].lower() == '.bank':
            return self.file_type
        return None


class TextFileHandler(CopyToModsBase):
    """文本内容替换包（JSON 形式）。"""

    file_type = 'textFile'
    label = '文本内容替换包'

    def detect(self, item: Any) -> str | None:
        if isinstance(item, JsonFormatInspection):
            data = item.data
            if isinstance(data, dict) and 'dataList' in data:
                return self.file_type
        return None


class LCTAChangeHandler(CopyToModsBase):
    """LCTA 文本修改包。"""

    file_type = 'LCTAchange'
    label = 'LCTA文本修改包'

    def detect(self, item: Any) -> str | None:
        if isinstance(item, JsonFormatInspection):
            data = item.data
            if isinstance(data, dict) and 'patches' in data:
                return self.file_type
        return None


class FLChangeHandler(CopyToModsBase):
    """浮士德启动器格式文本修改包。"""

    file_type = 'FLchange'
    label = '浮士德启动器格式文本修改包'

    def detect(self, item: Any) -> str | None:
        if isinstance(item, JsonFormatInspection):
            data = item.data
            if (
                isinstance(data, dict)
                and all(
                    isinstance(value, dict) and 'dataList' in value
                    for value in data.values()
                )
            ):
                return self.file_type
        return None
