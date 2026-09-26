# -*- coding: utf-8 -*-
"""LCTA 公告汉化 —— 服务端参考实现。

给 LCTA 的「公告汉化」功能自建翻译服务用。**不属于 LCTA 运行时**，是独立进程，
可以放在任意机器上跑。`store` / `pipeline` / `config` 为纯标准库实现；
HTTP 层为 FastAPI + Uvicorn，LLM 输出解析用 json_repair 容错
（依赖见 `requirements.txt`：`pip install -r tools/notice_server/requirements.txt`）。

模块：
* `config.py`     —— 默认配置（DEFAULT_CONFIG）+ 配置文件加载 + 环境变量密钥回退
* `translator.py` —— 翻译后端（OpenAI 兼容 / fake）+ 文本槽位与包裹处理
* `store.py`      —— 官方原文获取 + 译文缓存（含文件名校验，挡路径穿越）
* `pipeline.py`   —— 官方原文 → 槽位 → 翻译 → 自检 → 落盘
* `server.py`     —— FastAPI 应用工厂（`create_app`）+ 异步调度 + CLI

启动见 `README.md`。
"""
from .pipeline import NoticePipeline, PipelineError  # noqa: F401
from .store import NoticeStore, NoticeStoreError, is_valid_notice_name  # noqa: F401
from .translator import (  # noqa: F401
    FakeTranslator,
    OpenAIChatTranslator,
    TranslationError,
)

__all__ = [
    "NoticePipeline",
    "PipelineError",
    "NoticeStore",
    "NoticeStoreError",
    "is_valid_notice_name",
    "OpenAIChatTranslator",
    "FakeTranslator",
    "TranslationError",
]
