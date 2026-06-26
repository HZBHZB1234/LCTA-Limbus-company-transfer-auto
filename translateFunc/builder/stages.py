"""
translateFunc/builder/stages.py
StageStrategy —— 实现三阶段翻译管线。

阶段 0：术语消歧（相似度 / LLM / 混合）
阶段 1：主翻译，使用动态标签化提示词
阶段 2：自校验 —— 术语一致性 + 格式规则（+ 自动修正）
"""
from __future__ import annotations
import json
from typing import Any, Callable

from translateFunc.enums import FileType, MatchConfidence
from translateFunc.builder.prompt import PromptFactory


class StageStrategy:
    """封装翻译管线各阶段的逻辑。"""

    def __init__(self, config):
        """
        Args:
            config: TranslateConfig 实例，含 translation_mode、
                    disambiguation_mode、enable_self_check、min_confidence。
        """
        self._config = config
        self._prompt_factory = PromptFactory()

    # ========== 阶段 0：消歧 ==========

    def needs_disambiguation(self) -> bool:
        """判断是否需要执行阶段 0。"""
        return (
            self._config.translation_mode == "multi_stage"
            and self._config.disambiguation_mode != "similarity"
        )

    def should_llm_disambiguate(self, confidence: MatchConfidence) -> bool:
        """判断某个匹配是否需要 LLM 消歧。"""
        if self._config.disambiguation_mode == "llm":
            return True
        if self._config.disambiguation_mode == "hybrid":
            return confidence in (MatchConfidence.LOW, MatchConfidence.UNKNOWN)
        return False

    def filter_by_confidence(self, matches: list[dict], min_conf: MatchConfidence) -> list[dict]:
        """按最低置信度阈值过滤匹配。"""
        conf_order = {
            MatchConfidence.HIGH: 0,
            MatchConfidence.MEDIUM: 1,
            MatchConfidence.LOW: 2,
            MatchConfidence.UNKNOWN: 3,
            MatchConfidence.FALSE_MATCH: 4,
        }
        threshold = conf_order.get(min_conf, 1)
        return [m for m in matches if conf_order.get(m.get("confidence"), 4) <= threshold]

    def build_stage_0_prompt(
        self,
        candidate_terms: list[dict],
        text_blocks: list[dict],
    ) -> str:
        """构建阶段 0 的 LLM 消歧提示词。"""
        return self._prompt_factory.build_disambiguation_prompt(candidate_terms, text_blocks)

    def parse_stage_0_result(self, result_text: str) -> list[dict]:
        """将 LLM 消歧结果解析为结构化数据。"""
        try:
            data = json.loads(result_text)
            return data.get("disambiguations", [])
        except json.JSONDecodeError:
            return []

    # ========== 阶段 1：主翻译 ==========

    def build_stage_1_prompt(
        self,
        file_type: FileType,
        *,
        skill_doc: str = "",
        role_styles: list[dict] | None = None,
        examples: list[dict] | None = None,
    ) -> str:
        """构建主翻译系统提示词。"""
        return self._prompt_factory.build_system_prompt(
            file_type=file_type,
            stage=1,
            skill_doc=skill_doc,
            role_styles=role_styles,
            examples=examples,
        )

    def build_stage_1_user_prompt(
        self,
        text_blocks: list[dict],
        glossary_terms: list[dict] | None = None,
    ) -> str:
        """构建阶段 1 的用户提示词部分。"""
        parts: list[str] = []
        if glossary_terms:
            parts.append(self._prompt_factory.render_glossary(glossary_terms))
        parts.append(self._prompt_factory.render_text_blocks(text_blocks))
        return "\n".join(parts)

    def parse_stage_1_result(self, result_text: str) -> list[dict]:
        """解析阶段 1 翻译结果，同时支持 JSON 和纯文本格式。"""
        try:
            data = json.loads(result_text)
            return data.get("translations", [])
        except json.JSONDecodeError:
            # 回退：纯文本格式解析
            lines = result_text.strip().split("\n\n")
            translations = []
            for line in lines:
                line = line.strip()
                # 去除转义标记
                line = line.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
                translations.append({"id": len(translations) + 1, "translation": line})
            return translations

    # ========== 阶段 2：自校验 ==========

    def needs_self_check(self) -> bool:
        """判断是否需要执行阶段 2。"""
        return (
            self._config.translation_mode == "multi_stage"
            and self._config.enable_self_check
        )

    def build_stage_2_prompt(
        self,
        file_type: FileType,
        original_blocks: list[dict],
        translations: list[dict],
    ) -> str:
        """构建自校验提示词，将原文与译文并列对比。"""
        system = self._prompt_factory.build_system_prompt(file_type=file_type, stage=2)

        # 用户部分：原文与译文并列
        lines = [
            "<context>",
            "请校验以下翻译的术语一致性和格式正确性：",
        ]
        for i, (orig, trans) in enumerate(zip(original_blocks, translations)):
            lines.append(f'  <pair id="{i + 1}">')
            lines.append(f"    <original>")
            lines.append(f"      <kr>{orig.get('kr', '')}</kr>")
            lines.append(f"      <jp>{orig.get('jp', '')}</jp>")
            lines.append(f"      <en>{orig.get('en', '')}</en>")
            lines.append(f"    </original>")
            trans_text = trans.get("translation", "") if isinstance(trans, dict) else str(trans)
            lines.append(f"    <translation>{trans_text}</translation>")
            lines.append(f"  </pair>")
        lines.append("</context>")

        return system + "\n" + "\n".join(lines)

    def parse_stage_2_result(self, result_text: str) -> list[dict]:
        """解析自校验结果。"""
        try:
            data = json.loads(result_text)
            return data.get("checked_translations", [])
        except json.JSONDecodeError:
            return []
