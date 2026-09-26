# -*- coding: utf-8 -*-
"""公告汉化（Notice Localization）。

把游戏内公告的标题与正文替换为中文：按官方 `noticeMeta.json` 里的同名文件名，
把翻译服务返回的公告 JSON 预置到 `persistentDataPath/notice/noticeDetails/`。
游戏判定缓存只 `File.Exists`，因此写入的文件永远不会被覆盖或重新下载。

对外入口：
* `NoticeLocalizer`  —— 执行器（抓取 / 请求 / 校验 / 落盘 / 还原）
* `get_notice_manager()` —— WebUI 后台任务管理器（含进度与取消）
"""
from .core import (  # noqa: F401
    DEFAULT_LANG,
    LANGS,
    OFFICIAL_BASE_URL,
    NoticeLocalizeError,
    NoticeLocalizer,
    enumerate_targets,
    evaluate_validity,
    load_meta,
    resolve_language,
    validate_translated,
)
from .manager import NoticeManager, get_notice_manager  # noqa: F401
from .service import (  # noqa: F401
    DEFAULT_SERVICE_URL,
    DEFAULT_URL_TEMPLATE,
    PENDING_MAX_WAIT,
    NoticePendingError,
    NoticeServiceError,
    NoticeTranslationService,
)

__all__ = [
    "NoticeLocalizer",
    "NoticeLocalizeError",
    "NoticeManager",
    "get_notice_manager",
    "NoticeServiceError",
    "NoticePendingError",
    "NoticeTranslationService",
    "DEFAULT_SERVICE_URL",
    "DEFAULT_URL_TEMPLATE",
    "PENDING_MAX_WAIT",
    "DEFAULT_LANG",
    "LANGS",
    "OFFICIAL_BASE_URL",
    "enumerate_targets",
    "evaluate_validity",
    "load_meta",
    "resolve_language",
    "validate_translated",
]
