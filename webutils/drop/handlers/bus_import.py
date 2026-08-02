from __future__ import annotations

from typing import Any

from ..context import FileExecutionContext
from ..handler import DropFileHandler
from ..inspect import JsonFormatInspection
from ...bus_engine import is_bus_ruleset, is_tiaozhua_config
from ...function_fancy import import_bus_rules_file
from globalManagers.LogManager import LogManager

_log_manager = LogManager()


class BusImportHandler(DropFileHandler):
    """巴士替换规则配置导入。"""

    file_type = 'busimport'
    label = '巴士替换规则配置'

    def detect(self, item: Any) -> str | None:
        if isinstance(item, JsonFormatInspection):
            if is_bus_ruleset(item.data) or is_tiaozhua_config(item.data):
                return self.file_type
        return None

    def execute(self, context: FileExecutionContext) -> str:
        _log_manager.log_modal_process(
            f"正在导入巴士规则: {context.file_name}", context.modal_id)
        imported = import_bus_rules_file(context.file_path)
        stats = imported['stats']
        _log_manager.log_modal_process(
            f"规则导入完成: {imported['ruleset_name']}，"
            f"{stats['converted_rules']} 条规则/"
            f"{stats.get('converted_actions', 0)} 个操作",
            context.modal_id,
        )
        return 'imported'
