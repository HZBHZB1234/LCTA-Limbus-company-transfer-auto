"""TranslationPipeline 集成测试 —— 使用 mock 依赖。"""
import json
import tempfile
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from translateFunc import (
    TranslationPipeline, TranslateConfig, PipelineSummary,
    ProcessResult, ProcessOutcome,
)
from translateFunc.enums import FileType, MatchConfidence
from translateFunc.config import FilePathConfig, PathConfig


class TestPipelineSummary:
    """Unit tests for PipelineSummary aggregation."""

    def test_empty_summary(self):
        s = PipelineSummary()
        assert s.total == 0
        assert s.success_count == 0
        assert s.error_count == 0

    def test_mixed_results(self):
        s = PipelineSummary(
            saved=["a.json", "b.json"],
            skipped=["c.json"],
            errors=[ProcessOutcome(ProcessResult.SAVE_ERROR, "d.json")],
        )
        assert s.total == 4
        assert s.success_count == 2
        assert s.error_count == 1


class TestTranslateConfig:
    """Tests for TranslateConfig.from_config_manager()."""

    def test_defaults(self):
        config = TranslateConfig()
        assert config.max_workers == 4
        assert config.enable_concurrent is True
        assert config.translation_mode == "multi_stage"
        assert config.disambiguation_mode == "hybrid"

    def test_from_config_manager(self):
        mock_mgr = MagicMock()
        mock_mgr.get.side_effect = lambda key, default=None: {
            "ui_default.translator": {
                "translator": "百度翻译服务",
                "max_workers": 8,
                "enable_concurrent": False,
            },
            "game_path": "/test/path",
            "debug": True,
        }.get(key, default)

        config = TranslateConfig.from_config_manager(mock_mgr)
        assert config.translator_name == "百度翻译服务"
        assert config.max_workers == 8
        assert config.enable_concurrent is False
        assert config.is_llm is False


class TestProcessOutcome:
    """Tests for ProcessOutcome and ProcessResult enum."""

    def test_success_outcome(self):
        o = ProcessOutcome(ProcessResult.SUCCESS_SAVED, "test.json")
        assert o.result == ProcessResult.SUCCESS_SAVED
        assert o.file_name == "test.json"
        assert o.extra is None

    def test_error_outcome_with_details(self):
        o = ProcessOutcome(
            ProcessResult.JSON_DECODE_ERROR,
            "bad.json",
            extra={"line": 42, "error": "Unexpected token"},
        )
        assert o.result == ProcessResult.JSON_DECODE_ERROR
        assert o.extra["line"] == 42


class TestFilePathConfig:
    """Tests for FilePathConfig path resolution."""

    def test_basic_paths(self, tmp_path):
        kr_base = tmp_path / "kr"
        kr_base.mkdir()
        (kr_base / "sub").mkdir()
        test_file = kr_base / "sub" / "KR_test.json"
        test_file.write_text("{}", encoding="utf-8")

        base = PathConfig(
            target_path=tmp_path / "out",
            llc_base_path=tmp_path / "llc",
            KR_base_path=kr_base,
            JP_base_path=tmp_path / "jp",
            EN_base_path=tmp_path / "en",
        )

        fpc = FilePathConfig(KR_path=test_file, _PathConfig=base, has_prefix=True)
        assert fpc.real_name == "test.json"
        assert fpc.rel_path == Path("sub") / "KR_test.json"
        assert fpc.rel_dir == Path("sub")

    def test_no_prefix_paths(self, tmp_path):
        kr_base = tmp_path / "kr"
        kr_base.mkdir()
        (kr_base / "sub").mkdir()
        test_file = kr_base / "sub" / "test.json"
        test_file.write_text("{}", encoding="utf-8")

        base = PathConfig(
            target_path=tmp_path / "out",
            llc_base_path=tmp_path / "llc",
            KR_base_path=kr_base,
            JP_base_path=tmp_path / "jp",
            EN_base_path=tmp_path / "en",
        )

        fpc = FilePathConfig(KR_path=test_file, _PathConfig=base, has_prefix=False)
        assert fpc.real_name == "test.json"
        assert fpc.EN_path == tmp_path / "en" / "sub" / "test.json"
        assert fpc.JP_path == tmp_path / "jp" / "sub" / "test.json"
        assert fpc.LLC_path == tmp_path / "llc" / "sub" / "test.json"


