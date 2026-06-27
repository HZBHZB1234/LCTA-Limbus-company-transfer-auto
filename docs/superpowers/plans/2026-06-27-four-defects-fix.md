# 四项缺陷修复 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 prompt-format 重构后遗留的四项缺陷：实现三阶段管线编排、补充 per-block 引用字段、格式感知长度估算、全部格式失败提升为错误。

**Architecture:** 改动集中在 `translateFunc/` 模块的 5-6 个文件中。阶段 0（消歧）和阶段 2（自校验）的模板已就绪于 `StageStrategy`/`PromptFactory`，仅需在 `FileProcessor._translate()` 中添加编排逻辑。三个阶段的失败策略各不相同：阶段 0/2 失败 → warning + 继续；阶段 1 失败 → 格式回退；全部格式失败 → error。

**Tech Stack:** Python 3.11+, pytest, unittest.mock

## Global Constraints

- 阶段 0 和阶段 2 仅使用用户选择的主格式，不参与 `formats_chain` 回退
- 阶段 0/2 LLM 调用仅在 `translation_mode == "multi_stage"` 且对应开关开启时触发
- 非 LLM 翻译路径（`is_llm=False`）完全不受影响
- `_split_by_length` 必须对三种格式取 max 确保安全
- 全部格式失败 → `logging.warning()` 无条件输出（不受 `dump` 控制）
- 全部格式失败 → `ProcessResult.FALLBACK_TO_ORIGINAL` → `PipelineSummary.errors`

---

### Task 1: 新增 `FALLBACK_TO_ORIGINAL` 枚举值

**Files:**
- Modify: `translateFunc/enums.py:8-16`

**Interfaces:**
- Produces: `ProcessResult.FALLBACK_TO_ORIGINAL` — Task 6 使用

- [ ] **Step 1: 添加枚举值**

```python
# translateFunc/enums.py — 在 ProcessResult 类中追加
class ProcessResult(Enum):
    """单个文件的处理结果。"""
    SUCCESS_SAVED        = auto()   # 翻译成功并保存
    ALREADY_TRANSLATED   = auto()   # 已翻译，跳过
    EMPTY_WITH_LLC       = auto()   # 空文件，已复制现有 LLC
    EMPTY_SKIPPED        = auto()   # 空文件，无 LLC 可复制
    JSON_DECODE_ERROR    = auto()   # JSON 解析失败
    SAVE_ERROR           = auto()   # 保存失败
    TRANSLATION_MISMATCH = auto()   # 翻译结果数量与输入数量不匹配
    FALLBACK_TO_ORIGINAL = auto()   # 全部格式解析失败，回退保存为 KR 原文
```

- [ ] **Step 2: 验证枚举值可用**

```bash
python -c "from translateFunc.enums import ProcessResult; assert ProcessResult.FALLBACK_TO_ORIGINAL.name == 'FALLBACK_TO_ORIGINAL'; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add translateFunc/enums.py
git commit -m "feat: ProcessResult 新增 FALLBACK_TO_ORIGINAL 枚举值"
```

---

### Task 2: 格式感知 `_split_by_length` — `build()` 接受 `prompt_format`

**Files:**
- Modify: `translateFunc/builder/request.py:47-49` (`build` 签名)
- Modify: `translateFunc/builder/request.py:150-192` (`_split_by_length` 实现)
- Modify: `translateFunc/builder/request.py:216-223` (`_get_request_text` 恢复使用)
- Modify: `translateFunc/processor.py:167-168` (调用点传入格式)

**Interfaces:**
- Consumes: `TranslateConfig.prompt_format` (已有)
- Produces: `RequestBuilder.build(prompt_format: str = "xml_json") → dict`
- Produces: `RequestBuilder._split_by_length(prompt_format: str = "xml_json") → None`

- [ ] **Step 1: 修改 `build()` 签名，接受 `prompt_format` 参数**

```python
# translateFunc/builder/request.py — build 方法签名
def build(self, prompt_format: str = "xml_json") -> dict:
    """构建统一请求结构。prompt_format 用于长度估算。

    Args:
        prompt_format: "xml_json" | "xml_xml" | "json_json"
    """
    # ... 现有构建逻辑不变 ...
    self._split_by_length(prompt_format)  # 传入格式参数
    return self.unified_request
```

- [ ] **Step 2: 重写 `_split_by_length` 使用格式感知估算**

