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
        """构建主翻译系统提示词。v2 模式下自动加载 few-shot 示例。"""
        prompt_version = getattr(self._config, "prompt_version", "v2")
        # v2 模式下自动加载 FileType 对应的 few-shot 示例
        if prompt_version != "v1" and examples is None:
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
            prompt_version=prompt_version,
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
            prompt_version=getattr(self._config, "prompt_version", "v2"),
        )

    def build_stage_2_user_prompt(
        self,
        original_blocks: list[dict],
        translations: list[dict],
        prompt_format: str = "xml_json",
    ) -> str:
        """构建阶段 2 的 user message（原文/译文对）。"""
        _xml_escape = self._prompt_factory._xml_escape
        lines = [
            "<context>",
            "请校验以下翻译的术语一致性和格式正确性：",
        ]
        for i, (orig, trans) in enumerate(zip(original_blocks, translations)):
            lines.append(f'  <pair id="{i + 1}">')
            lines.append(f"    <original>")
            lines.append(f"      <kr>{_xml_escape(orig.get('kr', ''))}</kr>")
            lines.append(f"      <jp>{_xml_escape(orig.get('jp', ''))}</jp>")
            lines.append(f"      <en>{_xml_escape(orig.get('en', ''))}</en>")
            lines.append(f"    </original>")
            trans_text = trans.get("translation", "") if isinstance(trans, dict) else str(trans)
            lines.append(f"    <translation>{_xml_escape(trans_text)}</translation>")
            lines.append(f"  </pair>")
        lines.append("</context>")
        return "\n".join(lines)

    def parse_stage_2_result(self, result_text: str, prompt_format: str = "xml_json") -> list[dict]:
        """解析自校验结果。"""
        return self._prompt_factory.parse_response(result_text, stage=2, prompt_format=prompt_format)
