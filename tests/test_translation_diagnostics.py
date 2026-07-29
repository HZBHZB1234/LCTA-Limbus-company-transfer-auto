"""翻译调用 dump、HTTP 响应与异常诊断测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
from translatekit import APIError

from translateFunc.config import FilePathConfig, PathConfig, ProcessOutcome, TranslateConfig
from translateFunc.diagnostics import HttpResponseObserver, safe_json_value, serialize_exception
from translateFunc.enums import ProcessResult
from translateFunc.matcher.engine import MatcherEngine
from translateFunc.processor import FileProcessor
from translateFunc.recorder import TranslationRecorder


class _FakeSession:
    def __init__(self):
        self.hooks = {"response": []}


class _HttpErrorTranslator:
    def __init__(self):
        self._session = _FakeSession()

    def translate(self, text, timeout=None):
        request = requests.Request(
            "POST",
            "https://example.invalid/v1/chat/completions",
            headers={"Authorization": "Bearer secret-token"},
        ).prepare()
        response = requests.Response()
        response.status_code = 400
        response.reason = "Bad Request"
        response.url = request.url
        response.request = request
        response.headers["Set-Cookie"] = "session=secret"
        response._content = b'{"error":{"message":"invalid response_format"}}'
        for hook in self._session.hooks["response"]:
            hook(response)

        inner = requests.HTTPError("400 Client Error", response=response, request=request)
        raise APIError("请求构造错误") from inner


class _SequenceTranslator:
    def __init__(self):
        self._session = _FakeSession()
        self.calls = 0

    def translate(self, text, timeout=None):
        self.calls += 1
        if self.calls == 1:
            return '{"translations":[{"id":1,"translation":"成功"}]}'
        raise APIError("second call failed")


class _StaticTranslator:
    def __init__(self, response):
        self._session = _FakeSession()
        self.response = response

    def translate(self, text, timeout=None):
        return self.response

    def update_config(self, **_kwargs):
        return None


class _CountingMultiStageTranslator:
    def __init__(self):
        self._session = _FakeSession()
        self.system_prompt = ""
        self.stage_calls = {"stage_0": 0, "stage_1": 0, "stage_2": 0}

    def update_config(self, **kwargs):
        self.system_prompt = kwargs.get("system_prompt", "")

    def translate(self, text, timeout=None):
        if "disambiguations" in self.system_prompt:
            self.stage_calls["stage_0"] += 1
            return json.dumps({
                "disambiguations": [{
                    "term": f"observed-{self.stage_calls['stage_0']}",
                    "applies": True,
                }],
            })
        if "checked_translations" in self.system_prompt:
            self.stage_calls["stage_2"] += 1
            count = text.count('<pair id="')
            return json.dumps({
                "checked_translations": [
                    {
                        "id": index + 1,
                        "translation": f"checked-{self.stage_calls['stage_2']}-{index + 1}",
                        "changed": index == 0,
                    }
                    for index in range(count)
                ],
            })

        self.stage_calls["stage_1"] += 1
        count = text.count('<block id="')
        return json.dumps({
            "translations": [
                {
                    "id": index + 1,
                    "translation": f"translated-{index + 1}",
                    "confidence": "high",
                }
                for index in range(count)
            ],
        })


class _SupplementalBuilder:
    def __init__(self):
        self.unified_request = {
            "metadata": {"file_name": "test.json"},
            "reference": {
                "proper_terms": [],
                "affects": [],
                "models": [],
                "model_docs": [],
                "skill_doc": "",
            },
        }

    def _get_request_text(self, request_data, prompt_format):
        return json.dumps(request_data, ensure_ascii=False)


class _SupplementalStageStrategy:
    def build_stage_1_prompt(self, file_type, prompt_format):
        return f"translate {file_type} as {prompt_format}"

    def parse_stage_1_result(self, response, prompt_format):
        return json.loads(response)["translations"]

    def consume_parse_errors(self):
        return []


class _IdentityBuilder:
    def __init__(self, *_args, **_kwargs):
        self.unified_request = {
            "metadata": {},
            "reference": {},
            "text_blocks": [{"kr": "LCE", "jp": "LCE", "en": "LCE"}],
        }
        self.split_requests = []

    def build(self, prompt_format):
        return None

    def get_request_text(self, prompt_format):
        return ["translate LCE"]

    def deBuild(self, translations):
        return translations


class _IdentityStageStrategy:
    def __init__(self, _config):
        pass

    def needs_disambiguation(self):
        return False

    def build_stage_1_prompt(self, file_type, prompt_format):
        return f"translate {file_type} as {prompt_format}"

    def parse_stage_1_result(self, response, prompt_format):
        return json.loads(response)["translations"]

    def consume_parse_errors(self):
        return []

    def needs_self_check(self):
        return False


def _make_processor(tmp_path: Path, translator, recorder=None) -> FileProcessor:
    kr_base = tmp_path / "kr"
    kr_base.mkdir(exist_ok=True)
    kr_file = kr_base / "KR_test.json"
    kr_file.write_text('{"dataList": []}', encoding="utf-8")
    paths = PathConfig(
        target_path=tmp_path / "out",
        llc_base_path=tmp_path / "llc",
        KR_base_path=kr_base,
        JP_base_path=tmp_path / "jp",
        EN_base_path=tmp_path / "en",
    )
    return FileProcessor(
        FilePathConfig(kr_file, paths),
        engine=object(),
        translate_config=TranslateConfig(dump=recorder is not None),
        translator=translator,
        recorder=recorder,
    )


def test_http_error_body_and_exception_chain_are_recorded_and_redacted(tmp_path):
    recorder = TranslationRecorder(tmp_path / "dump.jsonl")
    processor = _make_processor(tmp_path, _HttpErrorTranslator(), recorder)

    with pytest.raises(APIError):
        processor._call_ai(
            stage="stage_1",
            system_prompt="system",
            user_prompt="user",
            response_format="json_object",
            timeout=60,
            prompt_format="xml_json",
            part=1,
            attempt=1,
        )

    call = processor._api_calls[0]
    assert call["status"] == "api_error"
    assert call["failure_kind"] == "translator_exception"
    assert call["http_attempts"][0]["status_code"] == 400
    assert "invalid response_format" in call["http_attempts"][0]["body"]
    assert call["http_attempts"][0]["request"]["headers"]["Authorization"] == "<redacted>"
    assert call["http_attempts"][0]["headers"]["Set-Cookie"] == "<redacted>"
    assert call["exception"]["type"] == "APIError"
    assert call["exception"]["cause"]["type"] == "HTTPError"


def test_failed_call_does_not_reuse_previous_raw_response(tmp_path):
    recorder = TranslationRecorder(tmp_path / "dump.jsonl")
    processor = _make_processor(tmp_path, _SequenceTranslator(), recorder)

    processor._call_ai(
        stage="stage_1",
        system_prompt="system",
        user_prompt="first",
        response_format="json_object",
        timeout=60,
        parser=json.loads,
        prompt_format="xml_json",
        part=1,
        attempt=1,
    )
    with pytest.raises(APIError):
        processor._call_ai(
            stage="stage_1",
            system_prompt="system",
            user_prompt="second",
            response_format="json_object",
            timeout=60,
            parser=json.loads,
            prompt_format="json_json",
            part=1,
            attempt=2,
        )

    assert processor._api_calls[0]["raw_response"] is not None
    assert processor._api_calls[1]["raw_response"] is None
    assert processor._api_calls[1]["status"] == "api_error"


def test_prompt_parse_failure_contains_json_location():
    from translateFunc.builder.prompt import PromptFactory

    factory = PromptFactory()
    assert factory.parse_response("not json {{{", 1, "xml_json") == []
    errors = factory.consume_parse_errors()

    assert errors[0]["type"] == "JSONDecodeError"
    assert errors[0]["line"] == 1
    assert errors[0]["column"] >= 1


def test_call_record_receives_structured_parse_errors(tmp_path):
    from translateFunc.builder.prompt import PromptFactory

    recorder = TranslationRecorder(tmp_path / "dump.jsonl")
    processor = _make_processor(tmp_path, _StaticTranslator("not json {{{"), recorder)
    factory = PromptFactory()

    _, parsed, record = processor._call_ai(
        stage="stage_1",
        system_prompt="system",
        user_prompt="user",
        response_format="json_object",
        timeout=60,
        parser=lambda response: factory.parse_response(response, 1, "xml_json"),
        parse_error_provider=factory.consume_parse_errors,
        prompt_format="xml_json",
        part=1,
        attempt=1,
    )

    assert parsed == []
    assert record["status"] == "parse_error"
    assert record["parse_errors"][0]["type"] == "JSONDecodeError"
    assert record["raw_response"] == "not json {{{"


def test_supplemental_translation_accepts_intentional_source_preservation(tmp_path):
    response = json.dumps({
        "translations": [{
            "id": 1,
            "translation": "LCE",
            "confidence": "high",
        }],
    })
    recorder = TranslationRecorder(tmp_path / "dump.jsonl")
    processor = _make_processor(tmp_path, _StaticTranslator(response), recorder)
    part_data = {
        "text_blocks": [
            {"kr": "LCE"},
            {"kr": "번역 대상"},
        ],
    }
    part_result = ["LCE", "翻译目标"]

    fixed = processor._retry_missing_entries(
        _SupplementalBuilder(),
        _SupplementalStageStrategy(),
        part_data,
        part_result,
        [0],
        ["xml_json"],
        0,
    )

    assert fixed == 1
    assert part_result == ["LCE", "翻译目标"]
    assert processor._api_calls[-1]["status"] == "success"


def test_intentional_source_preservation_does_not_trigger_supplemental_retry(
    tmp_path,
    monkeypatch,
):
    response = json.dumps({
        "translations": [{
            "id": 1,
            "translation": "LCE",
            "confidence": "high",
        }],
    })
    recorder = TranslationRecorder(tmp_path / "dump.jsonl")
    processor = _make_processor(tmp_path, _StaticTranslator(response), recorder)
    monkeypatch.setattr("translateFunc.processor.RequestBuilder", _IdentityBuilder)
    monkeypatch.setattr("translateFunc.processor.StageStrategy", _IdentityStageStrategy)

    translated, had_fallback = processor._translate({"dataList": []})

    assert translated == ["LCE"]
    assert had_fallback is False
    assert [call["stage"] for call in processor._api_calls] == ["stage_1"]


def test_multistage_translation_splits_stage_0_and_stage_2(tmp_path):
    translator = _CountingMultiStageTranslator()
    processor = _make_processor(tmp_path, translator)
    processor._config = TranslateConfig(
        translation_mode="multi_stage",
        disambiguation_mode="llm",
        enable_self_check=True,
        fallback=False,
    )

    engine = MatcherEngine()
    proper_terms = [
        {
            "term": f"[TERM-{index:03d}]",
            "translation": f"术语-{index}-" + "C" * 300,
            "note": "N" * 200,
        }
        for index in range(48)
    ]
    engine.build_proper(proper_terms)
    engine.build_roles([])
    engine.build_affects([])
    processor._engine = engine

    request_text = {
        "kr": {
            index: {("text",): f"[TERM-{index:03d}] " + "K" * 500}
            for index in range(48)
        },
        "jp": {
            index: {("text",): "J" * 200}
            for index in range(48)
        },
        "en": {
            index: {("text",): "E" * 200}
            for index in range(48)
        },
    }

    translated, had_fallback = processor._translate(request_text)

    assert had_fallback is False
    assert len(translated) == 48
    assert translator.stage_calls["stage_0"] > 1
    assert translator.stage_calls["stage_1"] > 1
    assert translator.stage_calls["stage_2"] > 1
    checked_values = [
        item[("text",)]
        for item in translated.values()
        if item[("text",)].startswith("checked-")
    ]
    assert len(checked_values) == translator.stage_calls["stage_2"]


def test_recovered_call_is_removed_from_failure_tracking(tmp_path):
    recorder = TranslationRecorder(tmp_path / "dump.jsonl")
    processor = _make_processor(tmp_path, _StaticTranslator("{}"), recorder)
    failed = processor._record_diagnostic_event(
        stage="stage_1",
        status="parse_error",
        failure_kind="empty_parsed_response",
        prompt_format="xml_json",
        part=1,
    )
    recovered_by = processor._record_diagnostic_event(
        stage="stage_1",
        status="success",
        prompt_format="json_json",
        part=1,
    )

    processor._mark_call_recovered(
        failed,
        recovery_kind="format_fallback",
        recovered_by=recovered_by,
    )

    assert failed["status"] == "recovered"
    assert failed["failure_kind"] is None
    assert failed["metadata"]["recovered_failure_kind"] == "empty_parsed_response"
    assert processor._last_failed_call is None


def test_recorder_serializes_unknown_values_and_redacts_secrets(tmp_path):
    class Unknown:
        def __repr__(self):
            return "Unknown(value=1)"

    path = tmp_path / "dump.jsonl"
    recorder = TranslationRecorder(path)
    recorder.write_record({
        "unknown": Unknown(),
        "api_key": "secret",
        "nested": {"Authorization": "Bearer secret"},
    })

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["unknown"] == "Unknown(value=1)"
    assert data["api_key"] == "<redacted>"
    assert data["nested"]["Authorization"] == "<redacted>"


def test_exception_serializer_preserves_cause_and_traceback():
    try:
        try:
            raise ValueError("inner")
        except ValueError as inner:
            raise RuntimeError("outer") from inner
    except RuntimeError as outer:
        serialized = serialize_exception(outer)

    assert serialized["type"] == "RuntimeError"
    assert serialized["cause"]["type"] == "ValueError"
    assert "ValueError: inner" in serialized["traceback"]


def test_processing_log_keeps_traceback_and_failed_call(tmp_path):
    processor = _make_processor(tmp_path, _SequenceTranslator())
    processor._last_failed_call = {
        "call_id": "call-1",
        "status": "api_error",
        "response_excerpt": "bad response",
    }
    outcome = ProcessOutcome(
        ProcessResult.SAVE_ERROR,
        "test.json",
        {"reason": "failed", "traceback": "full traceback"},
    )

    processor._write_processing_log(outcome, 0.0)

    log_path = tmp_path / "out" / "processing_log.jsonl"
    data = json.loads(log_path.read_text(encoding="utf-8"))
    assert data["extra"]["traceback"] == "full traceback"
    assert data["extra"]["last_failed_call"]["call_id"] == "call-1"


def test_safe_json_value_handles_recursive_structures():
    value = {}
    value["self"] = value
    assert safe_json_value(value)["self"] == "<recursive-reference>"


def test_string_credentials_are_redacted():
    value = safe_json_value({
        "url": "https://example.invalid/v1?api_key=secret&model=test",
        "message": "Authorization failed for Bearer token-value",
    })
    assert "secret" not in value["url"]
    assert "token-value" not in value["message"]


def test_http_observer_is_reused_per_translator():
    translator = _SequenceTranslator()
    first = HttpResponseObserver(translator)
    second = HttpResponseObserver(translator)

    assert first is second
    assert len(translator._session.hooks["response"]) == 1