```python
# translateFunc/builder/request.py — _split_by_length 完整重写
def _split_by_length(self, prompt_format: str = "xml_json") -> None:
    """将请求按 max_length 分割，使用格式感知长度估算。

    对三种格式均取 max 估算，确保无论后续回退到何种格式都不超限。
    """
    if self.unified_request is None:
        return

    all_formats = ["xml_json", "xml_xml", "json_json"]

    def estimate(request_dict, fmt: str) -> int:
        return len(self._get_request_text(request_dict, fmt))

    # 不分割检查：用主格式估算
    if estimate(self.unified_request, prompt_format) <= self.max_length:
        self.split_requests = [self.unified_request]
        return

    text_blocks = self.unified_request.get("text_blocks", [])
    total_blocks = len(text_blocks)

    # 尝试 2..min(10, total_blocks) 份分割
    for num_parts in range(2, min(10, total_blocks) + 1):
        part_size = total_blocks // num_parts
        remainder = total_blocks % num_parts
        parts = []
        start_idx = 0
        for i in range(num_parts):
            end_idx = start_idx + part_size + (1 if i < remainder else 0)
            part = {
                "metadata": {**self.unified_request["metadata"],
                             "total_text_blocks": end_idx - start_idx},
                "reference": self.unified_request["reference"],
                "text_blocks": text_blocks[start_idx:end_idx],
            }
            parts.append(part)
            start_idx = end_idx

        # 每个 part 对三种格式均不超限
        if all(estimate(p, fmt) <= self.max_length
               for p in parts for fmt in all_formats):
            self.split_requests = parts
            return

    # 回退：固定按 5 份分割
    parts = []
    part_size = max(1, total_blocks // 5)
    for i in range(0, total_blocks, part_size):
        end_idx = min(i + part_size, total_blocks)
        parts.append({
            "metadata": {**self.unified_request["metadata"],
                         "total_text_blocks": end_idx - i},
            "reference": self.unified_request["reference"],
            "text_blocks": text_blocks[i:end_idx],
        })
    self.split_requests = parts
```

- [ ] **Step 3: 更新 `processor.py` 中的调用点**

```python
# translateFunc/processor.py:_translate() — 约第 167 行
# 将 builder.build() 改为 builder.build(prompt_format=user_format)
builder.build(prompt_format=self._config.prompt_format)
```

- [ ] **Step 4: 运行现有测试确认无回归**

```bash
python -m pytest tests/test_prompt_format.py -v --tb=short -x
python -m pytest tests/test_pipeline.py -v --tb=short -x
python -m pytest tests/test_ac_automaton.py -v --tb=short -x
```

- [ ] **Step 5: Commit**

```bash
git add translateFunc/builder/request.py translateFunc/processor.py
git commit -m "fix: _split_by_length 恢复格式感知长度估算，build() 接受 prompt_format 参数"
```

---

### Task 3: Per-block 引用字段在 user prompt 中补充

**Files:**
- Modify: `translateFunc/builder/prompt.py:395-407` (`render_text_blocks`)
- Modify: `translateFunc/builder/prompt.py:425-436` (`render_text_blocks_json`)
- Modify: `translateFunc/builder/prompt.py:49-58` (`_STAGE1_RULES` — 微调规则文字)
- Modify: `translateFunc/builder/prompt.py:129-139` (`_JSON_STAGE1_RULES` — 微调规则文字)
- Modify: `translateFunc/builder/request.py:418-426` (`_make_json_user_prompt` text_blocks 构建)

**Interfaces:**
- Consumes: `text_block["proper_refs"]` (list[str] | None), `text_block["affect_refs"]` (list[str] | None), `text_block["model"]` (str | None)
- Produces: 与 Task 4/5/6 无接口依赖（输出字段在 user prompt 中，LLM 自动消费）

- [ ] **Step 1: 更新 `render_text_blocks`（XML 路径）— 追加可选子元素**

```python
# translateFunc/builder/prompt.py — render_text_blocks 方法
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
```

- [ ] **Step 2: 更新 `render_text_blocks_json`（JSON 路径）— 追加可选字段**

```python
# translateFunc/builder/prompt.py — render_text_blocks_json 方法
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
        # Per-block 引用字段
        if block.get("proper_refs"):
            item["proper_refs"] = block["proper_refs"]
        if block.get("affect_refs"):
            item["affect_refs"] = block["affect_refs"]
        if block.get("model"):
            item["model"] = block["model"]
        items.append(item)
    return _json.dumps({"text_blocks": items}, ensure_ascii=False, indent=2) + "\n"
```

