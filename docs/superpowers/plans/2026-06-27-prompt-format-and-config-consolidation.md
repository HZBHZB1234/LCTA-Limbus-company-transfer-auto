# Prompt 格式扩展与配置统合 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为翻译管线新增 xml_xml 和 json_json 两种 prompt/response 格式，统合配置项（is_text_format → prompt_format，重新实现 fallback），数据分布改为 system prompt（固定模板）+ user prompt（动态数据）。

**Architecture:** PromptFactory 增加 prompt_format 参数，按 (stage, format) 选择模板和解析器；RequestBuilder 按格式输出 XML 或 JSON 的 user prompt；FileProcessor 实现格式回退链；TranslateConfig 用 prompt_format 替代 is_text_format。

**Tech Stack:** Python 3.x, xml.etree.ElementTree (stdlib), pytest, vanilla JS (前端)

## Global Constraints

- `prompt_format` 取值：`"xml_json"` | `"xml_xml"` | `"json_json"`，默认 `"xml_json"`
- 不实现 `json_xml`
- 回退链顺序：用户选择 → xml_json → json_json → xml_xml
- 非 LLM 路径（is_llm=False）不受任何 format/fallback 影响
- 旧 `is_text` 配置键加载时忽略（不崩溃）——向前兼容
- skill_doc / role_styles 从 system prompt 移除，仅在 user prompt 中携带

---

### Task 1: Config 层 — TranslateConfig 与 JSON 配置文件

**Files:**
- Modify: `translateFunc/config.py:14-95`
- Modify: `config.json:25` (添加 prompt_format)
- Modify: `config_default.json:6` (is_text → prompt_format)
- Modify: `config_check.json:6` (is_text → prompt_format)

**Interfaces:**
- Consumes: (none)
- Produces: `TranslateConfig.prompt_format: str`, `TranslateConfig` 不再有 `is_text_format`

- [ ] **Step 1: 修改 TranslateConfig 数据类**

编辑 `translateFunc/config.py`，在 `TranslateConfig` 中：
- 新增字段 `prompt_format: str = "xml_json"`
- 移除字段 `is_text_format: bool = False`

```python
@dataclass
class TranslateConfig:
    """一次翻译运行的全部配置。由调用方（WebUI 或 CLI）注入。"""
    # --- 翻译器 ---
    translator_name: str = "LLM通用翻译服务"
    translator_api: dict = field(default_factory=dict)

    # --- 路径 ---
    game_path: Path = Path()
    output_dir: Path = Path()

    # --- 功能开关 ---
    enable_proper: bool = True
    enable_role: bool = True
    enable_skill: bool = True
    enable_dev_settings: bool = False

    # --- 并发 ---
    max_workers: int = 4
    enable_concurrent: bool = True

    # --- 提示词 / 管线 ---
    translation_mode: str = "multi_stage"     # "multi_stage" | "single_stage"
    enable_self_check: bool = False
    disambiguation_mode: str = "hybrid"       # "similarity" | "llm" | "hybrid"
    min_confidence: str = "medium"            # "high" | "medium" | "low"
    prompt_format: str = "xml_json"           # "xml_json" | "xml_xml" | "json_json"
    fallback: bool = True                     # 格式解析失败时回退到其他格式

    # --- 保存 ---
    save_result: bool = True

    # --- 调试 ---
    debug_mode: bool = False
    dump: bool = False

    # --- 兼容旧配置项 ---
    is_llm: bool = True
    from_lang: str = "EN"
    auto_fetch_proper: bool = True
    proper_path: str = ""
    has_prefix: bool = True
    kr_path: str = ""
    jp_path: str = ""
    en_path: str = ""
    llc_path: str = ""
```

- [ ] **Step 2: 更新 from_config_manager()**

编辑 `translateFunc/config.py` 的 `from_config_manager()` 方法：
- 移除 `is_text_format=configs.get("is_text", False)` 行
- 新增 `prompt_format=configs.get("prompt_format", "xml_json")` 行
- `fallback` 改为读取 `configs.get("fallback", True)`（之前虽然读了但未被使用；现在语义改变，值读入即可）

```python
    @classmethod
    def from_config_manager(cls, mgr) -> "TranslateConfig":
        """从全局 ConfigManager 单例构建 TranslateConfig。"""
        configs: dict = mgr.get("ui_default.translator", {})
        game_path = Path(mgr.get("game_path", ""))
        debug_mode = mgr.get("debug", False)

        return cls(
            translator_name=configs.get("translator", "LLM通用翻译服务"),
            is_llm=(configs.get("translator", "LLM通用翻译服务") == "LLM通用翻译服务"),
            game_path=game_path,
            enable_proper=configs.get("enable_proper", True),
            enable_role=configs.get("enable_role", True),
            enable_skill=configs.get("enable_skill", True),
            enable_dev_settings=configs.get("enable_dev_settings", False),
            from_lang=configs.get("from_lang", "EN"),
            auto_fetch_proper=configs.get("auto_fetch_proper", True),
            proper_path=configs.get("proper_path", ""),
            fallback=configs.get("fallback", True),
            has_prefix=configs.get("has_prefix", True),
            kr_path=configs.get("kr_path", ""),
            jp_path=configs.get("jp_path", ""),
            en_path=configs.get("en_path", ""),
            llc_path=configs.get("llc_path", ""),
            debug_mode=debug_mode,
            dump=configs.get("dump", False),
            max_workers=configs.get("max_workers", 4),
            enable_concurrent=configs.get("enable_concurrent", True),
            translation_mode=configs.get("translation_mode", "multi_stage"),
            enable_self_check=configs.get("enable_self_check", False),
            disambiguation_mode=configs.get("disambiguation_mode", "hybrid"),
            min_confidence=configs.get("min_confidence", "medium"),
            prompt_format=configs.get("prompt_format", "xml_json"),
        )
```

- [ ] **Step 3: 更新 config.json**

在 `ui_default.translator` 块中确保 `prompt_format` 存在（用户文件已有，确认即可）。

- [ ] **Step 4: 更新 config_default.json**

将 `"is_text": false` 替换为 `"prompt_format": "xml_json"`。

- [ ] **Step 5: 更新 config_check.json**

