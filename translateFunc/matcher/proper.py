"""
translateFunc/matcher/proper.py
ProperAnalyzer —— 专有名词 JP/EN 交叉验证消歧。

解决两类问题：
1. 短术语误匹配（如 "고" 出现在大量无关句子中）
2. 一词多义消歧（如 "이상" 既可以是人名"李箱"也可以是"不低于"）

两种消歧方式：
A. 相似度消歧：对正/负向上下文的 Jaccard 相似度计算
B. LLM 消歧：轻量消歧提示词（约 300 tokens）
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from translateFunc.enums import MatchConfidence
from translateFunc.get_proper import fetch as fetch_proper
from translateFunc.proper.analyze import extract_contexts


@dataclass
class ProperTerm:
    """经 JP/EN 交叉验证数据增强的专有名词术语。"""
    kr: str
    cn: str
    note: str = ""
    positive_contexts: list[dict] = field(default_factory=list)
    negative_contexts: list[dict] = field(default_factory=list)

    @property
    def is_short(self) -> bool:
        """短术语（≤2 字符）容易出现误匹配。"""
        return len(self.kr) <= 2

    @property
    def has_contexts(self) -> bool:
        return len(self.positive_contexts) > 0


class ProperAnalyzer:
    """获取并分析专有名词术语，附带 JP/EN 交叉验证。"""

    def __init__(self, kr_path: Path | None = None,
                 jp_path: Path | None = None,
                 en_path: Path | None = None):
        self._kr_path = kr_path
        self._jp_path = jp_path
        self._en_path = en_path
        self._terms: list[ProperTerm] = []

    # ----- 获取 -----

    def fetch_terms(self, min_len: int = 0, auto_fetch: bool = True,
                    proper_path: str = "") -> list[dict]:
        """从 paratranz API 或本地文件获取术语。"""
        if auto_fetch:
            return fetch_proper(min_len=min_len)
        else:
            import json
            return json.loads(Path(proper_path).read_text(encoding="utf-8"))

    # ----- 分析 -----

    def analyze(self, raw_terms: list[dict]) -> list[ProperTerm]:
        """从游戏文件中提取 JP/EN 上下文句子，增强原始术语。

        使用批量 AC 自动机扫描：一次文件遍历处理全部术语，
        对比逐术语扫描快约 N 倍（N = 术语数量）。
        """
        # 收集所有有效的 KR 术语文本
        raw_term_list: list[dict] = []
        kr_texts: list[str] = []
        for item in raw_terms:
            kr = item.get("term", "")
            if not kr:
                continue
            raw_term_list.append(item)
            kr_texts.append(kr)

        # 批量提取上下文
        contexts_map: dict[str, list[dict]] = {}
        if self._kr_path and self._jp_path and self._en_path and kr_texts:
            from translateFunc.proper.analyze import extract_contexts_batch
            contexts_map = extract_contexts_batch(
                kr_texts, self._kr_path, self._jp_path, self._en_path, max_examples=20
            )

        # 构建 ProperTerm 列表
        terms: list[ProperTerm] = []
        for item in raw_term_list:
            kr = item.get("term", "")
            cn = item.get("translation", "")
            note = item.get("note", "")
            positive_contexts = contexts_map.get(kr, [])
            term = ProperTerm(
                kr=kr,
                cn=cn,
                note=note,
                positive_contexts=positive_contexts,
            )
            terms.append(term)

        self._terms = terms
        return terms

    # ----- 置信度 -----

    def compute_confidence(
        self,
        term: ProperTerm,
        text_block_jp: str,
        text_block_en: str,
    ) -> MatchConfidence:
        """
        基于 JP/EN 句级相似度判断专有名词匹配是否真实适用。

        返回 MatchConfidence：
        - HIGH: JP/EN 平均相似度与正向上下文强匹配
        - MEDIUM: JP/EN 平均相似度中等匹配
        - LOW: 弱匹配，可能不适用
        - UNKNOWN: 术语无上下文数据，无法判断
        - FALSE_MATCH: 相似度过低，判定为假阳性
        """
        if not term.has_contexts:
            return MatchConfidence.UNKNOWN

        if not text_block_jp and not text_block_en:
            return MatchConfidence.UNKNOWN

        pos_scores: list[float] = []
        for ctx in term.positive_contexts:
            score = 0.0
            if text_block_jp and ctx.get("jp_sentence"):
                score += _jaccard_similarity(text_block_jp, ctx["jp_sentence"])
            if text_block_en and ctx.get("en_sentence"):
                score += _jaccard_similarity(text_block_en, ctx["en_sentence"])
            divisor = (1 if text_block_jp else 0) + (1 if text_block_en else 0)
            if divisor > 0:
                pos_scores.append(score / divisor)

        best_pos = max(pos_scores) if pos_scores else 0.0

        # 短术语需要更强的验证
        threshold_high = 0.7 if term.is_short else 0.5
        threshold_med = 0.5 if term.is_short else 0.3

        if best_pos >= threshold_high:
            return MatchConfidence.HIGH
        elif best_pos >= threshold_med:
            return MatchConfidence.MEDIUM
        elif best_pos > 0.1:
            return MatchConfidence.LOW
        else:
            return MatchConfidence.FALSE_MATCH

    @property
    def terms(self) -> list[ProperTerm]:
        return self._terms


def _jaccard_similarity(a: str, b: str) -> float:
    """基于词级重叠（按空格分词）的 Jaccard 相似度。"""
    if not a or not b:
        return 0.0
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        # CJK 文本回退到字符级
        set_a = set(a)
        set_b = set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0
