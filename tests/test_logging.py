"""Logging infrastructure tests."""
import json
import logging
import pytest
from unittest.mock import MagicMock, patch, call

from translateFunc.config import ProcessOutcome, PipelineSummary, TranslateConfig
from translateFunc.enums import ProcessResult
from translateFunc.log_bridge import LogBridge


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


class TestLogBridge:
    """LogBridge 双通道日志测试。"""

    def test_info_to_both(self):
        ui_msgs = []
        bridge = LogBridge(ui_callback=lambda msg: ui_msgs.append(msg))

        with patch.object(bridge._logger, 'info') as mock_info:
            bridge.info("test message")

        mock_info.assert_called_once_with("test message")
        assert ui_msgs == ["test message"]

    def test_warning_to_both(self):
        ui_msgs = []
        bridge = LogBridge(ui_callback=lambda msg: ui_msgs.append(msg))

        with patch.object(bridge._logger, 'warning') as mock_warning:
            bridge.warning("test warning")

        mock_warning.assert_called_once_with("test warning")
        assert "警告: test warning" in ui_msgs

    def test_error_to_both(self):
        ui_msgs = []
        bridge = LogBridge(ui_callback=lambda msg: ui_msgs.append(msg))

        with patch.object(bridge._logger, 'error') as mock_error:
            bridge.error("test error")

        mock_error.assert_called_once_with("test error")
        assert "错误: test error" in ui_msgs

    def test_exception_to_both(self):
        ui_msgs = []
        bridge = LogBridge(ui_callback=lambda msg: ui_msgs.append(msg))

        with patch.object(bridge._logger, 'exception') as mock_exc:
            bridge.exception("test exception")

        mock_exc.assert_called_once_with("test exception")
        assert "异常: test exception" in ui_msgs

    def test_set_ui_callback(self):
        bridge = LogBridge()
        msgs = []
        bridge.set_ui_callback(lambda msg: msgs.append(msg))
        bridge.info("hello")
        assert msgs == ["hello"]

    def test_default_ui_is_noop(self):
        bridge = LogBridge()
        # 不应抛出异常
        bridge.info("no UI attached")


class TestLoggingExceptionCalls:
    """验证 _logger.exception() 在关键路径被调用（使用 LCTA logger 确保日志正确路由到 app.log）。"""

    def test_worker_exception_logging(self):
        """WorkerPool 异常处理应调用 _logger.exception。"""
        from translateFunc.workers import WorkerPool
        import inspect
        source = inspect.getsource(WorkerPool.map)
        assert "_logger.exception" in source, (
            "WorkerPool.map() 应包含 _logger.exception() 调用"
        )

    def test_processor_exception_logging(self):
        """FileProcessor.process() 应包含 _logger.exception 调用。"""
        from translateFunc.processor import FileProcessor
        import inspect
        source = inspect.getsource(FileProcessor.process)
        assert "_logger.exception" in source, (
            "FileProcessor.process() 应包含 _logger.exception() 调用"
        )

    def test_pipeline_exception_logging(self):
        """TranslationPipeline 异常处理应包含 _logger.exception 调用。"""
        from translateFunc.pipeline import TranslationPipeline
        import inspect
        source = inspect.getsource(TranslationPipeline._update_roles)
        assert "_logger.exception" in source, (
            "TranslationPipeline._update_roles() 应包含 _logger.exception() 调用"
        )


class TestFancyLoggerConfiguration:
    """fancy / rule_editor 子日志器应接入 LogManager 的 handler，避免调试日志丢失。"""

    def _log_manager(self):
        from globalManagers.LogManager import LogManager
        return LogManager()

    def test_fancy_logger_is_configured(self):
        manager = self._log_manager()
        main_logger = manager._logger
        fancy = logging.getLogger("fancy")
        assert fancy.level == main_logger.level
        assert fancy.propagate is False
        assert len(fancy.handlers) >= len(main_logger.handlers)

    def test_rule_editor_logger_is_configured(self):
        manager = self._log_manager()
        main_logger = manager._logger
        rule_editor = logging.getLogger("rule_editor")
        assert rule_editor.level == main_logger.level
        assert rule_editor.propagate is False
        assert len(rule_editor.handlers) >= len(main_logger.handlers)

    def test_fancy_debug_message_reaches_shared_handlers(self):
        """通过 fancy 日志器发送的 DEBUG 消息应被其自身 handler 捕获。"""
        manager = self._log_manager()
        records = []
        class CaptureHandler(logging.Handler):
            def emit(self, record):
                records.append(record)

        capture = CaptureHandler(level=logging.DEBUG)
        fancy = logging.getLogger("fancy")
        fancy.addHandler(capture)
        try:
            fancy.debug("fancy 调试日志测试")
        finally:
            fancy.removeHandler(capture)
        assert any("fancy 调试日志测试" in record.getMessage() for record in records)