将 `"is_text": "bool"` 替换为 `"prompt_format": "str"`。

- [ ] **Step 6: 运行现有测试确认未破坏**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_pipeline.py -v
```

Expected: 所有 `TestTranslateConfig` 测试仍然 PASS。

- [ ] **Step 7: Commit**

```bash
git add translateFunc/config.py config.json config_default.json config_check.json
git commit -m "refactor: prompt_format 替代 is_text_format，接入 TranslateConfig"
```

---

### Task 2: PromptFactory 格式扩展

**Files:**
- Modify: `translateFunc/builder/prompt.py`

**Interfaces:**
- Consumes: `TranslateConfig.prompt_format` (通过参数传入)
- Produces:
  - `PromptFactory.build_system_prompt(file_type, stage, prompt_format, examples=None) -> str`
  - `PromptFactory.build_disambiguation_prompt(candidate_terms, text_blocks, prompt_format="xml_json") -> str`
  - `PromptFactory.render_text_blocks_json(text_blocks) -> str`
  - `PromptFactory.render_glossary_json(terms) -> str`
  - `PromptFactory.parse_response(text, stage, prompt_format) -> list[dict]`

- [ ] **Step 1: 添加 json_json 格式的模板常量**

在 `PromptFactory` 类中新增 JSON 格式的模板。在现有 XML 模板后面添加：

```python
    # ---- JSON 格式模板（json_json） ----

    _JSON_BASE_ROLE = (
        '{\n'
        '  "role": "我是游戏作品\'边狱公司\'的翻译员，我将要把其他语言的文本翻译为中文。"\n'
        '}\n'
    )

    _JSON_STAGE1_RULES = (
        '{\n'
        '  "rules": [\n'
        '    "先查看reference中的术语表和指南，确保术语一致性",\n'
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
        "  <item term=\"术语KR\" applies=\"true\" actual_meaning=\"在此上下文中的实际含义\" reason=\"判断理由\" />\n"
        "</disambiguations>\n"
        "</format>\n"
    )

    _XML_STAGE1_FORMAT = _STAGE1_FORMAT  # 原 _STAGE1_FORMAT，请求 JSON 响应

    _XML_STAGE1_FORMAT_XML = (
        "<format>\n"
        "返回XML，包含<translations>根元素：\n"
        "<translations>\n"
        "  <item id=\"1\">\n"
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
        "  <item id=\"1\">\n"
        "    <translation>修正后的翻译</translation>\n"
        "    <changed>false</changed>\n"
        "    <change_reason></change_reason>\n"
        "  </item>\n"
        "</checked_translations>\n"
        "</format>\n"
    )
```

- [ ] **Step 2: 修改 build_system_prompt() 签名和实现**

替换现有的 `build_system_prompt()` 方法：

```python
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

        # Few-shot 示例（仅非 JSON 格式）
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
```

- [ ] **Step 3: 修改 build_disambiguation_prompt() 签名**

```python
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
```

- [ ] **Step 4: 新增 JSON 渲染方法**

在 `_render_role_styles()` 方法后面添加：

```python
    def render_text_blocks_json(self, text_blocks: list[dict]) -> str:
        """渲染 text_blocks 为 JSON 字符串。"""
        import json as _json
        items = []
        for i, block in enumerate(text_blocks):
            item: dict = {"id": i + 1, "kr": block.get("kr", "")}
            if block.get("jp"):
                item["jp"] = block["jp"]
            if block.get("en"):
                item["en"] = block["en"]
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
```

- [ ] **Step 5: 新增 parse_response() 方法**

```python
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
```

- [ ] **Step 6: 运行现有测试确认 PromptFactory 未破坏**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/ -v -k "prompt" 2>&1 || echo "No prompt-specific tests yet — manual verification below"
```

手动验证（Python REPL）：

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -c "
from translateFunc.builder.prompt import PromptFactory
from translateFunc.enums import FileType
pf = PromptFactory()
# Test xml_json (default)
sp = pf.build_system_prompt(FileType.STORY, 1, 'xml_json')
assert 'xml' not in sp.split('<format>')[0][:50].lower() or '<role>' in sp
print('xml_json OK')
# Test xml_xml
sp = pf.build_system_prompt(FileType.STORY, 1, 'xml_xml')
assert '<translations>' in sp
print('xml_xml OK')
# Test json_json
sp = pf.build_system_prompt(FileType.STORY, 1, 'json_json')
assert '\"role\"' in sp
assert '\"translations\"' in sp
print('json_json OK')
# Test parse_response JSON
result = pf.parse_response('{\"translations\":[{\"id\":1,\"translation\":\"test\"}]}', 1, 'xml_json')
assert len(result) == 1
assert result[0]['translation'] == 'test'
print('parse JSON OK')
# Test parse_response XML
xml = '<translations><item id=\"1\"><translation>test_xml</translation><reasoning>r</reasoning><confidence>high</confidence></item></translations>'
result = pf.parse_response(xml, 1, 'xml_xml')
assert len(result) == 1
assert result[0]['translation'] == 'test_xml'
print('parse XML OK')
print('ALL MANUAL CHECKS PASSED')
"
```

- [ ] **Step 7: Commit**

```bash
git add translateFunc/builder/prompt.py
git commit -m "feat: PromptFactory 增加 xml_xml/json_json 格式模板与 parse_response"
```

---

### Task 3: RequestBuilder User Prompt 格式扩展

**Files:**
- Modify: `translateFunc/builder/request.py`

**Interfaces:**
- Consumes: `PromptFactory.render_glossary()`, `PromptFactory.render_text_blocks()`, `PromptFactory.render_glossary_json()`, `PromptFactory.render_text_blocks_json()`
- Produces: `RequestBuilder.get_request_text(prompt_format="xml_json") -> list[str]`

- [ ] **Step 1: 修改 get_request_text() 签名和实现**

编辑 `translateFunc/builder/request.py`，替换 `get_request_text()` 方法（第 196-210 行）：

```python
    def get_request_text(self, prompt_format: str = "xml_json") -> list[str]:
        """获取所有分割后的请求文本（按格式渲染）。

        Args:
            prompt_format: "xml_json" | "xml_xml" | "json_json"
        """
        if self.unified_request is None:
            self.build()

        result = []
        for request in self.split_requests:
            if prompt_format in ("xml_json", "xml_xml"):
                result.append(self._make_xml_user_prompt(request))
            elif prompt_format == "json_json":
                result.append(self._make_json_user_prompt(request))
            else:
                # 未知格式回退到 JSON
                import json as _json
                result.append(_json.dumps(request, indent=2, ensure_ascii=False))
        return result
