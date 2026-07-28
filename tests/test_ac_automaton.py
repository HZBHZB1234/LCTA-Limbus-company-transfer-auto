"""AC 自动机单元测试 —— 纯算法测试，零外部依赖。"""
import pytest
from translateFunc.matcher.ac_automaton import AcAutomaton, ACPattern
from translateFunc.matcher.engine import MatcherEngine


class TestAcAutomaton:
    """Aho-Corasick 自动机单元测试。"""

    def test_empty_automaton(self):
        """空自动机：未添加任何模式时，搜索应返回空列表。"""
        ac = AcAutomaton()
        ac.build()
        assert ac.search("hello") == []
        assert ac.search_batch(["a", "b"]) == [[], []]

    def test_single_pattern(self):
        """单一模式匹配。"""
        ac = AcAutomaton()
        ac.add_pattern("hello")
        ac.build()
        hits = ac.search("hello world")
        assert len(hits) == 1
        assert hits[0].pattern == "hello"

    def test_multiple_patterns(self):
        """多模式匹配。"""
        ac = AcAutomaton()
        ac.add_pattern("he")
        ac.add_pattern("she")
        ac.add_pattern("his")
        ac.add_pattern("hers")
        ac.build()
        hits = ac.search("ushers")
        patterns = {h.pattern for h in hits}
        assert patterns == {"he", "she", "hers"}

    def test_overlapping_patterns(self):
        """重叠模式：'aaa' 中包含 3 个 'a' 和 2 个 'aa'。"""
        ac = AcAutomaton()
        ac.add_pattern("a")
        ac.add_pattern("aa")
        ac.build()
        hits = ac.search("aaa")
        # 3 个单 'a' + 2 个 'aa'
        assert len(hits) == 5

    def test_no_match(self):
        """不存在的模式应返回空结果。"""
        ac = AcAutomaton()
        ac.add_pattern("xyz")
        ac.build()
        assert ac.search("abcdef") == []

    def test_unicode_patterns(self):
        """Unicode（韩文）模式匹配。"""
        ac = AcAutomaton()
        ac.add_pattern("이상")
        ac.add_pattern("이상하다")
        ac.build()
        hits = ac.search("이상한 나라의 이상")
        patterns = {h.pattern for h in hits}
        assert "이상" in patterns
        # '이상한' != '이상하다'，因此不应匹配
        assert "이상하다" not in patterns

    def test_pattern_with_data(self):
        """带附加数据的模式匹配。"""
        ac = AcAutomaton()
        ac.add_pattern("test", data={"id": 1, "cn": "测试"})
        ac.build()
        hits = ac.search("this is a test case")
        assert len(hits) == 1
        assert hits[0].data == {"id": 1, "cn": "测试"}

    def test_batch_search(self):
        """批量搜索。"""
        ac = AcAutomaton()
        ac.add_pattern("foo")
        ac.add_pattern("bar")
        ac.build()
        results = ac.search_batch(["foo bar", "nothing", "bar only"])
        assert len(results[0]) == 2
        assert len(results[1]) == 0
        assert len(results[2]) == 1

    def test_add_after_build_raises(self):
        """build() 之后再次 add_pattern() 应抛出 RuntimeError。"""
        ac = AcAutomaton()
        ac.add_pattern("test")
        ac.build()
        with pytest.raises(RuntimeError, match="不能在 build"):
            ac.add_pattern("another")

    def test_search_before_build_raises(self):
        """build() 之前调用 search() 应抛出 RuntimeError。"""
        ac = AcAutomaton()
        ac.add_pattern("test")
        with pytest.raises(RuntimeError, match="必须在 search"):
            ac.search("test")

    def test_empty_pattern_ignored(self):
        """空字符串模式应被忽略。"""
        ac = AcAutomaton()
        ac.add_pattern("")
        ac.add_pattern("valid")
        ac.build()
        assert ac.search("valid test")[0].pattern == "valid"

    def test_pattern_count(self):
        """pattern_count 属性应正确反映已添加的模式数量。"""
        ac = AcAutomaton()
        ac.add_pattern("a")
        ac.add_pattern("b")
        ac.add_pattern("c")
        assert ac.pattern_count == 3
        ac.build()
        assert ac.pattern_count == 3


class TestMultilingualAffectMatching:
    """状态效果韩文名称匹配需要 JP/EN 翻译交叉确认。"""

    @staticmethod
    def _build_engine() -> MatcherEngine:
        engine = MatcherEngine()
        engine.build_proper([])
        engine.build_affects([{
            "id": "Charge",
            "kr": "충전",
            "jp": "充電",
            "en": "Charge",
            "cn": "充能",
            "desc": "",
        }])
        return engine

    def test_korean_substring_without_jp_en_support_is_rejected(self):
        engine = self._build_engine()
        result = engine.match_all(
            "충전식 창 사용 ",
            jp_text="蓄電式の槍を使用",
            en_text="Use Battery Spear",
        )
        assert result.affect_name_matches == []

    def test_jp_or_en_support_keeps_affect_name_match(self):
        engine = self._build_engine()
        result = engine.match_all(
            "충전 획득 ",
            jp_text="充電を獲得",
            en_text="Gain energy",
        )
        assert [match.data["id"] for match in result.affect_name_matches] == ["Charge"]

    def test_explicit_effect_id_does_not_require_language_support(self):
        engine = self._build_engine()
        result = engine.match_all(
            "[Charge] 획득",
            jp_text="別名を獲得",
            en_text="Gain another effect",
        )
        assert [match.data["id"] for match in result.affect_id_matches] == ["Charge"]
