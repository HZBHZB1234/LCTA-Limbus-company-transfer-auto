# -*- coding: utf-8 -*-
"""公告翻译流水线：官方原文 → 文本槽位 → 翻译 → 自检 → 落盘。

`NoticePipeline.translate()` 是**同步**的（一篇公告一次调用），
异步调度与 HTTP 由 `server.py` 负责。
"""
from __future__ import annotations

import json

from .store import NoticeStore
from .translator import (
    TranslationError,
    apply_translations,
    build_slots,
    validate_payload,
)


class PipelineError(RuntimeError):
    """流水线自身失败（官方原文结构异常、译文自检不过等）。"""


class NoticePipeline:
    def __init__(self, store: NoticeStore, translator):
        self.store = store
        self.translator = translator

    def translate(self, file_name: str) -> bytes:
        """翻译一篇公告、写入缓存并返回译文 JSON 字节。

        失败抛 `PipelineError` / `TranslationError` / `NoticeStoreError`，
        调用方（server）把它们统一转成 `{"status": "error"}`。
        """
        official_raw = self.store.official(file_name)
        try:
            payload = json.loads(official_raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise PipelineError("官方公告不是合法 JSON: {}".format(exc))
        if not isinstance(payload, dict):
            raise PipelineError("官方公告结构异常")

        slots = build_slots(payload)
        if slots:
            translations = self.translator.translate([slot["text"] for slot in slots])
            apply_translations(payload, slots, translations)

        try:
            validate_payload(payload)
        except TranslationError as exc:
            raise PipelineError("译文自检未通过: {}".format(exc))

        return self.store.save_translated(file_name, payload)
