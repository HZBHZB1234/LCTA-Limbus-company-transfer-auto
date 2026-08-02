"""CDN 优选包 — 测试 Cloudflare / CloudFront 节点速度并写入系统 hosts 文件。
设计参考 LLC_BABEL（MIT License, Copyright (c) 2026 ZengXiaoPi），采用 Python 独立实现。

回调协议（所有对外流程函数共用）：
- log_cb(msg: str)：日志回调，单行文本。
- progress_cb(pct: float, msg: str)：进度回调，pct 为 0-100 且单调不倒退。
- cancel_check()：取消回调，抛出异常即中止流程；无需取消时传 None。
- hosts 写入/移除函数统一返回 (success: bool, error_message: Optional[str])。

模块划分：
- constants: 模块级常量（marker、域名表、CFST 配置、超时、探测失败分类与消息表）
- classify: classify_probe_exception / get_failure_message
- cfst: run_cfst（含 CFST 懒加载下载）
- cloudfront: resolve_cloudfront_dns / probe_cloudfront_endpoint
- selector: select_cloudfront_ip
- hosts: hosts 文件读写与映射读取
- elevate: 管理员提权写入/移除（UAC 子进程机制）
- optimize: cdn_optimize_* / cdn_full_optimization* 流程编排
"""
from __future__ import annotations

from .cfst import run_cfst
from .cloudfront import probe_cloudfront_endpoint, resolve_cloudfront_dns
from .elevate import elevate_remove_hosts, elevate_write_hosts
from .hosts import read_current_hosts_mappings, write_hosts
from .optimize import (
    cdn_full_optimization,
    cdn_full_optimization_simple,
    cdn_optimize_cloudflare,
    cdn_optimize_cloudfront,
)
from .selector import select_cloudfront_ip

__all__ = [
    'run_cfst',
    'resolve_cloudfront_dns',
    'probe_cloudfront_endpoint',
    'select_cloudfront_ip',
    'write_hosts',
    'elevate_write_hosts',
    'read_current_hosts_mappings',
    'cdn_optimize_cloudflare',
    'cdn_optimize_cloudfront',
    'cdn_full_optimization',
    'cdn_full_optimization_simple',
    'elevate_remove_hosts',
]
