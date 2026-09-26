# -*- coding: utf-8 -*-
"""公告翻译服务客户端。

契约（由服务端实现，客户端只发送目标文件名、无需鉴权）：

    请求  GET {base_url}{url_template 渲染结果}
          url_template 默认 `{base}/noticeDetails/{file}`，
          {base} = service_url（去尾部 `/`），{file} = 官方公告详情文件名，
          例如 noticeDetail_200001_EN_219.json

    响应  HTTP 200 + JSON 信封，由 `status` 决定语义：

          {"status": "ok",      "data": {…}}   译文就绪，`data` 为整篇公告 JSON
          {"status": "pending", "message": …}  未命中缓存，客户端应稍后重试
          {"status": "error",   "message": …}  服务端内部失败

          `data` 与官方 `NoticeDetail` 同结构，仅 `title` 与
          `content.list[*].formatValue` 为中文，其余字段原样保留。

**「未命中缓存」由客户端自行等待重试**：收到 `pending` 后按指数退避
1→2→4→8→16 秒（之后固定 16 秒）重试同一文件名，单篇累计等待不超过
`PENDING_MAX_WAIT` 秒（最后一次按剩余预算截断）。服务端**不需要**阻塞请求
或做长轮询，收到未命中直接回 `pending` 即可。

失败时也可返回非 200；兼容旧错误信封 `{"ok": false, "error": {...}}`。

客户端只做校验与落盘，不参与文本切分或回填。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional, Tuple

DEFAULT_URL_TEMPLATE = "{base}/noticeDetails/{file}"
USER_AGENT = "LCTA-NoticeLocalizer/1.0"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
# 状态页（服务端 `/status`）体量很小，单独设一个上限
MAX_STATUS_BYTES = 256 * 1024
# 状态页探测的超时上限：页面加载时自动刷新，不能挂在默认的 60 秒请求超时上
STATUS_TIMEOUT = 10

# 内置翻译服务地址：公告汉化页不再让用户配置，直接使用官方公共翻译服务
DEFAULT_SERVICE_URL = "https://notice.lcta.top"
# 服务端状态页路径（`server.create_app` 注册的 `/status`）
STATUS_PATH = "/status"

STATUS_OK = "ok"
STATUS_PENDING = "pending"

# 未命中缓存时的重试节奏：指数退避，超出序列后固定为最后一个间隔
PENDING_BACKOFF = (1, 2, 4, 8, 16)
# 单篇公告累计等待上限（秒）
PENDING_MAX_WAIT = 60
# 等待被切成的小片长度：让「取消」不必等满一个退避间隔（最长 16 秒）才生效
WAIT_SLICE_SECONDS = 0.5


class NoticeServiceError(RuntimeError):
    """翻译服务调用失败。`kind` 供页面/日志分类展示。"""

    def __init__(self, message: str, kind: str = "error", status: Optional[int] = None):
        super().__init__(message)
        self.kind = kind
        self.status = status


class NoticePendingError(NoticeServiceError):
    """服务端明确表示「未命中缓存」，需稍后重试。

    `reason` 说明等待为何结束：

    * `budget`    —— 累计等待已达 `PENDING_MAX_WAIT`，服务端仍未就绪；
    * `deadline`  —— 调用方给的时间预算用尽（Launcher 启动预算）；
    * `cancelled` —— 用户取消。
    """

    def __init__(
        self,
        message: str = "服务端尚未命中缓存",
        reason: str = "budget",
        waited: float = 0.0,
    ):
        super().__init__(message, kind="pending")
        self.reason = reason
        self.waited = waited


def normalize_base_url(url: str) -> str:
    return str(url or "").strip().rstrip("/")


def pending_delays(
    max_wait: float = PENDING_MAX_WAIT,
    schedule: Tuple[int, ...] = PENDING_BACKOFF,
) -> List[float]:
    """未命中缓存的等待序列：1,2,4,8,16 后固定 16，累计不超过 `max_wait`。

    最后一次等待按剩余预算截断，使总等待恰好用满而不超出预算。
    例如 `max_wait=60` → `[1, 2, 4, 8, 16, 16, 13]`（累计 60 秒，共 8 次尝试）。
    """
    delays: List[float] = []
    total = 0.0
    index = 0
    while True:
        remaining = max_wait - total
        if remaining <= 0:
            break
        delay = float(schedule[min(index, len(schedule) - 1)])
        delay = min(delay, remaining)
        delays.append(delay)
        total += delay
        index += 1
        if total >= max_wait:
            break
    return delays


def _wait(delay: float, cancel_event, sleeper: Callable[[float], None]) -> None:
    """等待 `delay` 秒；给了取消事件就切成小片，取消最多延迟一个片长生效。"""
    if cancel_event is None:
        sleeper(delay)
        return
    remaining = float(delay)
    while remaining > 0:
        if cancel_event.is_set():
            return
        chunk = min(WAIT_SLICE_SECONDS, remaining)
        sleeper(chunk)
        remaining -= chunk


def parse_envelope(raw: bytes) -> Tuple[str, bytes, str]:
    """拆开 `{status, data}` 信封。

    返回 `(status, data 字节, message)`，`status` 已小写。
    仅 `ok` 会带 data 字节，其余状态返回空字节，由调用方按状态处理。
    """
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise NoticeServiceError(
            "服务返回内容不是合法 JSON: {}".format(exc), kind="invalid_json"
        )
    if not isinstance(payload, dict):
        raise NoticeServiceError("服务响应顶层不是对象", kind="protocol")

    raw_status = payload.get("status")
    if raw_status is None:
        # 兼容旧错误信封 {"ok": false, "error": {...}}
        if payload.get("ok") is False:
            error = payload.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise NoticeServiceError(
                "服务端返回失败: {}".format(message or "未知原因"), kind="service_error"
            )
        raise NoticeServiceError(
            '服务响应缺少 status 字段（需按 {"status": "ok", "data": {…}} 信封返回）',
            kind="protocol",
        )

    status = str(raw_status).strip().lower()
    raw_message = payload.get("message")
    message = raw_message.strip() if isinstance(raw_message, str) else ""

    if status == STATUS_OK:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise NoticeServiceError("服务返回 status=ok 但缺少 data 对象", kind="protocol")
        return status, json.dumps(data, ensure_ascii=False).encode("utf-8"), message
    return status, b"", message


class NoticeTranslationService:
    def __init__(self, base_url: str, url_template: str = "", timeout: int = 60):
        self.base_url = normalize_base_url(base_url)
        self.url_template = (url_template or "").strip() or DEFAULT_URL_TEMPLATE
        try:
            self.timeout = max(1, int(timeout))
        except (TypeError, ValueError):
            self.timeout = 60

    def build_url(self, file_name: str) -> str:
        if not self.base_url:
            raise NoticeServiceError("未配置翻译服务地址", kind="config")
        try:
            url = self.url_template.format(base=self.base_url, file=file_name)
        except (KeyError, IndexError, ValueError) as exc:
            raise NoticeServiceError(
                "服务地址模板无法渲染: {}（可用占位符 {{base}} 与 {{file}}）".format(exc),
                kind="config",
            )
        if not url.lower().startswith(("http://", "https://")):
            raise NoticeServiceError("服务地址必须是 http/https 链接", kind="config")
        return url

    def fetch_raw(self, file_name: str) -> bytes:
        """单次 HTTP 往返，返回原始响应体（不拆信封）。"""
        return self._get(self.build_url(file_name))

    def _get(
        self,
        url: str,
        max_bytes: int = MAX_RESPONSE_BYTES,
        timeout: Optional[int] = None,
    ) -> bytes:
        """单次 GET，返回原始响应体并做体积 / 空响应检查。"""
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        wait = self.timeout if timeout is None else max(1, int(timeout))
        try:
            with urllib.request.urlopen(req, timeout=wait) as resp:
                status = getattr(resp, "status", 200)
                if status != 200:
                    raise NoticeServiceError(
                        "服务返回 HTTP {}".format(status), kind="http", status=status
                    )
                data = resp.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            kind = "not_found" if exc.code == 404 else "http"
            raise NoticeServiceError(
                "服务返回 HTTP {} {}".format(exc.code, exc.reason or "").strip(),
                kind=kind,
                status=exc.code,
            )
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise NoticeServiceError(
                    "连接翻译服务超时（{} 秒）".format(wait), kind="timeout"
                )
            raise NoticeServiceError("无法连接翻译服务: {}".format(reason), kind="network")
        except TimeoutError:
            raise NoticeServiceError(
                "连接翻译服务超时（{} 秒）".format(wait), kind="timeout"
            )
        except NoticeServiceError:
            raise
        except Exception as exc:  # pragma: no cover - 兜底
            raise NoticeServiceError("请求翻译服务失败: {}".format(exc), kind="network")

        if len(data) > max_bytes:
            raise NoticeServiceError(
                "服务返回内容过大（超过 {} KB），已拒绝".format(max_bytes // 1024),
                kind="too_large",
            )
        if not data.strip():
            raise NoticeServiceError("服务返回空内容", kind="empty")
        return data

    def status(self) -> dict:
        """查询服务端运行状态（`GET {base}/status`）。

        页面加载时自动刷新用：服务端返回缓存篇数 / 正在翻译的文件 / 最近错误。
        探测超时收紧到 `STATUS_TIMEOUT`，失败抛 `NoticeServiceError`。
        """
        if not self.base_url:
            raise NoticeServiceError("未配置翻译服务地址", kind="config")
        raw = self._get(
            self.base_url + STATUS_PATH,
            max_bytes=MAX_STATUS_BYTES,
            timeout=min(self.timeout, STATUS_TIMEOUT),
        )
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise NoticeServiceError(
                "服务状态页返回内容不是合法 JSON: {}".format(exc), kind="invalid_json"
            )
        if not isinstance(payload, dict):
            raise NoticeServiceError("服务状态页返回顶层不是对象", kind="protocol")
        return payload

    def fetch(self, file_name: str) -> bytes:
        """单次请求并拆信封，返回**译文 JSON 字节**。

        未命中缓存抛 `NoticePendingError`，由调用方决定是否等待重试。
        """
        status, payload, message = parse_envelope(self.fetch_raw(file_name))
        if status == STATUS_OK:
            return payload
        if status == STATUS_PENDING:
            raise NoticePendingError(message or "服务端尚未命中缓存")
        raise NoticeServiceError(
            message or "服务端返回未知状态 status={}".format(status), kind="service_error"
        )

    def request(
        self,
        file_name: str,
        cancel_event=None,
        deadline: Optional[float] = None,
        on_wait: Optional[Callable[[int, float, float], None]] = None,
        sleep: Optional[Callable[[float], None]] = None,
    ) -> bytes:
        """请求译文；服务端未命中缓存时按指数退避等待重试。

        * `deadline` —— `time.monotonic()` 时间点（Launcher 启动预算），
          剩余预算不足以再等一轮时立即放弃并抛 `reason="deadline"`；
        * `cancel_event` —— 等待期间被 set 则抛 `reason="cancelled"`；
        * `on_wait(attempt, delay, waited)` —— 每次等待前的回调，供页面显示进度；
        * `sleep` —— 可注入，便于测试。
        """
        sleeper = sleep or time.sleep
        delays = pending_delays(PENDING_MAX_WAIT)
        waited = 0.0
        index = 0

        while True:
            try:
                return self.fetch(file_name)
            except NoticePendingError as exc:
                if cancel_event is not None and cancel_event.is_set():
                    raise NoticePendingError(
                        "已取消等待服务端译文", reason="cancelled", waited=waited
                    )
                if index >= len(delays):
                    raise NoticePendingError(
                        "服务端 {} 秒内仍未返回译文（共尝试 {} 次）".format(
                            int(waited), index + 1
                        ),
                        reason="budget",
                        waited=waited,
                    ) from exc
                delay = delays[index]
                if deadline is not None and (deadline - time.monotonic()) <= delay:
                    raise NoticePendingError(
                        "时间预算不足，剩余公告留待下次同步",
                        reason="deadline",
                        waited=waited,
                    )
                if on_wait is not None:
                    try:
                        on_wait(index + 1, delay, waited)
                    except Exception:
                        pass
                _wait(delay, cancel_event, sleeper)
                waited += delay
                index += 1
                if cancel_event is not None and cancel_event.is_set():
                    # 等待期间被取消：立即退出，不再多发一次请求
                    raise NoticePendingError(
                        "已取消等待服务端译文", reason="cancelled", waited=waited
                    )

    def probe(self, file_name: str) -> dict:
        """连通性测试：单次请求并解析（不落盘、不等待重试）。

        未命中缓存不算连接失败——返回 `pending=True` 供页面提示。
        """
        try:
            data = self.fetch(file_name)
        except NoticePendingError as exc:
            return {
                "file": file_name,
                "title": None,
                "bytes": 0,
                "pending": True,
                "message": str(exc),
            }
        try:
            payload = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise NoticeServiceError(
                "服务返回内容不是合法 JSON: {}".format(exc), kind="invalid_json"
            )
        title = payload.get("title") if isinstance(payload, dict) else None
        return {"file": file_name, "title": title, "bytes": len(data), "pending": False}