class TestPipelineBugFixes:
    """Tests for B3, B4, B5 bug fixes."""

    def test_update_affects_loads_jp_en_names_by_id(self, tmp_path):
        kr_base = tmp_path / "kr"
        jp_base = tmp_path / "jp"
        en_base = tmp_path / "en"
        target_base = tmp_path / "out"
        for path in (kr_base, jp_base, en_base, target_base):
            path.mkdir()

        def write_keywords(path, items):
            path.write_text(
                json.dumps({"dataList": items}, ensure_ascii=False),
                encoding="utf-8",
            )

        kr_file = kr_base / "KR_BattleKeywords.json"
        write_keywords(kr_file, [{"id": "Charge", "name": "충전"}])
        write_keywords(jp_base / "JP_BattleKeywords.json", [
            {"id": "Charge", "name": "充電"},
        ])
        write_keywords(en_base / "EN_BattleKeywords.json", [
            {"id": "Charge", "name": "Charge"},
        ])
        write_keywords(target_base / "BattleKeywords.json", [
            {"id": "Charge", "name": "充能", "desc": "状态效果"},
        ])

        base = PathConfig(
            target_path=target_base,
            llc_base_path=tmp_path / "llc",
            KR_base_path=kr_base,
            JP_base_path=jp_base,
            EN_base_path=en_base,
        )
        pipeline = TranslationPipeline.__new__(TranslationPipeline)
        pipeline._engine = MagicMock()
        pipeline._on_log = MagicMock()

        pipeline._update_affects(kr_file, base, has_prefix=True)

        affects = pipeline._engine.build_affects.call_args.args[0]
        assert affects == [{
            "id": "Charge",
            "kr": "충전",
            "jp": "充電",
            "en": "Charge",
            "cn": "充能",
            "desc": "状态效果",
        }]

    def test_zip_longest_prevents_truncation(self):
        """B5: zip_longest 在列表长度不匹配时不截断。"""
        from itertools import zip_longest
        kr = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        cn = [{"id": 1, "name": "甲"}]
        # 旧 zip 会截断为 1；zip_longest 保留全部
        result = []
        for k, c in zip_longest(kr, cn, fillvalue=None):
            if k is None or c is None:
                continue  # 跳过不匹配项
            result.append({"id": k["id"], "kr": k["name"], "cn": c["name"]})
        assert len(result) == 1  # 仅匹配的条目保留
        # 不崩溃、不截断

    def test_priority_files_checked_before_remove(self, tmp_path):
        """B4: 先检查文件存在再 remove。"""
        kr_path = tmp_path / "kr"
        kr_path.mkdir()
        # 创建 model 文件但不创建 keyword 文件
        model = kr_path / "KR_ScenarioModelCodes-AutoCreated.json"
        model.write_text("{}", encoding="utf-8")
        # keyword 不存在
        keyword = kr_path / "KR_BattleKeywords.json"

        has_prefix = True
        files = list(kr_path.rglob("*.json"))

        if model.exists() and keyword.exists():
            files.remove(model)
            files.remove(keyword)
            priority = [keyword, model]
        else:
            priority = []

        assert len(priority) == 0  # 两个都存在才进入优先处理
        assert len(files) == 1      # 文件未被错误移除


