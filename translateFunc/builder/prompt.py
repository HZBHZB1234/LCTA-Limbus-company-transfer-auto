"""
translateFunc/builder/prompt.py
PromptTag 枚举与 PromptFactory —— 动态 XML 标签化提示词组装。

工厂按 FileType × Stage 选择模板，以 XML 标签渲染。
无内容的标签块自动省略。
"""
from __future__ import annotations
from enum import Enum, auto
import logging
from typing import Any

_logger = logging.getLogger("LCTA")  # 与 LogManager 一致，确保日志正确路由

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

    # ---- v2 提示词架构：数据驱动的规则 + 结构分离 ----

    _BASE_ROLE = (
        "<role>\n"
        "我是游戏'边狱公司(Limbus Company)'的专业本地化翻译员。\n"
        "我的任务是将韩文(KR)游戏文本翻译为简体中文(zh-CN)，\n"
        "目标是为中文玩家提供自然流畅的游戏体验。\n"
        "游戏文本包含代码占位符、富文本标签和技能描述等特殊格式，\n"
        "我会精确保留这些技术元素。\n"
        "</role>\n"
    )

    # 阶段 1 翻译规则 —— 按优先级排列
    _STAGE1_RULES_DATA: list[dict] = [
        {"priority": "P0", "text": "翻译优先级：以韩文(KR)为源语言；日文(JP)和英文(EN)仅作为理解辅助参考。当KR与JP/EN语义不一致时，以KR为准"},
        {"priority": "P0", "text": "术语一致性：先查看reference中的术语表及每条文本块的proper_refs/affect_refs/model引用，确保术语一致；术语内容可能存在错误引用，如果术语内容与原文意思偏差过大，忽略该术语"},
        {"priority": "P1", "text": "标点符号：中文翻译必须使用全角标点（！？，。：）、中文引号（“”），禁止使用半角标点(!?,. )"},
        {"priority": "P1", "text": "参数保护：原文中的尖括号参数（如<0>、<1>）是游戏代码占位符，不得破坏其格式；理解参数含义后按中文语序放置到语法正确的位置"},
        {"priority": "P2", "text": "省略号：剧情文本使用六点省略号……；技能/UI紧凑文本使用三点省略号…。原文为长省略号时对齐长度"},
        {"priority": "P2", "text": "波浪号：使用半角波浪号~，不得从原文复制全角波浪号～（游戏字库缺字会导致显示异常）"},
        {"priority": "P2", "text": "括号选择：剧情文本使用全角括号（）；技能/UI等紧凑文本优先使用半角括号()以减少留白"},
        {"priority": "P2", "text": "JSON引号：如原文前后有成对的半角引号包裹，可能是JSON格式标记，不可将其改为全角引号"},
        {"priority": "P2", "text": "保留原文的代码格式，如富文本标签和f-string占位符"},
    ]

    # 格式规则 —— 按响应格式分离，避免 JSON/XML 转义指令混淆导致解析失败
    # 共通规则（与响应格式无关）
    _COMMON_FORMAT_RULES_DATA: list[dict] = [
        {"priority": "P1", "text": "控制字符：原文的控制字符已被转义（如\\n），输出翻译时也使用转义后的字符"},
    ]
    # JSON 响应格式转义规则（xml_json / json_json 模式使用）
    _JSON_FORMAT_RULES_DATA: list[dict] = [
        {"priority": "P1", "text": "在JSON输出中，文本内的双引号必须转义为 \\\"，换行符写为 \\n，反斜杠写为 \\\\"},
    ]
    # XML 响应格式转义规则（xml_xml 模式使用）
    _XML_FORMAT_RULES_DATA: list[dict] = [
        {"priority": "P1", "text": "在XML输出中，文本内的双引号必须转义为 &quot;，& 写为 &amp;，< 写为 &lt;"},
    ]

    _STAGE0_RULES_DATA: list[dict] = [
        {"priority": "P0", "text": "你的任务是判断术语在当前上下文中是否适用，不需要翻译"},
        {"priority": "P0", "text": "对比术语的典型使用场景和当前文本块的JP/EN内容"},
        {"priority": "P1", "text": "如果术语明显不适用（如人名术语出现在技能描述中），标记为不适用"},
    ]

    _STAGE2_RULES_DATA: list[dict] = [
        {"priority": "P0", "text": "校验翻译结果中的术语一致性（与reference术语表对照）"},
        {"priority": "P1", "text": "校验标点符号：剧情文本是否使用全角标点（！？，。：）和中文引号（“”）；技能文本是否使用半角括号()和三点省略号…"},
        {"priority": "P1", "text": "校验特殊符号：波浪号是否为半角~；省略号剧情是否为六点……且技能为三点…；尖括号参数<N>格式是否完好无损"},
        {"priority": "P1", "text": "校验代码格式：富文本标签、f-string占位符是否完整保留且未被翻译"},
        {"priority": "P2", "text": "检查JSON格式标记（如原文有前后半角引号包裹的文本）是否保留了格式引号"},
        {"priority": "P2", "text": "发现错误时自动修正，并给出具体修正说明（改了什么、为什么）"},
    ]

    # FileType 特有规则
    _FILETYPE_RULES: dict = {
        "STORY": [
            {"priority": "P1", "text": "角色语气一致性：保持角色性格对应的语言风格"},
        ],
        "SKILL": [
            {"priority": "P0", "text": "Buff名称空格（强制）：所有Buff/状态效果的中文名称翻译后必须后跟一个半角空格（如'震颤 '），即使位于句尾或标点前也绝不可省略此空格。示例：'施加2层震颤 。'正确，'施加2层震颤。'错误。除非位于[]中"},
            {"priority": "P0", "text": "위력↔强度、횟수↔层数"},
            {"priority": "P1", "text": "技能描述紧凑：技能效果描述需精炼，Buff/Debuff名称遵循术语表约定"},
        ],
        "UI": [
            {"priority": "P1", "text": "UI标签简洁：按钮/标签文本尽量简短，不加句号等多余标点"},
        ],
    }

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

    # v2: reasoning 在 translation 之前，强制 LLM 先思考再翻译
    _STAGE1_FORMAT = (
        "<format>\n"
        "返回JSON对象，包含translations字段。\n"
        "每条翻译先输出reasoning（关键决策说明），再输出translation（翻译结果）：\n"
        "{\n"
        '  "translations": [\n'
        '    {"id": 1,\n'
        '     "reasoning": "先说明关键决策：术语选择、歧义处理、风格考量",\n'
        '     "translation": "再输出译文",\n'
        '     "confidence": "high|medium|low"}\n'
        "  ]\n"
        "}\n"
        "数量约束（必须严格遵守）：\n"
        "- translations数组的长度必须等于输入text_blocks的数量，不得多出或遗漏\n"
        "- 每条translation的id必须与对应text_block的id一致（按id一一对应）\n"
        "- 不得合并、拆分或跳过任何文本块；每个文本块必须且只能产出一条翻译\n"
        "confidence为low的条目说明翻译不确定，需要回退到原文。\n"
        "</format>\n"
    )

    # v2: 阶段 2 增加结构化 verification 字段
    _STAGE2_FORMAT = (
        "<format>\n"
        "返回JSON对象，包含checked_translations字段：\n"
        "{\n"
        '  "checked_translations": [\n'
        '    {"id": 1, "translation": "修正后的翻译",\n'
        '     "changed": false, "change_reason": "",\n'
        '     "verification": {\n'
        '       "terminology_ok": true,\n'
        '       "punctuation_ok": true,\n'
        '       "format_ok": true,\n'
        '       "notes": "术语一致，标点正确"\n'
        '     }}\n'
        "  ]\n"
        "}\n"
        "数量约束：checked_translations数组长度必须等于输入翻译数量；每条id必须与对应翻译的id一致。\n"
        "</format>\n"
    )

    # ---- JSON 格式的 format 模板（json_json 模式使用） ----

    _JSON_STAGE0_FORMAT = (
        '{\n'
        '  "format": {\n'
        '    "response_type": "json_object",\n'
        '    "description": "返回JSON对象，包含disambiguations字段",\n'
        '    "schema": {\n'
        '      "disambiguations": [\n'
        '        {"term": "术语KR", "applies": true, "actual_meaning": "在此上下文中的实际含义", "reason": "判断理由"}\n'
        '      ]\n'
        '    },\n'
        '    "escaping": "字符串值中的换行符必须写为 \\\\n，双引号必须写为 \\\\"，反斜杠必须写为 \\\\\\\\；确保输出是合法JSON"\n'
        '  }\n'
        '}\n'
    )

    _JSON_STAGE1_FORMAT = (
        '{\n'
        '  "format": {\n'
        '    "response_type": "json_object",\n'
        '    "description": "返回JSON对象，包含translations字段。每条先输出reasoning再输出translation",\n'
        '    "schema": {\n'
        '      "translations": [\n'
        '        {"id": 1, "reasoning": "先说明关键决策：术语选择、歧义处理、风格考量", "translation": "再输出译文", "confidence": "high|medium|low"}\n'
        '      ]\n'
        '    },\n'
        '    "count_constraint": "translations数组长度必须等于输入text_blocks数量；每条id必须与对应text_block的id一致",\n'
        '    "note": "confidence为low的条目说明翻译不确定，需要回退到原文",\n'
        '    "escaping": "字符串值中的换行符必须写为 \\\\n，双引号必须写为 \\\\"，反斜杠必须写为 \\\\\\\\；确保输出是合法JSON"\n'
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
        '        {"id": 1, "translation": "修正后的翻译", "changed": false, "change_reason": "",\n'
        '         "verification": {"terminology_ok": true, "punctuation_ok": true, "format_ok": true, "notes": "术语一致，标点正确"}}\n'
        '      ]\n'
        '    },\n'
        '    "count_constraint": "checked_translations数组长度必须等于输入翻译数量；每条id必须与对应翻译的id一致",\n'
        '    "escaping": "字符串值中的换行符必须写为 \\\\n，双引号必须写为 \\\\"，反斜杠必须写为 \\\\\\\\；确保输出是合法JSON"\n'
        '  }\n'
        '}\n'
    )

    # ---- XML 格式的 format 模板（xml_json / xml_xml 共享 role/rules，区分 format） ----

    _XML_STAGE0_FORMAT = _STAGE0_FORMAT  # 原 _STAGE0_FORMAT，请求 JSON 响应

    _XML_STAGE0_FORMAT_XML = (
        "<format>\n"
        "返回XML，包含<disambiguations>根元素：\n"
        "<disambiguations>\n"
        "  <item>\n"
        "    <term>术语KR</term>\n"
        "    <applies>true</applies>\n"
        "    <actual_meaning>在此上下文中的实际含义</actual_meaning>\n"
        "    <reason>判断理由</reason>\n"
        "  </item>\n"
        "</disambiguations>\n"
        "</format>\n"
    )

    _XML_STAGE1_FORMAT = _STAGE1_FORMAT  # 原 _STAGE1_FORMAT，请求 JSON 响应

    _XML_STAGE1_FORMAT_XML = (
        "<format>\n"
        "返回XML，包含<translations>根元素。\n"
        "每条先输出<reasoning>再输出<translation>：\n"
        "<translations>\n"
        '  <item id="1">\n'
        "    <reasoning>先说明关键决策：术语选择、歧义处理、风格考量</reasoning>\n"
        "    <translation>再输出译文</translation>\n"
        "    <confidence>high|medium|low</confidence>\n"
        "  </item>\n"
        "</translations>\n"
        "数量约束（必须严格遵守）：\n"
        "- translations下item的数量必须等于输入text_blocks的数量，不得多出或遗漏\n"
        "- 每个item的id必须与对应text_block的id一致（按id一一对应）\n"
        "- 不得合并、拆分或跳过任何文本块；每个文本块必须且只能产出一条翻译\n"
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
        "    <verification>\n"
        "      <terminology_ok>true</terminology_ok>\n"
        "      <punctuation_ok>true</punctuation_ok>\n"
        "      <format_ok>true</format_ok>\n"
        "      <notes>术语一致，标点正确</notes>\n"
        "    </verification>\n"
        "  </item>\n"
        "</checked_translations>\n"
        "</format>\n"
    )

    # ========== 工具方法 ==========

    @staticmethod
    def _xml_escape(text: str) -> str:
        """转义 XML 特殊字符（&, <, >, "）。"""
        if not isinstance(text, str):
            return str(text)
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace("\"", "&quot;")
        return text

    # ========== 公开 API ==========

    # ---- 阶段 0 system prompt（仅指令，不含数据） ----

    def build_stage_0_system_prompt(self, prompt_format: str = "xml_json") -> str:
        """构建阶段 0（消歧）的 system prompt —— 仅含 role + rules + format。

        与 build_system_prompt(stage=0) 的区别：stage 0 有专用的 role
        （"你是边狱公司的术语专家"），且不含 candidate_terms / text_blocks 数据。
        """
        is_json = (prompt_format == "json_json")
        is_xml_response = (prompt_format == "xml_xml")

        # Role
        if is_json:
            parts: list[str] = ['{\n  "role": "你是边狱公司的术语专家。"\n}\n']
        else:
            parts: list[str] = ["<role>你是边狱公司的术语专家。</role>\n"]

        # Rules (使用 v2 数据驱动渲染)
        parts.append(self._render_rules(self._STAGE0_RULES_DATA, is_json=is_json))

        # Output Format
        if is_json:
            parts.append(self._JSON_STAGE0_FORMAT)
        else:
            parts.append(self._XML_STAGE0_FORMAT_XML if is_xml_response else self._XML_STAGE0_FORMAT)

        return "\n".join(parts)

    def build_stage_0_user_message(
        self,
        candidate_terms: list[dict],
        text_blocks: list[dict],
        prompt_format: str = "xml_json",
    ) -> str:
        """构建阶段 0（消歧）的 user message —— 仅含候选术语和文本块上下文数据。

        不含 role / rules / format spec —— 这些已在 system prompt 中。
        """
        is_json = (prompt_format == "json_json")

        if is_json:
            import json as _json
            return _json.dumps({
                "task": "判断以下候选术语在当前文本上下文中是否适用",
                "candidate_terms": [
                    {"kr": t["kr"], "cn": t["cn"], "note": t.get("note", "")}
                    for t in candidate_terms
                ],
                "text_blocks": [
                    {"id": i + 1, "kr": b.get("kr", ""), "jp": b.get("jp", ""), "en": b.get("en", "")}
                    for i, b in enumerate(text_blocks[:3])
                ],
            }, ensure_ascii=False, indent=2)

        term_list = "\n".join(
            f"  - {self._xml_escape(t['kr'])} → {self._xml_escape(t['cn'])}" + (f" ({self._xml_escape(t.get('note', ''))})" if t.get('note') else "")
            for t in candidate_terms
        )
        block_text = ""
        for i, block in enumerate(text_blocks[:3]):
            block_text += (
                f"<block id=\"{i+1}\">\n"
                f"  <kr>{self._xml_escape(block.get('kr', ''))}</kr>\n"
                f"  <jp>{self._xml_escape(block.get('jp', ''))}</jp>\n"
                f"  <en>{self._xml_escape(block.get('en', ''))}</en>\n"
                f"</block>\n"
            )

        return (
            f"<task>判断以下候选术语在当前文本上下文中是否适用</task>\n"
            f"<context>\n"
            f"候选术语：\n{term_list}\n"
            f"当前文本：\n{block_text}"
            f"</context>\n"
        )

    # ---- 通用 system prompt（stage 1/2 使用） ----

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
        return self._build_system_prompt(file_type, stage, prompt_format, examples=examples)

    def _build_system_prompt(
        self, file_type: FileType, stage: int, prompt_format: str, *,
        examples: list[dict] | None = None,
    ) -> str:
        """构建系统提示词：
        role → translation_rules → format_rules → examples → output_format

        rules 带 priority 标记，reasoning 在 translation 之前。
        format_rules 按响应格式（JSON/XML）选择，避免转义指令混淆。
        """
        is_json = (prompt_format == "json_json")
        is_xml_response = (prompt_format == "xml_xml")

        parts: list[str] = []

        # 1. Role
        if is_json:
            parts.append(self._render_role_json())
        else:
            parts.append(self._BASE_ROLE)

        # 2. Translation Rules (semantic rules with priority)
        if stage == 0:
            rules_data = self._STAGE0_RULES_DATA
        elif stage == 1:
            rules_data = list(self._STAGE1_RULES_DATA)
            # FileType 特有规则
            if file_type.name in self._FILETYPE_RULES:
                rules_data.extend(self._FILETYPE_RULES[file_type.name])
        elif stage == 2:
            rules_data = list(self._STAGE2_RULES_DATA)
            # FileType 特有规则
            if file_type.name in self._FILETYPE_RULES:
                rules_data.extend(self._FILETYPE_RULES[file_type.name])
        else:
            rules_data = []

        if rules_data:
            parts.append(self._render_rules(rules_data, is_json=is_json))

        # 3. Format Rules (technical escape rules, only for stage 1)
        #    按响应格式选择：JSON 响应用 JSON 转义规则，XML 响应用 XML 转义规则
        if stage == 1:
            format_rules = list(self._COMMON_FORMAT_RULES_DATA)
            if is_xml_response:
                format_rules.extend(self._XML_FORMAT_RULES_DATA)
            else:
                format_rules.extend(self._JSON_FORMAT_RULES_DATA)
            if format_rules:
                parts.append(self._render_format_rules(format_rules, is_json=is_json))

        # 4. Examples
        if examples and not is_json:
            parts.append(self._render_examples(examples))
        elif examples and is_json:
            parts.append(self._render_examples_json(examples))

        # 5. Output Format (last, as concrete instruction)
        if is_json:
            if stage == 0:
                parts.append(self._JSON_STAGE0_FORMAT)
            elif stage == 1:
                parts.append(self._JSON_STAGE1_FORMAT)
            elif stage == 2:
                parts.append(self._JSON_STAGE2_FORMAT)
        else:
            if stage == 0:
                parts.append(self._XML_STAGE0_FORMAT_XML if is_xml_response else self._XML_STAGE0_FORMAT)
            elif stage == 1:
                parts.append(self._XML_STAGE1_FORMAT_XML if is_xml_response else self._XML_STAGE1_FORMAT)
            elif stage == 2:
                parts.append(self._XML_STAGE2_FORMAT_XML if is_xml_response else self._XML_STAGE2_FORMAT)

        return "\n".join(parts)

    # ========== v2 渲染辅助方法 ==========

    def _render_role_json(self) -> str:
        """v2 JSON 格式的 role 渲染。"""
        return (
            '{\n'
            '  "role": "我是游戏\'边狱公司(Limbus Company)\'的专业本地化翻译员。'
            '我的任务是将韩文(KR)游戏文本翻译为简体中文(zh-CN)。'
            '游戏文本包含代码占位符、富文本标签和技能描述等特殊格式，'
            '我会精确保留这些技术元素。"\n'
            '}\n'
        )

    @staticmethod
    def _render_rules(rules: list[dict], is_json: bool = False) -> str:
        """将规则列表渲染为 XML 或 JSON 格式，带 priority 标记。"""
        if is_json:
            items = [f'    {{"priority": "{r["priority"]}", "text": "{r["text"]}"}}' for r in rules]
            return '{\n  "translation_rules": [\n' + ",\n".join(items) + "\n  ]\n}\n"
        else:
            lines = ["<translation_rules>"]
            for r in rules:
                lines.append(f'  <rule priority="{r["priority"]}">{r["text"]}</rule>')
            lines.append("</translation_rules>")
            return "\n".join(lines) + "\n"

    @staticmethod
    def _render_format_rules(rules: list[dict], is_json: bool = False) -> str:
        """将格式规则列表渲染为 XML 或 JSON 格式。"""
        if is_json:
            items = [f'    {{"priority": "{r["priority"]}", "text": "{r["text"]}"}}' for r in rules]
            return '{\n  "format_rules": [\n' + ",\n".join(items) + "\n  ]\n}\n"
        else:
            lines = ["<format_rules>"]
            for r in rules:
                lines.append(f'  <rule priority="{r["priority"]}">{r["text"]}</rule>')
            lines.append("</format_rules>")
            return "\n".join(lines) + "\n"

    # ========== 内部渲染器 ==========

    def _render_role_styles(self, styles: list[dict]) -> str:
        """将角色风格参考渲染为 XML。"""
        lines = ["<role_styles>"]
        for s in styles:
            lines.append(f"  <style>")
            for k, v in s.items():
                lines.append(f"    <{self._xml_escape(k)}>{self._xml_escape(v)}</{self._xml_escape(k)}>")
            lines.append(f"  </style>")
        lines.append("</role_styles>")
        return "\n".join(lines) + "\n"

    def _render_examples(self, examples: list[dict]) -> str:
        """将 few-shot 示例渲染为 XML。"""
        lines = ["<examples>"]
        for ex in examples:
            lines.append("  <example>")
            lines.append(f"    <in>{self._xml_escape(ex.get('in', ''))}</in>")
            lines.append(f"    <out>")
            lines.append(f"      <translation>{self._xml_escape(ex.get('translation', ''))}</translation>")
            if ex.get('reasoning'):
                lines.append(f"      <reasoning>{self._xml_escape(ex['reasoning'])}</reasoning>")
            if ex.get('confidence'):
                lines.append(f"      <confidence>{self._xml_escape(ex['confidence'])}</confidence>")
            lines.append(f"    </out>")
            lines.append("  </example>")
        lines.append("</examples>")
        return "\n".join(lines) + "\n"

    def render_text_blocks(self, text_blocks: list[dict]) -> str:
        """渲染 <text> 节，包含 kr/jp/en 文本块及 per-block 引用。"""
        lines = ["<text>"]
        for i, block in enumerate(text_blocks):
            lines.append(f'  <block id="{i + 1}">')
            lines.append(f"    <kr>{self._xml_escape(block.get('kr', ''))}</kr>")
            if block.get('jp'):
                lines.append(f"    <jp>{self._xml_escape(block.get('jp', ''))}</jp>")
            if block.get('en'):
                lines.append(f"    <en>{self._xml_escape(block.get('en', ''))}</en>")
            # Per-block 引用字段
            if block.get('proper_refs'):
                refs = ", ".join(block['proper_refs'])
                lines.append(f"    <proper_refs>{self._xml_escape(refs)}</proper_refs>")
            if block.get('affect_refs'):
                refs = ", ".join(block['affect_refs'])
                lines.append(f"    <affect_refs>{self._xml_escape(refs)}</affect_refs>")
            if block.get('model'):
                lines.append(f"    <model>{self._xml_escape(block['model'])}</model>")
            lines.append(f"  </block>")
        lines.append("</text>")
        return "\n".join(lines) + "\n"

    def render_glossary(self, terms: list[dict]) -> str:
        """渲染 <glossary> 节。术语为空时省略。"""
        if not terms:
            return ""
        lines = ["<glossary>"]
        for t in terms:
            kr = self._xml_escape(t.get('kr', t.get('term', '')))
            cn = self._xml_escape(t.get('cn', t.get('translation', '')))
            note = self._xml_escape(t.get('note', ''))
            lines.append("  <term>")
            lines.append(f"    <kr>{kr}</kr>")
            lines.append(f"    <cn>{cn}</cn>")
            if t.get('note'):
                lines.append(f"    <note>{note}</note>")
            lines.append("  </term>")
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

        解析失败时先尝试修复（剥离 markdown 围栏、提取内容、修复常见格式错误），
        修复仍失败才返回空列表。

        Args:
            text: LLM 原始响应文本
            stage: 0（消歧）、1（翻译）、2（自校验）
            prompt_format: "xml_json" | "xml_xml" | "json_json"

        Returns:
            解析后的 dict 列表；所有尝试失败返回空列表
        """
        if prompt_format in ("xml_json", "json_json"):
            data = self._try_parse_json(text)
            if data is None:
                data = self._repair_json_response(text)
            if data is None:
                import logging
                _logger.warning(
                    f"parse_response JSON 全部修复失败 "
                    f"(stage={stage}, format={prompt_format}), "
                    f"原始文本 (截断500字符): {text[:500]}"
                )
                return []
            if stage == 0:
                return data.get("disambiguations", [])
            elif stage == 1:
                return data.get("translations", [])
            elif stage == 2:
                return data.get("checked_translations", [])
            return []
        elif prompt_format == "xml_xml":
            results = self._try_parse_xml(text, stage)
            if results is None:
                results = self._repair_xml_response(text, stage)
            if results is None:
                import logging
                _logger.warning(
                    f"parse_response XML 全部修复失败 "
                    f"(stage={stage}, format={prompt_format}), "
                    f"原始文本 (截断500字符): {text[:500]}"
                )
                return []
            return results
        return []

    # ========== 解析辅助：直接尝试 ==========

    @staticmethod
    def _try_parse_json(text: str) -> dict | None:
        """尝试直接 JSON 解析，失败返回 None。"""
        import json as _json
        try:
            return _json.loads(text)
        except _json.JSONDecodeError:
            return None

    def _try_parse_xml(self, text: str, stage: int) -> list[dict] | None:
        """尝试直接 XML 解析，失败返回 None。"""
        start = text.find('<')
        end = text.rfind('>')
        if start == -1 or end == -1 or end <= start:
            return None
        text = text[start:end + 1]
        result = self._parse_xml_response(text, stage)
        return result if result else None

    # ========== 解析修复 ==========

    @staticmethod
    def _repair_json_response(text: str) -> dict | None:
        """修复常见 JSON 格式问题后尝试解析。

        处理：markdown 代码围栏、周围文本、尾部逗号、控制字符。
        """
        import json as _json
        import re

        if not text or not text.strip():
            return None

        cleaned = text.strip()

        # 1. 剥离 BOM
        if cleaned.startswith('﻿'):
            cleaned = cleaned[1:]

        # 2. 剥离 markdown 代码围栏
        fence_patterns = [
            (r'^```(?:json)?\s*\n', r'\n?```\s*$'),
        ]
        for start_pat, end_pat in fence_patterns:
            if re.match(start_pat, cleaned):
                cleaned = re.sub(start_pat, '', cleaned, count=1)
                cleaned = re.sub(end_pat, '', cleaned, count=1)
                cleaned = cleaned.strip()
                break

        # 3. 提取第一个 { 到最后一个 } 之间的内容
        first_brace = cleaned.find('{')
        last_brace = cleaned.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace:last_brace + 1]

        if not cleaned:
            return None

        # 4. 尝试严格解析
        try:
            return _json.loads(cleaned)
        except _json.JSONDecodeError:
            pass

        # 5. 修复尾部逗号（对象和数组）
        try:
            fixed = re.sub(r',(\s*[}\]])', r'\1', cleaned)
            return _json.loads(fixed)
        except _json.JSONDecodeError:
            pass

        # 6. 放宽控制字符限制
        try:
            decoder = _json.JSONDecoder(strict=False)
            return decoder.decode(cleaned)
        except _json.JSONDecodeError:
            pass

        # 7. 修复单引号 JSON（将结构位置的 ' 替换为 "）
        try:
            # 简单启发式：在 {, [, ,, :, 空白 后的 ' 和 :, ,, }, ], 空白 前的 '
            fixed_sq = re.sub(r"(?<=[\{\[\:,])\s*'|'\s*(?=[\,\}\]\:])", '"', cleaned)
            if fixed_sq != cleaned:
                return _json.loads(fixed_sq)
        except _json.JSONDecodeError:
            pass

        # 8. 修复非标准字面量：NaN → null, Infinity → "Infinity"
        try:
            fixed_nan = re.sub(r'\bNaN\b', 'null', cleaned)
            fixed_nan = re.sub(r'\b-?Infinity\b', 'null', fixed_nan)
            if fixed_nan != cleaned:
                return _json.loads(fixed_nan)
        except _json.JSONDecodeError:
            pass

        # 9. 修复嵌套转义（\\\\n → \\n, \\\\\" → \\\"）—— 最后手段，可能改变内容
        try:
            fixed_esc = cleaned.replace('\\\\\\\\n', '\\\\n')
            fixed_esc = fixed_esc.replace('\\\\\\\\\"', '\\\\\"')
            if fixed_esc != cleaned:
                _double_newline = '\\\\n'
                _double_quote = '\\"'
                _logger.warning(
                    "JSON 修复：应用嵌套转义修复（最后手段），"
                    "替换了 %d 个 %s 和 %d 个 %s",
                    cleaned.count('\\\\\\\\n'), _double_newline,
                    cleaned.count('\\\\\\\\\"'), _double_quote,
                )
                return _json.loads(fixed_esc)
        except _json.JSONDecodeError:
            pass

        return None

    @staticmethod
    def _repair_xml_response(text: str, stage: int) -> list[dict] | None:
        """修复常见 XML 格式问题后尝试解析。

        处理：markdown 代码围栏、未转义 & 符号、多余文本。
        """
        import re
        import xml.etree.ElementTree as ET

        if not text or not text.strip():
            return None

        cleaned = text.strip()

        # 1. 剥离 markdown 代码围栏
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:xml)?\s*\n', '', cleaned, count=1)
            cleaned = re.sub(r'\n?```\s*$', '', cleaned, count=1)
            cleaned = cleaned.strip()

        # 2. 提取第一个 < 到最后一个 > 之间的内容
        first_lt = cleaned.find('<')
        last_gt = cleaned.rfind('>')
        if first_lt == -1 or last_gt == -1 or last_gt <= first_lt:
            return None
        cleaned = cleaned[first_lt:last_gt + 1]

        if not cleaned:
            return None

        # 3. 移除命名空间前缀（如 <ns:tag> → <tag>）
        cleaned = re.sub(r'(</?)\w+:', r'\1', cleaned)

        # 4. 修复未引号属性值（如 id=1 → id="1"）
        cleaned = re.sub(r'(\w+)=(\d+)', r'\1="\2"', cleaned)
        cleaned = re.sub(r'(\w+)="(\d+)"\s+(\w+)="(\d+)"', r'\1="\2" \3="\4"', cleaned)

        # 5. 尝试直接解析
        try:
            root = ET.fromstring(cleaned)
            return PromptFactory._parse_xml_response_static(root, stage)
        except ET.ParseError:
            pass

        # 6. 修复裸 & 符号（不破坏已有的合法实体）
        known_entities = {'&amp;', '&lt;', '&gt;', '&quot;', '&apos;', '&#39;'}
        # 找到所有 &...; 模式，保护已知实体，转义其余 &
        def _fix_ampersands(xml_text: str) -> str:
            # 匹配 & 后跟非空白字符，可能构成实体或裸 &
            result = []
            i = 0
            while i < len(xml_text):
                if xml_text[i] == '&':
                    # 检查是否已是合法实体
                    semicolon = xml_text.find(';', i)
                    if semicolon != -1 and semicolon - i <= 10:
                        entity = xml_text[i:semicolon + 1]
                        if entity in known_entities or re.match(r'^&#\d+;$', entity) or re.match(r'^&#x[0-9a-fA-F]+;$', entity):
                            result.append(entity)
                            i = semicolon + 1
                            continue
                    # 裸 &，转义
                    result.append('&amp;')
                    i += 1
                else:
                    result.append(xml_text[i])
                    i += 1
            return ''.join(result)

        try:
            fixed = _fix_ampersands(cleaned)
            if fixed != cleaned:
                root = ET.fromstring(fixed)
                return PromptFactory._parse_xml_response_static(root, stage)
        except ET.ParseError:
            pass

        # 7. 最终回退：用正则从乱 XML 中提取关键字段
        return PromptFactory._regex_extract_xml(cleaned, stage)

    @staticmethod
    def _parse_xml_response_static(root, stage: int) -> list[dict]:
        """_parse_xml_response 的静态版本，供 _repair_xml_response 调用。"""
        results: list[dict] = []

        if stage == 0:
            for item in root.findall("item"):
                term_el = item.find("term")
                applies_el = item.find("applies")
                meaning_el = item.find("actual_meaning")
                reason_el = item.find("reason")
                applies_text = applies_el.text if applies_el is not None and applies_el.text else ""
                results.append({
                    "term": term_el.text if term_el is not None and term_el.text else "",
                    "applies": applies_text.lower() in ("true", "1"),
                    "actual_meaning": meaning_el.text if meaning_el is not None and meaning_el.text else "",
                    "reason": reason_el.text if reason_el is not None and reason_el.text else "",
                })
        elif stage == 1:
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

    def _parse_xml_response(self, text: str, stage: int) -> list[dict]:
        """解析 XML 格式的 LLM 响应。委托给静态实现。"""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        return self._parse_xml_response_static(root, stage)

    @staticmethod
    def _regex_extract_xml(text: str, stage: int) -> list[dict] | None:
        """XML 全部修复失败时的最终回退：用正则从乱 XML 中提取关键字段。"""
        import re

        results: list[dict] = []
        # 匹配 <item ...> ... </item> 块
        item_pattern = re.compile(
            r'<item[^>]*?>(.*?)</item>',
            re.DOTALL | re.IGNORECASE,
        )
        items = item_pattern.findall(text)
        if not items:
            return None

        for idx, item_text in enumerate(items):
            entry: dict = {"id": idx + 1}

            # 提取 id 属性
            id_match = re.search(r'<item[^>]*?\bid\s*=\s*["\']?(\d+)', item_text, re.IGNORECASE)
            if id_match:
                entry["id"] = int(id_match.group(1))

            if stage == 0:
                _extract_tag(item_text, "term", entry)
                applies = _extract_tag(item_text, "applies", entry, default="false")
                entry["applies"] = applies.lower() in ("true", "1")
                _extract_tag(item_text, "actual_meaning", entry)
                _extract_tag(item_text, "reason", entry)
            elif stage == 1:
                _extract_tag(item_text, "translation", entry)
                _extract_tag(item_text, "reasoning", entry)
                conf = _extract_tag(item_text, "confidence", entry, default="medium")
                entry["confidence"] = conf if conf in ("high", "medium", "low") else "medium"
            elif stage == 2:
                _extract_tag(item_text, "translation", entry)
                changed = _extract_tag(item_text, "changed", entry, default="false")
                entry["changed"] = changed.lower() in ("true", "1")
                _extract_tag(item_text, "change_reason", entry)
                # 尝试提取 verification 子字段
                verif = {}
                _extract_tag(item_text, "terminology_ok", verif, default="true")
                _extract_tag(item_text, "punctuation_ok", verif, default="true")
                _extract_tag(item_text, "format_ok", verif, default="true")
                _extract_tag(item_text, "notes", verif)
                if verif:
                    entry["verification"] = {
                        "terminology_ok": verif.get("terminology_ok", "true").lower() in ("true", "1"),
                        "punctuation_ok": verif.get("punctuation_ok", "true").lower() in ("true", "1"),
                        "format_ok": verif.get("format_ok", "true").lower() in ("true", "1"),
                        "notes": verif.get("notes", ""),
                    }

            # 只保留有内容的条目
            if stage == 0 and entry.get("term"):
                results.append(entry)
            elif stage == 1 and entry.get("translation"):
                results.append(entry)
            elif stage == 2 and entry.get("translation"):
                results.append(entry)

        return results if results else None


def _extract_tag(text: str, tag: str, dest: dict, default: str = "") -> str:
    """从 XML 文本中用正则提取单个标签的内容。返回提取的值。"""
    import re
    pattern = re.compile(
        rf'<{tag}[^>]*?>(.*?)</{tag}>',
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    value = match.group(1).strip() if match else default
    dest[tag] = value
    return value
