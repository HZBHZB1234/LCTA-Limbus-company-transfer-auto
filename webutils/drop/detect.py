from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

from .handlers import REGISTRY
from .inspect import FolderFormatInspection, JsonFormatInspection, ZipFormatInspection
from ..utils.io import decompress_7z
from globalManagers.LogManager import LogManager
_log_manager = LogManager()


def evalZip(zip_path: str | os.PathLike[str]) -> str:
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        namelist = zip_ref.namelist()
    inspection = ZipFormatInspection(
        names=tuple(namelist),
        non_json_names=tuple(name for name in namelist if '.json' not in name),
    )
    return REGISTRY.detect('zip', inspection)


def evalFolder(folder_path: str | os.PathLike[str]) -> str:
    folder_path = os.fspath(folder_path)
    items = tuple(os.listdir(folder_path))
    inspection = FolderFormatInspection(path=folder_path, items=items)
    return REGISTRY.detect('folder', inspection)


def eval7zip(file_path: str | os.PathLike[str]) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            if decompress_7z(file_path, tmp):
                return evalFolder(tmp)
        except Exception as e:
            _log_manager.log_error(e)
        return 'invalid'


def evalJson(json_path: str | os.PathLike[str]) -> str:
    try:
        with open(json_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        return REGISTRY.detect('json', JsonFormatInspection(data))
    except Exception as e:
        _log_manager.log_error(e)
        return 'invalid'


def evalFile(file_path: str | os.PathLike[str]) -> str:
    file_path = os.fspath(file_path)
    if Path(file_path).is_dir():
        return evalFolder(file_path)
    suffix = Path(file_path).suffix.lower()
    if suffix == '.zip':
        return evalZip(file_path)
    if suffix == '.7z':
        return eval7zip(file_path)
    if suffix == '.json':
        return evalJson(file_path)
    return REGISTRY.detect('path', file_path)
