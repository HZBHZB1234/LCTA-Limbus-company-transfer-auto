# -*- coding: utf-8 -*-
"""公告汉化服务端（tools/notice_server）测试。

覆盖：
- 文本槽位：`HyperLink` / 裸 URL 不翻译，`title` 与 `Text`/`SubTitle` 翻译
- 包裹处理：`<...>` / `[...]` 按原文形式确定性还原（模型丢没丢都不影响）
- 模型输出解析（json_repair 容错）：代码块围栏、前后废话、`<think>` 标签、
  截断 / 未转义换行 / 单引号 / 尾逗号可修复，非数组 / 纯文本仍拒绝
- 后端：成功 / 重试 / HTTP 错误 / 未配置 / 截断输出经修复后可用
- 官方原文与译文缓存：文件名白名单（挡路径穿越）、内存缓存、原子写、404
- 流水线：结构保持（formatKey / id / noticeType / HyperLink）
- 服务端：缓存未命中回 pending、异步翻译后回 ok、失败只上报一次、并发去重
- **端到端**：真实客户端 `NoticeTranslationService` 打真实 Uvicorn HTTP 服务端
  （FastAPI 应用工厂 `create_app` 产物），另含状态路由 / 400 信封 / 任意前缀路由

依赖：`pip install -r tools/notice_server/requirements.txt`（未安装时整文件跳过）。
"""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

pytest.importorskip("fastapi")  # 服务端 HTTP 层依赖，缺失时跳过整个文件
pytest.importorskip("json_repair")
uvicorn = pytest.importorskip("uvicorn")

from tools.notice_server.config import load_config
from tools.notice_server.pipeline import NoticePipeline, PipelineError
from tools.notice_server import refresher as refresher_module
from tools.notice_server.refresher import (
    DEFAULT_INTERVAL_SECONDS,
    NoticeRefresher,
    enumerate_notice_names,
    evaluate_validity,
)
from tools.notice_server.server import NoticeService, create_app
from tools.notice_server.store import (
    NoticeStore,
    NoticeStoreError,
    is_valid_notice_name,
)
from tools.notice_server.translator import (
    FakeTranslator,
    OpenAIChatTranslator,
    TranslationError,
    apply_translations,
    build_slots,
    extract_json_array,
    is_translatable,
    restore_wrapper,
    split_wrapper,
    validate_payload,
)
from webutils.notice.service import NoticePendingError, NoticeTranslationService

NAME = "noticeDetail_200001_EN_219.json"


def to_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def official_payload(notice_id=200001):
    """与官方真实结构一致：Text / SubTitle（带包裹）/ HyperLink（裸 URL）。"""
    return {
        "id": notice_id,
        "noticeType": 0,
        "startDate": "Thu Sep 17 2099 01:04:36 GMT+0000 (Coordinated Universal Time)",
        "endDate": "Thu Sep 17 2099 01:04:36 GMT+0000 (Coordinated Universal Time)",
        "sprList": [str(notice_id)],
        "title": "Official Twitter and Youtube Accounts",
        "content": {
            "list": [
                {"formatKey": "Text", "formatValue": "Greetings, Dear Manager.\n\n● Limbus Company"},
                {"formatKey": "SubTitle", "formatValue": "<Official Twitter>"},
                {"formatKey": "Text", "formatValue": "● Project Moon"},
                {"formatKey": "HyperLink", "formatValue": "https://twitter.com/LimbusCompany_B"},
                {"formatKey": "SubTitle", "formatValue": "Notice: Lobotomy E.G.O::Red Sheet Sinclair"},
            ]
        },
    }


class StubResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self, *_args):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def opener_returning(body: bytes, calls=None):
    def opener(req, timeout=None):
        if calls is not None:
            calls.append(req)
        return StubResponse(body if isinstance(body, bytes) else to_bytes(body))

    return opener


class StubTranslator:
    """可控的翻译后端：记录收到的文本，可阻塞、可失败。"""

    def __init__(self, fail=False, gate=None, prefix="【中】"):
        self.fail = fail
        self.gate = gate
        self.prefix = prefix
        self.calls = []

    def translate(self, texts):
        self.calls.append(list(texts))
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.fail:
            raise TranslationError("模型炸了")
        return [self.prefix + text for text in texts]


def build_service(tmp_path, translator=None, opener=None, **kwargs):
    store = NoticeStore(
        tmp_path / "cache",
        "https://official.example",
        opener=opener or opener_returning(to_bytes(official_payload())),
    )
    service = NoticeService(
        store, NoticePipeline(store, translator or StubTranslator()), **kwargs
    )
    return service, store