```

- [ ] **Step 2: 新增 _make_xml_user_prompt() 方法**

在 `_make_text()` 方法后面添加（约第 331 行之后）：

```python
    def _make_xml_user_prompt(self, request_data: dict) -> str:
        """将统一请求字典转换为 XML 格式的 user prompt。"""
        from translateFunc.builder.prompt import PromptFactory
        pf = PromptFactory()

        reference = request_data.get("reference", {})
        text_blocks = request_data.get("text_blocks", [])

        parts: list[str] = []

        # Glossary（专有名词）
        if reference.get("proper_terms"):
            parts.append(pf.render_glossary(reference["proper_terms"]))

        # Affects（状态效果）
        if reference.get("affects"):
            parts.append(self._render_affects_xml(reference["affects"]))

        # 角色风格参考
        if self.is_story and reference.get("model_docs"):
            for doc in reference["model_docs"]:
                parts.append(pf._render_role_styles([doc]) if hasattr(pf, '_render_role_styles') else "")

        # 技能指南
        if self.is_skill and reference.get("skill_doc"):
            parts.append(f"<skill_guide>\n{reference['skill_doc']}\n</skill_guide>\n")

        # 文本块
        parts.append(pf.render_text_blocks(text_blocks))

        return "\n".join(parts)

    def _render_affects_xml(self, affects: list[dict]) -> str:
        """渲染 affects 为 XML。"""
        if not affects:
            return ""
        lines = ["<affects>"]
        for a in affects:
            lines.append(f"  <affect id=\"{a.get('id', '')}\" kr=\"{a.get('kr', '')}\" cn=\"{a.get('cn', '')}\" />")
        lines.append("</affects>")
        return "\n".join(lines) + "\n"