- [ ] **Step 3: 更新 `_make_json_user_prompt` 内联的 text_blocks 构建**

```python
# translateFunc/builder/request.py — _make_json_user_prompt 方法，约第 418 行
# 替换现有 items 构建逻辑：
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
output["text_blocks"] = items
```

- [ ] **Step 4: 微调 Stage 1 规则文字**

```python
# translateFunc/builder/prompt.py — _STAGE1_RULES (约第 49 行)
# 将第一条规则从：
# "<rule>先查看reference中的术语表和指南，确保术语一致性</rule>\n"
# 改为：
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

# _JSON_STAGE1_RULES 第一条同理：
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
```

- [ ] **Step 5: 验证 refs 在所有三种格式的 prompt 中均正确渲染**

```bash
python -c "
from translateFunc.builder.prompt import PromptFactory
pf = PromptFactory()

block = {'kr': '테스트', 'jp': 'テスト', 'en': 'Test',
         'proper_refs': ['용어1', '용어2'],
         'affect_refs': ['[1001]'],
         'model': 'char_01'}

# XML
xml = pf.render_text_blocks([block])
assert 'proper_refs' in xml
assert '용어1, 용어2' in xml
assert 'affect_refs' in xml
assert '[1001]' in xml
assert '<model>char_01</model>' in xml
print('XML: OK')

# JSON
json_str = pf.render_text_blocks_json([block])
import json
data = json.loads(json_str)
tb = data['text_blocks'][0]
assert tb['proper_refs'] == ['용어1', '용어2']
assert tb['affect_refs'] == ['[1001]']
assert tb['model'] == 'char_01'
print('JSON: OK')

# Block without refs (optional fields omitted)
block_no_refs = {'kr': '테스트', 'jp': 'テスト'}
xml2 = pf.render_text_blocks([block_no_refs])
assert 'proper_refs' not in xml2
assert 'model' not in xml2
print('No-refs: OK')
"
```

- [ ] **Step 6: Commit**

```bash
git add translateFunc/builder/prompt.py translateFunc/builder/request.py
git commit -m "feat: user prompt 补充 per-block 引用字段（proper_refs/affect_refs/model）"
```

---

### Task 4: 阶段 0 消歧编排

**Files:**
- Modify: `translateFunc/processor.py:154-237` (`_translate` — 在阶段 1 之前插入阶段 0 编排)
- Modify: `translateFunc/processor.py` (新增 2 个方法：`_collect_ambiguous_terms`, `_apply_disambiguation`)

**Interfaces:**
- Consumes: `StageStrategy.needs_disambiguation()`, `build_stage_0_prompt()`, `parse_stage_0_result()`, `should_llm_disambiguate()` (已有)
- Consumes: `RequestBuilder.unified_request["text_blocks"]`, `["reference"]["proper_terms"]`
- Consumes: `_build_translator_for_format(system_prompt, prompt_format)` (已有)
- Consumes: `builder.get_request_text(prompt_format=...)` (已有)
- Produces: `FileProcessor._collect_ambiguous_terms(builder, stage_strategy) → list[dict]`
- Produces: `FileProcessor._apply_disambiguation(builder, disambiguated: list[dict]) → None`

- [ ] **Step 1: 实现 `_collect_ambiguous_terms`**

在 `processor.py` 的 `FileProcessor` 类中添加：

