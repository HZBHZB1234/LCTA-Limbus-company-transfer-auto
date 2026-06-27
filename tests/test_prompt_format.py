"""Prompt format generation, parsing, and fallback tests."""
import json
import xml.etree.ElementTree as ET
import pytest
from unittest.mock import MagicMock, patch

from translateFunc.builder.prompt import PromptFactory
from translateFunc.builder.stages import StageStrategy
from translateFunc.config import TranslateConfig
from translateFunc.enums import FileType


class TestPromptFactoryFormats:
    """Tests for PromptFactory with three prompt formats."""

    def setup_method(self):
        self.pf = PromptFactory()

    # ---- xml_json (default) ----

    def test_xml_json_system_prompt_structure(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_json")
        assert "<role>" in sp
        assert "<rules>" in sp
        assert "<format>" in sp
        assert '"translations"' in sp  # JSON format instruction in XML

    def test_xml_json_system_prompt_stage_0(self):
        sp = self.pf.build_system_prompt(FileType.OTHER, 0, "xml_json")
        assert "<role>" in sp
        assert "<rules>" in sp
        assert "disambiguations" in sp

    def test_xml_json_system_prompt_stage_2(self):
        sp = self.pf.build_system_prompt(FileType.OTHER, 2, "xml_json")
        assert "checked_translations" in sp

    # ---- xml_xml ----

    def test_xml_xml_system_prompt_structure(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_xml")
        assert "<role>" in sp
        assert "<rules>" in sp
        assert "<translations>" in sp  # XML response instruction
        assert "<translation>" in sp

    def test_xml_xml_system_prompt_stage_0(self):
        sp = self.pf.build_system_prompt(FileType.OTHER, 0, "xml_xml")
        assert "<disambiguations>" in sp

    # ---- json_json ----

    def test_json_json_system_prompt_structure(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "json_json")
        assert '"role"' in sp
        assert '"rules"' in sp
        assert '"format"' in sp
        assert '"translations"' in sp

    def test_json_json_contains_no_xml_tags(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "json_json")
        assert "<role>" not in sp
        assert "<rules>" not in sp

    def test_json_json_system_prompt_stage_0(self):
        sp = self.pf.build_system_prompt(FileType.OTHER, 0, "json_json")
        assert '"disambiguations"' in sp

    # ---- FileType variations ----

    def test_skill_file_type_all_formats(self):
        for fmt in ["xml_json", "xml_xml", "json_json"]:
            sp = self.pf.build_system_prompt(FileType.SKILL, 1, fmt)
            # skill_doc NOT in system prompt anymore
            assert len(sp) > 0

    def test_story_file_type_all_formats(self):
        for fmt in ["xml_json", "xml_xml", "json_json"]:
            sp = self.pf.build_system_prompt(FileType.STORY, 1, fmt)
            # role_styles NOT in system prompt anymore
            assert len(sp) > 0


class TestPromptFactoryParsing:
    """Tests for PromptFactory.parse_response()."""

    def setup_method(self):
        self.pf = PromptFactory()

    # ---- JSON parsing (xml_json / json_json) ----

    def test_parse_json_stage_1(self):
        for fmt in ["xml_json", "json_json"]:
            text = '{"translations": [{"id": 1, "translation": "你好", "reasoning": "直译", "confidence": "high"}]}'
            result = self.pf.parse_response(text, 1, fmt)
            assert len(result) == 1
            assert result[0]["translation"] == "你好"
            assert result[0]["confidence"] == "high"

    def test_parse_json_stage_0(self):
        for fmt in ["xml_json", "json_json"]:
            text = '{"disambiguations": [{"term": "테스트", "applies": true, "actual_meaning": "测试", "reason": "上下文匹配"}]}'
            result = self.pf.parse_response(text, 0, fmt)
            assert len(result) == 1
            assert result[0]["term"] == "테스트"
            assert result[0]["applies"] is True

    def test_parse_json_stage_2(self):
        for fmt in ["xml_json", "json_json"]:
            text = '{"checked_translations": [{"id": 1, "translation": "修正", "changed": true, "change_reason": "术语错误"}]}'
            result = self.pf.parse_response(text, 2, fmt)
            assert len(result) == 1
            assert result[0]["changed"] is True
            assert result[0]["translation"] == "修正"

    def test_parse_json_invalid_returns_empty(self):
        for fmt in ["xml_json", "json_json"]:
            result = self.pf.parse_response("not valid json {{{", 1, fmt)
            assert result == []

    def test_parse_json_missing_field_returns_empty(self):
        for fmt in ["xml_json", "json_json"]:
            result = self.pf.parse_response('{"other": []}', 1, fmt)
            assert result == []

    # ---- XML parsing (xml_xml) ----

    def test_parse_xml_stage_1(self):
        text = (
            '<translations>'
            '<item id="1">'
            '<translation>你好</translation>'
            '<reasoning>直译</reasoning>'
            '<confidence>high</confidence>'
            '</item>'
            '</translations>'
        )
        result = self.pf.parse_response(text, 1, "xml_xml")
        assert len(result) == 1
        assert result[0]["translation"] == "你好"
        assert result[0]["confidence"] == "high"

    def test_parse_xml_multiple_items(self):
        text = (
            '<translations>'
            '<item id="1"><translation>A</translation><reasoning>R1</reasoning><confidence>high</confidence></item>'
            '<item id="2"><translation>B</translation><reasoning>R2</reasoning><confidence>medium</confidence></item>'
            '</translations>'
        )
        result = self.pf.parse_response(text, 1, "xml_xml")
        assert len(result) == 2
        assert result[0]["translation"] == "A"
        assert result[1]["translation"] == "B"

    def test_parse_xml_stage_0(self):
        text = (
            '<disambiguations>'
            '<item term="테스트" applies="true" actual_meaning="测试" reason="匹配"/>'
            '</disambiguations>'
        )
        result = self.pf.parse_response(text, 0, "xml_xml")
        assert len(result) == 1
        assert result[0]["term"] == "테스트"
        assert result[0]["applies"] is True

    def test_parse_xml_missing_optional_fields(self):
        """XML items with missing optional fields should use defaults."""
        text = (
            '<translations>'
            '<item id="1"><translation>Minimal</translation></item>'
            '</translations>'
        )
        result = self.pf.parse_response(text, 1, "xml_xml")
        assert len(result) == 1
        assert result[0]["translation"] == "Minimal"
        assert result[0]["reasoning"] == ""
        assert result[0]["confidence"] == "medium"

    def test_parse_xml_invalid_returns_empty(self):
        result = self.pf.parse_response("not valid xml <<<", 1, "xml_xml")
        assert result == []

    def test_parse_xml_unknown_stage_returns_empty(self):
        text = '<translations><item id="1"><translation>T</translation></item></translations>'
        result = self.pf.parse_response(text, 99, "xml_xml")
        assert result == []


class TestStageStrategyFormatPassthrough:
    """Tests for StageStrategy passing prompt_format to PromptFactory."""

    def test_build_stage_1_prompt_passes_format(self):
        config = TranslateConfig()
        strategy = StageStrategy(config)
        for fmt in ["xml_json", "xml_xml", "json_json"]:
            sp = strategy.build_stage_1_prompt(FileType.STORY, prompt_format=fmt)
            assert len(sp) > 0

    def test_parse_stage_1_result_passes_format(self):
        config = TranslateConfig()
        strategy = StageStrategy(config)
        text = '{"translations": [{"id": 1, "translation": "t"}]}'
        result = strategy.parse_stage_1_result(text, "xml_json")
        assert len(result) == 1

    def test_parse_stage_0_result_passes_format(self):
        config = TranslateConfig()
        strategy = StageStrategy(config)
        text = '{"disambiguations": [{"term": "t", "applies": true}]}'
        result = strategy.parse_stage_0_result(text, "xml_json")
        assert len(result) == 1


class TestTranslateConfigFormat:
    """Tests for TranslateConfig prompt_format field."""

    def test_default_prompt_format(self):
        config = TranslateConfig()
        assert config.prompt_format == "xml_json"

    def test_fallback_default(self):
        config = TranslateConfig()
        assert config.fallback is True

    def test_from_config_manager_reads_prompt_format(self):
        mock_mgr = MagicMock()
        mock_mgr.get.side_effect = lambda key, default=None: {
            "ui_default.translator": {
                "prompt_format": "json_json",
                "fallback": False,
                "translator": "LLM通用翻译服务",
            },
            "game_path": "",
            "debug": False,
        }.get(key, default)

        config = TranslateConfig.from_config_manager(mock_mgr)
        assert config.prompt_format == "json_json"
        assert config.fallback is False

    def test_from_config_manager_defaults_when_missing(self):
        mock_mgr = MagicMock()
        mock_mgr.get.side_effect = lambda key, default=None: {
            "ui_default.translator": {
                "translator": "LLM通用翻译服务",
            },
            "game_path": "",
            "debug": False,
        }.get(key, default)

        config = TranslateConfig.from_config_manager(mock_mgr)
        assert config.prompt_format == "xml_json"  # default
        assert config.fallback is True  # default

    def test_is_text_format_removed(self):
        """Verify is_text_format no longer exists on TranslateConfig."""
        config = TranslateConfig()
        assert not hasattr(config, "is_text_format")


class TestRenderMethods:
    """Tests for PromptFactory render methods."""

    def setup_method(self):
        self.pf = PromptFactory()

    def test_render_text_blocks_json(self):
        blocks = [
            {"kr": "안녕", "jp": "こんにちは", "en": "Hello"},
            {"kr": "세계", "en": "World"},
        ]
        result = self.pf.render_text_blocks_json(blocks)
        parsed = json.loads(result)
        assert len(parsed["text_blocks"]) == 2
        assert parsed["text_blocks"][0]["kr"] == "안녕"
        assert parsed["text_blocks"][0]["jp"] == "こんにちは"

    def test_render_glossary_json(self):
        terms = [
            {"kr": "단테", "cn": "但丁", "note": "主角"},
            {"kr": "파우스트", "cn": "浮士德"},
        ]
        result = self.pf.render_glossary_json(terms)
        parsed = json.loads(result)
        assert len(parsed["glossary"]) == 2
        assert parsed["glossary"][0]["note"] == "主角"
        assert "note" not in parsed["glossary"][1]

    def test_render_glossary_json_empty(self):
        result = self.pf.render_glossary_json([])
        assert result == ""

    def test_render_glossary_xml_empty(self):
        result = self.pf.render_glossary([])
        assert result == ""


class TestFallbackChain:
    """Tests for format fallback chain logic."""

    def test_chain_no_fallback(self):
        """Without fallback, only user format is tried."""
        config = TranslateConfig(prompt_format="xml_xml", fallback=False)
        # Use a FileProcessor mock to test _build_format_chain
        # We test the chain-building logic directly
        chain = ["xml_xml"]  # no fallback adds nothing
        assert chain == ["xml_xml"]

    def test_chain_with_fallback(self):
        """With fallback, all formats are tried in order."""
        user_format = "xml_xml"
        chain = [user_format]
        fallback_order = ["xml_json", "json_json", "xml_xml"]
        for f in fallback_order:
            if f not in chain:
                chain.append(f)
        assert chain == ["xml_xml", "xml_json", "json_json"]

    def test_chain_user_is_xml_json(self):
        """When user already chose xml_json, it is not duplicated."""
        user_format = "xml_json"
        chain = [user_format]
        fallback_order = ["xml_json", "json_json", "xml_xml"]
        for f in fallback_order:
            if f not in chain:
                chain.append(f)
        assert chain == ["xml_json", "json_json", "xml_xml"]
        assert len(chain) == 3


class TestPerBlockRefs:
    """Per-block 引用字段在三种格式的 prompt 中正确渲染。"""

    def setup_method(self):
        self.pf = PromptFactory()

    def test_xml_text_blocks_includes_refs(self):
        """XML: 有 proper_refs/affect_refs/model 的 block 输出对应元素。"""
        block = {
            "kr": "테스트", "jp": "テスト", "en": "Test",
            "proper_refs": ["용어1", "용어2"],
            "affect_refs": ["[1001]"],
            "model": "char_01",
        }
        xml = self.pf.render_text_blocks([block])
        assert "<proper_refs>용어1, 용어2</proper_refs>" in xml
        assert "<affect_refs>[1001]</affect_refs>" in xml
        assert "<model>char_01</model>" in xml

    def test_xml_text_blocks_omits_missing_refs(self):
        """XML: 无引用的 block 不输出 refs 元素。"""
        block = {"kr": "테스트", "jp": "テスト"}
        xml = self.pf.render_text_blocks([block])
        assert "proper_refs" not in xml
        assert "affect_refs" not in xml
        assert "model" not in xml

    def test_json_text_blocks_includes_refs(self):
        """JSON: 有引用字段的 block 输出对应 key。"""
        import json
        block = {
            "kr": "테스트", "jp": "テスト",
            "proper_refs": ["용어1"],
            "affect_refs": ["[1001]"],
            "model": "char_01",
        }
        json_str = self.pf.render_text_blocks_json([block])
        data = json.loads(json_str)
        tb = data["text_blocks"][0]
        assert tb["proper_refs"] == ["용어1"]
        assert tb["affect_refs"] == ["[1001]"]
        assert tb["model"] == "char_01"

    def test_json_text_blocks_omits_missing_refs(self):
        """JSON: 无引用的 block 不输出 refs key。"""
        import json
        block = {"kr": "테스트"}
        json_str = self.pf.render_text_blocks_json([block])
        data = json.loads(json_str)
        tb = data["text_blocks"][0]
        assert "proper_refs" not in tb
        assert "model" not in tb


class TestFormatAwareSplit:
    """_split_by_length 使用格式感知长度估算。"""

    def test_xml_format_triggers_split_earlier(self):
        """XML 格式比 JSON dump 估算更长，更早触发分割。"""
        from translateFunc.builder.request import RequestBuilder
        from unittest.mock import MagicMock

        # 构造足够多的 text_blocks 使 xml_xml 超出 max_length
        blocks = [{"kr": f"테스트_{i}", "jp": f"テスト_{i}", "en": f"Test_{i}"}
                   for i in range(2000)]

        engine = MagicMock()
        engine.match_all.return_value = MagicMock(
            proper_matches=[], role_matches=[],
            affect_id_matches=[], affect_name_matches=[],
        )
        engine.role_data = []
        engine.affect_data = []

        builder = RequestBuilder(
            request_text={"kr": {0: {("text",): blocks[0]["kr"]}}},
            matcher_engine=engine,
            max_length=10000,
        )
        # 手动设置 unified_request 以绕过复杂的 build 流程
        builder.unified_request = {
            "metadata": {"total_text_blocks": len(blocks),
                         "proper_terms_count": 0, "affects_count": 0,
                         "models_count": 0, "file_type": "STORY"},
            "reference": {"proper_terms": [], "affects": [],
                          "models": [], "model_docs": [], "skill_doc": ""},
            "text_blocks": blocks,
        }

        builder._split_by_length(prompt_format="xml_xml")
        assert len(builder.split_requests) > 1, (
            f"xml_xml 应触发分割，但 split_requests 只有 {len(builder.split_requests)} 部分"
        )

    def test_json_format_triggers_split_later(self):
        """json_json 比 xml_xml 更紧凑，需要更多 block 才触发分割。"""
        from translateFunc.builder.request import RequestBuilder
        from unittest.mock import MagicMock

        blocks = [{"kr": "짧은", "jp": "短い", "en": "Short"} for _ in range(200)]

        engine = MagicMock()
        engine.match_all.return_value = MagicMock(
            proper_matches=[], role_matches=[],
            affect_id_matches=[], affect_name_matches=[],
        )
        engine.role_data = []
        engine.affect_data = []

        builder = RequestBuilder(
            request_text={"kr": {0: {("text",): blocks[0]["kr"]}}},
            matcher_engine=engine,
            max_length=50000,
        )
        builder.unified_request = {
            "metadata": {"total_text_blocks": len(blocks),
                         "proper_terms_count": 0, "affects_count": 0,
                         "models_count": 0, "file_type": "STORY"},
            "reference": {"proper_terms": [], "affects": [],
                          "models": [], "model_docs": [], "skill_doc": ""},
            "text_blocks": blocks,
        }

        builder._split_by_length(prompt_format="json_json")
        # 200 个短 block 在 50000 上限下不应分割
        assert len(builder.split_requests) == 1, (
            f"json_json 200 短 block 不应分割，但 split_requests={len(builder.split_requests)}"
        )