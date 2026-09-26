# -*- coding: utf-8 -*-
"""公告汉化核心逻辑。

原理（详见上游逆向文档 `NOTICE_LOCALIZATION_WITHOUT_DLL_ANALYSIS.md`）：

* 公告文本**不经过**官方 `Lang/<语言包>/` 本地化系统，改语言包对公告零效果；
* `NoticeManager.DownloadNoticeDetails` 判定缓存命中**只看 `File.Exists`** ——
  文件在就永不下载；
* `RemoveInvalidNoticeFiles` 只删「不在官方 `noticeMeta.json` 名单里」的文件。

因此把译好的公告 JSON 按**官方同名文件名**写进
`persistentDataPath/notice/noticeDetails/` 即可，无需注入、无需打补丁。
中文字形由已安装的汉化语言包经 TMP 全局 fallback 提供。

客户端职责：取官方 meta → 逐个把目标文件名交给翻译服务 → 校验 → 原子落盘。
文本切分与回填由服务端完成，客户端不参与。

翻译服务地址**内置**为公共翻译服务（`service.DEFAULT_SERVICE_URL` =
`https://notice.lcta.top`），语言 / 超时 / 校验策略也全部取内置默认值——
公告汉化页面不提供任何配置项，`from_config()` 只负责组装这些常量。

服务端按 `{"status": "ok" | "pending", …}` 信封响应（契约见 `service.py`）：
`pending` 表示未命中缓存，客户端按指数退避等待重试，累计不超过
`service.PENDING_MAX_WAIT` 秒，并始终受调用方的时间预算与取消事件约束。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import paths
from .service import (
    DEFAULT_SERVICE_URL,
    DEFAULT_URL_TEMPLATE,
    NoticePendingError,
    NoticeServiceError,
    NoticeTranslationService,
    normalize_base_url,
)

OFFICIAL_BASE_URL = "https://notice.limbuscompanyapi.com"
LANGS = ("KR", "EN", "JP")
DEFAULT_LANG = "EN"
USER_AGENT = "LCTA-NoticeLocalizer/1.0"
MAX_META_BYTES = 2 * 1024 * 1024
MAX_DETAIL_BYTES = 2 * 1024 * 1024
DETAIL_NAME_RE = re.compile(r"^noticeDetail_(\d+)_(KR|EN|JP)_(\d+)\.json$", re.IGNORECASE)

STATE_VERSION = 1

ProgressCallback = Optional[Callable[[int, int, str], None]]


class NoticeLocalizeError(RuntimeError):
    """公告汉化流程失败（meta 获取、目录不可用等）。"""


# --------------------------------------------------------------------------
# 网络
# --------------------------------------------------------------------------
def http_get(url: str, timeout: int = 30, max_bytes: int = MAX_META_BYTES) -> bytes:
    """下载并返回原始字节，超长直接拒绝。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=max(1, int(timeout))) as resp:
            data = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise NoticeLocalizeError("请求 {} 失败: HTTP {}".format(url, exc.code))
    except urllib.error.URLError as exc:
        raise NoticeLocalizeError(
            "请求 {} 失败: {}".format(url, getattr(exc, "reason", exc))
        )
    except TimeoutError:
        raise NoticeLocalizeError("请求 {} 超时".format(url))
    if len(data) > max_bytes:
        raise NoticeLocalizeError("{} 返回内容过大，已拒绝".format(url))
    if not data.strip():
        raise NoticeLocalizeError("{} 返回空内容".format(url))
    return data


# --------------------------------------------------------------------------
# 日期 / 有效性
# --------------------------------------------------------------------------
def parse_datetime(value: str) -> Optional[datetime]:
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


