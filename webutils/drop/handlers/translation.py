from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from collections.abc import Iterable

from ..context import FileExecutionContext
from ..handler import DropFileHandler
from ..inspect import FolderFormatInspection, ZipFormatInspection
from ...packages.install import install_translation_package
from ...utils.io import decompress_7z
from globalManagers.LogManager import LogManager

_log_manager = LogManager()

_STRUCTURE_DIRS = (
    'BattleAnnouncerDlg',
    'BgmLyrics',
    'EGOVoiceDig',
    'PersonalityVoiceDlg',
    'StoryData',
)


class TranslationPackageBase(DropFileHandler):
    """汉化包（full / nofont）共用实现：包结构判定与安装。"""

    action_label = '汉化包'

    def _is_full_pkg_items(self, items: Iterable[str]) -> bool:
        """判断条目集合是否符合汉化包结构（结构目录特征全部出现）"""
        return all(any(folder in item for item in items) for folder in _STRUCTURE_DIRS)

    def _zip_top_items(self, namelist: Iterable[str]) -> tuple[set[str], set[str]]:
        """返回 (顶层条目, 包条目)。顶层仅一个目录条目（可有零散文件）时，
        包条目取其下一层，以识别单根目录包裹结构。"""
        top_names = set()
        dir_tops = set()
        for name in namelist:
            clean = name.replace('\\', '/').rstrip('/')
            parts = clean.split('/')
            top = parts[0] if parts else ''
            if top:
                top_names.add(top)
            if len(parts) >= 2 and top:
                dir_tops.add(top)
        if len(dir_tops) != 1:
            return top_names, top_names
        only = next(iter(dir_tops))
        prefix = only + '/'
        sub_names = set()
        for name in namelist:
            clean = name.replace('\\', '/').rstrip('/')
            if clean.startswith(prefix):
                rest = clean[len(prefix):]
                if rest:
                    sub_names.add(rest.split('/')[0])
        if not sub_names:
            return top_names, top_names
        return top_names, sub_names

    def _unwrap_items(self, inspection: FolderFormatInspection) -> tuple[str, ...]:
        """剥开单根目录包裹：顶层仅一个目录（可有零散文件）且该目录内含汉化包特征时，
        返回该目录的条目作为包根条目；否则返回原条目。"""
        dirs = [item for item in inspection.items
                if os.path.isdir(os.path.join(inspection.path, item))]
        if len(dirs) != 1:
            return inspection.items
        only_path = os.path.join(inspection.path, dirs[0])
        inner = tuple(os.listdir(only_path))
        if not self._is_full_pkg_items(inner):
            return inspection.items
        return inner

    def _detect_zip(self, inspection: ZipFormatInspection) -> str | None:
        _, package_names = self._zip_top_items(inspection.names)
        if not (self._is_full_pkg_items(package_names) and inspection.amount > 1500):
            return None
        return self._decide_has_font(inspection.has_font)

    def _detect_folder(self, inspection: FolderFormatInspection) -> str | None:
        package_items = self._unwrap_items(inspection)
        if not self._is_full_pkg_items(package_items):
            return None
        return self._decide_has_font(any('Font' in item for item in package_items))

    def _decide_has_font(self, has_font: bool) -> str | None:
        raise NotImplementedError

    def detect(self, item: Any) -> str | None:
        if isinstance(item, ZipFormatInspection):
            return self._detect_zip(item)
        if isinstance(item, FolderFormatInspection):
            return self._detect_folder(item)
        return None

    def _collect_package_dirs(self, root_dir: str | os.PathLike[str]) -> list[str]:
        """收集 7z 解压目录中的汉化包根目录列表。
        单根目录包裹时剥开包裹层；多顶层条目时仅目录项作为包根（文件项不构成汉化包结构，跳过）。"""
        items = sorted(os.listdir(root_dir))
        dirs = [os.path.join(root_dir, i) for i in items
                if os.path.isdir(os.path.join(root_dir, i))]
        if len(dirs) == 1:
            inner = dirs[0]
            if self._is_full_pkg_items(os.listdir(inner)):
                return [inner]
        return dirs

    def execute(self, context: FileExecutionContext) -> str:
        _log_manager.log_modal_process(
            f"正在安装汉化包: {context.file_name}", context.modal_id)
        self.update_progress(context)

        if not context.game_path:
            raise ValueError("未设置游戏路径，无法安装汉化包")

        if Path(context.file_path).suffix.lower() == '.7z':
            with tempfile.TemporaryDirectory() as tmp_dir:
                _log_manager.log_modal_process(
                    f"正在解压7z文件: {context.file_name}", context.modal_id)
                if not decompress_7z(context.file_path, tmp_dir):
                    raise RuntimeError(f"7z解压失败: {context.file_name}")
                package_dirs = self._collect_package_dirs(tmp_dir)
                if not package_dirs:
                    raise RuntimeError(
                        f"7z解压后未找到有效的汉化包目录: {context.file_name}")
                for package_dir in package_dirs:
                    install_translation_package(
                        package_dir, context.game_path, modal_id=context.modal_id)
        else:
            install_translation_package(
                context.file_path, context.game_path, modal_id=context.modal_id)

        _log_manager.log_modal_process(
            f"汉化包安装完成: {context.file_name}", context.modal_id)
        return 'installed'


class FullHandler(TranslationPackageBase):
    """完整汉化包（含字体）。"""

    file_type = 'full'
    label = '汉化包'

    def _decide_has_font(self, has_font: bool) -> str | None:
        return self.file_type if has_font else None


class NoFontHandler(TranslationPackageBase):
    """无字体汉化包。"""

    file_type = 'nofont'
    label = '无字体汉化包'

    def _decide_has_font(self, has_font: bool) -> str | None:
        return self.file_type if not has_font else None
