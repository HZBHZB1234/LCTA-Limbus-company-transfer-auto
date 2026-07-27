import json
from pathlib import Path

import pytest

from webutils.function_translation_logs import TranslationLogService


def _record(
    file_name: str,
    *,
    timestamp: str = "2026-07-27T12:00:00",
    outcome: str = "SUCCESS_SAVED",
    stage: str = "stage_1",
    status: str = "success",
    failure_kind=None,
    exception=None,
    raw_response: str = "translated response",
):
    call_exception = exception if status != "success" else None
    return {
        "schema_version": 2,
        "timestamp": timestamp,
        "file_name": file_name,
        "text_blocks": [{"en": "source text"}],
        "reference": {},
        "api_calls": [{
            "call_id": f"call-{file_name}",
            "stage": stage,
            "part": None,
            "attempt": 1,
            "format": "xml_json",
            "system_prompt": "system prompt",
            "user_prompt": "user prompt",
            "raw_response": raw_response,
            "parsed_response": {"translation": "译文"},
            "http_attempts": [],
            "parse_errors": [],
            "validation_errors": [],
            "exception": call_exception,
            "status": status,
            "failure_kind": failure_kind,
            "metadata": {},
            "started_at": timestamp,
            "finished_at": timestamp,
            "elapsed_seconds": 0.5,
        }],
        "outcome": outcome,
        "outcome_extra": {},
        "exception": exception if status == "success" else None,
        "call_summary": {"total": 1, "failed": 0 if status == "success" else 1},
        "elapsed_seconds": 1.25,
    }


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            if isinstance(record, str):
                handle.write(record + "\n")
            else:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_inspects_only_selected_current_schema_jsonl(tmp_path):
    log_dir = tmp_path / "translation_dump"
    _write_jsonl(log_dir / "current.jsonl", [_record("A.json")])
    _write_jsonl(log_dir / "legacy.jsonl", [{"file_name": "old.json"}])
    _write_jsonl(log_dir / "ignored.json", [_record("B.json")])
    service = TranslationLogService(log_dir)

    info = service.get_file_info("current.jsonl")

    assert info["name"] == "current.jsonl"
    assert info["record_count"] == 1
    with pytest.raises(ValueError):
        service.get_file_info("legacy.jsonl")
    with pytest.raises(ValueError):
        service.get_file_info("ignored.json")


def test_rejects_empty_selected_dump(tmp_path):
    log_path = tmp_path / "translation_dump" / "empty.jsonl"
    _write_jsonl(log_path, [])

    with pytest.raises(ValueError):
        TranslationLogService(log_path.parent).get_file_info(log_path.name)


def test_viewer_api_requires_native_file_selection(tmp_path):
    from webui.app import TranslationLogViewerAPI

    log_path = tmp_path / "chosen.jsonl"
    _write_jsonl(log_path, [_record("Chosen.json")])

    class FakeWindow:
        def create_file_dialog(self, *_args, **_kwargs):
            return (str(log_path),)

    api = TranslationLogViewerAPI()
    assert api.query_records()["success"] is False
    api.set_window(FakeWindow())

    selected = api.choose_dump()
    queried = api.query_records()

    assert selected["success"] is True
    assert selected["data"]["path"] == str(log_path.resolve())
    assert queried["success"] is True
    assert queried["data"]["records"][0]["file_name"] == "Chosen.json"


def test_query_filters_and_paginates_current_records(tmp_path):
    log_path = tmp_path / "translation_dump" / "current.jsonl"
    records = [
        _record(f"Success-{index}.json", raw_response=f"needle-{index}")
        for index in range(30)
    ]
    records.append(_record(
        "Failed.json",
        timestamp="2026-07-27T13:00:00",
        outcome="INTERNAL_ERROR",
        stage="stage_2",
        status="failed",
        failure_kind="parse_error",
        exception={"type": "ValueError", "message": "bad AI response"},
        raw_response="special broken payload",
    ))
    _write_jsonl(log_path, records)
    service = TranslationLogService(log_path.parent)

    page = service.query_records("current.jsonl", page=2, page_size=25)
    assert page["total"] == 31
    assert len(page["records"]) == 6
    assert page["total_pages"] == 2

    failed = service.query_records("current.jsonl", {
        "outcome": "INTERNAL_ERROR",
        "stage": "stage_2",
        "call_status": "failed",
        "failure_kind": "parse_error",
        "has_exception": True,
    })
    assert failed["total"] == 1
    assert failed["records"][0]["file_name"] == "Failed.json"
    assert failed["records"][0]["exception_type"] == "ValueError"


def test_recovered_calls_are_not_counted_as_failures(tmp_path):
    log_path = tmp_path / "translation_dump" / "current.jsonl"
    record = _record(
        "Recovered.json",
        status="recovered",
        failure_kind=None,
    )
    record["call_summary"] = {"total": 1, "failed": 0}
    record["api_calls"][0]["metadata"] = {
        "recovered_status": "parse_error",
        "recovered_failure_kind": "empty_parsed_response",
    }
    _write_jsonl(log_path, [record])

    result = TranslationLogService(log_path.parent).query_records("current.jsonl")

    assert result["records"][0]["failed_call_count"] == 0
    assert result["records"][0]["call_statuses"] == ["recovered"]
    assert result["records"][0]["has_exception"] is False


def test_reads_full_record_and_reports_broken_line(tmp_path):
    log_path = tmp_path / "translation_dump" / "current.jsonl"
    _write_jsonl(log_path, ["{broken-json", _record("Valid.json")])
    service = TranslationLogService(log_path.parent)

    result = service.query_records("current.jsonl")
    assert result["invalid_count"] == 1
    assert result["records"][0]["outcome"] == "FORMAT_ERROR"

    broken = service.get_record("current.jsonl", 1)
    valid = service.get_record("current.jsonl", 2)
    assert broken["invalid"] is True
    assert "parse_error" in broken
    assert valid["invalid"] is False
    assert valid["api_calls"][0]["raw_response"] == "translated response"


def test_export_preserves_all_filtered_v2_records(tmp_path):
    log_path = tmp_path / "translation_dump" / "current.jsonl"
    _write_jsonl(log_path, [
        _record("Keep.json", outcome="INTERNAL_ERROR", status="failed", failure_kind="api_error"),
        _record("Skip.json"),
        "{broken-json",
    ])
    destination = tmp_path / "filtered.jsonl"
    service = TranslationLogService(log_path.parent)

    result = service.export_filtered(
        "current.jsonl",
        {"outcome": "INTERNAL_ERROR"},
        destination,
    )

    exported = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()]
    assert result["exported"] == 1
    assert result["skipped_invalid"] == 0
    assert exported[0]["file_name"] == "Keep.json"
    assert exported[0]["schema_version"] == 2


def test_cache_invalidates_when_dump_grows(tmp_path):
    log_path = tmp_path / "translation_dump" / "current.jsonl"
    _write_jsonl(log_path, [_record("First.json")])
    service = TranslationLogService(log_path.parent)
    assert service.query_records("current.jsonl")["total"] == 1

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_record("Second.json"), ensure_ascii=False) + "\n")

    assert service.query_records("current.jsonl")["total"] == 2


@pytest.mark.parametrize("file_id", ["../secret.jsonl", "nested/file.jsonl", "dump.json"])
def test_rejects_paths_outside_current_dump_format(tmp_path, file_id):
    service = TranslationLogService(tmp_path / "translation_dump")
    with pytest.raises(ValueError):
        service.query_records(file_id)