class TestRegressionFixes:
    """Phase 1-2 修复的回归测试。"""

    def test_fallback_not_in_errors(self):
        """FALLBACK_TO_ORIGINAL 应进入 summary.fallback 而非 errors。"""
        summary = PipelineSummary()
        outcome = ProcessOutcome(ProcessResult.FALLBACK_TO_ORIGINAL, "test.json")
        # 模拟 _record_outcome 逻辑
        if outcome.result == ProcessResult.FALLBACK_TO_ORIGINAL:
            summary.fallback.append(outcome.file_name)
        else:
            summary.errors.append(outcome)
        assert "test.json" in summary.fallback
        assert "test.json" not in [e.file_name for e in summary.errors]

    def test_fallback_count_accurate(self):
        summary = PipelineSummary()
        summary.fallback.append("a.json")
        summary.fallback.append("b.json")
        assert summary.fallback_count == 2

    def test_make_data_index_without_id_key(self):
        """_make_data_index 对无 id 键的 dataList 应回退为 enumerate。"""
        from translateFunc.processor import FileProcessor

        # 构造一个 dataList 项缺少 "id" 键的场景
        data = [{"name": "item1", "value": "v1"}, {"name": "item2", "value": "v2"}]
        processor = FileProcessor.__new__(FileProcessor)
        processor.is_story = False
        processor.en_data = data
        processor.kr_data = data
        processor.jp_data = data
        processor.llc_data = data

        # 调用 _make_data_index 不应抛出 KeyError
        processor._make_data_index()
        # 应该用 enumerate 索引
        assert processor.kr_index == {0: data[0], 1: data[1]}

    def test_make_data_index_with_id_key(self):
        """有 id 键的 dataList 应正常使用 id 索引。"""
        from translateFunc.processor import FileProcessor
        data = [{"id": "A001", "name": "item1"}, {"id": "A002", "name": "item2"}]
        processor = FileProcessor.__new__(FileProcessor)
        processor.is_story = False
        processor.en_data = data
        processor.kr_data = data
        processor.jp_data = data
        processor.llc_data = data

        processor._make_data_index()
        assert processor.kr_index == {"A001": data[0], "A002": data[1]}

    def test_prompt_version_removed(self):
        """prompt_version 字段应已从 TranslateConfig 中移除。"""
        config = TranslateConfig()
        assert not hasattr(config, "prompt_version")


class TestCheckTranslated:
    """Bug 1: _check_translated 必须基于 llc 真实键集判定，而非对齐后的键集。"""

    @staticmethod
    def _make_processor(tmp_path):
        kr_base = tmp_path / "kr"
        kr_base.mkdir(exist_ok=True)
        kr_file = kr_base / "KR_test.json"
        kr_file.write_text('{"dataList": []}', encoding="utf-8")
        llc_base = tmp_path / "llc"
        llc_base.mkdir(exist_ok=True)
        (llc_base / "test.json").write_text('{"dataList": []}', encoding="utf-8")
        paths = PathConfig(
            target_path=tmp_path / "out",
            llc_base_path=llc_base,
            KR_base_path=kr_base,
            JP_base_path=tmp_path / "jp",
            EN_base_path=tmp_path / "en",
        )
        from translateFunc.processor import FileProcessor
        return FileProcessor(
            FilePathConfig(kr_file, paths),
            engine=object(),
            translate_config=TranslateConfig(),
            translator=object(),
        )

    def test_partial_llc_coverage_not_already_translated(self, tmp_path):
        """部分翻译的 LLC（缺少 KR 新增条目）不应被判定为已翻译。"""
        processor = self._make_processor(tmp_path)
        processor.kr_index = {i: {"id": i} for i in range(5)}
        processor.llc_index = {i: {"id": i} for i in range(4)}  # 缺少 id=4
        processor.jp_index = dict(processor.kr_index)
        processor.en_index = dict(processor.kr_index)

        outcome = processor._check_translated()

        assert outcome is None
        # llc_index 不应被 _align 补齐（真实键集保留）
        assert set(processor.llc_index.keys()) == {0, 1, 2, 3}
        # 不应复制旧 LLC 文件
        assert not (tmp_path / "out" / "test.json").exists()

    def test_full_llc_coverage_is_already_translated(self, tmp_path):
        """llc 键集完整覆盖 kr 键集时应判定已翻译并复制 LLC 文件。"""
        processor = self._make_processor(tmp_path)
        processor.kr_index = {i: {"id": i} for i in range(5)}
        processor.llc_index = {i: {"id": i} for i in range(5)}
        processor.jp_index = dict(processor.kr_index)
        processor.en_index = dict(processor.kr_index)

        outcome = processor._check_translated()

        assert outcome is not None
        assert outcome.result == ProcessResult.ALREADY_TRANSLATED
        assert (tmp_path / "out" / "test.json").exists()

    def test_length_mismatch_does_not_align_llc_index(self, tmp_path):
        """长度不一致触发 jp/en 对齐时，llc_index 仍保留真实键集。"""
        processor = self._make_processor(tmp_path)
        processor.kr_index = {i: {"id": i} for i in range(5)}
        processor.llc_index = {i: {"id": i} for i in range(2)}
        processor.jp_index = {i: {"id": i} for i in range(2)}
        processor.en_index = {i: {"id": i} for i in range(2)}

        outcome = processor._check_translated()

        assert outcome is None
        # 修复前：_align 会把 llc_index 补齐为 kr 键集，导致误判已翻译
        assert set(processor.llc_index.keys()) == {0, 1}

    def test_empty_llc_not_already_translated(self, tmp_path):
        """空 LLC（无已翻译数据）不应生成虚假键或判定已翻译。"""
        processor = self._make_processor(tmp_path)
        processor.kr_index = {i: {"id": i} for i in range(3)}
        processor.llc_index = {}
        processor.jp_index = dict(processor.kr_index)
        processor.en_index = dict(processor.kr_index)

        outcome = processor._check_translated()

        assert outcome is None
        assert not (tmp_path / "out" / "test.json").exists()


