# -*- coding: utf-8 -*-
"""公告汉化的路径解析。

游戏侧（落盘目标，位于 Unity `persistentDataPath`）：

    %USERPROFILE%\\AppData\\LocalLow\\ProjectMoon\\LimbusCompany\\notice\\
        noticeMeta.json           官方公告清单（游戏每 >=10 分钟重下一次）
        noticeDetails\\<fileName> 单篇公告详情，`File.Exists` 即缓存命中、永不重下

本工具侧（缓存与备份，不进游戏目录）：

    %LOCALAPPDATA%\\LCTA\\notice\\
        state.json            已写入文件的内容指纹（判断是否需要重新请求）
        originals\\<fileName> 官方原文备份（还原 / 对照用）

路径推导参考 `launcher/crash_export.py`（同为 Unity 标准目录布局）。
"""
from __future__ import annotations

import os
from pathlib import Path

META_FILE_NAME = "noticeMeta.json"
DETAILS_FOLDER_NAME = "noticeDetails"
STATE_FILE_NAME = "state.json"
ORIGINALS_FOLDER_NAME = "originals"


def _home_dir() -> Path:
    base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return Path(base)


def _local_appdata_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)
    return _home_dir() / "AppData" / "Local"


def get_notice_dir() -> Path:
    """游戏公告缓存根目录。"""
    return _home_dir() / "AppData" / "LocalLow" / "ProjectMoon" / "LimbusCompany" / "notice"


def get_details_dir() -> Path:
    """公告详情目录（汉化文件的落盘位置）。"""
    return get_notice_dir() / DETAILS_FOLDER_NAME


def get_meta_path() -> Path:
    return get_notice_dir() / META_FILE_NAME


def get_cache_dir() -> Path:
    """本工具的公告汉化缓存目录。"""
    return _local_appdata_dir() / "LCTA" / "notice"


def get_originals_dir() -> Path:
    return get_cache_dir() / ORIGINALS_FOLDER_NAME


def get_state_path() -> Path:
    return get_cache_dir() / STATE_FILE_NAME


def ensure_cache_dirs(cache_dir: Path = None) -> Path:
    """确保缓存目录存在，返回缓存根。"""
    root = Path(cache_dir) if cache_dir else get_cache_dir()
    (root / ORIGINALS_FOLDER_NAME).mkdir(parents=True, exist_ok=True)
    return root
