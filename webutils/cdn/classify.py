"""CloudFront 探测失败分类（对应 LLC_BABEL CloudFrontProbeFailure 枚举）。

每种失败类型都有对应的用户可读消息，方便日志诊断。
"""
from __future__ import annotations

import socket
import ssl
from typing import Optional

from .constants import (
    PROBE_FAILURE_CONNECTION,
    PROBE_FAILURE_MESSAGES,
    PROBE_FAILURE_NETWORK,
    PROBE_FAILURE_TIMEOUT,
    PROBE_FAILURE_TLS,
)


def classify_probe_exception(exc: Exception) -> str:
    """将探测过程中的异常映射为 PROBE_FAILURE_* 常量。"""
    if isinstance(exc, ssl.SSLError):
        return PROBE_FAILURE_TLS
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return PROBE_FAILURE_TIMEOUT
    if isinstance(exc, (ConnectionRefusedError, ConnectionError, ConnectionAbortedError,
                        ConnectionResetError, OSError)):
        return PROBE_FAILURE_CONNECTION
    return PROBE_FAILURE_NETWORK


def get_failure_message(failure: Optional[str]) -> Optional[str]:
    """获取失败类型的用户可读消息。"""
    if failure is None:
        return None
    return PROBE_FAILURE_MESSAGES.get(failure, f"探测失败（{failure}）。")
