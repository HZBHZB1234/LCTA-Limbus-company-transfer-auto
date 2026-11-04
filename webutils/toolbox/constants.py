# -*- coding: utf-8 -*-
"""订阅工具共用的 HTTP 常量。

## 为什么必须显式设置 User-Agent（2026-11 修复 Cloudflare error 1010）

资源站（``mods.lcta.top`` 及其 CDN ``dl.mods.lcta.top``）挂在 Cloudflare
后面，WAF 会按「浏览器签名」封禁脚本默认 UA（``Python-urllib/3.x``）。
而 Python ``urllib`` 在请求未显式设置 ``User-Agent`` 时会**自动补上**
``Python-urllib/<版本>``，于是所有未设 UA 的订阅工具请求都被 403 拦下：

    error code: 1010
    The site owner has blocked access based on your browser's signature.
    error_name: browser_signature_banned

站点只按 UA 判定脚本签名，任意非默认 UA（含本常量）都能正常通过。
因此订阅工具所有出站 HTTP 请求（API 客户端 ``api.py`` 与下载器
``download.py``）都必须显式带上本 UA，**切勿依赖 urllib 默认值**。
"""
from __future__ import annotations

import os


def _client_version() -> str:
    """读取打包注入的版本号（缺失时回落 0.0.0）。"""
    raw = (os.getenv("__version__") or "").strip().lstrip("vV")
    return raw or "0.0.0"


# 统一的客户端 User-Agent：既表明身份，又避免 urllib 默认的
# ``Python-urllib/x.y`` 被 Cloudflare 1010 封禁。
USER_AGENT = f"LCTA/{_client_version()} (Windows NT 10.0; Win64; x64)"
