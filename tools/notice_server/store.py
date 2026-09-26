# -*- coding: utf-8 -*-
"""官方原文获取 + 译文缓存。

两个职责：

* **官方原文**：按文件名从官方公告 CDN 取（内存缓存，同一进程内不重复拉）；
* **译文缓存**：把译好的整篇 JSON 落盘，下次请求直接命中。

文件名的白名单校验（`NOTICE_NAME_RE`）是**安全边界**：文件名来自 URL，不校验就等于
把 `../` 交给了 `cache_dir / file_name`。规则与客户端 `core.DETAIL_NAME_RE` 同源。
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional

USER_AGENT = "LCTA-NoticeServer/1.0"
MAX_OFFICIAL_BYTES = 4 * 1024 * 1024

NOTICE_NAME_RE = re.compile(r"^noticeDetail_(\d+)_(KR|EN|JP)_(\d+)\.json$", re.IGNORECASE)


class NoticeStoreError(RuntimeError):
    """官方原文获取或缓存读写失败。"""


def is_valid_notice_name(file_name: str) -> bool:
    """只接受官方命名，顺带挡住路径穿越。"""
    return bool(isinstance(file_name, str) and NOTICE_NAME_RE.match(file_name))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """同目录临时文件 + fsync + os.replace，避免留下半截文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = None
    tmp_path = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".lcta-", suffix=".tmp", dir=str(path.parent)
        )
        tmp_path = Path(tmp_name)
        handle = os.fdopen(fd, "wb")
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(str(tmp_path), str(path))
        tmp_path = None
    finally:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


class NoticeStore:
    def __init__(
        self,
        cache_dir,
        official_base_url: str,
        timeout: int = 30,
        opener: Optional[Callable] = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.official_base_url = (official_base_url or "").strip().rstrip("/")
        self.timeout = max(1, int(timeout))
        self._opener = opener or urllib.request.urlopen
        self._official: dict = {}
        self._lock = threading.Lock()

    # -- 译文缓存 ---------------------------------------------------------
    def cached_path(self, file_name: str) -> Path:
        return self.cache_dir / file_name

    def read_translated(self, file_name: str) -> Optional[bytes]:
        try:
            data = self.cached_path(file_name).read_bytes()
        except OSError:
            return None
        return data if data.strip() else None

    def save_translated(self, file_name: str, payload: dict) -> bytes:
        data = json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
        atomic_write_bytes(self.cached_path(file_name), data)
        return data

    def cached_names(self) -> List[str]:
        try:
            return sorted(
                path.name
                for path in self.cache_dir.glob("*.json")
                if is_valid_notice_name(path.name)
            )
        except OSError:
            return []

    # -- 官方原文 ---------------------------------------------------------
    def official(self, file_name: str) -> bytes:
        with self._lock:
            hit = self._official.get(file_name)
        if hit is not None:
            return hit

        if not self.official_base_url:
            raise NoticeStoreError("未配置官方公告地址")
        url = "{}/noticeDetails/{}".format(self.official_base_url, file_name)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with self._opener(req, timeout=self.timeout) as resp:
                data = resp.read(MAX_OFFICIAL_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise NoticeStoreError("官方公告不存在或不可用（HTTP {}）".format(exc.code))
        except urllib.error.URLError as exc:
            raise NoticeStoreError("无法获取官方公告: {}".format(getattr(exc, "reason", exc)))
        except TimeoutError:
            raise NoticeStoreError("获取官方公告超时（{} 秒）".format(self.timeout))

        if len(data) > MAX_OFFICIAL_BYTES:
            raise NoticeStoreError("官方公告过大，已拒绝")
        if not data.strip():
            raise NoticeStoreError("官方公告内容为空")

        with self._lock:
            self._official[file_name] = data
        return data