class TestLogManagerPercentSafety:
    """LogManager 的 %-格式化必须容忍消息正文里出现的 %（URL 编码等）。

    回归背景：`debug()` 曾以位置参数传 level，而 log() 里「首个位置参数是 int
    就当 level」的兼容启发式会被消息正文里的 `%20f` / `%20a` / `%20c` 绕过，
    转而对消息本身执行 `message % (logging.DEBUG,)` 抛 TypeError/ValueError。
    异常从 `function_aria2_downloader.add_uri` 的调试日志穿透出去，使文件名含
    `%20`（URL 编码空格）的 mod 下载在 0% 直接失败——日志调用反过来成了业务
    失败的来源。
    """

    _ALBINA = ("https://dl.mods.lcta.top/nexus/133/"
               "Albina%20and%20the%20master.mod.zip")
    _RODION = ("https://dl.mods.lcta.top/nexus/85/"
               "Rodion%20Thumb%20Father%20who%20can%20even%20spin%20in%20circles.mod.zip")
    _MIDDLEFINGER = ("https://dl.mods.lcta.top/nexus/139/530_debe8f70"
                     "?filename=Middlefinger%20father.Mod.zip")

    @pytest.fixture()
    def captured(self, monkeypatch):
        from globalManagers.LogManager import LogManager

        manager = LogManager()
        records = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                records.append(record)

        logger = logging.getLogger("LCTA.percent.safety")
        logger.handlers = [CaptureHandler(level=logging.DEBUG)]
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        monkeypatch.setattr(manager, "_logger", logger)
        return manager, records

    def test_url_encoded_space_is_not_a_format_placeholder(self, captured):
        """`%20f` 曾把文件名改写成 `           10.000000`（日志静默损坏）。"""
        manager, records = captured
        manager.debug(f"[高速下载器/aria2] 已提交 {self._MIDDLEFINGER} -> C:\\out")

        assert records[-1].levelno == logging.DEBUG
        assert "Middlefinger%20father.Mod.zip" in records[-1].getMessage()

    def test_albina_url_does_not_raise(self, captured):
        """修复前：TypeError: not enough arguments for format string。"""
        manager, records = captured
        manager.debug(f"已提交 {self._ALBINA}")

        assert "Albina%20and%20the%20master.mod.zip" in records[-1].getMessage()

    def test_rodion_url_does_not_raise(self, captured):
        """修复前：ValueError: unsupported format character 'T' (0x54)。"""
        manager, records = captured
        manager.debug(f"已提交 {self._RODION}")

        assert "Rodion%20Thumb%20Father" in records[-1].getMessage()

    def test_level_keyword_is_respected(self, captured):
        manager, records = captured
        manager.log("普通消息", level=logging.WARNING)

        assert records[-1].levelno == logging.WARNING

    def test_int_positional_arg_is_a_format_argument(self, captured):
        """位置参数只作为格式化实参，不再可能被当成 level。"""
        manager, records = captured
        manager.log("- Adding unused mod asset of type %d: %s", 3, "a.3")

        assert records[-1].levelno == logging.INFO
        assert records[-1].getMessage() == "- Adding unused mod asset of type 3: a.3"

    def test_message_without_placeholder_keeps_level(self, captured):
        """无占位符 + int 位置参数：按参数处理并降级输出，不改级别。"""
        manager, records = captured
        manager.log("no placeholder here", 20)

        assert records[-1].levelno == logging.INFO
        assert records[-1].getMessage() == "no placeholder here 20"

    def test_format_failure_never_raises(self, captured):
        manager, records = captured
        manager.log("broken %s %s", "only-one")

        assert records[-1].getMessage() == "broken %s %s only-one"

    def test_log_error_percent_safety(self, captured):
        manager, records = captured
        manager.log_error("错误 %20f 与 %20f", "detail")

        assert records[-1].levelno == logging.ERROR
        assert "detail" in records[-1].getMessage()
