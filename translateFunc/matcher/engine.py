"""
translateFunc/matcher/engine.py
MatcherEngine —— 管理全部四个 AC 自动机实例，提供统一匹配接口。
"""
from __future__ import annotations
from dataclasses import dataclass, field

from translateFunc.matcher.ac_automaton import AcAutomaton, ACPattern


@dataclass
class MatchResult:
    """同时对文本运行全部匹配器的聚合结果。"""
    proper_matches: list[ACPattern] = field(default_factory=list)
    role_matches: list[ACPattern] = field(default_factory=list)
    affect_id_matches: list[ACPattern] = field(default_factory=list)
    affect_name_matches: list[ACPattern] = field(default_factory=list)

    @property
    def has_any(self) -> bool:
        return bool(self.proper_matches or self.role_matches
                    or self.affect_id_matches or self.affect_name_matches)


class MatcherEngine:
    """统一匹配引擎，管理四个 AC 自动机：
    专有名词、角色、状态效果 ID（如 [Combustion]）、状态效果名称（如 '燃烧 '）。
    """

    def __init__(self):
        self._proper_ac = AcAutomaton()
        self._role_ac = AcAutomaton()
        self._affect_id_ac = AcAutomaton()
        self._affect_name_ac = AcAutomaton()

        self._role_data: list[dict] = []
        self._affect_data: list[dict] = []

        # 确保所有 AC 自动机在翻译优先文件前已处于已构建状态，
        # 后续通过 _update_roles / _update_affects 用实际数据重建。
        self._role_ac.build()
        self._affect_id_ac.build()
        self._affect_name_ac.build()

    # ----- 构建 -----

    def build_proper(self, proper_terms: list[dict]) -> None:
        """从 [{term, translation, note, ...}, ...] 构建专有名词 AC 自动机。"""
        self._proper_ac = AcAutomaton()
        for item in proper_terms:
            term = item.get("term", "")
            if term:
                self._proper_ac.add_pattern(term, data=item)
        self._proper_ac.build()

    def build_roles(self, role_items: list[dict]) -> None:
        """从 [{id, kr, cn, nickName}, ...] 构建角色 AC 自动机。
        角色通过 `id` 字段精确匹配，非子串匹配。"""
        self._role_data = role_items
        self._role_by_id_cache = None  # 清除缓存
        self._role_ac = AcAutomaton()
        for item in role_items:
            role_id = item.get("id", "")
            if role_id:
                self._role_ac.add_pattern(role_id, data=item)
        self._role_ac.build()

    def build_affects(self, affect_items: list[dict]) -> None:
        """从 [{id, kr, jp, en, cn, desc}, ...] 构建状态效果匹配器。"""
        self._affect_data = affect_items
        self._affect_id_ac = AcAutomaton()
        self._affect_name_ac = AcAutomaton()
        for item in affect_items:
            aff_id = f'[{item.get("id", "")}]'
            aff_name = f'{item.get("kr", "")} '
            if item.get("id"):
                self._affect_id_ac.add_pattern(aff_id, data=item)
            if item.get("kr"):
                self._affect_name_ac.add_pattern(aff_name, data=item)
        self._affect_id_ac.build()
        self._affect_name_ac.build()

    # ----- 匹配 -----

    def match_all(
        self,
        text: str,
        *,
        jp_text: str = "",
        en_text: str = "",
    ) -> MatchResult:
        """对文本运行全部匹配器，并用 JP/EN 参考过滤韩文名称误匹配。"""
        affect_name_matches = [
            match for match in self._affect_name_ac.search(text)
            if self._is_affect_name_supported(match.data, text, jp_text, en_text)
        ]
        return MatchResult(
            proper_matches=self._proper_ac.search(text),
            role_matches=self._role_ac.search(text),
            affect_id_matches=self._affect_id_ac.search(text),
            affect_name_matches=affect_name_matches,
        )

    @staticmethod
    def _is_affect_name_supported(
        affect_data: object,
        kr_text: str,
        jp_text: str,
        en_text: str,
    ) -> bool:
        """有可用 JP/EN 对照时，要求至少一种语言同时出现对应效果名。"""
        if not isinstance(affect_data, dict):
            return True

        comparisons: list[bool] = []
        jp_name = str(affect_data.get("jp", "") or "").strip()
        if jp_name and jp_text and jp_text != kr_text:
            comparisons.append(jp_name in jp_text)

        en_name = str(affect_data.get("en", "") or "").strip()
        if en_name and en_text and en_text != kr_text:
            comparisons.append(en_name.casefold() in en_text.casefold())

        return any(comparisons) if comparisons else True

    def match_proper(self, text: str) -> list[ACPattern]:
        """仅匹配专有名词。"""
        return self._proper_ac.search(text)

    # ----- 访问器 -----

    @property
    def role_data(self) -> list[dict]:
        return self._role_data

    @property
    def affect_data(self) -> list[dict]:
        return self._affect_data

    @property
    def role_by_id(self) -> dict[str, dict]:
        """以角色 ID 为键的 O(1) 查找表。"""
        if not hasattr(self, "_role_by_id_cache") or self._role_by_id_cache is None:
            self._role_by_id_cache = {r.get("id", ""): r for r in self._role_data}
        return self._role_by_id_cache