```python
def _collect_ambiguous_terms(
    self, builder: "RequestBuilder", stage_strategy: "StageStrategy"
) -> list[dict]:
    """收集需要 LLM 消歧的术语-文本块关联。

    遍历 unified_request["text_blocks"]，收集其中 proper_refs 引用的术语。
    disambiguation_mode="llm" 时全部匹配参与消歧；
    disambiguation_mode="hybrid" 时也收集全部（confidence 过滤依赖 ProperAnalyzer 集成）。

    Returns:
        [{term, cn, note, text_block_indices: [int, ...]}, ...]
    """
    text_blocks = builder.unified_request.get("text_blocks", [])
    proper_terms = {
        t.get("term", ""): t
        for t in builder.unified_request.get("reference", {}).get("proper_terms", [])
    }

    # term_key → 出现它的 text_block 索引列表
    term_block_map: dict[str, list[int]] = {}
    for i, block in enumerate(text_blocks):
        refs = block.get("proper_refs", [])
        for ref in refs:
            if ref not in term_block_map:
                term_block_map[ref] = []
            term_block_map[ref].append(i)

    if not term_block_map:
        return []

    # disambiguation_mode 判断
    mode = self._config.disambiguation_mode
    if mode == "similarity":
        return []  # 不需要 LLM 消歧

    # llm / hybrid 模式：收集所有匹配术语
    # 注：hybrid 模式理想行为是仅收集 LOW/UNKNOWN 置信度术语，
    # 但 confidence 数据需要 ProperAnalyzer 集成，当前暂全部收集
    if mode == "hybrid" and self._dump:
        self._log("hybrid 消歧模式：confidence 过滤需要 ProperAnalyzer 集成，当前收集全部匹配术语")

    result = []
    for term_key, block_indices in term_block_map.items():
        term_data = proper_terms.get(term_key, {"term": term_key, "translation": ""})
        result.append({
            "kr": term_data.get("term", term_key),
            "cn": term_data.get("translation", ""),
            "note": term_data.get("note", ""),
            "text_block_indices": block_indices,
        })
    return result
```

- [ ] **Step 2: 实现 `_apply_disambiguation`**

```python
def _apply_disambiguation(
    self, builder: "RequestBuilder", disambiguated: list[dict]
) -> None:
    """将消歧结果应用到 builder 的术语表。

    对 applies=false 的术语，从 unified_request["reference"]["proper_terms"] 中移除，
    并通过 unified_request["text_blocks"] 中对应的 proper_refs 清除引用。
    """
    import logging

    if not disambiguated:
        return

    excluded_terms: set[str] = set()
    for item in disambiguated:
        if not item.get("applies", True):
            excluded_terms.add(item.get("term", ""))

    if not excluded_terms:
        return

    # 从 reference 中移除不适用的术语
    proper_terms = builder.unified_request.get("reference", {}).get("proper_terms", [])
    builder.unified_request["reference"]["proper_terms"] = [
        t for t in proper_terms
        if t.get("term", "") not in excluded_terms
    ]

    # 从 text_blocks 中清除对应引用
    text_blocks = builder.unified_request.get("text_blocks", [])
    for block in text_blocks:
        refs = block.get("proper_refs", [])
        if refs:
            block["proper_refs"] = [r for r in refs if r not in excluded_terms]
            if not block["proper_refs"]:
                del block["proper_refs"]

    logging.info(
        f"[{self.file_name}] 阶段 0 消歧：排除了 {len(excluded_terms)} 个不适用的术语: "
        f"{', '.join(sorted(excluded_terms))}"
    )
```

- [ ] **Step 3: 在 `_translate()` 中插入阶段 0 编排**

在 `stage_strategy = StageStrategy(self._config)` 之后、阶段 1 循环之前插入：

```python
# ====== 阶段 0：消歧（仅主格式） ======
if stage_strategy.needs_disambiguation():
    ambiguous_terms = self._collect_ambiguous_terms(builder, stage_strategy)
    if ambiguous_terms:
        try:
            import logging
            s0_system = stage_strategy.build_stage_0_prompt(
                ambiguous_terms,
                builder.unified_request.get("text_blocks", []),
                prompt_format=user_format,
            )
            s0_translator = self._build_translator_for_format(s0_system, user_format)
            # user prompt 用主格式渲染
            s0_user_prompts = builder.get_request_text(prompt_format=user_format)
            s0_user = s0_user_prompts[0] if s0_user_prompts else ""

            raw_response = s0_translator.translate(s0_user, timeout=60)
            disambiguated = stage_strategy.parse_stage_0_result(raw_response, prompt_format=user_format)

            if disambiguated:
                if self._dump:
                    self._log(f"阶段 0 消歧：{len(disambiguated)} 个术语被评估")
                self._apply_disambiguation(builder, disambiguated)
            elif self._dump:
                self._log("阶段 0 消歧：解析结果为空，使用原始术语表")
        except Exception as e:
            logging.warning(f"[{self.file_name}] 阶段 0 消歧失败 ({e})，使用原始术语表继续")
```

- [ ] **Step 4: 运行现有测试确认无回归**

```bash
python -m pytest tests/test_prompt_format.py tests/test_pipeline.py tests/test_ac_automaton.py -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add translateFunc/processor.py
git commit -m "feat: 阶段 0 消歧编排 — 主格式 LLM 消歧注入术语表"
```

---

### Task 5: 阶段 2 自校验编排

