"""
webutils/llm_fancy/builder.py
将 LLM 美化结果打包为 bus 引擎格式规则集并落盘、自动启用。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from globalManagers.ConfigManager import ConfigManager
from webutils.fancy.bus import BUS_FORMAT, BUS_VERSION, compile_bus_ruleset
from webutils.function_fancy import save_ruleset_to_folder

logger = logging.getLogger("llm_fancy")


def build_ruleset(results, name: Optional[str] = None) -> dict:
    """将 (Candidate, 美化后文本) 列表打包为 bus 规则集。

    每条规则：files=[{exact: 相对路径}], path=bus 路径, replacements=[{set: 新文本}]。
    产物通过 compile_bus_ruleset 校验，保证可被 bus 引擎直接加载。
    """
    rules = []
    for candidate, new_text in results:
        rules.append({
            "name": f"{candidate.file} / {candidate.bus_path}",
            "files": [{"exact": candidate.file}],
            "path": candidate.bus_path,
            "replacements": [{"set": new_text}],
        })
    ruleset = {
        "format": BUS_FORMAT,
        "version": BUS_VERSION,
        "name": name or f"LLM 文本美化 {datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "desc": "由 LLM 文本美化窗口生成（LLM 重写文本）",
        "files": ["*.json"],
        "exclude_dirs": [],
        "rules": rules,
    }
    compile_bus_ruleset(ruleset)
    return ruleset


def save_ruleset(ruleset: dict, name: str) -> Path:
    """保存规则集到 fancy/ 文件夹并返回路径。"""
    return save_ruleset_to_folder(name, ruleset)


def enable_ruleset_in_config(name: str) -> bool:
    """在 fancy_allow 配置中自动启用新生成的规则集。"""
    mgr = ConfigManager()
    raw = mgr.get("fancy_allow", "{}")
    try:
        enabled = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        enabled = {}
    if not isinstance(enabled, dict):
        enabled = {}
    enabled[name] = True
    mgr.set("fancy_allow", json.dumps(enabled, ensure_ascii=False))
    return True
