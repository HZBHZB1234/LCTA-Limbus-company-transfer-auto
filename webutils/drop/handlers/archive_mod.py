from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

from ..context import FileExecutionContext
from ..handler import DropFileHandler, remove_existing
from ..inspect import FolderFormatInspection, ZipFormatInspection
from ...packages.clean import _sanitize_zip_member_name
from ...packages.manage import safe_join_path
from ...utils.io import extract_zip_smartly
from globalManagers.LogManager import LogManager

_log_manager = LogManager()


class ArchiveModBase(DropFileHandler):
    """压缩模组包（FLmod / jsononly）共用实现：解压到 mod 目录。"""

    def _zip_extract_root(self, zip_path: str | os.PathLike[str]) -> str | None:
        """返回 zip 按 extract_zip_smartly 解压后的实际根名（用于预删除对齐）。
        单根目录返回该根名，多根目录返回 zip 文件名（不含扩展名）。"""
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            root_items = set()
            for info in zip_ref.infolist():
                _sanitize_zip_member_name(info.filename)
                root_item = (info.filename.split('/')[0]
                             if '/' in info.filename else info.filename)
                if root_item:
                    root_items.add(root_item)
            if not root_items:
                return None
        if len(root_items) == 1:
            return next(iter(root_items))
        return Path(zip_path).stem

    def execute(self, context: FileExecutionContext) -> str:
        _log_manager.log_modal_process(
            f"正在安装{self.action_name}: {context.file_name}", context.modal_id)
        self.update_progress(context)

        if Path(context.file_path).suffix.lower() == '.zip':
            target_name = self._zip_extract_root(context.file_path)
            if target_name:
                remove_existing(
                    safe_join_path(str(context.mod_path), target_name))
            extract_zip_smartly(context.file_path, str(context.mod_path))
        else:
            target_path = safe_join_path(
                str(context.mod_path), Path(context.file_path).name)
            remove_existing(target_path)
            shutil.copytree(context.file_path, target_path)

        _log_manager.log_modal_process(
            f"{self.action_name}安装完成: {context.file_name}", context.modal_id)
        return 'modded'


class FLModHandler(ArchiveModBase):
    """浮士德启动器格式模组。"""

    file_type = 'FLmod'
    label = '浮士德启动器格式模组'
    action_label = '模组'

    def detect(self, item: Any) -> str | None:
        if isinstance(item, ZipFormatInspection):
            if any('mod_info.json' in name for name in item.names):
                return self.file_type
        elif isinstance(item, FolderFormatInspection):
            if 'mod_info.json' in item.items:
                return self.file_type
        return None


class JsonOnlyHandler(ArchiveModBase):
    """文本内容替换包（压缩包形式）。"""

    file_type = 'jsononly'
    label = '文本内容替换包'
    action_label = '文本替换包'

    def detect(self, item: Any) -> str | None:
        if isinstance(item, ZipFormatInspection):
            if item.non_json_amount >= 3:
                return self.file_type
        elif isinstance(item, FolderFormatInspection):
            if len(item.items) >= 3:
                return self.file_type
        return None