def evaluate_validity(start_raw: str, end_raw: str, now: Optional[datetime] = None) -> bool:
    """是否处于有效期内（与游戏 `onlyValid` 过滤同义）。

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


# --------------------------------------------------------------------------
# meta 与目标文件
# --------------------------------------------------------------------------
def load_meta(
    official_timeout: int = 30,
    local_meta_path: Optional[Path] = None,
) -> Tuple[dict, Optional[bytes], str]:
    """取官方 meta，失败时回退本地缓存。

    返回 `(meta_dict, raw_bytes, source)`，`source` 为 `official` / `local`。
    """
    url = OFFICIAL_BASE_URL + "/" + paths.META_FILE_NAME
    raw: Optional[bytes] = None
    source = "official"
    try:
        raw = http_get(url, timeout=official_timeout)
    except NoticeLocalizeError:
        local_path = Path(local_meta_path) if local_meta_path else paths.get_meta_path()
        if local_path.exists():
            try:
                raw = local_path.read_bytes()
                source = "local"
            except OSError:
                raw = None
        if raw is None:
            raise NoticeLocalizeError(
                "无法获取官方公告清单（网络不可用且本地无 noticeMeta.json）"
            )
    try:
        meta = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise NoticeLocalizeError("公告清单不是合法 JSON: {}".format(exc))
    if not isinstance(meta, dict):
        raise NoticeLocalizeError("公告清单结构异常")
    return meta, (raw if source == "official" else None), source


def resolve_language(mode: str, details_dir: Path) -> str:
    """确定要写入的语言文件名后缀。

    `auto`：按公告缓存目录里已有的文件名后缀推断（中文系统上游戏落 `default`
    分支 → `EN`），无迹可循时兜底 `EN`。
    """
    mode = (mode or "auto").strip().upper()
    if mode in LANGS:
        return mode
    counter: Counter = Counter()
    try:
        if details_dir.is_dir():
            for entry in details_dir.iterdir():
                match = DETAIL_NAME_RE.match(entry.name)
                if match:
                    counter[match.group(2).upper()] += 1
    except OSError:
        pass
    if counter:
        return counter.most_common(1)[0][0]
    return DEFAULT_LANG


def enumerate_targets(meta: dict, lang: str, only_valid: bool = True) -> List[dict]:
    """列出 meta 中该语言的目标公告文件。"""
    entries = meta.get("noticeDetailList")
    if not isinstance(entries, list):
        return []
    key = "fileName_" + (lang or DEFAULT_LANG).upper()
    targets: List[dict] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        file_name = item.get(key)
        if not isinstance(file_name, str) or not file_name.strip():
            continue
        file_name = file_name.strip()
        # 只接受官方命名格式，避免任何非法文件名被写进缓存目录
        if not DETAIL_NAME_RE.match(file_name):
            continue
        start_raw = item.get("startDate") or ""
        end_raw = item.get("endDate") or ""
        valid = evaluate_validity(start_raw, end_raw)
        if only_valid and not valid:
            continue
        targets.append(
            {
                "id": item.get("id"),
                "file": file_name,
                "start_date": start_raw,
                "end_date": end_raw,
                "valid": valid,
            }
        )
    return targets


# --------------------------------------------------------------------------
# 校验 / 落盘
# --------------------------------------------------------------------------
def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def validate_translated(raw: bytes, official_raw: Optional[bytes] = None) -> dict:
    """校验服务返回的公告 JSON 是否可安全写进游戏缓存。

    硬性错误（不落盘）：JSON 不可解析、缺字段、`formatKey` 序列与官方不一致
    —— 自创 / 丢失 `formatKey` 会让 `NoticeUIContentViewManager.SetData`
    抛空引用、整篇公告正文中断渲染。
    """
    errors: List[str] = []
    warnings: List[str] = []
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        return {"ok": False, "errors": ["返回内容不是合法 JSON: {}".format(exc)], "warnings": []}
    if isinstance(payload, dict) and payload.get("ok") is False:
        error = payload.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        return {"ok": False, "errors": ["服务端返回失败: {}".format(message or "未知原因")], "warnings": []}
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["公告 JSON 顶层不是对象"], "warnings": []}

    if not isinstance(payload.get("id"), int):
        errors.append("缺少 id 字段")
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("title 为空")
    if not isinstance(payload.get("noticeType"), int):
        errors.append("缺少 noticeType 字段")

    content = payload.get("content")
    items = content.get("list") if isinstance(content, dict) else None
    if not isinstance(items, list):
        errors.append("缺少 content.list 数组")
        items = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append("content.list[{}] 不是对象".format(index))
            continue
        if not isinstance(item.get("formatKey"), str) or not item.get("formatKey"):
            errors.append("content.list[{}] 缺少 formatKey".format(index))
        if not isinstance(item.get("formatValue"), str):
            errors.append("content.list[{}] 的 formatValue 不是字符串".format(index))

    if official_raw:
        try:
            official = json.loads(official_raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError):
            official = None
        if isinstance(official, dict):
            official_keys = [
                (c or {}).get("formatKey")
                for c in (official.get("content") or {}).get("list") or []
            ]
            new_keys = [(c or {}).get("formatKey") for c in items]
            if official_keys != new_keys:
                errors.append(
                    "formatKey 序列与官方不一致（官方 {} 项 / 译文 {} 项）".format(
                        len(official_keys), len(new_keys)
                    )
                )
            if official.get("id") != payload.get("id"):
                errors.append("id 与官方不一致")
            if official.get("noticeType") != payload.get("noticeType"):
                errors.append("noticeType 与官方不一致")
            if list(official.get("sprList") or []) != list(payload.get("sprList") or []):
                warnings.append("sprList（公告配图）与官方不一致")
            if official.get("title") == title and not _contains_cjk(title):
                warnings.append("标题与官方原文一致，可能未翻译")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 256), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """先写同目录临时文件再原子改名。

    游戏下载用的是 `DownloadHandlerFile` 直写目标文件，中断会留下半截 JSON
    且因 `File.Exists` 为真而永不重下；本工具侧必须避免同类问题。
    """
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


# --------------------------------------------------------------------------
# 状态
# --------------------------------------------------------------------------
def load_state(state_path: Path) -> dict:
    try:
        payload = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = None
    if not isinstance(payload, dict):
        payload = {}
    files = payload.get("files")
    if not isinstance(files, dict):
        files = {}
    return {
        "version": STATE_VERSION,
        "lang": payload.get("lang") or "",
        "files": files,
    }


def save_state(state_path: Path, state: dict) -> None:
    state_path = Path(state_path)
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": STATE_VERSION,
            "lang": state.get("lang") or "",
            "files": state.get("files") or {},
        }
        atomic_write_bytes(
            state_path,
            json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8"),
        )
    except Exception:
        # 状态文件只影响「是否需要重新请求」的判定，写失败不应中断同步流程
        pass


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
class NoticeLocalizer:
    """公告汉化执行器。

    所有路径与配置均可注入，便于单测；默认值取自 `paths` 与显式参数。
    `from_config()` 不读任何用户配置——服务地址与全部策略都内置
    （见 `service.DEFAULT_SERVICE_URL`），页面不提供配置项。
    """

    def __init__(
        self,
        notice_dir: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
        service_url: str = DEFAULT_SERVICE_URL,
        url_template: str = DEFAULT_URL_TEMPLATE,
        timeout: int = 60,
        lang_mode: str = "auto",
        only_valid: bool = True,
        verify_official: bool = True,
        seed_meta: bool = True,
        meta_timeout: int = 30,
    ):
        self.notice_dir = Path(notice_dir) if notice_dir else paths.get_notice_dir()
        self.cache_dir = Path(cache_dir) if cache_dir else paths.get_cache_dir()
        self.service_url = normalize_base_url(service_url)
        self.url_template = (url_template or "").strip() or DEFAULT_URL_TEMPLATE
        self.timeout = timeout
        self.lang_mode = lang_mode or "auto"
        self.only_valid = bool(only_valid)
        self.verify_official = bool(verify_official)
        self.seed_meta = bool(seed_meta)
        self.meta_timeout = meta_timeout

    # -- 派生路径 ---------------------------------------------------------
    @property
    def details_dir(self) -> Path:
        return self.notice_dir / paths.DETAILS_FOLDER_NAME

    @property
    def meta_path(self) -> Path:
        return self.notice_dir / paths.META_FILE_NAME

    @property
    def originals_dir(self) -> Path:
        return self.cache_dir / paths.ORIGINALS_FOLDER_NAME

    @property
    def state_path(self) -> Path:
        return self.cache_dir / paths.STATE_FILE_NAME

    def service(self) -> NoticeTranslationService:
        return NoticeTranslationService(
            self.service_url, self.url_template, self.timeout
        )

    # -- 配置组装 ---------------------------------------------------------
    @classmethod
    def from_config(cls) -> "NoticeLocalizer":
        """组装执行器：服务地址与全部策略都内置，页面不再提供任何配置项。

        服务地址固定为 `service.DEFAULT_SERVICE_URL`（公共翻译服务），
        `url_template` / `timeout` / `lang_mode` / `only_valid` / `verify_official`
        / `seed_meta` 一律取类默认值 —— 语言按公告缓存自动推断、校验与补种恒开，
        用户侧无需（也无法）配置。
        """
        return cls(service_url=DEFAULT_SERVICE_URL)

    # -- 服务状态 ---------------------------------------------------------
    def service_status(self) -> dict:
        """查询内置翻译服务的运行状态（页面加载时自动刷新，不落盘）。"""
        try:
            payload = self.service().status()
        except NoticeServiceError as exc:
            return {
                "success": False,
                "service_url": self.service_url,
                "kind": exc.kind,
                "message": str(exc),
            }
        return {
            "success": True,
            "service_url": self.service_url,
            "state": payload.get("state") or "",
            "cached": payload.get("cached"),
            "running": payload.get("running"),
            "translated": payload.get("translated"),
            "failed": payload.get("failed"),
        }

    # -- 只读状态 ---------------------------------------------------------
    def _classify(self, file_name: str, state: dict) -> Tuple[str, Optional[str]]:
        local = self.details_dir / file_name
        if not local.exists():
            return "missing", None
        recorded = (state.get("files") or {}).get(file_name) or {}
        recorded_hash = recorded.get("sha256")
        if recorded_hash and recorded_hash == sha256_file(local):
            return "translated", recorded.get("title")
        return "official", recorded.get("title")

    def info(self, meta: Optional[dict] = None, meta_source: str = "") -> dict:
        """页面初始化信息：路径、语言、公告清单与逐条状态。"""
        details_dir = self.details_dir
        state = load_state(self.state_path)
        lang = resolve_language(self.lang_mode, details_dir)

        items: List[dict] = []
        counts = {"total": 0, "translated": 0, "official": 0, "missing": 0}
        error = ""
        if meta is None:
            try:
                meta, _raw, meta_source = load_meta(
                    official_timeout=self.meta_timeout, local_meta_path=self.meta_path
                )
            except NoticeLocalizeError as exc:
                meta = None
                error = str(exc)
        if isinstance(meta, dict):
            for target in enumerate_targets(meta, lang, self.only_valid):
                status, title = self._classify(target["file"], state)
                counts["total"] += 1
                counts[status] = counts.get(status, 0) + 1
                items.append(
                    {
                        "file": target["file"],
                        "id": target["id"],
                        "valid": target["valid"],
                        "status": status,
                        "title": title,
                        "end_date": target["end_date"],
                    }
                )

        return {
            "success": True,
            "notice_dir": str(self.notice_dir),
            "details_dir": str(details_dir),
            "cache_dir": str(self.cache_dir),
            "notice_dir_exists": self.notice_dir.is_dir(),
            "service_url": self.service_url,
            "url_template": self.url_template,
            "timeout": self.timeout,
            "lang_mode": self.lang_mode,
            "lang": lang,
            "only_valid": self.only_valid,
            "verify_official": self.verify_official,
            "seed_meta": self.seed_meta,
            "meta_source": meta_source,
            "meta_error": error,
            "counts": counts,
            "items": items,
        }

    # -- 同步 -------------------------------------------------------------
    def sync(
        self,
        force: bool = False,
        cancel_event=None,
        progress: ProgressCallback = None,
        deadline: Optional[float] = None,
        targets_filter: Optional[List[str]] = None,
    ) -> dict:
        """增量同步：把 meta 中未汉化的公告逐篇交给翻译服务并落盘。

        `deadline` 为 `time.monotonic()` 时间点，用于 Launcher 阶段的启动预算；
        超时只影响本次剩余条目，已写入的文件保持有效。
        """

        def report(done: int, total: int, message: str) -> None:
            if progress is None:
                return
            try:
                progress(done, total, message)
            except Exception:
                pass

        def cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        def timed_out() -> bool:
            return deadline is not None and time.monotonic() >= deadline

        result = {
            "success": False,
            "total": 0,
            "translated": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": False,
            "timed_out": False,
            "pending": False,
            "lang": "",
            "meta_source": "",
            "items": [],
            "message": "",
        }

        try:
            meta, meta_raw, meta_source = load_meta(
                official_timeout=self.meta_timeout, local_meta_path=self.meta_path
            )
        except NoticeLocalizeError as exc:
            result["message"] = str(exc)
            return result

        result["meta_source"] = meta_source
        lang = resolve_language(self.lang_mode, self.details_dir)
        result["lang"] = lang

        if self.seed_meta and meta_raw and not self.meta_path.exists():
            # 只补缺失的 meta：内容随时会被游戏重下覆盖，改它没有意义
            try:
                atomic_write_bytes(self.meta_path, meta_raw)
            except Exception as exc:
                result["items"].append(
                    {"file": paths.META_FILE_NAME, "status": "failed", "message": "写入 meta 失败: {}".format(exc)}
                )

        targets = enumerate_targets(meta, lang, self.only_valid)
        if targets_filter:
            wanted = set(targets_filter)
            targets = [t for t in targets if t["file"] in wanted]
        result["total"] = len(targets)
        if not targets:
            result["success"] = True
            result["message"] = "官方公告清单中没有需要处理的公告"
            report(0, 0, result["message"])
            return result

        state = load_state(self.state_path)
        if state.get("lang") and state["lang"] != lang:
            # 语言变了：旧语言文件会被游戏的 RemoveInvalidNoticeFiles 删掉，
            # 状态里对应的指纹一并作废，避免误判「已汉化」
            state["files"] = {}
        state["lang"] = lang

        service = self.service()
        done = 0
        report(0, len(targets), "开始同步公告")

        for target in targets:
            file_name = target["file"]
            if cancelled():
                result["cancelled"] = True
                result["message"] = "已取消"
                break
            if timed_out():
                result["timed_out"] = True
                result["message"] = "已达时间预算，剩余公告留待下次同步"
                break

            local = self.details_dir / file_name
            recorded = (state.get("files") or {}).get(file_name) or {}
            if not force and local.exists() and recorded.get("sha256") == sha256_file(local):
                done += 1
                result["skipped"] += 1
                result["items"].append(
                    {"file": file_name, "id": target["id"], "status": "skipped", "message": "已汉化"}
                )
                report(done, len(targets), "已汉化: {}".format(file_name))
                continue

            report(done, len(targets), "正在翻译: {}".format(file_name))
            official_raw: Optional[bytes] = None
            if self.verify_official:
                try:
                    official_raw = http_get(
                        "{}/noticeDetails/{}".format(OFFICIAL_BASE_URL, file_name),
                        timeout=self.meta_timeout,
                        max_bytes=MAX_DETAIL_BYTES,
                    )
                except NoticeLocalizeError:
                    official_raw = None

            def on_wait(attempt: int, delay: float, waited: float) -> None:
                report(
                    done,
                    len(targets),
                    "服务端未命中缓存，{} 秒后重试（第 {} 次，已等待 {} 秒）".format(
                        int(delay), attempt, int(waited)
                    ),
                )

            try:
                translated = service.request(
                    file_name,
                    cancel_event=cancel_event,
                    deadline=deadline,
                    on_wait=on_wait,
                )
            except NoticePendingError as exc:
                # 服务端明确表示「未命中缓存」且等待预算已耗尽。
                # 这不是失败：服务端正在译，剩余公告留待下次同步即可。
                if exc.reason == "cancelled":
                    result["cancelled"] = True
                    result["message"] = "已取消"
                    break
                if exc.reason == "deadline":
                    result["timed_out"] = True
                    result["message"] = "已达时间预算，剩余公告留待下次同步"
                    break
                result["pending"] = True
                result["items"].append(
                    {
                        "file": file_name,
                        "id": target["id"],
                        "status": "pending",
                        "message": str(exc),
                        "kind": "pending",
                    }
                )
                result["message"] = "{}；本次同步已停止，稍后重试可继续".format(exc)
                report(done, len(targets), "服务端未就绪: {}".format(file_name))
                break
            except NoticeServiceError as exc:
                done += 1
                result["failed"] += 1
                result["items"].append(
                    {
                        "file": file_name,
                        "id": target["id"],
                        "status": "failed",
                        "message": str(exc),
                        "kind": exc.kind,
                    }
                )
                report(done, len(targets), "失败: {} ({})".format(file_name, exc))
                continue

            verdict = validate_translated(translated, official_raw)
            if not verdict["ok"]:
                done += 1
                result["failed"] += 1
                result["items"].append(
                    {
                        "file": file_name,
                        "id": target["id"],
                        "status": "failed",
                        "message": "；".join(verdict["errors"]),
                        "kind": "invalid",
                    }
                )
                report(done, len(targets), "校验未通过: {}".format(file_name))
                continue

            try:
                if official_raw:
                    self.originals_dir.mkdir(parents=True, exist_ok=True)
                    backup = self.originals_dir / file_name
                    if not backup.exists():
                        atomic_write_bytes(backup, official_raw)
                atomic_write_bytes(local, translated)
            except Exception as exc:
                done += 1
                result["failed"] += 1
                result["items"].append(
                    {"file": file_name, "id": target["id"], "status": "failed", "message": "写入失败: {}".format(exc)}
                )
                continue

            try:
                payload = json.loads(translated.decode("utf-8-sig"))
            except (UnicodeDecodeError, ValueError):
                payload = {}
            state.setdefault("files", {})[file_name] = {
                "sha256": sha256_bytes(translated),
                "size": len(translated),
                "title": payload.get("title") if isinstance(payload, dict) else None,
                "fetched_at": int(time.time()),
                "service": self.service_url,
                "warnings": verdict["warnings"],
            }
            save_state(self.state_path, state)

            done += 1
            result["translated"] += 1
            result["items"].append(
                {
                    "file": file_name,
                    "id": target["id"],
                    "status": "translated",
                    "title": (payload or {}).get("title"),
                    "message": "已汉化",
                    "warnings": verdict["warnings"],
                }
            )
            report(done, len(targets), "已完成: {}".format(file_name))

        save_state(self.state_path, state)
        result["success"] = result["failed"] == 0 and not result["cancelled"]
        if not result["message"]:
            result["message"] = "完成：汉化 {} 篇，跳过 {} 篇，失败 {} 篇".format(
                result["translated"], result["skipped"], result["failed"]
            )
        return result

    # -- 还原 -------------------------------------------------------------
    def restore(self, files: Optional[List[str]] = None) -> dict:
        """还原官方原文：删除本工具写入的公告文件（游戏下次进大厅会重新下载原文）。"""
        state = load_state(self.state_path)
        recorded = state.get("files") or {}
        removed: List[str] = []
        failed: List[str] = []
        for file_name in list(recorded.keys()):
            if files and file_name not in files:
                continue
            local = self.details_dir / file_name
            try:
                if local.exists() and recorded[file_name].get("sha256") == sha256_file(local):
                    local.unlink()
                    removed.append(file_name)
                elif local.exists():
                    # 已被游戏重新下载 / 外部改动，不动它，只清状态
                    failed.append(file_name)
                recorded.pop(file_name, None)
            except Exception:
                failed.append(file_name)
        state["files"] = recorded
        save_state(self.state_path, state)
        return {
            "success": not failed,
            "removed": removed,
            "skipped": failed,
            "message": "已还原 {} 篇公告，游戏下次进入大厅会自动下载官方原文".format(len(removed)),
        }

    # -- 连通性 -----------------------------------------------------------
    def test_service(self, file_name: str = "") -> dict:
        """测试翻译服务连通性：请求一篇目标公告并校验（不落盘）。"""
        target = file_name
        if not target:
            try:
                meta, _raw, _source = load_meta(
                    official_timeout=self.meta_timeout, local_meta_path=self.meta_path
                )
            except NoticeLocalizeError as exc:
                return {"success": False, "message": str(exc)}
            lang = resolve_language(self.lang_mode, self.details_dir)
            targets = enumerate_targets(meta, lang, only_valid=False)
            if not targets:
                return {"success": False, "message": "官方公告清单为空，无法测试"}
            target = targets[0]["file"]

        started = time.time()
        try:
            probe = self.service().probe(target)
        except NoticeServiceError as exc:
            return {"success": False, "message": str(exc), "kind": exc.kind, "file": target}

        elapsed = round(time.time() - started, 2)
        if probe.get("pending"):
            # 连接是通的，只是服务端还没译好这一篇；同步时会自动等待重试
            return {
                "success": True,
                "file": target,
                "pending": True,
                "title": None,
                "bytes": 0,
                "elapsed": elapsed,
                "message": "服务可用，但该公告尚未命中缓存（同步时会自动等待重试）",
            }
        return {
            "success": True,
            "file": target,
            "pending": False,
            "title": probe.get("title"),
            "bytes": probe.get("bytes"),
            "elapsed": elapsed,
            "message": "服务可用（{}）".format(target),
        }
