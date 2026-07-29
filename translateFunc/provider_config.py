from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict


def _field(
    field_id: str,
    name: str,
    field_type: str,
    description: str,
    *,
    required: bool = False,
) -> dict[str, Any]:
    return {
        "id": field_id,
        "name": name,
        "type": field_type,
        "required": required,
        "description": description,
    }


LLM_DEFAULTS: dict[str, Any] = {
    "api_key": "",
    "base_url": "https://api.openai.com/v1",
    "model_name": "gpt-4o-mini",
    "temperature": 0.0,
    "top_p": 1.0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "max_tokens": 4000,
    "extra_body": {},
    "timeout": 120,
    "max_retries": 3,
}

LLM_FIELDS = [
    _field("api_key", "API密钥", "string", "OpenAI 兼容接口的 API 密钥", required=True),
    _field("base_url", "API基础地址", "string", "OpenAI 兼容接口基础地址"),
    _field("model_name", "模型名称", "string", "请求使用的模型名称"),
    _field("temperature", "温度系数", "number", "翻译建议使用 0.0 到 0.3"),
    _field("top_p", "核采样阈值", "number", "OpenAI 兼容 top_p 参数"),
    _field("frequency_penalty", "频率惩罚", "number", "OpenAI 兼容 frequency_penalty 参数"),
    _field("presence_penalty", "存在惩罚", "number", "OpenAI 兼容 presence_penalty 参数"),
    _field("max_tokens", "最大生成令牌数", "number", "单次请求最大生成令牌数"),
    _field("extra_body", "额外请求体", "dictionary", "合并到请求体的额外 JSON 参数"),
    _field("timeout", "请求超时", "number", "单次 HTTP 请求超时秒数"),
    _field("max_retries", "最大重试次数", "number", "429 和 5xx 响应的最大重试次数"),
]

TKIT_SERVER = ["LLMGeneralTranslator", "NullTranslator"]

TKIT_MACHINE: Dict[str, dict] = {
    "LLM通用翻译服务": {
        "metadata": {
            "console_url": "",
            "description": "由 Rust/Tokio 驱动的 OpenAI 兼容大模型翻译服务",
            "documentation_url": "",
            "short_description": "Rust 原生 OpenAI 兼容翻译",
            "usage_documentation": "配置 API 密钥、基础地址和模型名称。每次请求独立携带 system_prompt 与 user_prompt。",
        },
        "api-setting": LLM_FIELDS,
        "defaults": LLM_DEFAULTS,
        "provider_kind": "open_ai_compatible",
        "langCode": {"zh": "zh", "en": "en", "kr": "ko", "jp": "ja"},
    },
    "空翻译器(使用原文)": {
        "metadata": {
            "console_url": "",
            "description": "不发送网络请求，直接返回原文，用于验证原生文件与规则流水线",
            "documentation_url": "",
            "short_description": "Rust 原生空翻译器",
            "usage_documentation": "无需配置，所有输入直接返回原文。",
        },
        "api-setting": [],
        "defaults": {},
        "provider_kind": "null",
        "langCode": {"zh": "zh", "en": "en", "kr": "ko", "jp": "ja"},
    },
}

LLM_TRANSLATOR: Dict[str, dict] = {
    "OpenAI 官方": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "阿里云百炼 OpenAI 兼容": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-turbo",
    },
    "智谱 AI OpenAI 兼容": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4",
    },
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama3-70b-8192",
    },
}

TKIT_MACHINE_OBJECT = deepcopy(TKIT_MACHINE)


def format_api_settings(service_name: str, api_settings: dict[str, Any]) -> dict[str, Any]:
    service = TKIT_MACHINE.get(service_name)
    if service is None:
        raise ValueError(f"不支持的翻译服务: {service_name}")
    result = deepcopy(service.get("defaults", {}))
    descriptions = {
        item["id"]: item for item in service.get("api-setting", [])
    }
    for key, value in api_settings.items():
        if key not in descriptions or value in (None, ""):
            continue
        field_type = descriptions[key].get("type")
        if field_type == "number":
            value = float(value)
            if value.is_integer():
                value = int(value)
        elif field_type == "string":
            value = str(value)
        elif field_type == "dictionary" and isinstance(value, str):
            value = json.loads(value) if value.strip() else {}
        result[key] = value
    return result