**Files:**
- Modify: `translateFunc/processor.py:154-237` (`_translate` — 在阶段 1 之后追加阶段 2 编排)
- Modify: `translateFunc/processor.py` (新增 `_apply_corrections` 方法)

**Interfaces:**
- Consumes: `StageStrategy.needs_self_check()`, `build_stage_2_prompt()`, `parse_stage_2_result()` (已有)
- Consumes: 阶段 1 输出 — `result` (list[str]) 和 `builder.unified_request["text_blocks"]`
- Produces: `FileProcessor._apply_corrections(translations: list[str], checked: list[dict]) → list[str]`

- [ ] **Step 1: 实现 `_apply_corrections`**

在 `processor.py` 的 `FileProcessor` 类中添加：

```python
def _apply_corrections(
    self, translations: list[str], checked: list[dict]
) -> list[str]:
    """应用阶段 2 自校验修正。

    仅对 checked 中 changed=true 的条目替换对应索引的翻译文本。
    checked 中的 id 字段为 1-based 序号，对应 translations 的索引。

    Args:
        translations: 阶段 1 的翻译文本列表
        checked: 阶段 2 的校验结果 [{id, translation, changed, change_reason}, ...]

    Returns:
        修正后的翻译文本列表
    """
    import logging

    result = list(translations)  # 浅拷贝
    corrections = 0
    for item in checked:
        if item.get("changed", False):
            idx = int(item.get("id", 0)) - 1  # 1-based → 0-based
            if 0 <= idx < len(result):
                result[idx] = item.get("translation", result[idx])
                corrections += 1

    if corrections > 0:
        logging.info(
            f"[{self.file_name}] 阶段 2 自校验：修正了 {corrections}/{len(checked)} 条翻译"
        )
    return result
```

- [ ] **Step 2: 在 `_translate()` 中插入阶段 2 编排**

在阶段 1 结果还原后、`return` 之前插入：

```python
# ====== 阶段 2：自校验（仅主格式，阶段 1 全部成功时执行） ======
if stage_strategy.needs_self_check() and not had_fallback:
    try:
        import logging
        # 收集原文块（从 builder.unified_request 中）
        original_blocks = builder.unified_request.get("text_blocks", [])
        # 构建译文 dict 列表（格式与 parse_stage_1_result 输出一致）
        translations_for_check = [
            {"id": i + 1, "translation": t}
            for i, t in enumerate(result)
        ]

        s2_prompt = stage_strategy.build_stage_2_prompt(
            self.file_type,
            prompt_format=user_format,
            original_blocks=original_blocks,
            translations=translations_for_check,
        )
        s2_translator = self._build_translator_for_format(s2_prompt, user_format)
        # 阶段 2 的 user prompt 为空字符串（全部在 system prompt 中）
        raw_response = s2_translator.translate("", timeout=120)
        checked = stage_strategy.parse_stage_2_result(raw_response, prompt_format=user_format)

        if checked:
            result = self._apply_corrections(result, checked)
        elif self._dump:
            self._log("阶段 2 自校验：解析结果为空，保留阶段 1 翻译")
    except Exception as e:
        logging.warning(
            f"[{self.file_name}] 阶段 2 自校验失败 ({e})，使用未校验的翻译结果"
        )
```

注意：`_translate()` 中阶段 1 现在将翻译结果存入 `result` (list[str])，阶段 2 结束后再调用 `builder.deBuild(result)`。需要调整阶段 1 后的还原逻辑：

```python
# 阶段 1 结束后的还原（原有逻辑，移至阶段 2 之后）
translations_dict = builder.deBuild(result)
return translations_dict, had_fallback
```

- [ ] **Step 3: 运行现有测试确认无回归**

```bash
python -m pytest tests/test_prompt_format.py tests/test_pipeline.py tests/test_ac_automaton.py -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add translateFunc/processor.py
git commit -m "feat: 阶段 2 自校验编排 — changed=true 自动修正翻译"
```

---

### Task 6: 全部格式失败提升为错误

**Files:**
- Modify: `translateFunc/processor.py:154-237` (`_translate` 返回类型 + had_fallback 标记)
- Modify: `translateFunc/processor.py:84-150` (`process` 方法处理 FALLBACK_TO_ORIGINAL)

**Interfaces:**
- Consumes: `ProcessResult.FALLBACK_TO_ORIGINAL` (Task 1)
- Consumes: Task 4, Task 5 中的 `_translate()` 重构
- Produces: `FileProcessor._translate(request_text) → tuple[dict, bool]`  — `had_fallback` 字段

