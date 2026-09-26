# -*- coding: utf-8 -*-
"""公告预热：定时拉官方公告清单，把新增公告提前翻好。

为什么需要：客户端只在需要时才请求译文，未命中缓存要按指数退避重试
（单篇最多等 60 秒）。服务端主动预热后，客户端第一次请求通常就直接命中 `ok`，
公共翻译服务（`https://notice.lcta.top`）上尤其重要——一次预热全量用户受益。

默认**每 30 分钟一轮**（`config.DEFAULT_CONFIG["refresh_interval"]` = 1800 秒）：
拉 `noticeMeta.json` → 按配置语言枚举文件名 → 未缓存的交给 `NoticeService`
异步翻译（复用请求路径的并发上限与去重，同一文件不会重复翻译）。

只处理**有效期内**的公告（与客户端 `only_valid` 语义一致），过期的没人看。
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence

from .store import NoticeStore, NoticeStoreError, is_valid_notice_name

LANGS = ("KR", "EN", "JP")
DEFAULT_LANGUAGES = ("EN",)
DEFAULT_INTERVAL_SECONDS = 1800
MIN_INTERVAL_SECONDS = 60
# 并发已满时的排队等待上限：等运行中的翻译腾出名额，避免整轮预热被跳过
QUEUE_WAIT_SECONDS = 120.0
QUEUE_POLL_SECONDS = 0.2


def parse_datetime(value) -> Optional[datetime]:
    """解析官方两种日期格式，失败返回 None。

    * meta：`2023-01-01T00:00:00.000Z`
    * 详情：`Thu Sep 17 2026 01:04:36 GMT+0000 (Coordinated Universal Time)`
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    iso = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        parsed = None
    if parsed is None:
        head = text.split(" (", 1)[0].strip()
        for fmt in ("%a %b %d %Y %H:%M:%S GMT%z", "%a %b %d %Y %H:%M:%S %z"):
            try:
                parsed = datetime.strptime(head, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def evaluate_validity(start_raw, end_raw, now: Optional[datetime] = None) -> bool:
    """是否处于有效期内（与客户端 `core.evaluate_validity` 同义）。

    解析失败时保守判定为「有效」——宁可多译一篇，也不漏译。
    """
    now = now or datetime.now(timezone.utc)
    start = parse_datetime(start_raw)
    end = parse_datetime(end_raw)
    if start is not None and start > now:
        return False
    if end is not None and end < now:
        return False
    return True


def enumerate_notice_names(
    meta: dict,
    languages: Sequence[str] = DEFAULT_LANGUAGES,
    only_valid: bool = True,
) -> List[str]:
    """按语言列出官方清单里的公告文件名（保持清单顺序、去重、白名单校验）。"""
    entries = meta.get("noticeDetailList") if isinstance(meta, dict) else None
    if not isinstance(entries, list):
        return []
    wanted = [str(lang or "").strip().upper() for lang in (languages or DEFAULT_LANGUAGES)]
    names: List[str] = []
    seen = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        if only_valid and not evaluate_validity(
            item.get("startDate") or "", item.get("endDate") or ""
        ):
            continue
        for lang in wanted:
            name = item.get("fileName_" + lang)
            if not isinstance(name, str):
                continue
            name = name.strip()
            # 与请求路径同一条白名单：清单里出现意外文件名时直接跳过
            if not name or name in seen or not is_valid_notice_name(name):
                continue
            seen.add(name)
            names.append(name)
    return names


class NoticeRefresher:
    """定时预热线程：拉官方清单 → 未缓存的公告交给 `NoticeService` 翻译。"""

    def __init__(
        self,
        store: NoticeStore,
        service,
        interval: int = DEFAULT_INTERVAL_SECONDS,
        languages: Sequence[str] = DEFAULT_LANGUAGES,
        only_valid: bool = True,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.store = store
        self.service = service
        try:
            seconds = int(interval)
        except (TypeError, ValueError):
            seconds = DEFAULT_INTERVAL_SECONDS
        # 0 / 负数 = 关闭定时预热；给了间隔则不低于 MIN_INTERVAL_SECONDS，防止打爆官方 CDN
        self.interval = max(MIN_INTERVAL_SECONDS, seconds) if seconds > 0 else 0
        self.languages = tuple(languages or DEFAULT_LANGUAGES)
        self.only_valid = bool(only_valid)
        self._logger = logger
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_run = 0
        self._last_summary: Optional[dict] = None

    # -- 对外 -------------------------------------------------------------
    def start(self) -> bool:
        """启动后台预热线程（已启动或已关闭时是空操作）。"""
        if not self.interval:
            return False
        if self._thread is not None and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="notice-refresh", daemon=True
        )
        self._thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def status(self) -> dict:
        with self._lock:
            last_run = self._last_run
            last = dict(self._last_summary) if self._last_summary else None
        return {
            "enabled": bool(self.interval),
            "interval": self.interval,
            "languages": list(self.languages),
            "only_valid": self.only_valid,
            "last_run": last_run or None,
            "last": last,
        }

    def run_once(self) -> dict:
        """跑一轮预热并返回摘要；任何异常都收敛进摘要，不向外抛。"""
        started = time.time()
        summary = {
            "success": False,
            "total": 0,
            "cached": 0,
            "queued": 0,
            "deferred": 0,
            "failed": 0,
            "message": "",
        }
        try:
            raw = self.store.official_meta()
            meta = json.loads(raw.decode("utf-8-sig"))
        except (NoticeStoreError, UnicodeDecodeError, ValueError) as exc:
            summary["message"] = "读取官方公告清单失败: {}".format(exc)
            return self._finish(summary, started)
        if not isinstance(meta, dict):
            summary["message"] = "官方公告清单结构异常"
            return self._finish(summary, started)

        names = enumerate_notice_names(meta, self.languages, self.only_valid)
        summary["total"] = len(names)
        for name in names:
            if self._stop.is_set():
                summary["message"] = "预热已中止"
                return self._finish(summary, started)
            if self.store.read_translated(name) is not None:
                summary["cached"] += 1
                continue
            outcome = self._queue(name)
            summary[outcome] = summary.get(outcome, 0) + 1

        summary["success"] = True
        summary["message"] = "清单 {} 篇：已有译文 {} 篇，新排队 {} 篇，失败 {} 篇{}".format(
            summary["total"],
            summary["cached"],
            summary["queued"],
            summary["failed"],
            "，{} 篇并发已满留待下轮".format(summary["deferred"]) if summary["deferred"] else "",
        )
        return self._finish(summary, started)

    # -- 内部 -------------------------------------------------------------
    def _queue(self, name: str) -> str:
        """把一篇公告交给服务翻译，返回 `queued` / `failed` / `deferred`。

        并发已满时等运行中的翻译腾出名额再重试（上限 `QUEUE_WAIT_SECONDS`），
        否则整轮预热会因为并发上限而大面积漏掉。`NoticeService.respond()` 用
        `reason="busy"` 标记「并发已满」，与「这篇已在翻译中」区分开。
        """
        deadline = time.monotonic() + QUEUE_WAIT_SECONDS
        while True:
            _code, envelope = self.service.respond(name)
            status = str(envelope.get("status") or "")
            if status == "pending":
                if envelope.get("reason") != "busy":
                    # 已在翻译中：本轮的活已经派下去了
                    return "queued"
                if self._stop.is_set() or time.monotonic() >= deadline:
                    return "deferred"
                time.sleep(QUEUE_POLL_SECONDS)
                continue
            if status == "error":
                # 上一轮失败的残留（服务端只上报一次）：本轮记失败，下轮重新排队
                return "failed"
            if status == "ok":
                # 竞态：上一轮刚译好，本轮检查缓存时还没落盘
                return "cached"
            return "queued"

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:  # pragma: no cover - 兜底，线程不能带异常退出
                self._log("预热异常: {}".format(exc))
            if self._stop.wait(self.interval):
                break

    def _finish(self, summary: dict, started: float) -> dict:
        summary["elapsed"] = round(time.time() - started, 2)
        with self._lock:
            self._last_run = int(time.time())
            self._last_summary = dict(summary)
        self._log(summary.get("message") or "预热完成")
        return summary

    def _log(self, message: str) -> None:
        if not message or self._logger is None:
            return
        try:
            self._logger(message)
        except Exception:  # pragma: no cover - 日志失败不影响预热
            pass


__all__ = [
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_LANGUAGES",
    "LANGS",
    "MIN_INTERVAL_SECONDS",
    "NoticeRefresher",
    "enumerate_notice_names",
    "evaluate_validity",
    "parse_datetime",
]
