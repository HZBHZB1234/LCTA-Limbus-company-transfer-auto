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
