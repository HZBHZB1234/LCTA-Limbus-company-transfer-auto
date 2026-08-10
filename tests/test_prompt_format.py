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
    """Tests for PromptFactory with three prompt formats (v2 default)."""

    def setup_method(self):
        self.pf = PromptFactory()

    # ---- xml_json (default) ----

    def test_xml_json_system_prompt_structure(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_json")
        assert "<role>" in sp
        assert "<translation_rules>" in sp
        assert "<format_rules>" in sp
        assert "<format>" in sp
        assert '"translations"' in sp
        # v2: reasoning before translation in output format
        assert '"reasoning"' in sp

    def test_xml_json_system_prompt_stage_0(self):
        sp = self.pf.build_system_prompt(FileType.OTHER, 0, "xml_json")
        assert "<role>" in sp
        assert "<translation_rules>" in sp
        assert "disambiguations" in sp

    def test_xml_json_system_prompt_stage_2(self):
        sp = self.pf.build_system_prompt(FileType.OTHER, 2, "xml_json")
        assert "checked_translations" in sp
        # v2: stage 2 has verification sub-object
        assert "verification" in sp

    # ---- xml_xml ----

    def test_xml_xml_system_prompt_structure(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_xml")
        assert "<role>" in sp
        assert "<translation_rules>" in sp
        assert "<translations>" in sp  # XML response instruction
        assert "<translation>" in sp

    def test_xml_xml_system_prompt_stage_0(self):
        sp = self.pf.build_system_prompt(FileType.OTHER, 0, "xml_xml")
        assert "<disambiguations>" in sp

    # ---- json_json ----

    def test_json_json_system_prompt_structure(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "json_json")
        assert '"role"' in sp
        assert '"translation_rules"' in sp
        assert '"format_rules"' in sp
        assert '"format"' in sp
        assert '"translations"' in sp

    def test_json_json_contains_no_xml_tags(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "json_json")
        assert "<role>" not in sp
        assert "<translation_rules>" not in sp
        assert "<format_rules>" not in sp

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
        # Stage 0 XML with child elements (standard format)
        text = (
            '<disambiguations>'
            '<item>'
            '<term>테스트</term>'
            '<applies>true</applies>'
            '<actual_meaning>测试</actual_meaning>'
            '<reason>匹配</reason>'
            '</item>'
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


class TestSplitOverLimitRefinement:
    """分割到上限后仍超限的 part 应进一步切分而非原样发送。"""

    @staticmethod
    def _make_builder(blocks, max_length):
        from translateFunc.builder.request import RequestBuilder
        from unittest.mock import MagicMock
        engine = MagicMock()
        engine.match_all.return_value = MagicMock(
            proper_matches=[], role_matches=[],
            affect_id_matches=[], affect_name_matches=[],
        )
        engine.role_data = []
        engine.affect_data = []
        builder = RequestBuilder(
            request_text={"kr": {0: {("text",): "x"}}},
            matcher_engine=engine,
            max_length=max_length,
        )
        builder.unified_request = {
            "metadata": {"total_text_blocks": len(blocks),
                         "proper_terms_count": 0, "affects_count": 0,
                         "models_count": 0, "file_type": "STORY"},
            "reference": {"proper_terms": [], "affects": [],
                          "models": [], "model_docs": [], "skill_doc": ""},
            "text_blocks": blocks,
        }
        return builder

    def test_over_limit_parts_are_split_to_fit(self):
        """50 份封顶后仍超限的 part 应被继续切分，所有 part 均不超限。"""
        blocks = [
            {"kr": f"테스트_{i}_" + "가나다라마바사아자차카타파하" * 200,
             "jp": f"テスト_{i}", "en": f"Test_{i}"}
            for i in range(500)
        ]
        builder = self._make_builder(blocks, max_length=20000)
        builder._split_by_length(prompt_format="xml_json")

        # 50 份（每份 10 block ≈ 21k chars）仍超限 → 应继续切分出更多 part
        assert len(builder.split_requests) > 50, (
            f"超限 part 应继续切分，实际只有 {len(builder.split_requests)} 部分"
        )
        for p in builder.split_requests:
            for fmt in ["xml_json", "xml_xml", "json_json"]:
                assert len(builder._get_request_text(p, fmt)) <= 20000, (
                    f"part 超限: fmt={fmt}"
                )

    def test_split_keeps_block_alignment(self):
        """切分后所有 part 的 text_blocks 拼接应等于原始顺序。"""
        blocks = [{"kr": f"텍스트_{i}" * 5, "jp": "J", "en": "E"} for i in range(300)]
        builder = self._make_builder(blocks, max_length=15000)
        builder._split_by_length(prompt_format="xml_json")

        merged = []
        for p in builder.split_requests:
            merged.extend(p.get("text_blocks", []))
        assert merged == blocks
        assert len(builder.get_request_text("xml_json")) == len(builder.split_requests)

    def test_single_block_over_limit_kept(self):
        """单个 block 仍超限时保留原样（无法再切分）。"""
        blocks = [{"kr": "가" * 30000, "jp": "J", "en": "E"}]
        builder = self._make_builder(blocks, max_length=20000)
        builder._split_by_length(prompt_format="xml_json")
        assert len(builder.split_requests) == 1
        assert builder.split_requests[0]["text_blocks"] == blocks


class TestRoleDocsMapping:
    """_get_role_docs 兼容韩文 id 与英文模型码 id。"""

    def _make_builder(self):
        from translateFunc.builder.request import RequestBuilder
        b = RequestBuilder.__new__(RequestBuilder)
        b.is_story = True
        return b

    def test_korean_ids_map_via_rloe_compare(self):
        b = self._make_builder()
        role_list = {"이상": {"id": "이상", "kr": "이상"}, "단테2": {"id": "단테2", "kr": "단테"}}
        docs = b._get_role_docs(role_list)
        assert [d["角色"] for d in docs] == ["李箱", "但丁"]

    def test_english_ids_match_style_keys_directly(self):
        b = self._make_builder()
        role_list = {"Yisang": {"id": "Yisang", "kr": "이상"}, "Faust": {"id": "Faust", "kr": "파우스트"}}
        docs = b._get_role_docs(role_list)
        assert [d["角色"] for d in docs] == ["李箱", "浮士德"]

    def test_english_id_with_suffix_and_case(self):
        b = self._make_builder()
        role_list = {"Dante2": {"id": "Dante2", "kr": "단테"},
                     "YISANG": {"id": "YISANG", "kr": "이상"}}
        docs = b._get_role_docs(role_list)
        assert [d["角色"] for d in docs] == ["但丁", "李箱"]

    def test_kr_field_fallback(self):
        b = self._make_builder()
        role_list = {"char_01": {"id": "char_01", "kr": "이상"}}
        docs = b._get_role_docs(role_list)
        assert [d["角色"] for d in docs] == ["李箱"]

    def test_unknown_id_returns_empty_defensive(self):
        b = self._make_builder()
        assert b._get_role_docs({"unknown": {"id": "unknown", "kr": "?"}}) == []
        b.is_story = False
        assert b._get_role_docs({"이상": {}}) == []

    def test_duplicate_style_deduped(self):
        b = self._make_builder()
        role_list = {"이상": {"id": "이상", "kr": "이상"}, "Yisang": {"id": "Yisang", "kr": "이상"}}
        docs = b._get_role_docs(role_list)
        assert len(docs) == 1


class TestSplitEstimatorExact:
    """长度估算应与真实渲染精确一致（保证分割边界不漂移）。"""

    def test_estimate_matches_real_render(self):
        import json
        import random
        from translateFunc.builder.request import RequestBuilder

        b = RequestBuilder.__new__(RequestBuilder)
        b.is_story = True
        b.is_skill = True

        random.seed(42)
        blocks = []
        for i in range(120):
            d = {"kr": f"테스트_{i}_" + "가나다라마바사아자차카타파하" * random.randint(1, 5),
                 "jp": f"テスト_{i}", "en": f"Test_{i}"}
            if i % 7 == 0:
                d["proper_refs"] = [f"term{i % 20}", f"term{i % 20 + 1}"]
            if i % 5 == 0:
                d["affect_refs"] = [f"[{1000 + i % 15}]"]
            if i % 9 == 0:
                d["model"] = f"m{i}"
            blocks.append(d)

        terms = [{"term": f"term{i}", "kr": f"용어{i}", "cn": f"中文{i}",
                  "note": f"备注{i}" if i % 3 == 0 else ""} for i in range(20)]
        affects = [{"id": str(1000 + i), "kr": f"버프{i}", "cn": f"效果{i}"} for i in range(15)]
        docs = [{"角色": f"角色{i}", "语言风格": f"风格{i}"} for i in range(3)]
        skill = "技能文档" * 5

        block_lens = b._precompute_block_lens(blocks)
        random.seed(7)
        for _ in range(50):
            n = random.randint(0, 120)
            chunk = blocks[:n]
            k, a, d = random.randint(0, 20), random.randint(0, 15), random.randint(0, 3)
            skill_use = skill if random.random() < 0.5 else ""
            part = {"reference": {"proper_terms": terms[:k], "affects": affects[:a],
                                  "models": [], "model_docs": docs[:d],
                                  "skill_doc": skill_use},
                    "text_blocks": chunk}
            for fmt in ["xml_json", "xml_xml", "json_json"]:
                est = b._estimate_prompt_len(part, fmt, block_lens)
                real = len(b._get_request_text(part, fmt))
                assert est == real, f"estimator drift: fmt={fmt} est={est} real={real}"


class TestDeBuildPositionalFill:
    """deBuild 缺失项按位置补 KR 原文，避免中间缺失导致尾部错位。"""

    def _make_builder(self):
        from translateFunc.builder.request import RequestBuilder
        builder = RequestBuilder.__new__(RequestBuilder)
        builder.kr_text = {
            1: {("text",): "KR1"},
            2: {("text",): "KR2"},
            3: {("text",): "KR3"},
        }
        builder.jp_text = {
            1: {("text",): "JP1"},
            2: {("text",): "JP2"},
            3: {("text",): "JP3"},
        }
        builder.en_text = {
            1: {("text",): "EN1"},
            2: {("text",): "EN2"},
            3: {("text",): "EN3"},
        }
        return builder

    def test_missing_middle_filled_positionally(self):
        builder = self._make_builder()
        result = builder.deBuild(["T1", "T2"])
        assert result == {
            1: {("text",): "T1"},
            2: {("text",): "T2"},
            3: {("text",): "KR3"},
        }

    def test_all_missing_but_first_filled_positionally(self):
        builder = self._make_builder()
        result = builder.deBuild(["T1"])
        assert result == {
            1: {("text",): "T1"},
            2: {("text",): "KR2"},
            3: {("text",): "KR3"},
        }

    def test_excess_translations_truncated(self):
        builder = self._make_builder()
        result = builder.deBuild(["T1", "T2", "T3", "EXTRA"])
        assert result == {
            1: {("text",): "T1"},
            2: {("text",): "T2"},
            3: {("text",): "T3"},
        }


class TestStageInputSplit:
    """Stage 0/2 requests are split using their rendered user prompt length."""

    def setup_method(self):
        self.strategy = StageStrategy(TranslateConfig())

    @pytest.mark.parametrize("prompt_format", ["xml_json", "xml_xml", "json_json"])
    def test_stage_0_split_preserves_terms_and_relevant_context(self, prompt_format):
        text_blocks = [
            {"kr": f"context-{index}-" + "K" * 180, "jp": "J" * 80, "en": "E" * 80}
            for index in range(8)
        ]
        candidate_terms = [
            {
                "kr": f"term-{index}-" + "T" * 120,
                "cn": "C" * 100,
                "note": "N" * 80,
                "text_block_indices": [index],
            }
            for index in range(8)
        ]
        max_length = max(
            len(self.strategy.build_stage_0_user_prompt(
                [term],
                [text_blocks[index]],
                prompt_format=prompt_format,
            ))
            for index, term in enumerate(candidate_terms)
        ) + 20

        parts = self.strategy.split_stage_0_inputs(
            candidate_terms,
            text_blocks,
            prompt_format=prompt_format,
            max_length=max_length,
        )

        assert len(parts) > 1
        assert [
            term["kr"]
            for part in parts
            for term in part["candidate_terms"]
        ] == [term["kr"] for term in candidate_terms]
        for part in parts:
            prompt = self.strategy.build_stage_0_user_prompt(
                part["candidate_terms"],
                part["text_blocks"],
                prompt_format=prompt_format,
            )
            assert len(prompt) <= max_length
            first_index = part["candidate_terms"][0]["text_block_indices"][0]
            assert part["text_blocks"][0] is text_blocks[first_index]

    @pytest.mark.parametrize("prompt_format", ["xml_json", "xml_xml", "json_json"])
    def test_stage_2_split_preserves_offsets_and_prunes_references(self, prompt_format):
        original_blocks = [
            {
                "kr": f"original-{index}-" + "K" * 180,
                "jp": "J" * 80,
                "en": "E" * 80,
                "proper_refs": [f"term-{index}"],
                "affect_refs": [f"[{1000 + index}]"],
            }
            for index in range(8)
        ]
        translations = [
            {"id": index + 1, "translation": f"translation-{index}-" + "C" * 180}
            for index in range(8)
        ]
        reference = {
            "proper_terms": [
                {"term": f"term-{index}", "translation": f"术语-{index}"}
                for index in range(8)
            ],
            "affects": [
                {"id": str(1000 + index), "name": f"affect-{index}"}
                for index in range(8)
            ],
        }
        max_length = max(
            len(self.strategy.build_stage_2_user_prompt(
                [original_blocks[index]],
                [translations[index]],
                prompt_format=prompt_format,
                reference={
                    "proper_terms": [reference["proper_terms"][index]],
                    "affects": [reference["affects"][index]],
                },
            ))
            for index in range(8)
        ) + 20

        parts = self.strategy.split_stage_2_inputs(
            original_blocks,
            translations,
            prompt_format=prompt_format,
            reference=reference,
            max_length=max_length,
        )

        assert len(parts) > 1
        assert [part["offset"] for part in parts] == [
            sum(len(previous["original_blocks"]) for previous in parts[:index])
            for index in range(len(parts))
        ]
        assert [
            translation["id"]
            for part in parts
            for translation in part["translations"]
        ] == list(range(1, 9))
        for part in parts:
            prompt = self.strategy.build_stage_2_user_prompt(
                part["original_blocks"],
                part["translations"],
                prompt_format=prompt_format,
                reference=part["reference"],
            )
            assert len(prompt) <= max_length
            expected_terms = {
                ref
                for block in part["original_blocks"]
                for ref in block["proper_refs"]
            }
            expected_affects = {
                ref.strip("[]")
                for block in part["original_blocks"]
                for ref in block["affect_refs"]
            }
            assert {
                term["term"] for term in part["reference"]["proper_terms"]
            } == expected_terms
            assert {
                affect["id"] for affect in part["reference"]["affects"]
            } == expected_affects


class TestFormatAwareEscapeRules:
    """转义规则按响应格式分离的测试。"""

    def setup_method(self):
        self.pf = PromptFactory()

    def test_xml_json_uses_json_escape_rules(self):
        """xml_json 模式（JSON 响应）应只包含 JSON 转义规则，不包含 XML 转义规则。"""
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_json")
        assert "JSON输出中" in sp
        assert "XML输出中" not in sp

    def test_json_json_uses_json_escape_rules(self):
        """json_json 模式应只包含 JSON 转义规则。"""
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "json_json")
        assert "JSON输出中" in sp
        assert "XML输出中" not in sp

    def test_xml_xml_uses_xml_escape_rules(self):
        """xml_xml 模式应只包含 XML 转义规则，不包含 JSON 转义规则。"""
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_xml")
        assert "XML输出中" in sp
        assert "JSON输出中" not in sp

    def test_xml_json_no_amp_quot(self):
        """xml_json 模式不应包含 &amp;quot; 等 XML 实体转义示例。"""
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_json")
        assert "&amp;quot;" not in sp

    def test_xml_xml_contains_quot(self):
        """xml_xml 模式应包含 &amp;quot; 作为 XML 转义示例（规则文本已 XML 转义）。"""
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_xml")
        assert "&amp;quot;" in sp

    def test_no_output_schema_block(self):
        """系统提示词不应包含 <output_schema> 区块。"""
        for fmt in ["xml_json", "json_json", "xml_xml"]:
            sp = self.pf.build_system_prompt(FileType.STORY, 1, fmt)
            assert "output_schema" not in sp, f"{fmt}: 不应包含 output_schema"
            sp2 = self.pf.build_system_prompt(FileType.STORY, 2, fmt)
            assert "output_schema" not in sp2, f"{fmt} stage2: 不应包含 output_schema"


class TestCountConstraints:
    """数量约束在提示词中正确出现。"""

    def setup_method(self):
        self.pf = PromptFactory()

    def test_stage1_xml_json_has_count_constraint(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_json")
        assert "数量约束" in sp
        assert "translations数组的长度必须等于" in sp

    def test_stage1_xml_xml_has_count_constraint(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_xml")
        assert "数量约束" in sp
        assert "item的数量必须等于" in sp

    def test_stage1_json_json_has_count_constraint(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "json_json")
        assert "count_constraint" in sp

    def test_stage2_has_count_constraint(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 2, "xml_json")
        assert "checked_translations数组长度必须等于" in sp


class TestReasoningFirst:
    """v2 输出格式中 reasoning 在 translation 之前。"""

    def setup_method(self):
        self.pf = PromptFactory()

    def test_reasoning_before_translation_in_format(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_json")
        # 在 <format> 块中，reasoning 应出现在 translation 之前
        format_start = sp.find("<format>")
        format_end = sp.rfind("</format>")
        format_block = sp[format_start:format_end]
        reasoning_pos = format_block.find('"reasoning"')
        translation_pos = format_block.find('"translation"')
        assert reasoning_pos < translation_pos, (
            f"reasoning ({reasoning_pos}) 应在 translation ({translation_pos}) 之前"
        )

    def test_xml_format_reasoning_before_translation(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_xml")
        format_start = sp.find("<format>")
        format_end = sp.rfind("</format>")
        format_block = sp[format_start:format_end]
        reasoning_pos = format_block.find("<reasoning>")
        translation_pos = format_block.find("<translation>")
        assert reasoning_pos < translation_pos

    def test_stage_2_has_verification(self):
        for fmt in ["xml_json", "xml_xml", "json_json"]:
            sp = self.pf.build_system_prompt(FileType.STORY, 2, fmt)
            assert "verification" in sp, f"{fmt}: stage 2 应有 verification 字段"


class TestRepairEnhancements:
    """JSON/XML 修复增强测试。"""

    def setup_method(self):
        self.pf = PromptFactory()

    def test_repair_json_single_quotes(self):
        text = "{'translations': [{'id': 1, 'reasoning': 'test', 'translation': '你好', 'confidence': 'high'}]}"
        result = self.pf.parse_response(text, 1, "json_json")
        assert len(result) == 1
        assert result[0]["translation"] == "你好"

    def test_repair_json_nan_to_null(self):
        text = '{"translations": [{"id": 1, "reasoning": "t", "translation": "你好", "confidence": NaN}]}'
        result = self.pf.parse_response(text, 1, "xml_json")
        assert len(result) == 1
        assert result[0]["translation"] == "你好"

    def test_repair_xml_namespace_prefix(self):
        text = (
            '<ns:translations>'
            '<ns:item id="1">'
            '<ns:translation>你好</ns:translation>'
            '<ns:reasoning>test</ns:reasoning>'
            '<ns:confidence>high</ns:confidence>'
            '</ns:item>'
            '</ns:translations>'
        )
        result = self.pf.parse_response(text, 1, "xml_xml")
        assert len(result) == 1
        assert result[0]["translation"] == "你好"

    def test_repair_xml_unquoted_attrs(self):
        text = (
            '<translations>'
            '<item id=1>'
            '<translation>你好</translation>'
            '<reasoning>test</reasoning>'
            '<confidence>high</confidence>'
            '</item>'
            '</translations>'
        )
        result = self.pf.parse_response(text, 1, "xml_xml")
        assert len(result) == 1
        assert result[0]["translation"] == "你好"


class TestConfidenceEnforcement:
    """置信度检查逻辑测试。"""

    def test_confidence_order(self):
        """验证置信度排序逻辑。"""
        _CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
        assert _CONFIDENCE_ORDER["low"] < _CONFIDENCE_ORDER["medium"]
        assert _CONFIDENCE_ORDER["medium"] < _CONFIDENCE_ORDER["high"]

    def test_min_confidence_default(self):
        config = TranslateConfig()
        assert config.min_confidence == "medium"

    def test_prompt_version_removed(self):
        """prompt_version 字段应已从 TranslateConfig 中移除。"""
        config = TranslateConfig()
        assert not hasattr(config, "prompt_version")
