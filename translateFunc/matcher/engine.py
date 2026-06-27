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
        self._role_ac = AcAutomaton()
        for item in role_items:
            role_id = item.get("id", "")
            if role_id:
                self._role_ac.add_pattern(role_id, data=item)
        self._role_ac.build()

    def build_affects(self, affect_items: list[dict]) -> None:
        """从 [{id, kr, cn, desc}, ...] 构建状态效果 ID 和名称 AC 自动机。"""
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

    def match_all(self, text: str) -> MatchResult:
        """对文本运行全部四个匹配器。"""
        return MatchResult(
            proper_matches=self._proper_ac.search(text),
            role_matches=self._role_ac.search(text),
            affect_id_matches=self._affect_id_ac.search(text),
            affect_name_matches=self._affect_name_ac.search(text),
        )

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
