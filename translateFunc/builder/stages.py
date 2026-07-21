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

    def build_stage_0_prompt(
        self,
        prompt_format: str = "xml_json",
    ) -> str:
        """构建阶段 0 的 system prompt（仅 role + rules + format，不含数据）。"""
        return self._prompt_factory.build_stage_0_system_prompt(prompt_format)

    def build_stage_0_user_prompt(
        self,
        candidate_terms: list[dict],
        text_blocks: list[dict],
        prompt_format: str = "xml_json",
    ) -> str:
        """构建阶段 0 的 user message（候选术语 + 文本块上下文数据）。"""
        return self._prompt_factory.build_stage_0_user_message(
            candidate_terms, text_blocks, prompt_format,
        )

    def parse_stage_0_result(self, result_text: str, prompt_format: str = "xml_json") -> list[dict]:
        """将 LLM 消歧结果解析为结构化数据。"""
        return self._prompt_factory.parse_response(result_text, stage=0, prompt_format=prompt_format)

    # ========== 阶段 1：主翻译 ==========

    def build_stage_1_prompt(
        self,
        file_type: FileType,
        prompt_format: str = "xml_json",
        *,
        examples: list[dict] | None = None,
    ) -> str:
        """构建主翻译系统提示词。自动加载 FileType 对应的 few-shot 示例。"""
        # 自动加载 FileType 对应的 few-shot 示例
        if examples is None:
            try:
                from translateFunc.builder.examples import get_examples
                examples = get_examples(file_type.name)
            except ImportError:
                pass
        return self._prompt_factory.build_system_prompt(
            file_type=file_type,
            stage=1,
            prompt_format=prompt_format,
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

    def parse_stage_1_result(self, result_text: str, prompt_format: str = "xml_json") -> list[dict]:
        """解析阶段 1 翻译结果，按格式分发。"""
        if prompt_format in ("xml_json", "json_json", "xml_xml"):
            return self._prompt_factory.parse_response(result_text, stage=1, prompt_format=prompt_format)
        # 未知格式回退：纯文本解析
        try:
            import json as _json
            data = _json.loads(result_text)
            return data.get("translations", [])
        except _json.JSONDecodeError:
            lines = result_text.strip().split("\n\n")
            translations = []
            for line in lines:
                line = line.strip()
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
        prompt_format: str = "xml_json",
    ) -> str:
        """构建阶段 2 的 system prompt（仅 role + rules + format，不含数据）。"""
        return self._prompt_factory.build_system_prompt(
            file_type=file_type, stage=2, prompt_format=prompt_format,
        )

    def build_stage_2_user_prompt(
        self,
        original_blocks: list[dict],
        translations: list[dict],
        prompt_format: str = "xml_json",
        *,
        reference: dict | None = None,
    ) -> str:
        """构建阶段 2 的 user message（原文/译文对 + 引用字段 + 术语表）。

        Args:
            original_blocks: 原文文本块（含 proper_refs/affect_refs/model 等引用字段）
            translations: 阶段 1 的翻译结果 [{id, translation}, ...]
            prompt_format: 提示词格式
            reference: 可选的 reference dict（含 proper_terms/affects），用于术语一致性校验
        """
        _xml_escape = self._prompt_factory._xml_escape
        parts: list[str] = []

        # 术语表（帮助 LLM 校验术语一致性）
        if reference:
            if reference.get("proper_terms"):
                parts.append(self._prompt_factory.render_glossary(reference["proper_terms"]))
            if reference.get("affects"):
                from translateFunc.builder.request import RequestBuilder
                builder = RequestBuilder.__new__(RequestBuilder)
                parts.append(builder._render_affects_xml(reference["affects"]))

        parts.append("<context>")
        parts.append("请校验以下翻译的术语一致性和格式正确性：")
        for i, (orig, trans) in enumerate(zip(original_blocks, translations)):
            parts.append(f'  <pair id="{i + 1}">')
            parts.append(f"    <original>")
            parts.append(f"      <kr>{_xml_escape(orig.get('kr', ''))}</kr>")
            if orig.get('jp'):
                parts.append(f"      <jp>{_xml_escape(orig.get('jp', ''))}</jp>")
            if orig.get('en'):
                parts.append(f"      <en>{_xml_escape(orig.get('en', ''))}</en>")
            parts.append(f"    </original>")
            # 引用字段（帮助 LLM 校验术语一致性）
            if orig.get('proper_refs'):
                refs = ", ".join(orig['proper_refs'])
                parts.append(f"    <proper_refs>{_xml_escape(refs)}</proper_refs>")
            if orig.get('affect_refs'):
                refs = ", ".join(orig['affect_refs'])
                parts.append(f"    <affect_refs>{_xml_escape(refs)}</affect_refs>")
            if orig.get('model'):
                parts.append(f"    <model>{_xml_escape(orig['model'])}</model>")
            trans_text = trans.get("translation", "") if isinstance(trans, dict) else str(trans)
            parts.append(f"    <translation>{_xml_escape(trans_text)}</translation>")
            parts.append(f"  </pair>")
        parts.append("</context>")
        return "\n".join(parts)

    def parse_stage_2_result(self, result_text: str, prompt_format: str = "xml_json") -> list[dict]:
        """解析自校验结果。"""
        return self._prompt_factory.parse_response(result_text, stage=2, prompt_format=prompt_format)
