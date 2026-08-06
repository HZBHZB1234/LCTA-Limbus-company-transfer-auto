"""
webutils/llm_fancy/llm.py
LLM 调用：translatekit LLMGeneralTranslator 封装 + 响应解析。

仅依赖 translatekit 与标准库，不 import 任何翻译功能模块。
API 设置由调用方（前端解密 api_config 后）传入。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import translatekit as tkit

logger = logging.getLogger("llm_fancy")

DEFAULT_SYSTEM_PROMPT = (
    "你是一个文本美化工具。只输出一个合法的 JSON 数组，禁止输出任何其他内容。"
    "数组每个元素格式为 {\"id\": 整数, \"text\": \"美化后的文本\"}。"
    "id 必须与输入中的 id 一一对应，元素数量必须与输入完全一致，顺序必须与输入一致。"
    "不要添加 markdown 代码块，不要输出任何解释。"
)

FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?```$", re.DOTALL)


def format_api_settings(api_settings: dict) -> dict:
    """将用户填写/保存的 API 设置归一化为 LLMGeneralTranslator 完整配置。

    与 webui/app.py 的 format_api_settings 逻辑一致（默认值合并 + 类型归一化），
    但独立实现，避免桥接层依赖。
    """
    translator_cls = tkit.LLMGeneralTranslator
    result_settings = translator_cls.DEFAULT_API_KEY.copy()
    for key, value in api_settings.items():
        if key in result_settings and value not in (None, ""):
            result_settings[key] = value
    for describe in translator_cls.DESCRIBE_API_KEY:
        setting_id = describe.get("id")
        if setting_id not in result_settings:
            continue
        setting_type = describe.get("type")
        if setting_type == "string":
            result_settings[setting_id] = str(result_settings[setting_id])
        elif setting_type == "number":
            value = result_settings[setting_id]
            if isinstance(value, str):
                if value.isdigit():
                    result_settings[setting_id] = int(value)
                else:
                    result_settings[setting_id] = float(value)
    return result_settings


def build_translator(
    api_settings: dict,
    system_prompt: str,
    *,
    max_length: int = 20000,
    debug_mode: bool = False,
):
    """构造配置好 system_prompt 的 LLMGeneralTranslator 实例。"""
    normalized = format_api_settings(api_settings)
    tkit_config = tkit.TranslationConfig(
        api_setting=normalized,
        debug_mode=debug_mode,
        enable_cache=True,
        enable_metrics=True,
    )
    tkit_config.text_max_length = max_length
    tkit_config.max_workers = 1
    translator = tkit.LLMGeneralTranslator(tkit_config)
    translator.update_config(
        system_prompt=system_prompt,
        response_format="json_object",
    )
    return translator


def build_system_prompt(custom_prompt: str = "", enabled: bool = False) -> str:
    """组装系统提示词：默认仅注入解析保证提示，用户自定义提示追加在后。"""
    prompt = DEFAULT_SYSTEM_PROMPT
    if enabled and custom_prompt and custom_prompt.strip():
        prompt += "\n\n" + custom_prompt.strip()
    return prompt


def build_user_prompt(items: list) -> str:
    """构造单批请求的 user prompt（items: [{"id": int, "text": str}]）。"""
    return json.dumps({"items": items}, ensure_ascii=False)


def strip_code_fence(response: str) -> str:
    """剥离 markdown 代码围栏（```json ... ```）。"""
    text = response.strip()
    match = FENCE_RE.match(text)
    if match:
        return match.group(1).strip()
    return text


def parse_batch_response(response: str, expected_count: int) -> list[Optional[str]]:
    """解析 LLM 批量响应为与输入对齐的文本列表。

    返回长度与 expected_count 一致的列表；缺失/无效条目为 None。
    整体解析失败时抛出 ValueError（由调用方决定回退策略）。
    """
    text = strip_code_fence(response)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("LLM 响应不是 JSON 数组")
    by_id: dict[int, Any] = {}
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            by_id[item["id"]] = item.get("text")
    results: list[Optional[str]] = []
    for index in range(1, expected_count + 1):
        value = by_id.get(index)
        results.append(value if isinstance(value, str) else None)
    return results


def translate_batch(
    translator,
    items: list,
    from_lang: str = "EN",
    to_lang: str = "zh",
) -> str:
    """调用 LLM 翻译器翻译一个批次，返回原始响应文本。"""
    return translator.translate(build_user_prompt(items), from_lang, to_lang)