# --------------------------------------------------------------------------
# 文本槽位与包裹
# --------------------------------------------------------------------------
class TestSlotsAndWrapper:
    def test_hyperlink_and_bare_url_are_not_translatable(self):
        assert is_translatable("HyperLink", "https://twitter.com/LimbusCompany_B") is False
        assert is_translatable("Text", "https://twitter.com/LimbusCompany_B") is False
        assert is_translatable("Text", "") is False
        assert is_translatable("Text", "   ") is False
        assert is_translatable("Text", "Greetings, Dear Manager.") is True

    def test_build_slots_picks_title_and_text_but_skips_hyperlink(self):
        slots = build_slots(official_payload())
        assert [slot["where"] for slot in slots] == ["title", "list", "list", "list", "list"]
        assert [slot["key"] for slot in slots] == [None, "Text", "SubTitle", "Text", "SubTitle"]
        assert [slot["index"] for slot in slots] == [None, 0, 1, 2, 4]
        assert "https://twitter.com" not in " ".join(slot["text"] for slot in slots)

    def test_split_wrapper(self):
        assert split_wrapper("<Official Twitter>") == ("<", "Official Twitter", ">")
        assert split_wrapper("[Season 6: Zàng Huā Yín]") == ("[", "Season 6: Zàng Huā Yín", "]")
        assert split_wrapper("Notice: plain") == ("", "Notice: plain", "")
        assert split_wrapper("<") == ("", "<", "")

    def test_restore_wrapper_keeps_original_form(self):
        # 模型丢了包裹
        assert restore_wrapper("<Official Twitter>", "官方 Twitter") == "<官方 Twitter>"
        # 模型自己又加了一层
        assert restore_wrapper("<Official Twitter>", "<官方 Twitter>") == "<官方 Twitter>"
        # 模型换了包裹符号
        assert restore_wrapper("[Season 6]", "《第六赛季》") == "[《第六赛季》]"
        # 原文没有包裹 → 原样返回
        assert restore_wrapper("Notice: plain", "公告：纯文本") == "公告：纯文本"

    def test_apply_translations_preserves_structure(self):
        payload = official_payload()
        slots = build_slots(payload)
        apply_translations(payload, slots, ["标题" + str(i) for i in range(len(slots))])

        assert payload["id"] == 200001
        assert payload["noticeType"] == 0
        assert payload["sprList"] == ["200001"]
        assert payload["title"] == "标题0"
        items = payload["content"]["list"]
        assert [item["formatKey"] for item in items] == [
            "Text", "SubTitle", "Text", "HyperLink", "SubTitle"
        ]
        # HyperLink 一个字符都没动
        assert items[3]["formatValue"] == "https://twitter.com/LimbusCompany_B"
        # 带包裹的 SubTitle 包裹还在，裸的 SubTitle 不带包裹
        assert items[1]["formatValue"] == "<标题2>"
        assert items[4]["formatValue"] == "标题4"

    def test_validate_payload_rejects_broken(self):
        with pytest.raises(TranslationError):
            validate_payload({"noticeType": 0, "title": "x", "content": {"list": [{"formatKey": "Text", "formatValue": "y"}]}})
        with pytest.raises(TranslationError):
            validate_payload({"id": 1, "noticeType": 0, "title": "", "content": {"list": [{"formatKey": "Text", "formatValue": "y"}]}})
        with pytest.raises(TranslationError):
            validate_payload({"id": 1, "noticeType": 0, "title": "x", "content": {"list": []}})

    def test_validate_payload_accepts_good(self):
        validate_payload(official_payload())