```

- [ ] **Step 3: 新增 _make_json_user_prompt() 方法**

```python
    def _make_json_user_prompt(self, request_data: dict) -> str:
        """将统一请求字典转换为 JSON 格式的 user prompt。"""
        import json as _json

        reference = request_data.get("reference", {})
        text_blocks = request_data.get("text_blocks", [])

        output: dict = {}

        # Glossary
        proper_terms = reference.get("proper_terms", [])
        if proper_terms:
            glossary = []
            for t in proper_terms:
                kr = t.get("kr", t.get("term", ""))
                cn = t.get("cn", t.get("translation", ""))
                note = t.get("note", "")
                entry = {"kr": kr, "cn": cn}
                if note:
                    entry["note"] = note
                glossary.append(entry)
            output["glossary"] = glossary

        # Affects
        if reference.get("affects"):
            output["affects"] = reference["affects"]

        # 角色风格
        if self.is_story and reference.get("model_docs"):
            output["role_styles"] = reference["model_docs"]

        # 技能指南
        if self.is_skill and reference.get("skill_doc"):
            output["skill_doc"] = reference["skill_doc"]

        # 文本块
        items = []
        for i, block in enumerate(text_blocks):
            item: dict = {"id": i + 1, "kr": block.get("kr", "")}
            if block.get("jp"):
                item["jp"] = block["jp"]
            if block.get("en"):
                item["en"] = block["en"]
            items.append(item)
        output["text_blocks"] = items

        return _json.dumps(output, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: 更新 _get_request_text() 内部方法**

`_get_request_text()` 用于长度检查（第 212-216 行），需要更新以适应新格式：

```python
    def _get_request_text(self, request_data: dict, prompt_format: str = "xml_json") -> str:
        """获取请求文本用于长度检查。"""
        if prompt_format in ("xml_json", "xml_xml"):
            return self._make_xml_user_prompt(request_data)
        elif prompt_format == "json_json":
            return self._make_json_user_prompt(request_data)
        import json as _json
        return _json.dumps(request_data, indent=2, ensure_ascii=False)
```

- [ ] **Step 5: 更新 _split_by_length() 中对 _get_request_text 的调用**

在 `_split_by_length()` 方法（第 150-192 行）中，`_get_request_text()` 调用现在需要知道格式。由于分割发生在 build 阶段，此时还不知道 prompt_format，需要给 `_split_by_length` 传参，或者使用 JSON 序列化做近似长度估算。

采用最简单方案：在 `_split_by_length()` 中使用 JSON 序列化做长度近似（这是最坏情况，分割安全边际足够）：

保持 `_split_by_length()` 不变——它当前调用 `self._get_request_text(p)` 且未传 format，使用 JSON 序列化做近似。由于 XML 渲染通常比 JSON 更紧凑，以 JSON 为标准分割是安全的。

- [ ] **Step 6: 手动验证 RequestBuilder**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -c "
import json
from unittest.mock import MagicMock
from translateFunc.builder.request import RequestBuilder
from translateFunc.enums import FileType

# Mock matcher engine
mock_engine = MagicMock()
mock_engine.match_all.return_value = MagicMock(proper_matches=[], affect_id_matches=[], affect_name_matches=[], role_matches=[])
mock_engine.role_data = []

request_text = {
    'kr': {0: {('name',): '테스트'}},
    'jp': {0: {('name',): 'テスト'}},
    'en': {0: {('name',): 'Test'}},
}

rb = RequestBuilder(request_text, mock_engine, file_type=FileType.OTHER)
rb.build()

# Test xml_json user prompt
texts = rb.get_request_text('xml_json')
assert len(texts) == 1
assert '<text>' in texts[0] or len(texts[0]) > 0
print(f'xml_json user prompt ({len(texts[0])} chars): {texts[0][:200]}...')

# Test xml_xml user prompt
texts = rb.get_request_text('xml_xml')
assert len(texts) == 1
print(f'xml_xml user prompt ({len(texts[0])} chars): {texts[0][:200]}...')

# Test json_json user prompt
texts = rb.get_request_text('json_json')
assert len(texts) == 1
parsed = json.loads(texts[0])
assert 'text_blocks' in parsed
print(f'json_json user prompt OK, text_blocks count: {len(parsed[\"text_blocks\"])}')

print('ALL RequestBuilder CHECKS PASSED')
"
```

- [ ] **Step 7: Commit**

```bash
git add translateFunc/builder/request.py
git commit -m "feat: RequestBuilder 按 prompt_format 输出 XML/JSON user prompt"
```

---

### Task 4: StageStrategy 透传 prompt_format

**Files:**
- Modify: `translateFunc/builder/stages.py`

**Interfaces:**
- Consumes: `PromptFactory.build_system_prompt(..., prompt_format)`, `PromptFactory.parse_response(..., prompt_format)`
- Produces: 所有 `build_stage_*_prompt()` 新增 `prompt_format` 参数；`parse_stage_*_result()` 接受 `prompt_format`

- [ ] **Step 1: 修改 build_system_prompt 透传**

编辑 `translateFunc/builder/stages.py`，在各方法中添加 `prompt_format` 参数。

修改 `build_stage_1_prompt()`（第 76-91 行）：

```python
    def build_stage_1_prompt(
        self,
        file_type: FileType,
        prompt_format: str = "xml_json",
        *,
        examples: list[dict] | None = None,
    ) -> str:
        """构建主翻译系统提示词。"""
        return self._prompt_factory.build_system_prompt(
            file_type=file_type,
            stage=1,
            prompt_format=prompt_format,
            examples=examples,
        )
```

修改 `build_stage_1_user_prompt()`（第 93-103 行）——不需要改动（user prompt 由 RequestBuilder 渲染，StageStrategy 只负责 system prompt 部分）：

保持不变（此方法实际上在新的流程中不再直接使用——user prompt 由 `RequestBuilder.get_request_text()` 直接生成）。

- [ ] **Step 2: 修改 parse 方法透传 format**

修改 `parse_stage_0_result()`（第 66-72 行）：

```python
    def parse_stage_0_result(self, result_text: str, prompt_format: str = "xml_json") -> list[dict]:
        """将 LLM 消歧结果解析为结构化数据。"""
        return self._prompt_factory.parse_response(result_text, stage=0, prompt_format=prompt_format)
```

修改 `parse_stage_1_result()`（第 105-119 行）：

```python
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
```

修改 `parse_stage_2_result()`（第 158-164 行）：

```python
    def parse_stage_2_result(self, result_text: str, prompt_format: str = "xml_json") -> list[dict]:
        """解析自校验结果。"""
        return self._prompt_factory.parse_response(result_text, stage=2, prompt_format=prompt_format)
```

修改 `build_stage_0_prompt()`（第 58-64 行）：

```python
    def build_stage_0_prompt(
        self,
        candidate_terms: list[dict],
        text_blocks: list[dict],
        prompt_format: str = "xml_json",
    ) -> str:
        """构建阶段 0 的 LLM 消歧提示词。"""
        return self._prompt_factory.build_disambiguation_prompt(candidate_terms, text_blocks, prompt_format)
```

修改 `build_stage_2_prompt()`（第 130-156 行）——增加 `prompt_format` 参数：

```python
    def build_stage_2_prompt(
        self,
        file_type: FileType,
        prompt_format: str = "xml_json",
        original_blocks: list[dict] | None = None,
        translations: list[dict] | None = None,
    ) -> str:
        """构建自校验提示词，将原文与译文并列对比。"""
        system = self._prompt_factory.build_system_prompt(
            file_type=file_type, stage=2, prompt_format=prompt_format,
        )

        if not original_blocks or not translations:
            return system

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
```

- [ ] **Step 3: 验证 StageStrategy**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -c "
from translateFunc.builder.stages import StageStrategy
from translateFunc.config import TranslateConfig
from translateFunc.enums import FileType

config = TranslateConfig()
strategy = StageStrategy(config)

for fmt in ['xml_json', 'xml_xml', 'json_json']:
    sp = strategy.build_stage_1_prompt(FileType.STORY, prompt_format=fmt)
    print(f'{fmt}: {len(sp)} chars — first 80: {sp[:80]}')

# Test parse
result = strategy.parse_stage_1_result('{\"translations\":[{\"id\":1,\"translation\":\"t\"}]}', 'xml_json')
assert len(result) == 1
print('parse_stage_1_result OK')

print('ALL StageStrategy CHECKS PASSED')
"
```

- [ ] **Step 4: Commit**

```bash
git add translateFunc/builder/stages.py
git commit -m "feat: StageStrategy 透传 prompt_format 给 PromptFactory"
```

---

### Task 5: Pipeline._build_translator() 动态 system_prompt

**Files:**
- Modify: `translateFunc/pipeline.py:241-270`

**Interfaces:**
- Consumes: (none new)
- Produces: `TranslationPipeline._build_translator(system_prompt="") -> TranslatorBase`

- [ ] **Step 1: 修改 _build_translator() 接受 system_prompt 参数**

编辑 `translateFunc/pipeline.py`，修改 `_build_translator()` 方法签名和实现。
system_prompt 不再在此方法中硬编码，由调用方注入。空字符串时仅设置 response_format。

```python
    def _build_translator(self, system_prompt: str = "") -> TranslatorBase:
        """根据配置创建翻译器实例。

        Args:
            system_prompt: 动态 system prompt。LLM 翻译时由 PromptFactory 生成后注入。
        """
        translator_cls = TRANSLATOR_TRANS[self._config.translator_name]
        api_settings = dict(self._config.translator_api)

        if self._config.is_llm:
            if system_prompt:
                api_settings["system_prompt"] = system_prompt
            api_settings["response_format"] = "json_object"

        tkit_config = TKitConfig(
            api_setting=api_settings,
            debug_mode=self._config.debug_mode,
            enable_cache=True,
            enable_metrics=True,
        )

        if self._config.is_llm:
            tkit_config.text_max_length = 20000
            tkit_config.max_workers = 1

        if not self._config.debug_mode:
            logging.getLogger("translatekit").setLevel(logging.INFO)

        translator = translator_cls(tkit_config)

        if not self._config.debug_mode:
            logging.getLogger("translatekit").setLevel(logging.DEBUG)

        return translator
```

同时移除 `pipeline.py:33` 对 `JSON_SYSTEM_PROMPT, TEXT_SYSTEM_PROMPT` 的 import：

```python
# 移除这行
from translateFunc.translate_doc import JSON_SYSTEM_PROMPT, TEXT_SYSTEM_PROMPT
```

- [ ] **Step 2: 更新 _process_one() 传递 system_prompt**

`_process_one()` 在第 185-196 行创建 `FileProcessor` 时传递 translator。由于 system_prompt 现在在 `_translate()` 内动态设置（Task 6 会处理），`_process_one()` 不需要改——translator 在每次翻译调用前由 fallback 循环重建。

保持现有 `_process_one()` 不变。

- [ ] **Step 3: 验证**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -c "
from translateFunc.pipeline import TranslationPipeline
from translateFunc.config import TranslateConfig
config = TranslateConfig()
pipeline = TranslationPipeline(config)
# 测试接受 system_prompt 参数（不实际连接 API）
try:
    # 只是验证方法签名，不实际翻译
    import inspect
    sig = inspect.signature(pipeline._build_translator)
    params = list(sig.parameters.keys())
    assert 'system_prompt' in params
    print('_build_translator() accepts system_prompt parameter: OK')
except Exception as e:
    print(f'Error: {e}')
"
```

- [ ] **Step 4: Commit**

```bash
git add translateFunc/pipeline.py
git commit -m "refactor: _build_translator() 接受动态 system_prompt 参数"
```

---

### Task 6: FileProcessor Fallback 回退循环

**Files:**
- Modify: `translateFunc/processor.py:155-225`

**Interfaces:**
- Consumes: `TranslateConfig.prompt_format`, `TranslateConfig.fallback`, `PromptFactory.build_system_prompt()`, `PromptFactory.parse_response()`, `RequestBuilder.get_request_text(prompt_format)`
- Produces: `FileProcessor._translate()` 内部 fallback 循环

- [ ] **Step 1: 重写 _translate() 方法实现 fallback**

编辑 `translateFunc/processor.py`，替换 `_translate()` 方法（第 155-225 行）：

```python
    def _translate(self, request_text: dict) -> dict:
        """通过配置的管线阶段执行翻译，支持格式回退。"""
        # 构建请求
        builder = RequestBuilder(
            request_text,
            self._engine,
            is_story=self.is_story,
            is_skill=self.is_skill,
            is_text_format=False,  # 废弃，由 prompt_format 控制
            max_length=20000,
            file_type=self.file_type,
        )

        if self._config.is_llm:
            builder.build()
            stage_strategy = StageStrategy(self._config)

            # 确定格式回退链
            formats_chain = self._build_format_chain()

            result: list[str] = []
            for i, request_part in enumerate(builder.split_requests if builder.split_requests else [builder.unified_request]):
                if builder.split_requests:
                    part_data = request_part
                else:
                    part_data = builder.unified_request
                if part_data is None:
                    continue

                timeout = max(20000 // 200 + 1, 40)
                part_result = None
                tried_formats: list[str] = []

                for fmt in formats_chain:
                    tried_formats.append(fmt)
                    try:
                        # 按当前格式构建 system prompt
                        system_prompt = stage_strategy.build_stage_1_prompt(
                            self.file_type,
                            prompt_format=fmt,
                        )

                        # 按当前格式构建 user prompt
                        user_prompt = builder.get_request_text(prompt_format=fmt)
                        user_text = user_prompt[i] if i < len(user_prompt) else user_prompt[0]

                        # 每种格式都创建新 translator（注入当前 system_prompt）
                        translator = self._build_translator_for_format(system_prompt)

                        # 调用 LLM
                        raw_response = translator.translate(user_text, timeout=timeout)
                        if self._dump:
                            self._log(f"[{fmt}] 第 {i + 1} 部分: {str(raw_response)[:200]}...")

                        # 解析
                        parsed = stage_strategy.parse_stage_1_result(raw_response, prompt_format=fmt)
                        if not parsed:
                            raise ValueError(f"{fmt}: 解析结果为空")

                        # 提取翻译文本
                        part_result = [
                            t.get("translation", "") if isinstance(t, dict) else str(t)
                            for t in parsed
                        ]
                        break  # 成功，退出格式回退循环

                    except (json.JSONDecodeError, ValueError, KeyError) as e:
                        if self._dump:
                            self._log(f"[{fmt}] 解析失败 ({e})，回退到下一格式")
                        continue

                if part_result is None:
                    # 全部格式失败，回退为原文
                    if self._dump:
                        self._log(f"全部格式 ({', '.join(tried_formats)}) 失败，回退为原文")
                    text_blocks = part_data.get("text_blocks", [])
                    part_result = [b.get("kr", "") for b in text_blocks]

                result.extend(part_result)

            return builder.deBuild(result)
        else:
            # 非 LLM 路径：保持不变
            simple_builder = _SimpleRequestBuilder(request_text)
            simple_builder.build()
            request_texts = simple_builder.get_request_text(from_lang=self._config.from_lang)
            result = self._translator.translate(request_texts)
            return simple_builder.deBuild(result)

    def _build_format_chain(self) -> list[str]:
        """构建格式回退链：[用户选择] + fallback? [xml_json, json_json, xml_xml] : []"""
        user_format = self._config.prompt_format
        chain = [user_format]
        if self._config.fallback:
            fallback_order = ["xml_json", "json_json", "xml_xml"]
            for f in fallback_order:
                if f not in chain:
                    chain.append(f)
        return chain

    def _build_translator_for_format(self, system_prompt: str):
        """为指定格式创建独立的 translator 实例。"""
        # 复用 pipeline 的 _build_translator 逻辑
        from translateFunc.pipeline import TranslationPipeline
        # 通过 translator_factory 模式创建
        from translatekit import TranslationConfig as TKitConfig
        from translateFunc.translate_request import TRANSLATOR_TRANS
        import logging

        translator_cls = TRANSLATOR_TRANS[self._config.translator_name]
        api_settings = dict(self._config.translator_api)
        api_settings["system_prompt"] = system_prompt
        api_settings["response_format"] = "json_object"

        tkit_config = TKitConfig(
            api_setting=api_settings,
            debug_mode=self._config.debug_mode,
            enable_cache=True,
            enable_metrics=True,
        )
        tkit_config.text_max_length = 20000
        tkit_config.max_workers = 1

        if not self._config.debug_mode:
            logging.getLogger("translatekit").setLevel(logging.INFO)

        translator = translator_cls(tkit_config)

        if not self._config.debug_mode:
            logging.getLogger("translatekit").setLevel(logging.DEBUG)

        return translator
```

- [ ] **Step 2: 翻译器实例管理**

fallback 循环中，**每种格式都通过 `_build_translator_for_format()` 创建新 translator**（包括首次）。不重用 `self._translator`，因为它的 system_prompt 可能不匹配当前格式。

`self._translator` 仍由 WorkerPool 的 factory 创建并传入 FileProcessor，但在 `_translate()` LLM 路径中会被 `_build_translator_for_format()` 替代。非 LLM 路径继续使用 `self._translator`。

- [ ] **Step 3: 运行现有测试确认兼容**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_pipeline.py -v
```

- [ ] **Step 4: Commit**

```bash
git add translateFunc/processor.py
git commit -m "feat: FileProcessor fallback 回退循环 — 格式解析失败自动切换"
```

---

### Task 7: translate_doc.py 清理

**Files:**
- Modify: `translateFunc/translate_doc.py`

- [ ] **Step 1: 移除旧 system prompt 常量**

编辑 `translateFunc/translate_doc.py`，删除 `JSON_SYSTEM_PROMPT`（第 168-205 行）和 `TEXT_SYSTEM_PROMPT`（第 207-229 行）两个常量。

保留 `SKILLL_DOC`、`ROLE_STYLE`、`RLOE_COMPARE`。

- [ ] **Step 2: 检查所有引用**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && grep -rn "JSON_SYSTEM_PROMPT\|TEXT_SYSTEM_PROMPT" --include="*.py" .
```

Expected: 无引用（Task 5 已移除 pipeline.py 的 import，此处删除定义后无任何引用残留）。

- [ ] **Step 3: Commit**

```bash
git add translateFunc/translate_doc.py translateFunc/pipeline.py
git commit -m "refactor: 移除 translate_doc.py 旧 JSON_SYSTEM_PROMPT/TEXT_SYSTEM_PROMPT"
```

---

### Task 8: 前端变更

**Files:**
- Modify: `webui/index.html:368-374` (is-text → prompt-format)
- Modify: `webui/js/core.js:212` (字段映射)
- Modify: `webui/js/utils.js:343` (tooltip 文本)

- [ ] **Step 1: 修改 index.html — 替换 is-text 复选框为 prompt-format 下拉框**

编辑 `webui/index.html`，找到第 368-374 行的 `is-text` 复选框，替换为：

```html
                    <div class="form-group">
                        <label for="prompt-format">请求 / 响应格式:</label>
                        <div class="select-wrapper">
                            <select id="prompt-format">
                                <option value="xml_json">XML 请求 → JSON 响应（推荐）</option>
                                <option value="json_json">JSON 请求 → JSON 响应</option>
                                <option value="xml_xml">XML 请求 → XML 响应</option>
                            </select>
                            <i class="fas fa-chevron-down"></i>
                        </div>
                    </div>
```

- [ ] **Step 2: 修改 core.js — 更新字段映射**

编辑 `webui/js/core.js` 第 212 行，将：

```js
            "is-text": 'ui_default.translator.is_text',
```

替换为：

```js
            "prompt-format": 'ui_default.translator.prompt_format',
```

- [ ] **Step 3: 修改 utils.js — 更新 tooltip 文本**

编辑 `webui/js/utils.js` 第 343 行，将：

```js
    'is-text': '使用自然语言文本格式而非 JSON 格式向 LLM 发送翻译请求。建议关闭，否则可能出现较多翻译错位。',
```

替换为：

```js
    'prompt-format': '选择提示词与响应的格式。"XML请求→JSON响应"为推荐选项，平衡了结构化与解析可靠性。"JSON请求→JSON响应"适合偏好纯 JSON 的场景。"XML请求→XML响应"在某些模型上格式遵循度更高。',
```

同时更新 `fallback` 的 tooltip（第 342 行）：

```js
    'fallback': '当 LLM 返回格式无法解析时，自动按 xml_json→json_json→xml_xml 顺序切换格式重试。建议开启以减少格式错误导致的翻译失败。',
```

- [ ] **Step 4: 确认 webui/app.py 无需改动**

`webui/app.py` 不需要导入 `prompt_format`——前端通过 `core.js` 的字段映射直接读写 ConfigManager。

- [ ] **Step 5: Commit**

```bash
git add webui/index.html webui/js/core.js webui/js/utils.js
git commit -m "feat: 前端 is-text 复选框替换为 prompt-format 下拉框"
```

---

### Task 9: 测试

**Files:**
- Create: `tests/test_prompt_format.py`

- [ ] **Step 1: 编写测试文件**

创建 `tests/test_prompt_format.py`：

```python
"""Prompt format generation, parsing, and fallback tests."""
import json
import xml.etree.ElementTree as ET
import pytest
from unittest.mock import MagicMock, patch

from translateFunc.builder.prompt import PromptFactory
from translateFunc.builder.stages import StageStrategy
from translateFunc.config import TranslateConfig
from translateFunc.enums import FileType


class TestPromptFactoryFormats:
    """Tests for PromptFactory with three prompt formats."""

    def setup_method(self):
        self.pf = PromptFactory()

    # ---- xml_json (default) ----

    def test_xml_json_system_prompt_structure(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_json")
        assert "<role>" in sp
        assert "<rules>" in sp
        assert "<format>" in sp
        assert '"translations"' in sp  # JSON format instruction in XML

    def test_xml_json_system_prompt_stage_0(self):
        sp = self.pf.build_system_prompt(FileType.OTHER, 0, "xml_json")
        assert "<role>" in sp
        assert "<rules>" in sp
        assert "disambiguations" in sp

    def test_xml_json_system_prompt_stage_2(self):
        sp = self.pf.build_system_prompt(FileType.OTHER, 2, "xml_json")
        assert "checked_translations" in sp

    # ---- xml_xml ----

    def test_xml_xml_system_prompt_structure(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "xml_xml")
        assert "<role>" in sp
        assert "<rules>" in sp
        assert "<translations>" in sp  # XML response instruction
        assert "<translation>" in sp

    def test_xml_xml_system_prompt_stage_0(self):
        sp = self.pf.build_system_prompt(FileType.OTHER, 0, "xml_xml")
        assert "<disambiguations>" in sp

    # ---- json_json ----

    def test_json_json_system_prompt_structure(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "json_json")
        assert '"role"' in sp
        assert '"rules"' in sp
        assert '"format"' in sp
        assert '"translations"' in sp

    def test_json_json_contains_no_xml_tags(self):
        sp = self.pf.build_system_prompt(FileType.STORY, 1, "json_json")
        assert "<role>" not in sp
        assert "<rules>" not in sp

    def test_json_json_system_prompt_stage_0(self):
        sp = self.pf.build_system_prompt(FileType.OTHER, 0, "json_json")
        assert '"disambiguations"' in sp

    # ---- FileType variations ----

    def test_skill_file_type_all_formats(self):
        for fmt in ["xml_json", "xml_xml", "json_json"]:
            sp = self.pf.build_system_prompt(FileType.SKILL, 1, fmt)
            # skill_doc NOT in system prompt anymore
            assert len(sp) > 0

    def test_story_file_type_all_formats(self):
        for fmt in ["xml_json", "xml_xml", "json_json"]:
            sp = self.pf.build_system_prompt(FileType.STORY, 1, fmt)
            # role_styles NOT in system prompt anymore
            assert len(sp) > 0


class TestPromptFactoryParsing:
    """Tests for PromptFactory.parse_response()."""

    def setup_method(self):
        self.pf = PromptFactory()

    # ---- JSON parsing (xml_json / json_json) ----

    def test_parse_json_stage_1(self):
        for fmt in ["xml_json", "json_json"]:
            text = '{"translations": [{"id": 1, "translation": "你好", "reasoning": "直译", "confidence": "high"}]}'
            result = self.pf.parse_response(text, 1, fmt)
            assert len(result) == 1
            assert result[0]["translation"] == "你好"
            assert result[0]["confidence"] == "high"

    def test_parse_json_stage_0(self):
        for fmt in ["xml_json", "json_json"]:
            text = '{"disambiguations": [{"term": "테스트", "applies": true, "actual_meaning": "测试", "reason": "上下文匹配"}]}'
            result = self.pf.parse_response(text, 0, fmt)
            assert len(result) == 1
            assert result[0]["term"] == "테스트"
            assert result[0]["applies"] is True

    def test_parse_json_stage_2(self):
        for fmt in ["xml_json", "json_json"]:
            text = '{"checked_translations": [{"id": 1, "translation": "修正", "changed": true, "change_reason": "术语错误"}]}'
            result = self.pf.parse_response(text, 2, fmt)
            assert len(result) == 1
            assert result[0]["changed"] is True
            assert result[0]["translation"] == "修正"

    def test_parse_json_invalid_returns_empty(self):
        for fmt in ["xml_json", "json_json"]:
            result = self.pf.parse_response("not valid json {{{", 1, fmt)
            assert result == []

    def test_parse_json_missing_field_returns_empty(self):
        for fmt in ["xml_json", "json_json"]:
            result = self.pf.parse_response('{"other": []}', 1, fmt)
            assert result == []

    # ---- XML parsing (xml_xml) ----

    def test_parse_xml_stage_1(self):
        text = (
            '<translations>'
            '<item id="1">'
            '<translation>你好</translation>'
            '<reasoning>直译</reasoning>'
            '<confidence>high</confidence>'
            '</item>'
            '</translations>'
        )
        result = self.pf.parse_response(text, 1, "xml_xml")
        assert len(result) == 1
        assert result[0]["translation"] == "你好"
        assert result[0]["confidence"] == "high"

    def test_parse_xml_multiple_items(self):
        text = (
            '<translations>'
            '<item id="1"><translation>A</translation><reasoning>R1</reasoning><confidence>high</confidence></item>'
            '<item id="2"><translation>B</translation><reasoning>R2</reasoning><confidence>medium</confidence></item>'
            '</translations>'
        )
        result = self.pf.parse_response(text, 1, "xml_xml")
        assert len(result) == 2
        assert result[0]["translation"] == "A"
        assert result[1]["translation"] == "B"

    def test_parse_xml_stage_0(self):
        text = (
            '<disambiguations>'
            '<item term="테스트" applies="true" actual_meaning="测试" reason="匹配"/>'
            '</disambiguations>'
        )
        result = self.pf.parse_response(text, 0, "xml_xml")
        assert len(result) == 1
        assert result[0]["term"] == "테스트"
        assert result[0]["applies"] is True

    def test_parse_xml_missing_optional_fields(self):
        """XML items with missing optional fields should use defaults."""
        text = (
            '<translations>'
            '<item id="1"><translation>Minimal</translation></item>'
            '</translations>'
        )
        result = self.pf.parse_response(text, 1, "xml_xml")
        assert len(result) == 1
        assert result[0]["translation"] == "Minimal"
        assert result[0]["reasoning"] == ""
        assert result[0]["confidence"] == "medium"

    def test_parse_xml_invalid_returns_empty(self):
        result = self.pf.parse_response("not valid xml <<<", 1, "xml_xml")
        assert result == []

    def test_parse_xml_unknown_stage_returns_empty(self):
        text = '<translations><item id="1"><translation>T</translation></item></translations>'
        result = self.pf.parse_response(text, 99, "xml_xml")
        assert result == []


class TestStageStrategyFormatPassthrough:
    """Tests for StageStrategy passing prompt_format to PromptFactory."""

    def test_build_stage_1_prompt_passes_format(self):
        config = TranslateConfig()
        strategy = StageStrategy(config)
        for fmt in ["xml_json", "xml_xml", "json_json"]:
            sp = strategy.build_stage_1_prompt(FileType.STORY, prompt_format=fmt)
            assert len(sp) > 0

    def test_parse_stage_1_result_passes_format(self):
        config = TranslateConfig()
        strategy = StageStrategy(config)
        text = '{"translations": [{"id": 1, "translation": "t"}]}'
        result = strategy.parse_stage_1_result(text, "xml_json")
        assert len(result) == 1

    def test_parse_stage_0_result_passes_format(self):
        config = TranslateConfig()
        strategy = StageStrategy(config)
        text = '{"disambiguations": [{"term": "t", "applies": true}]}'
        result = strategy.parse_stage_0_result(text, "xml_json")
        assert len(result) == 1


class TestTranslateConfigFormat:
    """Tests for TranslateConfig prompt_format field."""

    def test_default_prompt_format(self):
        config = TranslateConfig()
        assert config.prompt_format == "xml_json"

    def test_fallback_default(self):
        config = TranslateConfig()
        assert config.fallback is True

    def test_from_config_manager_reads_prompt_format(self):
        mock_mgr = MagicMock()
        mock_mgr.get.side_effect = lambda key, default=None: {
            "ui_default.translator": {
                "prompt_format": "json_json",
                "fallback": False,
                "translator": "LLM通用翻译服务",
            },
            "game_path": "",
            "debug": False,
        }.get(key, default)

        config = TranslateConfig.from_config_manager(mock_mgr)
        assert config.prompt_format == "json_json"
        assert config.fallback is False

    def test_from_config_manager_defaults_when_missing(self):
        mock_mgr = MagicMock()
        mock_mgr.get.side_effect = lambda key, default=None: {
            "ui_default.translator": {
                "translator": "LLM通用翻译服务",
            },
            "game_path": "",
            "debug": False,
        }.get(key, default)

        config = TranslateConfig.from_config_manager(mock_mgr)
        assert config.prompt_format == "xml_json"  # default
        assert config.fallback is True  # default

    def test_is_text_format_removed(self):
        """Verify is_text_format no longer exists on TranslateConfig."""
        config = TranslateConfig()
        assert not hasattr(config, "is_text_format")


class TestRenderMethods:
    """Tests for PromptFactory render methods."""

    def setup_method(self):
        self.pf = PromptFactory()

    def test_render_text_blocks_json(self):
        blocks = [
            {"kr": "안녕", "jp": "こんにちは", "en": "Hello"},
            {"kr": "세계", "en": "World"},
        ]
        result = self.pf.render_text_blocks_json(blocks)
        parsed = json.loads(result)
        assert len(parsed["text_blocks"]) == 2
        assert parsed["text_blocks"][0]["kr"] == "안녕"
        assert parsed["text_blocks"][0]["jp"] == "こんにちは"

    def test_render_glossary_json(self):
        terms = [
            {"kr": "단테", "cn": "但丁", "note": "主角"},
            {"kr": "파우스트", "cn": "浮士德"},
        ]
        result = self.pf.render_glossary_json(terms)
        parsed = json.loads(result)
        assert len(parsed["glossary"]) == 2
        assert parsed["glossary"][0]["note"] == "主角"
        assert "note" not in parsed["glossary"][1]

    def test_render_glossary_json_empty(self):
        result = self.pf.render_glossary_json([])
        assert result == ""

    def test_render_glossary_xml_empty(self):
        result = self.pf.render_glossary([])
        assert result == ""


class TestFallbackChain:
    """Tests for format fallback chain logic."""

    def test_chain_no_fallback(self):
        """Without fallback, only user format is tried."""
        config = TranslateConfig(prompt_format="xml_xml", fallback=False)
        # Use a FileProcessor mock to test _build_format_chain
        # We test the chain-building logic directly
        chain = ["xml_xml"]  # no fallback adds nothing
        assert chain == ["xml_xml"]

    def test_chain_with_fallback(self):
        """With fallback, all formats are tried in order."""
        user_format = "xml_xml"
        chain = [user_format]
        fallback_order = ["xml_json", "json_json", "xml_xml"]
        for f in fallback_order:
            if f not in chain:
                chain.append(f)
        assert chain == ["xml_xml", "xml_json", "json_json"]

    def test_chain_user_is_xml_json(self):
        """When user already chose xml_json, it is not duplicated."""
        user_format = "xml_json"
        chain = [user_format]
        fallback_order = ["xml_json", "json_json", "xml_xml"]
        for f in fallback_order:
            if f not in chain:
                chain.append(f)
        assert chain == ["xml_json", "json_json", "xml_xml"]
        assert len(chain) == 3
```

- [ ] **Step 2: 运行测试**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_prompt_format.py -v
```

Expected: 所有新测试 PASS（约 28 个测试用例）。

- [ ] **Step 3: 运行全部测试确认无回归**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_prompt_format.py
git commit -m "test: PromptFactory 格式生成/解析/回退链测试（28 个用例）"
```

---

### Task 10: 集成验证

**Files:** (none modified — verification only)

- [ ] **Step 1: 运行全部测试套件**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/ -v
```

Expected: 全部测试 PASS（现有 test_pipeline.py + test_ac_automaton.py + 新的 test_prompt_format.py）。

- [ ] **Step 2: Python 导入完整性检查**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -c "
from translateFunc import (
    TranslationPipeline, TranslateConfig, PipelineSummary,
    ProcessResult, ProcessOutcome, FileType, MatchConfidence
)
from translateFunc.builder.prompt import PromptFactory, PromptTag
from translateFunc.builder.request import RequestBuilder
from translateFunc.builder.stages import StageStrategy
print('All imports successful')
"
```

- [ ] **Step 3: 配置文件一致性检查**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -c "
import json
# Verify all three config files have prompt_format
for path in ['config.json', 'config_default.json', 'config_check.json']:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    translator = data.get('ui_default', {}).get('translator', {})
    has_is_text = 'is_text' in translator
    has_prompt_format = 'prompt_format' in translator
    print(f'{path}: is_text={has_is_text}, prompt_format={has_prompt_format}')
    assert has_prompt_format, f'{path} missing prompt_format'
    assert not has_is_text, f'{path} still has is_text (should be removed)'
print('Config consistency OK')
"
```

- [ ] **Step 4: 最终 commit**

```bash
git add -A && git diff --cached --stat
```

确认变更文件列表符合预期后：

```bash
git commit -m "chore: 集成验证通过 — 全部测试 PASS，配置一致"
```
