# -*- coding: utf-8 -*-
"""服务端配置：默认值、配置文件加载、环境变量密钥回退。

默认值**全部集中在本文件**；`server.py` 只负责 CLI 参数覆盖与组装。
用户侧配置模板见 `config.example.json`（复制为 `config.json` 后按需修改，
本地 `config.json` 已被 `.gitignore` 覆盖，不会误提交密钥）。

加载优先级：默认值 < `config.json` < CLI 参数（`server.apply_cli_overrides`）；
密钥额外支持环境变量 `LCTA_NOTICE_API_KEY` / `OPENAI_API_KEY`（配置文件优先）。

`refresh_interval` 控制**定时预热**：默认每 30 分钟拉一次官方公告清单，把清单里
还没有译文的公告提前翻好，客户端第一次请求就能命中缓存（见 `refresher.py`）。
"""
from __future__ import annotations

import copy
import json
import os

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8000,
    "cache_dir": "cache",
    "official_base_url": "https://notice.limbuscompanyapi.com",
    "official_timeout": 30,
    "max_concurrency": 2,
    # 定时预热：每 refresh_interval 秒拉一次官方公告清单，把新增公告提前翻好
    # （0 = 关闭；下限 60 秒，防止打爆官方 CDN）
    "refresh_interval": 1800,
    "refresh_languages": ["EN"],
    "refresh_only_valid": True,
    "translate": {
        "backend": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "timeout": 120,
        "temperature": 0.2,
        "max_retries": 2,
        "target_language": "简体中文",
    },
}

API_KEY_ENV_VARS = ("LCTA_NOTICE_API_KEY", "OPENAI_API_KEY")


def load_config(path) -> dict:
    """加载配置：深拷贝默认值 → 覆盖用户文件（`translate` 子对象合并）→ 环境变量密钥。"""
    config = copy.deepcopy(DEFAULT_CONFIG)
    if path:
        with open(path, "r", encoding="utf-8") as handle:
            user = json.load(handle)
        if not isinstance(user, dict):
            raise ValueError("配置文件顶层必须是对象")
        for key, value in user.items():
            if key == "translate" and isinstance(value, dict):
                config["translate"].update(value)
            else:
                config[key] = value
    for env_name in API_KEY_ENV_VARS:
        if not config["translate"].get("api_key") and os.environ.get(env_name):
            config["translate"]["api_key"] = os.environ[env_name]
    return config
