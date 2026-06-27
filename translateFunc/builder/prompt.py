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
        "<rule>先查看reference中的术语表及每条文本块的proper_refs/affect_refs/model引用，确保术语一致性</rule>\n"
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

    # ---- 输出格式规范（xml_json 模式：XML 包裹的 JSON 响应描述） ----

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

    # ---- JSON 格式模板（json_json） ----

    _JSON_BASE_ROLE = (
        '{\n'
        '  "role": "我是游戏作品\'边狱公司\'的翻译员，我将要把其他语言的文本翻译为中文。"\n'
        '}\n'
    )

    _JSON_STAGE1_RULES = (
        '{\n'
        '  "rules": [\n'
        '    "先查看reference中的术语表及每条文本块的proper_refs/affect_refs/model引用，确保术语一致性",\n'
        '    "在翻译剧情文本时使用全角符号，否则使用半角符号",\n'
        '    "波浪号使用半角波浪号~",\n'
        '    "保留原文的代码格式，如富文本和f-string",\n'
        '    "术语内容可能存在错误引用，如果术语内容与原文意思偏差过大，忽略该术语",\n'
        '    "原文的控制字符会被转义，输出时也使用转义后的字符（如\\\\n）"\n'
        '  ]\n'
        '}\n'
    )

    _JSON_STAGE0_RULES = (
        '{\n'
        '  "rules": [\n'
        '    "你的任务是判断术语在当前上下文中是否适用，不需要翻译",\n'
        '    "对比术语的典型使用场景和当前文本块的JP/EN内容",\n'
        '    "如果术语明显不适用（如人名术语出现在技能描述中），标记为不适用"\n'
        '  ]\n'
        '}\n'
    )

    _JSON_STAGE2_RULES = (
        '{\n'
        '  "rules": [\n'
        '    "校验翻译结果中的术语一致性",\n'
        '    "检查格式规则：全角/半角符号、波浪号、代码格式保留",\n'
        '    "发现错误时自动修正并给出修正说明"\n'
        '  ]\n'
        '}\n'
    )

    _JSON_STAGE0_FORMAT = (
        '{\n'
        '  "format": {\n'
        '    "response_type": "json_object",\n'
        '    "description": "返回JSON对象，包含disambiguations字段",\n'
        '    "schema": {\n'
        '      "disambiguations": [\n'
        '        {"term": "术语KR", "applies": true, "actual_meaning": "在此上下文中的实际含义", "reason": "判断理由"}\n'
        '      ]\n'
        '    }\n'
        '  }\n'
        '}\n'
    )

    _JSON_STAGE1_FORMAT = (
        '{\n'
        '  "format": {\n'
        '    "response_type": "json_object",\n'
        '    "description": "返回JSON对象，包含translations字段",\n'
        '    "schema": {\n'
        '      "translations": [\n'
        '        {"id": 1, "translation": "翻译结果", "reasoning": "关键决策说明", "confidence": "high|medium|low"}\n'
        '      ]\n'
        '    },\n'
        '    "note": "confidence为low的条目说明翻译不确定，需要回退到原文"\n'
        '  }\n'
        '}\n'
    )

    _JSON_STAGE2_FORMAT = (
        '{\n'
        '  "format": {\n'
        '    "response_type": "json_object",\n'
        '    "description": "返回JSON对象，包含checked_translations字段",\n'
        '    "schema": {\n'
        '      "checked_translations": [\n'
        '        {"id": 1, "translation": "修正后的翻译", "changed": false, "change_reason": ""}\n'
        '      ]\n'
        '    }\n'
        '  }\n'
        '}\n'
    )

    # ---- XML 格式的 format 模板（xml_json / xml_xml 共享 role/rules，区分 format） ----

    _XML_STAGE0_FORMAT = _STAGE0_FORMAT  # 原 _STAGE0_FORMAT，请求 JSON 响应

    _XML_STAGE0_FORMAT_XML = (
        "<format>\n"
        "返回XML，包含<disambiguations>根元素：\n"
        "<disambiguations>\n"
        '  <item term="术语KR" applies="true" actual_meaning="在此上下文中的实际含义" reason="判断理由" />\n'
        "</disambiguations>\n"
        "</format>\n"
    )

    _XML_STAGE1_FORMAT = _STAGE1_FORMAT  # 原 _STAGE1_FORMAT，请求 JSON 响应

    _XML_STAGE1_FORMAT_XML = (
        "<format>\n"
        "返回XML，包含<translations>根元素：\n"
        "<translations>\n"
        '  <item id="1">\n'
        "    <translation>翻译结果</translation>\n"
        "    <reasoning>关键决策说明</reasoning>\n"
        "    <confidence>high|medium|low</confidence>\n"
        "  </item>\n"
        "</translations>\n"
        "confidence为low的条目说明翻译不确定，需要回退到原文。\n"
        "</format>\n"
    )

    _XML_STAGE2_FORMAT = _STAGE2_FORMAT  # 原 _STAGE2_FORMAT，请求 JSON 响应

    _XML_STAGE2_FORMAT_XML = (
        "<format>\n"
        "返回XML，包含<checked_translations>根元素：\n"
        "<checked_translations>\n"
        '  <item id="1">\n'
        "    <translation>修正后的翻译</translation>\n"
        "    <changed>false</changed>\n"
        "    <change_reason></change_reason>\n"
        "  </item>\n"
        "</checked_translations>\n"
        "</format>\n"
    )

    # ========== 公开 API ==========

    def build_system_prompt(
        self,
        file_type: FileType,
        stage: int,
        prompt_format: str = "xml_json",
        *,
        examples: list[dict] | None = None,
    ) -> str:
        """为给定文件类型、阶段和格式构建系统提示词。

        Args:
            file_type: STORY、SKILL、UI 或 OTHER
            stage: 0（消歧）、1（翻译）、2（自校验）
            prompt_format: "xml_json" | "xml_xml" | "json_json"
            examples: 可选的 few-shot 示例
        """
        is_json = (prompt_format == "json_json")

        if is_json:
            parts: list[str] = [self._JSON_BASE_ROLE]
        else:
            parts: list[str] = [self._BASE_ROLE]

        # 分阶段规则
        if stage == 0:
            parts.append(self._JSON_STAGE0_RULES if is_json else self._STAGE0_RULES)
        elif stage == 1:
            parts.append(self._JSON_STAGE1_RULES if is_json else self._STAGE1_RULES)
        elif stage == 2:
            parts.append(self._JSON_STAGE2_RULES if is_json else self._STAGE2_RULES)

        # Few-shot 示例
        if examples and not is_json:
            parts.append(self._render_examples(examples))
        elif examples and is_json:
            parts.append(self._render_examples_json(examples))

        # 输出格式
        if is_json:
            if stage == 0:
                parts.append(self._JSON_STAGE0_FORMAT)
            elif stage == 1:
                parts.append(self._JSON_STAGE1_FORMAT)
            elif stage == 2:
                parts.append(self._JSON_STAGE2_FORMAT)
        else:
            is_xml_response = (prompt_format == "xml_xml")
            if stage == 0:
                parts.append(self._XML_STAGE0_FORMAT_XML if is_xml_response else self._XML_STAGE0_FORMAT)
            elif stage == 1:
                parts.append(self._XML_STAGE1_FORMAT_XML if is_xml_response else self._XML_STAGE1_FORMAT)
            elif stage == 2:
                parts.append(self._XML_STAGE2_FORMAT_XML if is_xml_response else self._XML_STAGE2_FORMAT)

        return "\n".join(parts)

    def build_disambiguation_prompt(
        self,
        candidate_terms: list[dict],
        text_blocks: list[dict],
        prompt_format: str = "xml_json",
    ) -> str:
        """构建轻量 LLM 消歧提示词（约 300 tokens）。"""
        is_json = (prompt_format == "json_json")
        is_xml_response = (prompt_format == "xml_xml")

        if is_json:
            import json as _json
            return _json.dumps({
                "role": "你是边狱公司的术语专家。",
                "context": {
                    "candidate_terms": [
                        {"kr": t["kr"], "cn": t["cn"], "note": t.get("note", "")}
                        for t in candidate_terms
                    ],
                    "text_blocks": [
                        {"id": i + 1, "kr": b.get("kr", ""), "jp": b.get("jp", ""), "en": b.get("en", "")}
                        for i, b in enumerate(text_blocks[:3])
                    ],
                },
                "format": {
                    "response_type": "json_object",
                    "schema": {
                        "disambiguations": [
                            {"term": "...", "applies": True, "actual_meaning": "...", "reason": "..."}
                        ]
                    }
                }
            }, ensure_ascii=False, indent=2)

        term_list = "\n".join(
            f"  - {t['kr']} → {t['cn']}" + (f" ({t.get('note', '')})" if t.get('note') else "")
            for t in candidate_terms
        )
        block_text = ""
        for i, block in enumerate(text_blocks[:3]):
            block_text += (
                f"<block id=\"{i+1}\">\n"
                f"  <kr>{block.get('kr', '')}</kr>\n"
                f"  <jp>{block.get('jp', '')}</jp>\n"
                f"  <en>{block.get('en', '')}</en>\n"
                f"</block>\n"
            )

        format_part = self._XML_STAGE0_FORMAT_XML if is_xml_response else self._XML_STAGE0_FORMAT
        return (
            f"<role>你是边狱公司的术语专家。</role>\n"
            f"<context>\n"
            f"候选术语：\n{term_list}\n"
            f"当前文本：\n{block_text}"
            f"</context>\n"
            f"{format_part}"
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
        """渲染 <text> 节，包含 kr/jp/en 文本块及 per-block 引用。"""
        lines = ["<text>"]
        for i, block in enumerate(text_blocks):
            lines.append(f'  <block id="{i + 1}">')
            lines.append(f"    <kr>{block.get('kr', '')}</kr>")
            if block.get('jp'):
                lines.append(f"    <jp>{block.get('jp', '')}</jp>")
            if block.get('en'):
                lines.append(f"    <en>{block.get('en', '')}</en>")
            # Per-block 引用字段
            if block.get('proper_refs'):
                refs = ", ".join(block['proper_refs'])
                lines.append(f"    <proper_refs>{refs}</proper_refs>")
            if block.get('affect_refs'):
                refs = ", ".join(block['affect_refs'])
                lines.append(f"    <affect_refs>{refs}</affect_refs>")
            if block.get('model'):
                lines.append(f"    <model>{block['model']}</model>")
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

    def render_text_blocks_json(self, text_blocks: list[dict]) -> str:
        """渲染 text_blocks 为 JSON 字符串，包含 per-block 引用。"""
        import json as _json
        items = []
        for i, block in enumerate(text_blocks):
            item: dict = {"id": i + 1, "kr": block.get("kr", "")}
            if block.get("jp"):
                item["jp"] = block["jp"]
            if block.get("en"):
                item["en"] = block["en"]
            # Per-block 引用字段
            if block.get("proper_refs"):
                item["proper_refs"] = block["proper_refs"]
            if block.get("affect_refs"):
                item["affect_refs"] = block["affect_refs"]
            if block.get("model"):
                item["model"] = block["model"]
            items.append(item)
        return _json.dumps({"text_blocks": items}, ensure_ascii=False, indent=2) + "\n"

    def render_glossary_json(self, terms: list[dict]) -> str:
        """渲染 glossary 为 JSON 字符串。术语为空时省略。"""
        if not terms:
            return ""
        import json as _json
        items = []
        for t in terms:
            kr = t.get("kr", t.get("term", ""))
            cn = t.get("cn", t.get("translation", ""))
            note = t.get("note", "")
            entry = {"kr": kr, "cn": cn}
            if note:
                entry["note"] = note
            items.append(entry)
        return _json.dumps({"glossary": items}, ensure_ascii=False, indent=2) + "\n"

    def _render_examples_json(self, examples: list[dict]) -> str:
        """将 few-shot 示例渲染为 JSON。"""
        import json as _json
        items = []
        for ex in examples:
            item = {
                "in": ex.get("in", ""),
                "out": {
                    "translation": ex.get("translation", ""),
                }
            }
            if ex.get("reasoning"):
                item["out"]["reasoning"] = ex["reasoning"]
            if ex.get("confidence"):
                item["out"]["confidence"] = ex["confidence"]
            items.append(item)
        return _json.dumps({"examples": items}, ensure_ascii=False, indent=2) + "\n"

    def parse_response(self, text: str, stage: int, prompt_format: str) -> list[dict]:
        """按格式解析 LLM 响应，返回结构化数据列表。

        Args:
            text: LLM 原始响应文本
            stage: 0（消歧）、1（翻译）、2（自校验）
            prompt_format: "xml_json" | "xml_xml" | "json_json"

        Returns:
            解析后的 dict 列表；解析失败返回空列表
        """
        if prompt_format in ("xml_json", "json_json"):
            import json as _json
            try:
                data = _json.loads(text)
            except _json.JSONDecodeError:
                return []
            if stage == 0:
                return data.get("disambiguations", [])
            elif stage == 1:
                return data.get("translations", [])
            elif stage == 2:
                return data.get("checked_translations", [])
            return []
        elif prompt_format == "xml_xml":
            return self._parse_xml_response(text, stage)
        return []

    def _parse_xml_response(self, text: str, stage: int) -> list[dict]:
        """解析 XML 格式的 LLM 响应。"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []

        results: list[dict] = []

        if stage == 0:
            # <disambiguations><item term="..." applies="true" ... /></disambiguations>
            for item in root.findall("item"):
                results.append({
                    "term": item.get("term", ""),
                    "applies": item.get("applies", "").lower() in ("true", "1"),
                    "actual_meaning": item.get("actual_meaning", ""),
                    "reason": item.get("reason", ""),
                })
        elif stage == 1:
            # <translations><item id="1"><translation>...</translation>...</item></translations>
            for item in root.findall("item"):
                entry: dict = {"id": int(item.get("id", len(results) + 1))}
                trans_el = item.find("translation")
                entry["translation"] = trans_el.text if trans_el is not None and trans_el.text else ""
                reason_el = item.find("reasoning")
                entry["reasoning"] = reason_el.text if reason_el is not None and reason_el.text else ""
                conf_el = item.find("confidence")
                entry["confidence"] = conf_el.text if conf_el is not None and conf_el.text else "medium"
                results.append(entry)
        elif stage == 2:
            # <checked_translations><item id="1"><translation>...</translation>...</item></checked_translations>
            for item in root.findall("item"):
                entry: dict = {"id": int(item.get("id", len(results) + 1))}
                trans_el = item.find("translation")
                entry["translation"] = trans_el.text if trans_el is not None and trans_el.text else ""
                changed_el = item.find("changed")
                entry["changed"] = changed_el.text.lower() in ("true", "1") if changed_el is not None and changed_el.text else False
                reason_el = item.find("change_reason")
                entry["change_reason"] = reason_el.text if reason_el is not None and reason_el.text else ""
                results.append(entry)

        return results