- [ ] **Step 1: 修改 `_translate()` 签名和返回值**

```python
# translateFunc/processor.py — _translate 方法
def _translate(self, request_text: dict) -> tuple[dict, bool]:
    """通过配置的管线阶段执行翻译，支持格式回退。

    Returns:
        (翻译结果字典, had_fallback) — had_fallback=True 表示至少一个
        part 的全部格式失败，已回退为 KR 原文。
    """
    builder = RequestBuilder(
        request_text,
        self._engine,
        is_story=self.is_story,
        is_skill=self.is_skill,
        is_text_format=False,
        max_length=20000,
        file_type=self.file_type,
    )

    if self._config.is_llm:
        builder.build(prompt_format=self._config.prompt_format)
        stage_strategy = StageStrategy(self._config)
        user_format = self._config.prompt_format
        formats_chain = self._build_format_chain()

        had_fallback = False

        # ====== 阶段 0 ======
        # (Task 4 代码)

        # ====== 阶段 1 ======
        result: list[str] = []
        for i, request_part in enumerate(
            builder.split_requests if builder.split_requests else [builder.unified_request]
        ):
            if builder.split_requests:
                part_data = request_part
            else:
                part_data = builder.unified_request
            if part_data is None:
                continue

            part_result = None
            tried_formats: list[str] = []

            for fmt in formats_chain:
                tried_formats.append(fmt)
                system_prompt = stage_strategy.build_stage_1_prompt(
                    self.file_type, prompt_format=fmt,
                )
                user_prompt = builder.get_request_text(prompt_format=fmt)
                user_text = user_prompt[i] if i < len(user_prompt) else user_prompt[0]
                timeout = max(len(json.dumps(request_part, ensure_ascii=False)) // 200 + 1, 40)
                translator = self._build_translator_for_format(system_prompt, fmt)

                try:
                    raw_response = translator.translate(user_text, timeout=timeout)
                    if self._dump:
                        self._log(f"[{fmt}] 第 {i + 1} 部分: {str(raw_response)[:200]}...")
                    parsed = stage_strategy.parse_stage_1_result(raw_response, prompt_format=fmt)
                    if not parsed:
                        raise ValueError(f"{fmt}: 解析结果为空")
                    part_result = [
                        t.get("translation", "") if isinstance(t, dict) else str(t)
                        for t in parsed
                    ]
                    break
                except (json.JSONDecodeError, ValueError) as e:
                    if self._dump:
                        self._log(f"[{fmt}] 解析失败 ({e})，回退到下一格式")
                    continue

            if part_result is None:
                # 全部格式失败 → 无条件 warning + 标记降级
                import logging
                logging.warning(
                    f"[{self.file_name}] 全部格式 ({', '.join(tried_formats)}) "
                    f"解析失败，第 {i + 1}/{len(builder.split_requests)} 部分回退为 KR 原文"
                )
                had_fallback = True
                text_blocks = part_data.get("text_blocks", [])
                part_result = [b.get("kr", "") for b in text_blocks]

            result.extend(part_result)

        # ====== 阶段 2 ======
        # (Task 5 代码)

        return builder.deBuild(result), had_fallback
    else:
        # 非 LLM 路径：不存在格式回退
        simple_builder = _SimpleRequestBuilder(request_text)
        simple_builder.build()
        request_texts = simple_builder.get_request_text(from_lang=self._config.from_lang)
        result = self._translator.translate(request_texts)
        return simple_builder.deBuild(result), False
```

- [ ] **Step 2: 更新 `process()` 方法处理 had_fallback**

```python
# translateFunc/processor.py — process 方法，约第 119-150 行
# 将原来的：
#     translated_data = self._translate(request_text)
#     ...
#     self._de_get_translating_text(translated_data)
#     result = self._de_get_translating()
#     self._save_result(result)
#     return ProcessOutcome(ProcessResult.SUCCESS_SAVED, self.file_name)
#
# 改为：

        # 8. 构建并翻译
        try:
            translated_data, had_fallback = self._translate(request_text)
        except StopIteration:
            self._save_except()
            return ProcessOutcome(
                ProcessResult.TRANSLATION_MISMATCH,
                self.file_name,
                {"reason": "译文数量与原文不匹配"},
            )
        except Exception as e:
            self._save_except()
            return ProcessOutcome(
                ProcessResult.SAVE_ERROR,
                self.file_name,
                {"reason": str(e)},
            )

        # 9. 重建并保存
        self._de_get_translating_text(translated_data)
        result = self._de_get_translating()

        try:
            self._save_result(result)
        except Exception as e:
            return ProcessOutcome(
                ProcessResult.SAVE_ERROR,
                self.file_name,
                {"reason": str(e)},
            )

        if had_fallback:
            return ProcessOutcome(
                ProcessResult.FALLBACK_TO_ORIGINAL,
                self.file_name,
                {"fallback_parts": "部分文本块回退为 KR 原文"},
            )

        return ProcessOutcome(ProcessResult.SUCCESS_SAVED, self.file_name)
```

