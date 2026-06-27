"""extract_contexts 批量扫描对比测试。使用 tests/example 真实数据。"""
import json
from pathlib import Path
import pytest
from translateFunc.proper.analyze import extract_contexts, extract_contexts_batch
from translateFunc.matcher.ac_automaton import AcAutomaton

EXAMPLE_DIR = Path(__file__).parent / "example"
KR_PATH = EXAMPLE_DIR / "LocalizeTemp_kr"
JP_PATH = EXAMPLE_DIR / "LocalizeTemp_jp"
EN_PATH = EXAMPLE_DIR / "LocalizeTemp_en"


class TestExtractContextsBatch:
    """extract_contexts_batch 正确性测试。"""

    @pytest.fixture(autouse=True)
    def _require_example_data(self):
        if not KR_PATH.exists():
            pytest.skip("tests/example 数据不存在")

    def test_batch_returns_known_terms(self):
        """已知的韩文术语应在批量扫描中被找到。"""
        terms = ["분노", "색욕", "나태"]  # 来自 KR_AttributeText.json
        results = extract_contexts_batch(terms, KR_PATH, JP_PATH, EN_PATH, max_examples=20)
        assert len(results) > 0
        # 至少某个术语被匹配到
        matched = sum(1 for v in results.values() if v)
        assert matched > 0

    def test_batch_empty_terms_returns_empty(self):
        """空术语列表返回空字典。"""
        results = extract_contexts_batch([], KR_PATH, JP_PATH, EN_PATH)
        assert results == {}

    def test_batch_respects_max_examples(self):
        """max_examples 限制每个术语的上下文条数。"""
        # 使用一个常见术语（可能出现很多次）
        results = extract_contexts_batch(["분노"], KR_PATH, JP_PATH, EN_PATH, max_examples=3)
        for term, contexts in results.items():
            assert len(contexts) <= 3

    def test_batch_and_single_equivalent(self):
        """batch 模式与逐个 extract_contexts 结果一致。"""
        terms = ["분노", "나태", "탐식"]
        batch_results = extract_contexts_batch(terms, KR_PATH, JP_PATH, EN_PATH, max_examples=5)
        individual_results = {}
        for term in terms:
            individual_results[term] = extract_contexts(
                term, KR_PATH, JP_PATH, EN_PATH, max_examples=5
            )
        # 每个术语的命中数应一致
        for term in terms:
            assert len(batch_results.get(term, [])) == len(individual_results.get(term, []))

    def test_batch_nonexistent_term_returns_empty(self):
        """不存在的术语返回空列表。"""
        results = extract_contexts_batch(["不存在的术语XYZ123"], KR_PATH, JP_PATH, EN_PATH)
        assert results.get("不存在的术语XYZ123", []) == []


class TestAcAutomatonBatchMatching:
    """AC 自动机在批量上下文提取中的行为测试。"""

    def test_build_with_unicode_terms(self):
        """韩文术语正确构建 AC 自动机。"""
        terms = ["이상", "파우스트", "돈키호테"]
        ac = AcAutomaton()
        for t in terms:
            ac.add_pattern(t)
        ac.build()
        hits = ac.search("파우스트는 조용히 있었다")
        assert len(hits) == 1
        assert hits[0].pattern == "파우스트"

    def test_overlapping_korean_terms(self):
        """重叠韩文术语匹配。"""
        terms = ["이상", "이상하다"]
        ac = AcAutomaton()
        for t in terms:
            ac.add_pattern(t)
        ac.build()
        hits = ac.search("이상한 나라의 이상")
        patterns = {h.pattern for h in hits}
        assert "이상" in patterns
        assert "이상하다" not in patterns  # '이상한' ≠ '이상하다'
