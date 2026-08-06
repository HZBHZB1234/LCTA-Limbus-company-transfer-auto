"""
webutils/llm_fancy/config.py
LLM 文本美化窗口的配置数据类与 ConfigManager 持久化。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

CONFIG_ROOT = "ui_default.llm_fancy"

DEFAULT_MAX_LENGTH = 20000
DEFAULT_MAX_WORKERS = 4


@dataclass
class LLMFancyConfig:
    """一次 LLM 美化运行的配置。

    仅包含窗口可持久化/可编辑的项；语言包目录与 LLM API 设置
    在运行时刻由 runner 从 ConfigManager / 前端传入注入。
    """

    selection: dict = field(
        default_factory=lambda: {
            "name": "LLM 文本美化",
            "files": ["*.json"],
            "rules": [],
        }
    )
    exclusions: list = field(default_factory=list)
    custom_prompt: str = ""
    custom_prompt_enabled: bool = False
    max_length: int = DEFAULT_MAX_LENGTH
    max_workers: int = DEFAULT_MAX_WORKERS
    dedup_enabled: bool = True


def load_config(mgr) -> LLMFancyConfig:
    """从 ConfigManager 读取窗口持久化配置。"""
    section = mgr.get(CONFIG_ROOT, {})

    def _json_value(raw, default):
        if not isinstance(raw, str) or not raw:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default

    max_length = _to_int(section.get("max_length"), DEFAULT_MAX_LENGTH)
    max_workers = _to_int(section.get("max_workers"), DEFAULT_MAX_WORKERS)
    return LLMFancyConfig(
        selection=_json_value(section.get("rules"), {"name": "LLM 文本美化", "files": ["*.json"], "rules": []}),
        exclusions=_json_value(section.get("exclusions"), []),
        custom_prompt=section.get("prompt", ""),
        custom_prompt_enabled=bool(section.get("prompt_enabled", False)),
        max_length=max_length,
        max_workers=max_workers,
        dedup_enabled=bool(section.get("dedup_enabled", True)),
    )


def save_config(mgr, config: LLMFancyConfig) -> None:
    """将窗口配置写入 ConfigManager（rules/exclusions 以 JSON 字符串存储）。"""
    mgr.set_batch({
        f"{CONFIG_ROOT}.rules": json.dumps(config.selection, ensure_ascii=False),
        f"{CONFIG_ROOT}.exclusions": json.dumps(config.exclusions, ensure_ascii=False),
        f"{CONFIG_ROOT}.prompt": config.custom_prompt,
        f"{CONFIG_ROOT}.prompt_enabled": bool(config.custom_prompt_enabled),
        f"{CONFIG_ROOT}.max_length": str(config.max_length),
        f"{CONFIG_ROOT}.max_workers": str(config.max_workers),
        f"{CONFIG_ROOT}.dedup_enabled": bool(config.dedup_enabled),
    })


def _to_int(raw: Any, default: int) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default