- [ ] **Step 3: 验证 `PipelineSummary` 正确分类 FALLBACK_TO_ORIGINAL**

`pipeline.py:_record_outcome()` 的 else 分支已正确处理：

```python
# 确认无误 —— 无需修改 pipeline.py
# else 分支将 FALLBACK_TO_ORIGINAL 归入 summary.errors
```

- [ ] **Step 4: 运行现有测试确认无回归**

```bash
python -m pytest tests/ -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add translateFunc/processor.py
git commit -m "feat: 全部格式失败 → FALLBACK_TO_ORIGINAL 错误 + 无条件 logging.warning"
```

---

### Task 7: 集成测试与回归验证

**Files:**
- Modify: `tests/test_prompt_format.py` (追加 per-block refs 测试 + 格式感知长度估算测试)

**Interfaces:**
- Consumes: Task 3 的 render_text_blocks 新输出格式
- Consumes: Task 2 的 _split_by_length 新行为
- 不依赖 Task 4/5/6（阶段编排需要 mock LLM 调用，集成测试用单独脚本）

- [ ] **Step 1: 追加 per-block refs 渲染测试**

在 `tests/test_prompt_format.py` 文件末尾追加：

```python
class TestPerBlockRefs:
    """Per-block 引用字段在三种格式的 prompt 中正确渲染。"""

    def setup_method(self):
        self.pf = PromptFactory()

    def test_xml_text_blocks_includes_refs(self):
        """XML: 有 proper_refs/affect_refs/model 的 block 输出对应元素。"""
        block = {
            "kr": "테스트", "jp": "テスト", "en": "Test",
            "proper_refs": ["용어1", "용어2"],
            "affect_refs": ["[1001]"],
            "model": "char_01",
        }
        xml = self.pf.render_text_blocks([block])
        assert "<proper_refs>용어1, 용어2</proper_refs>" in xml
        assert "<affect_refs>[1001]</affect_refs>" in xml
        assert "<model>char_01</model>" in xml

    def test_xml_text_blocks_omits_missing_refs(self):
        """XML: 无引用的 block 不输出 refs 元素。"""
        block = {"kr": "테스트", "jp": "テスト"}
        xml = self.pf.render_text_blocks([block])
        assert "proper_refs" not in xml
        assert "affect_refs" not in xml
        assert "model" not in xml

    def test_json_text_blocks_includes_refs(self):
        """JSON: 有引用字段的 block 输出对应 key。"""
        import json
        block = {
            "kr": "테스트", "jp": "テスト",
            "proper_refs": ["용어1"],
            "affect_refs": ["[1001]"],
            "model": "char_01",
        }
        json_str = self.pf.render_text_blocks_json([block])
        data = json.loads(json_str)
        tb = data["text_blocks"][0]
        assert tb["proper_refs"] == ["용어1"]
        assert tb["affect_refs"] == ["[1001]"]
        assert tb["model"] == "char_01"

    def test_json_text_blocks_omits_missing_refs(self):
        """JSON: 无引用的 block 不输出 refs key。"""
        import json
        block = {"kr": "테스트"}
        json_str = self.pf.render_text_blocks_json([block])
        data = json.loads(json_str)
        tb = data["text_blocks"][0]
        assert "proper_refs" not in tb
        assert "model" not in tb
```

- [ ] **Step 2: 追加格式感知长度估算的单元测试**

