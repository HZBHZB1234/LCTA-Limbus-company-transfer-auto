"""
translateFunc/builder/prompt.py
PromptTag 枚举与 PromptFactory —— 动态 XML 标签化提示词组装。

工厂按 FileType × Stage 选择模板，以 XML 标签渲染。
无内容的标签块自动省略。
"""
from __future__ import annotations
from enum import Enum, auto
from typing import Any

from translateFunc.enums import FileType


class PromptTag(Enum):
    """提示词构建中使用的 XML 标签。"""
    ROLE       = "role"
    RULES      = "rules"
    RULE       = "rule"
    GLOSSARY   = "glossary"
    TERM       = "term"
    EXAMPLES   = "examples"
    EXAMPLE    = "example"
    IN         = "in"
    OUT        = "out"
    TRANSLATION = "translation"
    REASONING  = "reasoning"
    CONFIDENCE = "confidence"
    CONTEXT    = "context"
    TEXT       = "text"
    BLOCK      = "block"
    KR         = "kr"
    JP         = "jp"
    EN         = "en"
    FORMAT     = "format"


class PromptFactory:
    """构建分阶段提示词，使用 XML 标签，按 FileType 动态组装。"""

    # ---- 基础角色提示词（保留自 translate_doc.py 结构） ----

    _BASE_ROLE = (
        "<role>\n"
        "我是游戏作品'边狱公司'的翻译员，我将要把其他语言的文本翻译为中文。\n"
        "</role>\n"
    )

    _STAGE1_RULES = (
        "<rules>\n"
        "<rule>先查看reference中的术语表和指南，确保术语一致性</rule>\n"
        "<rule>在翻译剧情文本时使用全角符号，否则使用半角符号</rule>\n"
        "<rule>波浪号使用半角波浪号~</rule>\n"
        "<rule>保留原文的代码格式，如富文本和f-string</rule>\n"
        "<rule>术语内容可能存在错误引用，如果术语内容与原文意思偏差过大，忽略该术语</rule>\n"
        "<rule>原文的控制字符会被转义，输出时也使用转义后的字符（如\\n）</rule>\n"
        "</rules>\n"
    )

    _STAGE0_RULES = (
        "<rules>\n"
        "<rule>你的任务是判断术语在当前上下文中是否适用，不需要翻译</rule>\n"
        "<rule>对比术语的典型使用场景和当前文本块的JP/EN内容</rule>\n"
        "<rule>如果术语明显不适用（如人名术语出现在技能描述中），标记为不适用</rule>\n"
        "</rules>\n"
    )

    _STAGE2_RULES = (
        "<rules>\n"
        "<rule>校验翻译结果中的术语一致性</rule>\n"
        "<rule>检查格式规则：全角/半角符号、波浪号、代码格式保留</rule>\n"
        "<rule>发现错误时自动修正并给出修正说明</rule>\n"
        "</rules>\n"
    )

    # ---- 输出格式规范 ----

    _STAGE0_FORMAT = (
        "<format>\n"
        "返回JSON对象，包含disambiguations字段：\n"
        "{\n"
        '  "disambiguations": [\n'
        '    {"term": "术语KR", "applies": true/false,\n'
        '     "actual_meaning": "在此上下文中的实际含义",\n'
        '     "reason": "判断理由"}\n'
        "  ]\n"
        "}\n"
        "</format>\n"
    )

    _STAGE1_FORMAT = (
        "<format>\n"
        "返回JSON对象，包含translations字段：\n"
        "{\n"
        '  "translations": [\n'
        '    {"id": 1, "translation": "翻译结果",\n'
        '     "reasoning": "关键决策说明",\n'
        '     "confidence": "high|medium|low"}\n'
        "  ]\n"
        "}\n"
        "confidence为low的条目说明翻译不确定，需要回退到原文。\n"
        "</format>\n"
    )

    _STAGE2_FORMAT = (
        "<format>\n"
        "返回JSON对象，包含checked_translations字段：\n"
        "{\n"
        '  "checked_translations": [\n'
        '    {"id": 1, "translation": "修正后的翻译",\n'
        '     "changed": false, "change_reason": ""}\n'
        "  ]\n"
        "}\n"
        "</format>\n"
    )

    # ---- 技能文档模板 ----

    _SKILL_DOC_TEMPLATE = "<skill_guide>\n{content}\n</skill_guide>\n"

    # ========== 公开 API ==========

    def build_system_prompt(
        self,
        file_type: FileType,
        stage: int,
        *,
        skill_doc: str = "",
        role_styles: list[dict] | None = None,
        examples: list[dict] | None = None,
    ) -> str:
        """为给定文件类型和阶段构建系统提示词。

        Args:
            file_type: STORY、SKILL、UI 或 OTHER
            stage: 0（消歧）、1（翻译）、2（自校验）
            skill_doc: 技能翻译指南（SKILL 文件专用）
            role_styles: 角色说话风格参考（STORY 文件专用）
            examples: 可选的 few-shot 示例
        """
        parts: list[str] = [self._BASE_ROLE]

        # 分阶段规则
        if stage == 0:
            parts.append(self._STAGE0_RULES)
        elif stage == 1:
            parts.append(self._STAGE1_RULES)
        elif stage == 2:
            parts.append(self._STAGE2_RULES)

        # 技能指南（仅 stage 1，SKILL 文件）
        if stage == 1 and file_type == FileType.SKILL and skill_doc:
            parts.append(self._SKILL_DOC_TEMPLATE.format(content=skill_doc))

        # 角色风格（仅 stage 1，STORY 文件）
        if stage == 1 and file_type == FileType.STORY and role_styles:
            parts.append(self._render_role_styles(role_styles))

        # Few-shot 示例
        if examples:
            parts.append(self._render_examples(examples))

        # 输出格式
        if stage == 0:
            parts.append(self._STAGE0_FORMAT)
        elif stage == 1:
            parts.append(self._STAGE1_FORMAT)
        elif stage == 2:
            parts.append(self._STAGE2_FORMAT)

        return "\n".join(parts)

    def build_disambiguation_prompt(
        self,
        candidate_terms: list[dict],
        text_blocks: list[dict],
    ) -> str:
        """构建轻量 LLM 消歧提示词（约 300 tokens）。"""
        term_list = "\n".join(
            f"  - {t['kr']} → {t['cn']}" + (f" ({t.get('note', '')})" if t.get('note') else "")
            for t in candidate_terms
        )
        block_text = ""
        for i, block in enumerate(text_blocks[:3]):  # 最多 3 个文本块
            block_text += (
                f"<block id=\"{i+1}\">\n"
                f"  <kr>{block.get('kr', '')}</kr>\n"
                f"  <jp>{block.get('jp', '')}</jp>\n"
                f"  <en>{block.get('en', '')}</en>\n"
                f"</block>\n"
            )

        return (
            f"<role>你是边狱公司的术语专家。</role>\n"
            f"<context>\n"
            f"候选术语：\n{term_list}\n"
            f"当前文本：\n{block_text}"
            f"</context>\n"
            f"{self._STAGE0_FORMAT}"
        )

    # ========== 内部渲染器 ==========

    def _render_role_styles(self, styles: list[dict]) -> str:
        """将角色风格参考渲染为 XML。"""
        lines = ["<role_styles>"]
        for s in styles:
            lines.append(f"  <style>")
            for k, v in s.items():
                lines.append(f"    <{k}>{v}</{k}>")
            lines.append(f"  </style>")
        lines.append("</role_styles>")
        return "\n".join(lines) + "\n"

    def _render_examples(self, examples: list[dict]) -> str:
        """将 few-shot 示例渲染为 XML。"""
        lines = ["<examples>"]
        for ex in examples:
            lines.append("  <example>")
            lines.append(f"    <in>{ex.get('in', '')}</in>")
            lines.append(f"    <out>")
            lines.append(f"      <translation>{ex.get('translation', '')}</translation>")
            if ex.get('reasoning'):
                lines.append(f"      <reasoning>{ex['reasoning']}</reasoning>")
            if ex.get('confidence'):
                lines.append(f"      <confidence>{ex['confidence']}</confidence>")
            lines.append(f"    </out>")
            lines.append("  </example>")
        lines.append("</examples>")
        return "\n".join(lines) + "\n"

    def render_text_blocks(self, text_blocks: list[dict]) -> str:
        """渲染 <text> 节，包含 kr/jp/en 文本块。"""
        lines = ["<text>"]
        for i, block in enumerate(text_blocks):
            lines.append(f'  <block id="{i + 1}">')
            lines.append(f"    <kr>{block.get('kr', '')}</kr>")
            if block.get('jp'):
                lines.append(f"    <jp>{block.get('jp', '')}</jp>")
            if block.get('en'):
                lines.append(f"    <en>{block.get('en', '')}</en>")
            lines.append(f"  </block>")
        lines.append("</text>")
        return "\n".join(lines) + "\n"

    def render_glossary(self, terms: list[dict]) -> str:
        """渲染 <glossary> 节。术语为空时省略。"""
        if not terms:
            return ""
        lines = ["<glossary>"]
        for t in terms:
            kr = t.get('kr', t.get('term', ''))
            cn = t.get('cn', t.get('translation', ''))
            note = t.get('note', '')
            attr = f' kr="{kr}" cn="{cn}"'
            if note:
                attr += f' note="{note}"'
            lines.append(f"  <term{attr} />")
        lines.append("</glossary>")
        return "\n".join(lines) + "\n"
