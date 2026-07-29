"""Logging infrastructure tests."""
import json

from translateFunc.config import ProcessOutcome, PipelineSummary
from translateFunc.enums import ProcessResult


class TestProcessOutcomeExtra:
    """ProcessOutcome.extra 结构化数据测试。"""

    def test_outcome_preserves_extra_fields(self):
        extra = {"reason": "test", "traceback": "tb", "elapsed_seconds": 1.5}
        outcome = ProcessOutcome(ProcessResult.SAVE_ERROR, "test.json", extra)
        assert outcome.extra["reason"] == "test"
        assert outcome.extra["traceback"] == "tb"
        assert outcome.extra["elapsed_seconds"] == 1.5

    def test_outcome_extra_default_none(self):
        outcome = ProcessOutcome(ProcessResult.SUCCESS_SAVED, "test.json")
        assert outcome.extra is None

    def test_outcome_with_extra_roundtrip(self):
        extra = {
            "reason": "some error",
            "exception_type": "ValueError",
            "traceback": "line1\nline2",
            "text_blocks_count": 42,
            "elapsed_seconds": 3.14,
        }
        outcome = ProcessOutcome(ProcessResult.SAVE_ERROR, "file.json", extra)
        dumped = json.dumps({
            "file_name": outcome.file_name,
            "result": outcome.result.name,
            "extra": outcome.extra,
        })
        loaded = json.loads(dumped)
        assert loaded["extra"]["text_blocks_count"] == 42


class TestPipelineSummaryFallback:
    """PipelineSummary.fallback 字段测试。"""

    def test_fallback_field_exists(self):
        summary = PipelineSummary()
        assert hasattr(summary, "fallback")
        assert summary.fallback == []

    def test_fallback_count_property(self):
        summary = PipelineSummary()
        summary.fallback.append("file1.json")
        summary.fallback.append("file2.json")
        assert summary.fallback_count == 2

    def test_total_includes_fallback(self):
        summary = PipelineSummary()
        summary.saved.append("a.json")
        summary.skipped.append("b.json")
        summary.fallback.append("c.json")
        summary.errors.append(ProcessOutcome(ProcessResult.SAVE_ERROR, "d.json"))
        assert summary.total == 4

    def test_fallback_not_in_errors(self):
        """fallback 中的文件不应出现在 errors 中。"""
        summary = PipelineSummary()
        summary.fallback.append("fallback.json")
        assert "fallback.json" not in [e.file_name for e in summary.errors]