# --------------------------------------------------------------------------
# 模型输出解析（json_repair 容错）
# --------------------------------------------------------------------------
class TestExtractJsonArray:
    def test_plain_array(self):
        assert extract_json_array('["a", "b"]') == ["a", "b"]

    def test_code_fence(self):
        assert extract_json_array('```json\n["a"]\n```') == ["a"]

    def test_surrounding_prose(self):
        assert extract_json_array('好的，结果如下：\n["a", "b"]\n以上。') == ["a", "b"]

    def test_brackets_inside_strings_with_prose(self):
        assert extract_json_array('结果：["a", "参考[1]", "b"] 以上') == ["a", "参考[1]", "b"]

    def test_think_tags_are_stripped(self):
        # 推理模型（Qwen 系经 vLLM）常把 <think> 混在 content 里
        assert extract_json_array('<think>用户给了数组，逐项翻译</think>["译"]') == ["译"]

    def test_truncated_json_is_repaired(self):
        # 缺右括号 / 半截字符串 → json_repair 救回
        assert extract_json_array('["a", "b') == ["a", "b"]

    def test_unescaped_newline_is_repaired(self):
        # LLM 在 JSON 字符串里输出裸换行的经典失败模式
        assert extract_json_array('["第一行\n第二行"]') == ["第一行\n第二行"]

    def test_single_quotes_and_trailing_comma_are_repaired(self):
        assert extract_json_array("['a', 'b',]") == ["a", "b"]

    def test_rejects_non_array(self):
        with pytest.raises(TranslationError):
            extract_json_array('{"a": 1}')

    def test_rejects_garbage(self):
        with pytest.raises(TranslationError):
            extract_json_array("抱歉，我无法翻译。")


