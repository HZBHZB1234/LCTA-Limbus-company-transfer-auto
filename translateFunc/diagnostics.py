"""翻译调用诊断工具：异常序列化、敏感信息脱敏和 HTTP 响应捕获。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import threading
import traceback
from typing import Any


_SENSITIVE_KEY = re.compile(
    r"api[-_]?key|authorization|proxy[-_]?authorization|cookie|set-cookie|"
    r"access[-_]?token|refresh[-_]?token|client[-_]?secret|password|secret",
    re.IGNORECASE,
)
_REDACTED = "<redacted>"
_BEARER_TOKEN = re.compile(r"(?i)(bearer\s+)[^\s,;\"']+")
_QUERY_SECRET = re.compile(
    r"(?i)((?:api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|"
    r"password|secret)=)[^&\s,;\"']+"
)


def redact_text(value: str) -> str:
    """脱敏字符串中的 Bearer token 和常见查询参数凭据。"""
    value = _BEARER_TOKEN.sub(r"\1<redacted>", value)
    return _QUERY_SECRET.sub(r"\1<redacted>", value)


def redact_value(value: Any, key: str = "") -> Any:
    """递归脱敏常见认证字段，同时保持数据结构可读。"""
    if key and _SENSITIVE_KEY.search(str(key)):
        return _REDACTED
    if isinstance(value, dict):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact_value(item) for item in value]
    return value


def safe_json_value(value: Any, _seen: set[int] | None = None) -> Any:
    """将任意 Python 值转换为可 JSON 序列化的安全表示。"""
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()

    if _seen is None:
        _seen = set()
    value_id = id(value)
    if value_id in _seen:
        return "<recursive-reference>"

    if isinstance(value, dict):
        _seen.add(value_id)
        try:
            return {
                str(key): (
                    _REDACTED
                    if _SENSITIVE_KEY.search(str(key))
                    else safe_json_value(item, _seen)
                )
                for key, item in value.items()
            }
        finally:
            _seen.remove(value_id)

    if isinstance(value, (list, tuple, set)):
        _seen.add(value_id)
        try:
            return [safe_json_value(item, _seen) for item in value]
        finally:
            _seen.remove(value_id)

    try:
        return repr(value)
    except Exception:
        return f"<unrepresentable {type(value).__name__}>"


def _response_text(response: Any) -> str:
    try:
        return response.text
    except Exception:
        try:
            content = response.content
            if isinstance(content, bytes):
                return content.decode("utf-8", errors="replace")
            return str(content)
        except Exception:
            return ""


def snapshot_http_response(response: Any) -> dict:
    """提取 requests 风格响应的可序列化快照。"""
    request = getattr(response, "request", None)
    elapsed = getattr(response, "elapsed", None)
    try:
        elapsed_seconds = elapsed.total_seconds() if elapsed is not None else None
    except Exception:
        elapsed_seconds = None

    return safe_json_value({
        "status_code": getattr(response, "status_code", None),
        "reason": getattr(response, "reason", None),
        "url": getattr(response, "url", None),
        "elapsed_seconds": elapsed_seconds,
        "headers": redact_value(dict(getattr(response, "headers", {}) or {})),
        "body": _response_text(response),
        "request": {
            "method": getattr(request, "method", None),
            "url": getattr(request, "url", None),
            "headers": redact_value(dict(getattr(request, "headers", {}) or {})),
        } if request is not None else None,
    })


def serialize_exception(exc: BaseException | None) -> dict | None:
    """序列化异常、traceback、cause/context 以及关联 HTTP 响应。"""
    if exc is None:
        return None

    seen: set[int] = set()

    def _serialize(current: BaseException) -> dict:
        if id(current) in seen:
            return {
                "type": type(current).__name__,
                "message": str(current),
                "recursive": True,
            }
        seen.add(id(current))

        response = getattr(current, "response", None)
        request = getattr(current, "request", None)
        result = {
            "type": type(current).__name__,
            "module": type(current).__module__,
            "message": str(current),
            "args": safe_json_value(getattr(current, "args", ())),
            "traceback": "".join(
                traceback.TracebackException.from_exception(current).format()
            ),
        }
        if response is not None:
            result["http_response"] = snapshot_http_response(response)
        elif request is not None:
            result["http_request"] = safe_json_value({
                "method": getattr(request, "method", None),
                "url": getattr(request, "url", None),
                "headers": redact_value(dict(getattr(request, "headers", {}) or {})),
            })

        cause = getattr(current, "__cause__", None)
        context = getattr(current, "__context__", None)
        if cause is not None:
            result["cause"] = _serialize(cause)
        elif context is not None and not getattr(current, "__suppress_context__", False):
            result["context"] = _serialize(context)
        return result

    return safe_json_value(_serialize(exc))


class HttpResponseObserver:
    """通过 requests Session response hook 捕获一次翻译调用内的全部响应。"""

    def __new__(cls, translator: Any):
        existing = getattr(translator, "_lcta_http_response_observer", None)
        if isinstance(existing, cls):
            return existing
        instance = super().__new__(cls)
        try:
            setattr(translator, "_lcta_http_response_observer", instance)
        except Exception:
            pass
        return instance

    def __init__(self, translator: Any):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._local = threading.local()
        self._installed = False
        session = getattr(translator, "_session", None)
        hooks = getattr(session, "hooks", None)
        if not isinstance(hooks, dict):
            return

        response_hooks = hooks.setdefault("response", [])
        if self._capture not in response_hooks:
            response_hooks.append(self._capture)
        self._installed = True

    @property
    def installed(self) -> bool:
        return self._installed

    def begin(self) -> None:
        self._local.responses = []

    def finish(self) -> list[dict]:
        responses = list(getattr(self._local, "responses", []))
        self._local.responses = []
        return responses

    def _capture(self, response: Any, *args, **kwargs) -> Any:
        responses = getattr(self._local, "responses", None)
        if responses is not None:
            responses.append(snapshot_http_response(response))
        return response
