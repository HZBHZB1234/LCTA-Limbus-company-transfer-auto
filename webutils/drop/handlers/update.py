from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from ..context import FileExecutionContext
from ..handler import DropFileHandler
from ..inspect import ZipFormatInspection
from ...packages.clean import _sanitize_zip_member_name
from ...update import Updater
from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager

_log_manager = LogManager()


class UpdatePackageHandler(DropFileHandler):
    """更新包安装。"""

    file_type = 'update'
    label = '更新包'
    action_label = '更新包'

    def detect(self, item: Any) -> str | None:
        if isinstance(item, ZipFormatInspection):
            non_json_names = item.non_json_names
            if (
                any('requirements.txt' in name for name in non_json_names)
                and any('start_webui.py' in name for name in non_json_names)
            ):
                return self.file_type
        return None

    def _validate_zip_members(self, zip_path: str | os.PathLike[str]) -> None:
        """校验 zip 成员名安全性，拒绝含 `..` 段、绝对路径或盘符的成员，防止路径穿越"""
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for info in zip_ref.infolist():
                _sanitize_zip_member_name(info.filename)

    def execute(self, context: FileExecutionContext) -> str:
        _log_manager.log_modal_process(
            f"正在安装更新包: {context.file_name}", context.modal_id)
        self.update_progress(context)

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._validate_zip_members(context.file_path)
            with zipfile.ZipFile(context.file_path, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)

            source_dir = Path(tmp_dir)
            for item in os.listdir(tmp_dir):
                item_path = Path(tmp_dir) / item
                if (
                    item_path.is_dir()
                    and (item_path / 'start_webui.py').exists()
                    and (item_path / 'requirements.txt').exists()
                ):
                    source_dir = item_path
                    break

            cfg = ConfigManager()
            updater = Updater(
                "HZBHZB1234", "LCTA-Limbus-company-transfer-auto",
                delete_old_files=cfg.get("delete_updating", True),
                use_proxy=cfg.get("update_use_proxy", True),
                only_stable=cfg.get("update_only_stable", False),
                modal_id=context.modal_id,
            )
            updater.install_requirements(str(source_dir))
            _log_manager.check_running(context.modal_id)
            if not updater.update_files(source_dir):
                raise RuntimeError("更新文件失败")

        _log_manager.log_modal_process(
            f"更新包安装完成，请手动重启程序: {context.file_name}",
            context.modal_id,
        )
        return 'updated'