# --------------------------------------------------------------------------
# OpenAI 兼容后端
# --------------------------------------------------------------------------
class TestOpenAITranslator:
    def _chat_body(self, texts):
        return to_bytes({"choices": [{"message": {"content": json.dumps(texts, ensure_ascii=False)}}]})

    def test_translates(self):
        translator = OpenAIChatTranslator(
            "https://api.example/v1", "m", api_key="k",
            opener=opener_returning(self._chat_body(["一", "二"])),
        )
        assert translator.translate(["a", "b"]) == ["一", "二"]

    def test_missing_config_fails_fast(self):
        with pytest.raises(TranslationError):
            OpenAIChatTranslator("", "m").translate(["a"])
        with pytest.raises(TranslationError):
            OpenAIChatTranslator("https://api.example/v1", "").translate(["a"])

    def test_empty_input_needs_no_call(self):
        calls = []
        translator = OpenAIChatTranslator(
            "https://api.example/v1", "m", opener=opener_returning(b"{}", calls)
        )
        assert translator.translate([]) == []
        assert calls == []

    def test_length_mismatch_is_retried_then_fails(self):
        calls = []
        translator = OpenAIChatTranslator(
            "https://api.example/v1", "m", max_retries=2,
            opener=opener_returning(self._chat_body(["只有一条"]), calls),
        )
        with pytest.raises(TranslationError) as excinfo:
            translator.translate(["a", "b"])
        assert "期望 2 条" in str(excinfo.value)
        assert len(calls) == 3          # 首次 + 2 次重试

    def test_http_error_reports_status(self):
        import urllib.error

        def opener(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

        translator = OpenAIChatTranslator("https://api.example/v1", "m", opener=opener)
        with pytest.raises(TranslationError) as excinfo:
            translator.translate(["a"])
        assert "401" in str(excinfo.value)

    def test_api_key_header_only_when_set(self):
        calls = []
        translator = OpenAIChatTranslator(
            "https://api.example/v1", "m", api_key="secret",
            opener=opener_returning(self._chat_body(["一"]), calls),
        )
        translator.translate(["a"])
        assert calls[0].get_header("Authorization") == "Bearer secret"

        calls.clear()
        OpenAIChatTranslator(
            "https://api.example/v1", "m", opener=opener_returning(self._chat_body(["一"]), calls)
        ).translate(["a"])
        assert calls[0].get_header("Authorization") is None

    def test_truncated_model_output_is_repaired(self):
        """输出截断（缺右括号）但条目完整时，json_repair 救回，无需重试。"""
        calls = []
        translator = OpenAIChatTranslator(
            "https://api.example/v1", "m", max_retries=2,
            opener=opener_returning(to_bytes(
                {"choices": [{"message": {"content": '["一",\n"二'}}]}
            ), calls),
        )
        assert translator.translate(["a", "b"]) == ["一", "二"]
        assert len(calls) == 1              # 修复成功，没走重试


# --------------------------------------------------------------------------
# 官方原文与缓存
# --------------------------------------------------------------------------
class TestStore:
    def test_name_whitelist_blocks_traversal(self):
        assert is_valid_notice_name(NAME) is True
        assert is_valid_notice_name("noticeDetail_1_JP_2.json") is True
        assert is_valid_notice_name("../../evil.json") is False
        assert is_valid_notice_name("noticeDetail_1_XX_2.json") is False
        assert is_valid_notice_name("noticeMeta.json") is False
        assert is_valid_notice_name("") is False
        assert is_valid_notice_name(None) is False

    def test_official_is_fetched_once(self, tmp_path):
        calls = []
        store = NoticeStore(
            tmp_path / "cache", "https://official.example",
            opener=opener_returning(to_bytes(official_payload()), calls),
        )
        assert json.loads(store.official(NAME))["id"] == 200001
        store.official(NAME)
        assert len(calls) == 1          # 第二次走内存缓存

    def test_official_404(self, tmp_path):
        import urllib.error

        def opener(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

        store = NoticeStore(tmp_path / "cache", "https://official.example", opener=opener)
        with pytest.raises(NoticeStoreError) as excinfo:
            store.official(NAME)
        assert "404" in str(excinfo.value)

    def test_save_and_read_round_trip_leaves_no_temp(self, tmp_path):
        store = NoticeStore(tmp_path / "cache", "https://official.example")
        store.save_translated(NAME, official_payload())
        raw = store.read_translated(NAME)
        assert json.loads(raw.decode("utf-8"))["title"] == "Official Twitter and Youtube Accounts"
        leftovers = [p.name for p in store.cache_dir.iterdir() if p.name != NAME]
        assert leftovers == []
        assert store.cached_names() == [NAME]

    def test_read_missing_returns_none(self, tmp_path):
        store = NoticeStore(tmp_path / "cache", "https://official.example")
        assert store.read_translated(NAME) is None

    def test_official_meta_is_refetched_every_time(self, tmp_path):
        """清单刻意不做内存缓存：定时预热每轮都要拿到最新清单。"""
        calls = []
        store = NoticeStore(
            tmp_path / "cache", "https://official.example",
            opener=opener_returning(to_bytes({"noticeDetailList": []}), calls),
        )
        store.official_meta()
        store.official_meta()
        assert len(calls) == 2
        assert calls[0].full_url == "https://official.example/noticeMeta.json"


# --------------------------------------------------------------------------
# 定时预热（refresher）
# --------------------------------------------------------------------------
def make_meta(entries, latest="Fri Jun 20 2025 18:29:34 GMT+0900 (KST)"):
    return {"latestUpdateDate": latest, "noticeDetailList": entries}


def make_meta_entry(notice_id, suffix, start=None, end=None, langs=("KR", "EN", "JP")):
    entry = {
        "id": notice_id,
        "startDate": start or "Thu Sep 17 2020 01:04:36 GMT+0000 (Coordinated Universal Time)",
        "endDate": end or "Thu Sep 17 2099 01:04:36 GMT+0000 (Coordinated Universal Time)",
    }
    for lang in langs:
        entry["fileName_" + lang] = "noticeDetail_{}_{}_{}.json".format(notice_id, lang, suffix)
    return entry


def meta_opener(meta, detail_calls=None):
    """meta URL 返回清单，详情 URL 返回官方原文（同时记录详情请求）。"""

    def opener(req, timeout=None):
        if req.full_url.endswith("noticeMeta.json"):
            return StubResponse(to_bytes(meta))
        if detail_calls is not None:
            detail_calls.append(req.full_url)
        return StubResponse(to_bytes(official_payload()))

    return opener


class TestRefresherHelpers:
    def test_enumerate_picks_configured_languages(self):
        meta = make_meta([make_meta_entry(200001, "219")])
        assert enumerate_notice_names(meta, ("EN",)) == ["noticeDetail_200001_EN_219.json"]
        assert enumerate_notice_names(meta, ("EN", "KR")) == [
            "noticeDetail_200001_EN_219.json",
            "noticeDetail_200001_KR_219.json",
        ]

    def test_enumerate_skips_expired_and_duplicates(self):
        expired = make_meta_entry(
            200002, "564",
            end="Thu Sep 17 2020 01:04:36 GMT+0000 (Coordinated Universal Time)",
        )
        meta = make_meta([make_meta_entry(200001, "219"), expired, make_meta_entry(200001, "219")])
        names = enumerate_notice_names(meta, ("EN",))
        assert names == ["noticeDetail_200001_EN_219.json"]
        # only_valid=False 时过期公告也进清单
        assert len(enumerate_notice_names(meta, ("EN",), only_valid=False)) == 2

    def test_enumerate_rejects_unexpected_names(self):
        entry = make_meta_entry(200003, "1")
        entry["fileName_EN"] = "../../evil.json"
        assert enumerate_notice_names(make_meta([entry]), ("EN",)) == []
        assert enumerate_notice_names({"noticeDetailList": "nope"}, ("EN",)) == []

    def test_evaluate_validity_iso_and_dateutil(self):
        assert evaluate_validity("2020-01-01T00:00:00.000Z", "2098-12-31T21:00:00.000Z") is True
        assert evaluate_validity("2098-01-01T00:00:00.000Z", "2099-01-01T00:00:00.000Z") is False
        assert evaluate_validity("", "") is True      # 解析失败保守放行


class TestRefresher:
    def test_run_once_queues_uncached_and_skips_cached(self, tmp_path):
        meta = make_meta([make_meta_entry(200001, "219"), make_meta_entry(200002, "564")])
        store = NoticeStore(
            tmp_path / "cache", "https://official.example", opener=meta_opener(meta)
        )
        service = NoticeService(store, NoticePipeline(store, StubTranslator()))
        # 200001 预先译好 → 本轮应被跳过
        store.save_translated("noticeDetail_200001_EN_219.json", official_payload())

        logs = []
        refresher = NoticeRefresher(store, service, interval=1800, logger=logs.append)
        summary = refresher.run_once()

        assert summary["success"] is True
        assert summary["total"] == 2
        assert summary["cached"] == 1
        assert summary["queued"] == 1

        for _ in range(200):
            if service.status()["running"] == 0:
                break
            time.sleep(0.02)
        assert store.read_translated("noticeDetail_200002_EN_564.json") is not None
        assert refresher.status()["last_run"] is not None
        assert logs and "清单 2 篇" in logs[-1]

    def test_run_once_reports_meta_failure(self, tmp_path):
        def opener(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 503, "down", {}, None)

        store = NoticeStore(tmp_path / "cache", "https://official.example", opener=opener)
        service = NoticeService(store, NoticePipeline(store, StubTranslator()))
        summary = NoticeRefresher(store, service).run_once()
        assert summary["success"] is False
        assert "官方公告清单" in summary["message"]

    def test_interval_zero_disables_refresh(self, tmp_path):
        store = NoticeStore(tmp_path / "cache", "https://official.example")
        service = NoticeService(store, NoticePipeline(store, StubTranslator()))
        refresher = NoticeRefresher(store, service, interval=0)
        assert refresher.interval == 0
        assert refresher.status()["enabled"] is False
        assert refresher.start() is False

    def test_start_runs_a_round_then_stops(self, tmp_path):
        meta = make_meta([make_meta_entry(200001, "219")])
        store = NoticeStore(
            tmp_path / "cache", "https://official.example", opener=meta_opener(meta)
        )
        service = NoticeService(store, NoticePipeline(store, StubTranslator()))
        refresher = NoticeRefresher(store, service, interval=DEFAULT_INTERVAL_SECONDS)
        assert refresher.start() is True
        for _ in range(200):
            if refresher.status()["last_run"] is not None:
                break
            time.sleep(0.02)
        refresher.stop()
        assert refresher.status()["last_run"] is not None
        assert refresher.status()["interval"] == 1800

    def test_interval_is_clamped_to_minimum(self, tmp_path):
        store = NoticeStore(tmp_path / "cache", "https://official.example")
        service = NoticeService(store, NoticePipeline(store, StubTranslator()))
        assert NoticeRefresher(store, service, interval=1).interval == 60

    def test_queue_waits_for_a_free_slot(self, tmp_path, monkeypatch):
        """并发已满（reason=busy）时先等名额，等到就继续排队，不算漏掉。"""
        meta = make_meta([make_meta_entry(200001, "219")])
        store = NoticeStore(
            tmp_path / "cache", "https://official.example", opener=meta_opener(meta)
        )
        service = NoticeService(store, NoticePipeline(store, StubTranslator()))
        monkeypatch.setattr(refresher_module, "QUEUE_POLL_SECONDS", 0.0)

        calls = []

        class BusyOnce:
            def respond(self, name):
                calls.append(name)
                if len(calls) == 1:
                    return 200, {
                        "status": "pending",
                        "reason": "busy",
                        "message": "并发已满，稍后重试时会再排队",
                    }
                return service.respond(name)

        refresher = NoticeRefresher(store, BusyOnce(), interval=1800)
        summary = refresher.run_once()
        assert summary["queued"] == 1
        assert summary["deferred"] == 0
        assert len(calls) == 2

    def test_queue_defers_when_slots_never_free(self, tmp_path, monkeypatch):
        """名额一直不腾出来：记为「留待下轮」而不是失败，也不会卡死整轮。"""
        meta = make_meta([make_meta_entry(200001, "219")])
        store = NoticeStore(
            tmp_path / "cache", "https://official.example", opener=meta_opener(meta)
        )
        monkeypatch.setattr(refresher_module, "QUEUE_WAIT_SECONDS", 0.0)

        class AlwaysBusy:
            def respond(self, name):
                return 200, {"status": "pending", "reason": "busy", "message": "并发已满"}

        refresher = NoticeRefresher(store, AlwaysBusy(), interval=1800)
        summary = refresher.run_once()
        assert summary["success"] is True
        assert summary["deferred"] == 1
        assert summary["queued"] == 0
        assert summary["failed"] == 0
        assert "留待下轮" in summary["message"]

    def test_queue_reports_error_envelope(self, tmp_path):
        """服务端回 error（上一轮失败残留）：本轮记失败，不误记为排队成功。"""
        meta = make_meta([make_meta_entry(200001, "219")])
        store = NoticeStore(
            tmp_path / "cache", "https://official.example", opener=meta_opener(meta)
        )

        class Broken:
            def respond(self, name):
                return 200, {"status": "error", "message": "翻译引擎失败"}

        refresher = NoticeRefresher(store, Broken(), interval=1800)
        summary = refresher.run_once()
        assert summary["failed"] == 1
        assert summary["queued"] == 0


# --------------------------------------------------------------------------
# 流水线
# --------------------------------------------------------------------------
class TestPipeline:
    def test_translates_and_preserves_structure(self, tmp_path):
        translator = StubTranslator()
        store = NoticeStore(
            tmp_path / "cache", "https://official.example",
            opener=opener_returning(to_bytes(official_payload())),
        )
        data = NoticePipeline(store, translator).translate(NAME)
        payload = json.loads(data.decode("utf-8"))

        assert payload["title"].startswith("【中】")
        assert payload["id"] == 200001
        assert payload["noticeType"] == 0
        items = payload["content"]["list"]
        assert [i["formatKey"] for i in items] == ["Text", "SubTitle", "Text", "HyperLink", "SubTitle"]
        assert items[3]["formatValue"] == "https://twitter.com/LimbusCompany_B"
        assert items[1]["formatValue"].startswith("<") and items[1]["formatValue"].endswith(">")
        # 送进模型的文本里没有 HyperLink
        sent = translator.calls[0]
        assert not any("twitter.com" in text for text in sent)
        assert len(sent) == 5
        # 已落盘
        assert store.read_translated(NAME) is not None

    def test_translation_failure_writes_nothing(self, tmp_path):
        store = NoticeStore(
            tmp_path / "cache", "https://official.example",
            opener=opener_returning(to_bytes(official_payload())),
        )
        with pytest.raises(TranslationError):
            NoticePipeline(store, StubTranslator(fail=True)).translate(NAME)
        assert store.read_translated(NAME) is None

    def test_broken_official_payload_is_rejected(self, tmp_path):
        store = NoticeStore(
            tmp_path / "cache", "https://official.example",
            opener=opener_returning(b"<html>502</html>"),
        )
        with pytest.raises(PipelineError):
            NoticePipeline(store, StubTranslator()).translate(NAME)


# --------------------------------------------------------------------------
# 服务端（不经 HTTP）
# --------------------------------------------------------------------------
class TestNoticeService:
    def test_invalid_name_is_rejected(self, tmp_path):
        service, _store = build_service(tmp_path)
        code, envelope = service.respond("../../evil.json")
        assert code == 400
        assert envelope["status"] == "error"

    def test_cache_miss_then_ok(self, tmp_path):
        service, _store = build_service(tmp_path)
        code, envelope = service.respond(NAME)
        assert code == 200
        assert envelope["status"] == "pending"

        for _ in range(100):
            if service.status()["running"] == 0:
                break
            time.sleep(0.02)

        code, envelope = service.respond(NAME)
        assert envelope["status"] == "ok"
        assert envelope["data"]["title"].startswith("【中】")

    def test_failure_is_reported_once_then_retried(self, tmp_path):
        translator = StubTranslator(fail=True)
        service, store = build_service(tmp_path, translator=translator)

        service.respond(NAME)
        for _ in range(100):
            if service.status()["running"] == 0:
                break
            time.sleep(0.02)

        _code, envelope = service.respond(NAME)
        assert envelope["status"] == "error"
        assert "模型炸了" in envelope["message"]

        # 第二次请求不再吐旧错误，而是重新排队
        _code, envelope = service.respond(NAME)
        assert envelope["status"] == "pending"
        assert store.read_translated(NAME) is None

    def test_concurrent_requests_translate_once(self, tmp_path):
        gate = threading.Event()
        translator = StubTranslator(gate=gate)
        service, _store = build_service(tmp_path, translator=translator)

        assert service.respond(NAME)[1]["status"] == "pending"
        assert service.respond(NAME)[1]["status"] == "pending"
        assert service.respond(NAME)[1]["status"] == "pending"
        gate.set()
        for _ in range(100):
            if service.status()["running"] == 0:
                break
            time.sleep(0.02)

        assert len(translator.calls) == 1

    def test_concurrency_limit_defers(self, tmp_path):
        gate = threading.Event()
        service, _store = build_service(tmp_path, translator=StubTranslator(gate=gate), max_concurrency=1)

        assert service.respond(NAME)[1]["status"] == "pending"
        _code, envelope = service.respond("noticeDetail_200002_EN_564.json")
        assert envelope["status"] == "pending"
        assert "并发已满" in envelope["message"]
        gate.set()

    def test_corrupted_cache_is_dropped(self, tmp_path):
        service, store = build_service(tmp_path)
        store.cache_dir.mkdir(parents=True, exist_ok=True)
        store.cached_path(NAME).write_bytes(b'{"id": 1, "truncated')
        _code, envelope = service.respond(NAME)
        assert envelope["status"] == "pending"
        assert not store.cached_path(NAME).exists()

    def test_status_payload(self, tmp_path):
        service, _store = build_service(tmp_path)
        info = service.status()
        assert info["service"] == "lcta-notice-server"
        assert info["cached"] == 0
        assert info["max_concurrency"] == 2


# --------------------------------------------------------------------------
# 端到端：真实客户端 ↔ 真实 HTTP 服务端（Uvicorn 承载 FastAPI 应用）
# --------------------------------------------------------------------------
class LiveServer:
    """把 FastAPI 应用跑在真实端口上的 Uvicorn 服务器（测试用）。

    端口用 0（系统随机分配），从 `server.servers[0].sockets` 读回实际端口；
    `should_exit` 触发 Uvicorn 优雅停机。跑在守护线程里，
    Uvicorn 检测到非主线程会跳过信号处理器安装，不会报错。
    """

    def __init__(self, app, host="127.0.0.1"):
        self.server = uvicorn.Server(
            uvicorn.Config(app, host=host, port=0, log_level="warning")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        for _ in range(500):  # 最多等 10 秒
            if self.server.started:
                break
            time.sleep(0.02)
        if not self.server.started:
            raise RuntimeError("Uvicorn 测试服务器未能启动")
        self.port = self.server.servers[0].sockets[0].getsockname()[1]

    @property
    def url(self) -> str:
        return "http://127.0.0.1:{}".format(self.port)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def live_server(tmp_path):
    servers = []

    def build(translator=None, **kwargs):
        service, store = build_service(tmp_path, translator=translator, **kwargs)
        server = LiveServer(create_app(service))
        servers.append(server)
        return server.url, service, store

    yield build
    for server in servers:
        server.stop()


class TestEndToEndWithRealClient:
    def test_client_waits_out_pending_and_gets_translated_notice(self, live_server):
        """这是最关键的一条：新协议两端真的对得上。"""
        base_url, _service, _store = live_server()
        client = NoticeTranslationService(base_url, timeout=10)

        # 首次必然未命中 → 客户端自己会等；把退避压缩成 20ms 让测试快
        data = client.request(NAME, sleep=lambda _delay: time.sleep(0.02))
        payload = json.loads(data.decode("utf-8"))

        assert payload["title"].startswith("【中】")
        assert [i["formatKey"] for i in payload["content"]["list"]] == [
            "Text", "SubTitle", "Text", "HyperLink", "SubTitle"
        ]
        assert payload["content"]["list"][3]["formatValue"] == "https://twitter.com/LimbusCompany_B"

    def test_second_request_hits_cache_immediately(self, live_server):
        base_url, _service, store = live_server()
        client = NoticeTranslationService(base_url, timeout=10)
        client.request(NAME, sleep=lambda _delay: time.sleep(0.02))

        slept = []
        data = client.request(NAME, sleep=slept.append)
        assert slept == []              # 直接命中缓存，一次都没等
        assert json.loads(data.decode("utf-8"))["title"].startswith("【中】")

    def test_probe_reports_pending_on_first_hit(self, live_server):
        base_url, _service, _store = live_server()
        probe = NoticeTranslationService(base_url, timeout=10).probe(NAME)
        assert probe["pending"] is True   # 连通性测试只发一次请求，首次必然未命中

    def test_client_rejects_malformed_filename_via_http(self, live_server):
        base_url, _service, _store = live_server()
        client = NoticeTranslationService(base_url, timeout=10)
        with pytest.raises(Exception):
            client.fetch("../../evil.json")

    def test_status_routes_served_over_http(self, live_server):
        """`/`、`/status`、`/healthz` 在真实 HTTP 上返回状态 JSON（非公告信封）。"""
        base_url, _service, _store = live_server()
        for path in ("/", "/status", "/healthz"):
            with urllib.request.urlopen(base_url + path, timeout=10) as resp:
                assert resp.status == 200
                payload = json.loads(resp.read().decode("utf-8"))
            assert payload["service"] == "lcta-notice-server"
            # 未传 refresher 时该字段为 None（不影响老客户端）
            assert payload["refresh"] is None

    def test_status_route_carries_refresh_info(self, tmp_path):
        """传了 refresher 时 `/status` 带出预热状态（间隔 / 语言 / 上一轮摘要）。"""
        service, store = build_service(tmp_path)
        refresher = NoticeRefresher(store, service, interval=1800, languages=("EN",))
        server = LiveServer(create_app(service, refresher))
        try:
            with urllib.request.urlopen(server.url + "/status", timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        finally:
            server.stop()
        assert payload["refresh"]["enabled"] is True
        assert payload["refresh"]["interval"] == 1800
        assert payload["refresh"]["languages"] == ["EN"]

    def test_invalid_filename_is_http_400_envelope(self, live_server):
        """文件名不合法：HTTP 400 + error 信封（而非 FastAPI 默认 404/422）。"""
        base_url, _service, _store = live_server()
        req = urllib.request.Request(base_url + "/noticeDetails/evil.json")
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(req, timeout=10)
        assert excinfo.value.code == 400
        envelope = json.loads(excinfo.value.read().decode("utf-8"))
        assert envelope["status"] == "error"
        assert "文件名不合法" in envelope["message"]

    def test_arbitrary_path_prefix_matches(self, live_server):
        """catch-all 路由：路径前缀任意（LCTA 侧 url_template 可配），只取最后一段。"""
        base_url, _service, _store = live_server()
        client = NoticeTranslationService(
            base_url, url_template="{base}/deeply/nested/prefix/{file}", timeout=10
        )
        data = client.request(NAME, sleep=lambda _delay: time.sleep(0.02))
        assert json.loads(data.decode("utf-8"))["title"].startswith("【中】")

    def test_fake_backend_produces_client_acceptable_payload(self, tmp_path):
        """fake 后端（--backend fake）的产物必须能通过客户端硬门。"""
        store = NoticeStore(
            tmp_path / "cache", "https://official.example",
            opener=opener_returning(to_bytes(official_payload())),
        )
        data = NoticePipeline(store, FakeTranslator()).translate(NAME)
        payload = json.loads(data.decode("utf-8"))
        assert payload["title"].startswith("【中】")
        assert payload["content"]["list"][1]["formatValue"] == "<【中】Official Twitter>"


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
class TestConfig:
    def test_defaults_without_file(self, monkeypatch):
        for env_name in ("LCTA_NOTICE_API_KEY", "OPENAI_API_KEY"):
            monkeypatch.delenv(env_name, raising=False)
        config = load_config(None)
        assert config["port"] == 8000
        assert config["translate"]["backend"] == "openai"
        assert config["translate"]["api_key"] == ""

    def test_file_overrides_and_deep_merge(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LCTA_NOTICE_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps({"port": 9001, "translate": {"model": "gpt-x"}}), encoding="utf-8"
        )
        config = load_config(str(path))
        assert config["port"] == 9001
        assert config["translate"]["model"] == "gpt-x"
        # 未覆盖的键保留默认值
        assert config["translate"]["max_retries"] == 2
        assert config["official_base_url"].startswith("https://notice.")

    def test_env_var_supplies_api_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LCTA_NOTICE_API_KEY", "sk-from-env")
        assert load_config(None)["translate"]["api_key"] == "sk-from-env"