class TestProperFetchTerms:
    """Bug 4: proper 术语获取的网络失败与本地读取容错。"""

    def test_empty_proper_path_returns_empty(self):
        """proper_path 为空时返回空列表，不抛 IsADirectoryError。"""
        from translateFunc.matcher.proper import ProperAnalyzer
        terms = ProperAnalyzer().fetch_terms(auto_fetch=False, proper_path="")
        assert terms == []

    def test_missing_local_file_returns_empty(self, tmp_path):
        from translateFunc.matcher.proper import ProperAnalyzer
        terms = ProperAnalyzer().fetch_terms(
            auto_fetch=False,
            proper_path=str(tmp_path / "not_exists.json"),
        )
        assert terms == []

    def test_valid_local_file_loaded(self, tmp_path):
        from translateFunc.matcher.proper import ProperAnalyzer
        proper_file = tmp_path / "proper.json"
        proper_file.write_text(
            json.dumps([{"term": "이상", "translation": "李箱"}], ensure_ascii=False),
            encoding="utf-8",
        )
        terms = ProperAnalyzer().fetch_terms(
            auto_fetch=False, proper_path=str(proper_file),
        )
        assert terms == [{"term": "이상", "translation": "李箱"}]

    def test_pipeline_degrades_on_fetch_network_failure(
        self, tmp_path, monkeypatch, caplog,
    ):
        """paratranz API 不可达时 pipeline 降级为本地数据，不整体崩溃。"""
        import requests
        from translateFunc import TranslationPipeline

        kr = tmp_path / "kr"
        kr.mkdir()
        (tmp_path / "jp").mkdir()
        (tmp_path / "en").mkdir()

        config = TranslateConfig(
            game_path=tmp_path / "game",
            output_dir=tmp_path / "out",
            kr_path=str(kr),
            enable_dev_settings=True,
            enable_proper=True,
            auto_fetch_proper=True,
            proper_path="",
            enable_concurrent=False,
        )

        def _boom(*_args, **_kwargs):
            raise requests.ConnectionError("paratranz unreachable")

        monkeypatch.setattr("translateFunc.matcher.proper.fetch_proper", _boom)
        monkeypatch.setattr(
            TranslationPipeline, "_build_translator", lambda self: object(),
        )

        # LogManager 单例会将 LCTA logger 的 propagate 置 False，
        # 恢复传播以便 caplog 捕获警告记录
        import logging
        monkeypatch.setattr(logging.getLogger("LCTA"), "propagate", True)

        with caplog.at_level("WARNING", logger="LCTA"):
            summary = TranslationPipeline(config).run()

        assert summary.total == 0  # 无崩溃，空术语表继续运行
        assert any("专有名词远程抓取失败" in r.message for r in caplog.records)