```python
class TestFormatAwareSplit:
    """_split_by_length 使用格式感知长度估算。"""

    def test_xml_format_triggers_split_earlier(self):
        """XML 格式比 JSON dump 估算更长，更早触发分割。"""
        from translateFunc.builder.request import RequestBuilder
        from unittest.mock import MagicMock

        # 构造足够多的 text_blocks 使 xml_xml 超出 max_length
        blocks = [{"kr": f"테스트_{i}", "jp": f"テスト_{i}", "en": f"Test_{i}"}
                   for i in range(2000)]

        engine = MagicMock()
        engine.match_all.return_value = MagicMock(
            proper_matches=[], role_matches=[],
            affect_id_matches=[], affect_name_matches=[],
        )
        engine.role_data = []
        engine.affect_data = []

        builder = RequestBuilder(
            request_text={"kr": {0: {("text",): blocks[0]["kr"]}}},
            matcher_engine=engine,
            max_length=10000,
        )
        # 手动设置 unified_request 以绕过复杂的 build 流程
        builder.unified_request = {
            "metadata": {"total_text_blocks": len(blocks),
                         "proper_terms_count": 0, "affects_count": 0,
                         "models_count": 0, "file_type": "STORY"},
            "reference": {"proper_terms": [], "affects": [],
                          "models": [], "model_docs": [], "skill_doc": ""},
            "text_blocks": blocks,
        }

        builder._split_by_length(prompt_format="xml_xml")
        assert len(builder.split_requests) > 1, (
            f"xml_xml 应触发分割，但 split_requests 只有 {len(builder.split_requests)} 部分"
        )

    def test_json_format_triggers_split_later(self):
        """json_json 比 xml_xml 更紧凑，需要更多 block 才触发分割。"""
        from translateFunc.builder.request import RequestBuilder
        from unittest.mock import MagicMock

        blocks = [{"kr": "짧은", "jp": "短い", "en": "Short"} for _ in range(200)]

        engine = MagicMock()
        engine.match_all.return_value = MagicMock(
            proper_matches=[], role_matches=[],
            affect_id_matches=[], affect_name_matches=[],
        )
        engine.role_data = []
        engine.affect_data = []

        builder = RequestBuilder(
            request_text={"kr": {0: {("text",): blocks[0]["kr"]}}},
            matcher_engine=engine,
            max_length=50000,
        )
        builder.unified_request = {
            "metadata": {"total_text_blocks": len(blocks),
                         "proper_terms_count": 0, "affects_count": 0,
                         "models_count": 0, "file_type": "STORY"},
            "reference": {"proper_terms": [], "affects": [],
                          "models": [], "model_docs": [], "skill_doc": ""},
            "text_blocks": blocks,
        }

        builder._split_by_length(prompt_format="json_json")
        # 200 个短 block 在 50000 上限下不应分割
        assert len(builder.split_requests) == 1, (
            f"json_json 200 短 block 不应分割，但 split_requests={len(builder.split_requests)}"
        )
```

- [ ] **Step 3: 运行全部测试**

```bash
python -m pytest tests/ -v --tb=short
```

预期：全部通过，包括新增的 per-block refs 和分片测试。

- [ ] **Step 4: Commit**

```bash
git add tests/test_prompt_format.py
git commit -m "test: per-block refs 渲染 + 格式感知分片测试"
```

---

### 验证清单

全部任务完成后，确认：

- [ ] `ProcessResult.FALLBACK_TO_ORIGINAL` 枚举存在
- [ ] `enable_self_check: true` + `translation_mode: "multi_stage"` → 阶段 2 被执行
- [ ] `disambiguation_mode: "llm"` + `translation_mode: "multi_stage"` → 阶段 0 被执行
- [ ] `disambiguation_mode: "similarity"` → 阶段 0 被跳过
- [ ] 阶段 0 失败 → `logging.warning` + 阶段 1 正常执行
- [ ] 阶段 2 失败 → `logging.warning` + 阶段 1 结果保留
- [ ] `disambiguation_mode: "llm"` + `translation_mode: "single_stage"` → 阶段 0 被跳过
- [ ] `enable_self_check: true` + `translation_mode: "single_stage"` → 阶段 2 被跳过
- [ ] 非 LLM 路径（`is_llm=False`）不受影响
- [ ] XML user prompt 包含 `<proper_refs>`, `<affect_refs>`, `<model>` 元素
- [ ] JSON user prompt 包含 `proper_refs`, `affect_refs`, `model` 字段
- [ ] 格式感知分片对 xml_xml 更早触发分割
- [ ] 全部格式失败 → `logging.warning()` 无条件输出
- [ ] 全部格式失败 → `FALLBACK_TO_ORIGINAL` → `PipelineSummary.errors`
- [ ] `tests/` 下全部 56+ 测试通过
