# -*- coding: utf-8 -*-
"""公告汉化（webutils/notice）核心逻辑测试。

覆盖：
- 目标语言判定（显式指定 / 按缓存目录推断 / 兜底 EN）
- 有效期过滤（ISO 与 Unity DateUtil 两种日期格式、解析失败保守放行）
- 目标文件枚举（拒绝非法文件名、缺语言字段、过期公告）
- 译文校验（formatKey 序列、id/noticeType 一致性、非 JSON、服务端失败信封）
- 原子落盘（不留临时文件、覆盖已有文件）
- 增量同步（已汉化跳过、force 重取、状态指纹失效后重取、失败不落盘）
- 未命中缓存（`status=pending`）的等待重试：退避序列、预算耗尽、取消、时间预算
- 还原（删除本工具写入的文件、外部改动不动）
- 翻译服务客户端（URL 模板渲染、`{status, data}` 信封拆解、404/非 JSON/成功）
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from webutils.notice import core
from webutils.notice.core import (
    NoticeLocalizer,
    atomic_write_bytes,
    enumerate_targets,
    evaluate_validity,
    resolve_language,
    validate_translated,
)
from webutils.notice.service import (
    DEFAULT_SERVICE_URL,
    DEFAULT_URL_TEMPLATE,
    PENDING_MAX_WAIT,
    WAIT_SLICE_SECONDS,
    NoticePendingError,
    NoticeServiceError,
    NoticeTranslationService,
    pending_delays,
)

ISO_PAST = "2020-01-01T00:00:00.000Z"
ISO_FUTURE = "2098-12-31T21:00:00.000Z"
DATEUTIL_PAST = "Thu Sep 17 2025 01:04:36 GMT+0000 (Coordinated Universal Time)"
DATEUTIL_FUTURE = "Thu Sep 17 2099 01:04:36 GMT+0000 (Coordinated Universal Time)"


def make_meta(entries):
    return {"latestUpdateDate": "Fri Jun 20 2025 18:29:34 GMT+0900 (KST)", "noticeDetailList": entries}


def make_entry(notice_id=200001, suffix="219", start=ISO_PAST, end=ISO_FUTURE, langs=("KR", "EN", "JP")):
    entry = {"id": notice_id, "startDate": start, "endDate": end}
    for lang in langs:
        entry["fileName_" + lang] = "noticeDetail_{}_{}_{}.json".format(notice_id, lang, suffix)
    return entry


def make_detail(notice_id=200001, title="Official Twitter", keys=("Text", "HyperLink")):
    return {
        "id": notice_id,
        "noticeType": 0,
        "startDate": DATEUTIL_FUTURE,
        "endDate": DATEUTIL_FUTURE,
        "sprList": [str(notice_id)],
        "title": title,
        "content": {
            "list": [
                {"formatKey": key, "formatValue": "value-{}".format(index)}
                for index, key in enumerate(keys)
            ]
        },
    }


def to_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def envelope(payload=None, status="ok", message=None):
    """构造服务端 `{status, data}` 信封。"""
    body = {"status": status}
    if status == "ok":
        body["data"] = payload
    if message is not None:
        body["message"] = message
    return to_bytes(body)


# --------------------------------------------------------------------------
# 语言判定
# --------------------------------------------------------------------------
class TestResolveLanguage:
    def test_explicit_mode_wins(self, tmp_path):
        (tmp_path / "noticeDetail_1_KR_1.json").write_text("{}", encoding="utf-8")
        assert resolve_language("JP", tmp_path) == "JP"
        assert resolve_language("en", tmp_path) == "EN"

    def test_auto_infers_from_existing_files(self, tmp_path):
        for name in ("noticeDetail_1_KR_1.json", "noticeDetail_2_KR_2.json", "noticeDetail_3_EN_3.json"):
            (tmp_path / name).write_text("{}", encoding="utf-8")
        assert resolve_language("auto", tmp_path) == "KR"

    def test_auto_falls_back_to_en(self, tmp_path):
        assert resolve_language("auto", tmp_path) == "EN"
        assert resolve_language("auto", tmp_path / "missing") == "EN"
        assert resolve_language("", tmp_path) == "EN"


# --------------------------------------------------------------------------
# 有效期
# --------------------------------------------------------------------------
class TestValidity:
    def test_iso_bounds(self):
        assert evaluate_validity(ISO_PAST, ISO_FUTURE) is True
        assert evaluate_validity(ISO_FUTURE, ISO_FUTURE) is False
        assert evaluate_validity(ISO_PAST, ISO_PAST) is False

    def test_dateutil_format(self):
        now = datetime(2026, 9, 22, tzinfo=timezone.utc)
        assert evaluate_validity(DATEUTIL_PAST, DATEUTIL_FUTURE, now=now) is True
        assert evaluate_validity(DATEUTIL_FUTURE, DATEUTIL_FUTURE, now=now) is False
        assert evaluate_validity(DATEUTIL_PAST, DATEUTIL_PAST, now=now) is False

    def test_unparseable_is_treated_as_valid(self):
        assert evaluate_validity("", "") is True
        assert evaluate_validity("not a date", "also not") is True
        assert core.parse_datetime("") is None


# --------------------------------------------------------------------------
# 目标枚举
# --------------------------------------------------------------------------
class TestEnumerateTargets:
    def test_filters_invalid_names_and_expired(self):
        meta = make_meta(
            [
                make_entry(200001),
                make_entry(200002, start=ISO_FUTURE),  # 未开始
                make_entry(200003, end=ISO_PAST),      # 已过期
                {"id": 200004, "startDate": ISO_PAST, "endDate": ISO_FUTURE,
                 "fileName_EN": "../../evil.json"},
                {"id": 200005, "startDate": ISO_PAST, "endDate": ISO_FUTURE},
            ]
        )
        files = [t["file"] for t in enumerate_targets(meta, "EN", only_valid=True)]
        assert files == ["noticeDetail_200001_EN_219.json"]

        all_files = [t["file"] for t in enumerate_targets(meta, "EN", only_valid=False)]
        assert all_files == [
            "noticeDetail_200001_EN_219.json",
            "noticeDetail_200002_EN_219.json",
            "noticeDetail_200003_EN_219.json",
        ]

    def test_missing_language_field_is_skipped(self):
        meta = make_meta([make_entry(200001, langs=("KR",))])
        assert enumerate_targets(meta, "EN") == []
        assert len(enumerate_targets(meta, "KR")) == 1

    def test_broken_meta_shapes(self):
        assert enumerate_targets({}, "EN") == []
        assert enumerate_targets({"noticeDetailList": "nope"}, "EN") == []


# --------------------------------------------------------------------------
# 译文校验
# --------------------------------------------------------------------------
class TestValidateTranslated:
    def test_accepts_matching_payload(self):
        official = to_bytes(make_detail())
        translated = to_bytes(make_detail(title="官方 Twitter 账号"))
        verdict = validate_translated(translated, official)
        assert verdict["ok"] is True
        assert verdict["errors"] == []

    def test_rejects_non_json(self):
        verdict = validate_translated(b"<html>502</html>")
        assert verdict["ok"] is False

    def test_rejects_service_error_envelope(self):
        verdict = validate_translated(to_bytes({"ok": False, "error": {"message": "boom"}}))
        assert verdict["ok"] is False
        assert "boom" in verdict["errors"][0]

    def test_rejects_format_key_drift(self):
        official = to_bytes(make_detail(keys=("Text", "HyperLink")))
        translated = to_bytes(make_detail(title="中文标题", keys=("Text", "SubTitle")))
        verdict = validate_translated(translated, official)
        assert verdict["ok"] is False
        assert any("formatKey" in e for e in verdict["errors"])

    def test_rejects_id_and_notice_type_drift(self):
        official = to_bytes(make_detail(notice_id=200001))
        translated = to_bytes(make_detail(notice_id=999999, title="中文"))
        verdict = validate_translated(translated, official)
        assert verdict["ok"] is False
        assert any("id" in e for e in verdict["errors"])

    def test_rejects_missing_fields(self):
        verdict = validate_translated(to_bytes({"title": "", "content": {}}))
        assert verdict["ok"] is False
        assert len(verdict["errors"]) >= 3

    def test_warns_when_title_untouched(self):
        official = to_bytes(make_detail())
        translated = to_bytes(make_detail())
        verdict = validate_translated(translated, official)
        assert verdict["ok"] is True
        assert any("未翻译" in w for w in verdict["warnings"])


# --------------------------------------------------------------------------
# 原子落盘
# --------------------------------------------------------------------------
class TestAtomicWrite:
    def test_writes_and_leaves_no_temp(self, tmp_path):
        target = tmp_path / "noticeDetails" / "a.json"
        atomic_write_bytes(target, b'{"a":1}')
        assert target.read_bytes() == b'{"a":1}'
        leftovers = [p.name for p in target.parent.iterdir() if p.name != "a.json"]
        assert leftovers == []

    def test_replaces_existing(self, tmp_path):
        target = tmp_path / "a.json"
        target.write_bytes(b"old")
        atomic_write_bytes(target, b"new")
        assert target.read_bytes() == b"new"


# --------------------------------------------------------------------------
# 同步流程
# --------------------------------------------------------------------------
class FakeService:
    """假翻译服务客户端替身。

    注意：`NoticeTranslationService.request()` 的返回值是**已拆开信封的**译文 JSON
    字节（`{status, data}` 的拆解由客户端负责），所以这里直接给 `data` 本体，
    信封本身的解析在 `TestServiceClient` / `TestPendingRetry` 里用真实 HTTP 覆盖。

    * `pending_error` 非空时所有请求都抛它（模拟服务端一直未命中缓存）；
    * `probe_pending` 为真时 `probe()` 报告 pending（连通性测试用）。
    """

    def __init__(self, payloads=None, error=None, title_prefix="中文公告",
                 pending_error=None, probe_pending=False):
        self.payloads = payloads or {}
        self.error = error
        self.title_prefix = title_prefix
        self.pending_error = pending_error
        self.probe_pending = probe_pending
        self.requests = []
        self.request_kwargs = []

    def request(self, file_name, **kwargs):
        self.requests.append(file_name)
        self.request_kwargs.append(kwargs)
        if self.pending_error is not None:
            raise self.pending_error
        if self.error is not None:
            raise self.error
        if file_name in self.payloads:
            return self.payloads[file_name]
        match = core.DETAIL_NAME_RE.match(file_name)
        notice_id = int(match.group(1)) if match else 0
        return to_bytes(
            make_detail(notice_id, title="{}-{}".format(self.title_prefix, notice_id))
        )

    def probe(self, file_name):
        if self.probe_pending:
            return {"file": file_name, "title": None, "bytes": 0, "pending": True}
        data = self.request(file_name)
        return {
            "file": file_name,
            "title": json.loads(data.decode("utf-8"))["title"],
            "bytes": len(data),
            "pending": False,
        }


class FakeLocalizer(NoticeLocalizer):
    def __init__(self, *args, service=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._service = service

    def service(self):
        return self._service


@pytest.fixture
def localizer_env(tmp_path, monkeypatch):
    """构造一个完全离线的环境：官方 CDN 与翻译服务均由假实现提供。"""
    notice_dir = tmp_path / "LocalLow" / "notice"
    cache_dir = tmp_path / "LCTA" / "notice"
    meta = make_meta([make_entry(200001), make_entry(200002, suffix="564")])
    official_details = {
        "noticeDetail_200001_EN_219.json": to_bytes(make_detail(200001)),
        "noticeDetail_200002_EN_564.json": to_bytes(make_detail(200002)),
    }

    def fake_http_get(url, timeout=30, max_bytes=None):
        if url.endswith("noticeMeta.json"):
            return to_bytes(meta)
        name = url.rsplit("/", 1)[-1]
        if name in official_details:
            return official_details[name]
        raise core.NoticeLocalizeError("404 {}".format(url))

    monkeypatch.setattr(core, "http_get", fake_http_get)
    return {"notice_dir": notice_dir, "cache_dir": cache_dir, "official": official_details}


def build_localizer(env, service, **kwargs):
    params = {
        "notice_dir": env["notice_dir"],
        "cache_dir": env["cache_dir"],
        "service_url": "http://127.0.0.1:1",
        "lang_mode": "EN",
    }
    params.update(kwargs)
    return FakeLocalizer(service=service, **params)


class TestSync:
    def test_translates_and_writes(self, localizer_env):
        service = FakeService(
            {
                "noticeDetail_200001_EN_219.json": to_bytes(make_detail(200001, title="公告一")),
                "noticeDetail_200002_EN_564.json": to_bytes(make_detail(200002, title="公告二")),
            }
        )
        localizer = build_localizer(localizer_env, service)
        result = localizer.sync()

        assert result["success"] is True
        assert result["translated"] == 2
        assert result["failed"] == 0
        assert result["pending"] is False
        details = localizer_env["notice_dir"] / "noticeDetails"
        written = sorted(p.name for p in details.iterdir())
        assert written == ["noticeDetail_200001_EN_219.json", "noticeDetail_200002_EN_564.json"]
        payload = json.loads((details / "noticeDetail_200001_EN_219.json").read_text(encoding="utf-8"))
        assert payload["title"] == "公告一"
        # 落盘的是 data 本体，不是整封信封
        assert "status" not in payload
        # 官方原文被备份到工具缓存
        assert (localizer_env["cache_dir"] / "originals" / "noticeDetail_200001_EN_219.json").exists()
        # meta 被补种到游戏目录（避免首启下载失败弹窗）
        assert (localizer_env["notice_dir"] / "noticeMeta.json").exists()

    def test_second_run_skips(self, localizer_env):
        service = FakeService()
        localizer = build_localizer(localizer_env, service)
        localizer.sync()
        assert len(service.requests) == 2

        service.requests = []
        result = localizer.sync()
        assert result["skipped"] == 2
        assert service.requests == []

        localizer.sync(force=True)
        assert len(service.requests) == 2

    def test_retranslates_when_local_file_replaced(self, localizer_env):
        service = FakeService()
        localizer = build_localizer(localizer_env, service)
        localizer.sync()

        # 模拟游戏重新下载了官方原文（覆盖我们的文件）
        target = localizer_env["notice_dir"] / "noticeDetails" / "noticeDetail_200001_EN_219.json"
        target.write_bytes(to_bytes(make_detail(200001)))

        service.requests = []
        result = localizer.sync()
        assert result["translated"] == 1
        assert result["skipped"] == 1
        assert service.requests == ["noticeDetail_200001_EN_219.json"]

    def test_failed_service_does_not_write(self, localizer_env):
        service = FakeService(error=NoticeServiceError("无法连接翻译服务", kind="network"))
        localizer = build_localizer(localizer_env, service)
        result = localizer.sync()

        assert result["success"] is False
        assert result["failed"] == 2
        assert result["pending"] is False
        assert not (localizer_env["notice_dir"] / "noticeDetails").exists()

    def test_invalid_payload_is_rejected(self, localizer_env):
        bad = to_bytes(make_detail(200001, keys=("Text", "SubTitle")))
        service = FakeService(
            {
                "noticeDetail_200001_EN_219.json": bad,
                "noticeDetail_200002_EN_564.json": bad,
            }
        )
        localizer = build_localizer(localizer_env, service)
        result = localizer.sync()
        assert result["failed"] == 2
        assert all("formatKey" in item["message"] for item in result["items"])

    def test_pending_stops_sync_without_counting_as_failure(self, localizer_env):
        """服务端未命中缓存且等待预算耗尽 → 记 pending、停止本轮、不算失败。"""
        service = FakeService(
            pending_error=NoticePendingError("服务端 60 秒内仍未返回译文（共尝试 8 次）", waited=60.0)
        )
        localizer = build_localizer(localizer_env, service)
        result = localizer.sync()

        assert result["pending"] is True
        assert result["failed"] == 0
        assert result["translated"] == 0
        assert result["cancelled"] is False
        assert result["items"][0]["status"] == "pending"
        assert result["items"][0]["kind"] == "pending"
        assert "未返回译文" in result["message"]
        # 只问了第一篇就停手，剩余公告留待下次同步
        assert service.requests == ["noticeDetail_200001_EN_219.json"]
        assert not (localizer_env["notice_dir"] / "noticeDetails").exists()

    def test_sync_passes_cancel_deadline_and_wait_hook(self, localizer_env):
        """sync() 必须把取消事件 / 时间预算 / 等待回调透传给服务客户端。"""
        service = FakeService()
        localizer = build_localizer(localizer_env, service)
        cancel_event = threading.Event()
        localizer.sync(cancel_event=cancel_event)

        assert service.request_kwargs, "服务客户端未被调用"
        kwargs = service.request_kwargs[0]
        assert kwargs["cancel_event"] is cancel_event
        assert kwargs["deadline"] is None
        assert callable(kwargs["on_wait"])

    def test_pending_cancel_reason_maps_to_cancelled(self, localizer_env):
        service = FakeService(
            pending_error=NoticePendingError("已取消等待服务端译文", reason="cancelled")
        )
        localizer = build_localizer(localizer_env, service)
        result = localizer.sync()
        assert result["cancelled"] is True
        assert result["pending"] is False
        assert result["failed"] == 0

    def test_pending_deadline_reason_maps_to_timed_out(self, localizer_env):
        service = FakeService(
            pending_error=NoticePendingError("时间预算不足，剩余公告留待下次同步", reason="deadline")
        )
        localizer = build_localizer(localizer_env, service)
        result = localizer.sync()
        assert result["timed_out"] is True
        assert result["pending"] is False
        assert result["failed"] == 0

    def test_cancel_stops_early(self, localizer_env):
        service = FakeService()
        localizer = build_localizer(localizer_env, service)
        cancel_event = threading.Event()
        cancel_event.set()
        result = localizer.sync(cancel_event=cancel_event)
        assert result["cancelled"] is True
        assert service.requests == []

    def test_deadline_stops_early(self, localizer_env):
        service = FakeService()
        localizer = build_localizer(localizer_env, service)
        result = localizer.sync(deadline=0)
        assert result["timed_out"] is True
        assert service.requests == []

    def test_meta_falls_back_to_local_copy(self, localizer_env, monkeypatch):
        def failing_http_get(url, timeout=30, max_bytes=None):
            raise core.NoticeLocalizeError("network down")

        monkeypatch.setattr(core, "http_get", failing_http_get)
        notice_dir = localizer_env["notice_dir"]
        notice_dir.mkdir(parents=True, exist_ok=True)
        (notice_dir / "noticeMeta.json").write_bytes(to_bytes(make_meta([make_entry(200001)])))

        service = FakeService()
        localizer = build_localizer(localizer_env, service)
        result = localizer.sync()
        assert result["meta_source"] == "local"
        assert result["translated"] == 1

    def test_meta_unavailable_reports_error(self, localizer_env, monkeypatch):
        def failing_http_get(url, timeout=30, max_bytes=None):
            raise core.NoticeLocalizeError("network down")

        monkeypatch.setattr(core, "http_get", failing_http_get)
        localizer = build_localizer(localizer_env, FakeService())
        result = localizer.sync()
        assert result["success"] is False
        assert "noticeMeta.json" in result["message"]


class TestRestore:
    def test_removes_only_own_files(self, localizer_env):
        service = FakeService()
        localizer = build_localizer(localizer_env, service)
        localizer.sync()
        details = localizer_env["notice_dir"] / "noticeDetails"
        assert len(list(details.iterdir())) == 2

        result = localizer.restore()
        assert result["success"] is True
        assert len(result["removed"]) == 2
        assert list(details.iterdir()) == []

    def test_externally_modified_file_is_kept(self, localizer_env):
        service = FakeService()
        localizer = build_localizer(localizer_env, service)
        localizer.sync()
        target = localizer_env["notice_dir"] / "noticeDetails" / "noticeDetail_200001_EN_219.json"
        target.write_bytes(b'{"id": 1}')

        result = localizer.restore()
        assert result["removed"] == ["noticeDetail_200002_EN_564.json"]
        assert result["skipped"] == ["noticeDetail_200001_EN_219.json"]
        assert target.exists()


class TestInfoAndTestService:
    def test_info_counts(self, localizer_env):
        localizer = build_localizer(localizer_env, FakeService())
        info = localizer.info()
        assert info["lang"] == "EN"
        assert info["counts"] == {"total": 2, "translated": 0, "official": 0, "missing": 2}

        localizer.sync()
        info = localizer.info()
        assert info["counts"]["translated"] == 2

    def test_test_service_success_and_failure(self, localizer_env):
        localizer = build_localizer(localizer_env, FakeService())
        ok = localizer.test_service()
        assert ok["success"] is True
        assert ok["pending"] is False
        assert ok["file"] == "noticeDetail_200001_EN_219.json"

        failing = build_localizer(
            localizer_env, FakeService(error=NoticeServiceError("拒绝连接", kind="network"))
        )
        bad = failing.test_service()
        assert bad["success"] is False
        assert bad["kind"] == "network"

    def test_test_service_reports_pending_as_reachable(self, localizer_env):
        """未命中缓存说明连接是通的，不能报成连接失败。"""
        localizer = build_localizer(localizer_env, FakeService(probe_pending=True))
        result = localizer.test_service()
        assert result["success"] is True
        assert result["pending"] is True
        assert result["title"] is None
        assert "缓存" in result["message"]


# --------------------------------------------------------------------------
# 服务客户端（真实 HTTP）
# --------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    routes = {}
    seen = []

    def do_GET(self):  # noqa: N802
        _Handler.seen.append(self.path)
        body = _Handler.routes.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"missing")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 静音
        pass


@pytest.fixture
def http_service():
    _Handler.seen = []
    _Handler.routes = {
        "/noticeDetails/noticeDetail_200001_EN_219.json": envelope(make_detail(title="中文标题")),
        "/v1/translate/noticeDetail_200001_EN_219.json": envelope(make_detail(title="模板路径")),
        "/noticeDetails/not-json.json": b"<html>oops</html>",
        "/noticeDetails/pending.json": envelope(status="pending", message="正在翻译，请稍后重试"),
        "/noticeDetails/no-status.json": to_bytes({"title": "缺少 status 字段"}),
        "/noticeDetails/ok-without-data.json": to_bytes({"status": "ok"}),
        "/noticeDetails/error-status.json": to_bytes({"status": "error", "message": "翻译引擎挂了"}),
        "/noticeDetails/legacy-error.json": to_bytes({"ok": False, "error": {"message": "旧信封错误"}}),
        "/status": to_bytes(
            {
                "service": "lcta-notice-server",
                "state": "ok",
                "cached": 7,
                "running": 1,
                "translated": 9,
                "failed": 0,
            }
        ),
        "/v1/status": b"<html>oops</html>",
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:{}".format(server.server_port)
    finally:
        server.shutdown()
        server.server_close()


class TestServiceClient:
    def test_default_template(self, http_service):
        client = NoticeTranslationService(http_service)
        assert client.build_url("a.json") == http_service + "/noticeDetails/a.json"
        probe = client.probe("noticeDetail_200001_EN_219.json")
        assert probe["title"] == "中文标题"
        assert probe["pending"] is False
        assert _Handler.seen == ["/noticeDetails/noticeDetail_200001_EN_219.json"]

    def test_custom_template_and_trailing_slash(self, http_service):
        client = NoticeTranslationService(
            http_service + "/", "{base}/v1/translate/{file}", timeout=10
        )
        probe = client.probe("noticeDetail_200001_EN_219.json")
        assert probe["title"] == "模板路径"

    def test_envelope_is_unwrapped(self, http_service):
        data = NoticeTranslationService(http_service).fetch("noticeDetail_200001_EN_219.json")
        payload = json.loads(data.decode("utf-8"))
        assert payload["title"] == "中文标题"
        assert "status" not in payload  # 拿到的是 data 本体

    def test_pending_is_reported_by_probe(self, http_service):
        probe = NoticeTranslationService(http_service).probe("pending.json")
        assert probe["pending"] is True
        assert probe["title"] is None
        assert probe["bytes"] == 0

    def test_missing_status_is_protocol_error(self, http_service):
        with pytest.raises(NoticeServiceError) as excinfo:
            NoticeTranslationService(http_service).fetch("no-status.json")
        assert excinfo.value.kind == "protocol"
        assert "status" in str(excinfo.value)

    def test_ok_without_data_is_protocol_error(self, http_service):
        with pytest.raises(NoticeServiceError) as excinfo:
            NoticeTranslationService(http_service).fetch("ok-without-data.json")
        assert excinfo.value.kind == "protocol"

    def test_error_status_is_service_error(self, http_service):
        with pytest.raises(NoticeServiceError) as excinfo:
            NoticeTranslationService(http_service).fetch("error-status.json")
        assert excinfo.value.kind == "service_error"
        assert "翻译引擎挂了" in str(excinfo.value)

    def test_legacy_error_envelope_still_reported(self, http_service):
        with pytest.raises(NoticeServiceError) as excinfo:
            NoticeTranslationService(http_service).fetch("legacy-error.json")
        assert excinfo.value.kind == "service_error"
        assert "旧信封错误" in str(excinfo.value)

    def test_missing_base_url(self):
        client = NoticeTranslationService("")
        with pytest.raises(NoticeServiceError) as excinfo:
            client.build_url("a.json")
        assert excinfo.value.kind == "config"

    def test_bad_template(self):
        client = NoticeTranslationService("http://127.0.0.1:1", "{base}/{unknown}")
        with pytest.raises(NoticeServiceError) as excinfo:
            client.build_url("a.json")
        assert excinfo.value.kind == "config"

    def test_404_is_classified(self, http_service):
        client = NoticeTranslationService(http_service)
        with pytest.raises(NoticeServiceError) as excinfo:
            client.request("noticeDetail_999999_EN_1.json")
        assert excinfo.value.kind == "not_found"

    def test_non_json_body(self, http_service):
        client = NoticeTranslationService(http_service)
        with pytest.raises(NoticeServiceError) as excinfo:
            client.probe("not-json.json")
        assert excinfo.value.kind == "invalid_json"

    def test_connection_refused(self):
        client = NoticeTranslationService("http://127.0.0.1:1", timeout=2)
        with pytest.raises(NoticeServiceError) as excinfo:
            client.request("a.json")
        assert excinfo.value.kind in ("network", "timeout")

    def test_default_template_constant(self):
        assert DEFAULT_URL_TEMPLATE == "{base}/noticeDetails/{file}"

    def test_status_route_is_parsed(self, http_service):
        info = NoticeTranslationService(http_service).status()
        assert info["service"] == "lcta-notice-server"
        assert info["cached"] == 7
        assert _Handler.seen == ["/status"]

    def test_status_requires_base_url(self):
        with pytest.raises(NoticeServiceError) as excinfo:
            NoticeTranslationService("").status()
        assert excinfo.value.kind == "config"

    def test_status_non_json_is_classified(self, http_service):
        client = NoticeTranslationService(http_service + "/v1", timeout=10)
        with pytest.raises(NoticeServiceError) as excinfo:
            client.status()
        assert excinfo.value.kind == "invalid_json"


class TestBuiltinService:
    """服务地址与全部策略内置：页面不再有任何配置项。"""

    def test_service_url_is_hardcoded(self):
        assert DEFAULT_SERVICE_URL == "https://notice.lcta.top"

    def test_from_config_uses_builtin_defaults(self):
        localizer = NoticeLocalizer.from_config()
        assert localizer.service_url == DEFAULT_SERVICE_URL
        assert localizer.url_template == DEFAULT_URL_TEMPLATE
        assert localizer.lang_mode == "auto"
        assert localizer.only_valid is True
        assert localizer.verify_official is True
        assert localizer.seed_meta is True

    def test_service_status_success(self, http_service):
        result = NoticeLocalizer(service_url=http_service).service_status()
        assert result["success"] is True
        assert result["cached"] == 7
        assert result["running"] == 1
        assert result["service_url"] == http_service

    def test_service_status_failure_is_reported(self):
        result = NoticeLocalizer(service_url="http://127.0.0.1:1", timeout=2).service_status()
        assert result["success"] is False
        assert result["kind"] in ("network", "timeout")


# --------------------------------------------------------------------------
# 未命中缓存（status=pending）的等待重试
# --------------------------------------------------------------------------
class _PendingHandler(BaseHTTPRequestHandler):
    """前 `pending_left` 次返回 pending，之后返回 ok（模拟服务端边译边等）。"""

    pending_left = 0
    payload = b""
    seen = []

    def do_GET(self):  # noqa: N802
        type(self).seen.append(self.path)
        if type(self).pending_left > 0:
            type(self).pending_left -= 1
            body = envelope(status="pending", message="正在翻译，请稍后重试")
        else:
            body = type(self).payload
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 静音
        pass


class SleepRecorder:
    """记录等待间隔，避免测试真的睡满 60 秒。"""

    def __init__(self):
        self.calls = []

    def __call__(self, delay):
        self.calls.append(delay)


@pytest.fixture
def pending_service():
    servers = []

    def build(pending_left=1):
        _PendingHandler.pending_left = pending_left
        _PendingHandler.seen = []
        _PendingHandler.payload = envelope(make_detail(title="中文标题"))
        server = ThreadingHTTPServer(("127.0.0.1", 0), _PendingHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        client = NoticeTranslationService("http://127.0.0.1:{}".format(server.server_port))
        return client, SleepRecorder()

    yield build
    for server in servers:
        server.shutdown()
        server.server_close()


class TestPendingRetry:
    def test_delays_schedule(self):
        assert pending_delays(60) == [1, 2, 4, 8, 16, 16, 13]
        assert sum(pending_delays(60)) == 60
        assert pending_delays(3) == [1, 2]
        assert pending_delays(1) == [1]
        assert pending_delays(0) == []

    def test_waits_until_ready(self, pending_service):
        client, sleeper = pending_service(pending_left=3)
        data = client.request("a.json", sleep=sleeper)

        assert json.loads(data.decode("utf-8"))["title"] == "中文标题"
        assert sleeper.calls == [1, 2, 4]           # 退避序列
        assert len(_PendingHandler.seen) == 4       # 3 次 pending + 1 次成功

    def test_no_wait_when_first_attempt_succeeds(self, pending_service):
        client, sleeper = pending_service(pending_left=0)
        client.request("a.json", sleep=sleeper)
        assert sleeper.calls == []
        assert len(_PendingHandler.seen) == 1

    def test_gives_up_after_wait_budget(self, pending_service):
        client, sleeper = pending_service(pending_left=99)
        with pytest.raises(NoticePendingError) as excinfo:
            client.request("a.json", sleep=sleeper)

        assert excinfo.value.reason == "budget"
        assert excinfo.value.waited == PENDING_MAX_WAIT
        assert sleeper.calls == [1, 2, 4, 8, 16, 16, 13]
        assert len(_PendingHandler.seen) == 8       # 7 次等待 + 最后一次尝试

    def test_cancel_aborts_waiting(self, pending_service):
        client, sleeper = pending_service(pending_left=99)
        cancel_event = threading.Event()
        cancel_event.set()
        with pytest.raises(NoticePendingError) as excinfo:
            client.request("a.json", cancel_event=cancel_event, sleep=sleeper)

        assert excinfo.value.reason == "cancelled"
        assert sleeper.calls == []

    def test_deadline_aborts_waiting(self, pending_service):
        client, sleeper = pending_service(pending_left=99)
        with pytest.raises(NoticePendingError) as excinfo:
            client.request("a.json", deadline=time.monotonic() + 0.5, sleep=sleeper)

        assert excinfo.value.reason == "deadline"
        assert sleeper.calls == []

    def test_on_wait_reports_progress(self, pending_service):
        client, sleeper = pending_service(pending_left=2)
        events = []
        client.request("a.json", on_wait=lambda a, d, w: events.append((a, d, w)), sleep=sleeper)

        assert events == [(1, 1, 0), (2, 2, 1)]

    def test_on_wait_exception_does_not_break_request(self, pending_service):
        client, sleeper = pending_service(pending_left=1)

        def boom(attempt, delay, waited):
            raise RuntimeError("回调炸了")

        data = client.request("a.json", on_wait=boom, sleep=sleeper)
        assert json.loads(data.decode("utf-8"))["title"] == "中文标题"

    def test_cancel_during_wait_aborts_before_full_delay(self, pending_service):
        """取消不必等满一个退避间隔：等待被切成小片，取消后立即退出。"""
        client, _sleeper = pending_service(pending_left=99)
        cancel_event = threading.Event()
        slept = []

        def sleeper(delay):
            slept.append(delay)
            cancel_event.set()  # 第一片就取消

        with pytest.raises(NoticePendingError) as excinfo:
            client.request("a.json", cancel_event=cancel_event, sleep=sleeper)

        assert excinfo.value.reason == "cancelled"
        assert slept == [WAIT_SLICE_SECONDS]     # 只等了半片，没等满 1 秒
        assert len(_PendingHandler.seen) == 1    # 也没有再发一次请求
