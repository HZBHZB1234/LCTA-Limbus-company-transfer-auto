# Prompt 格式扩展与配置统合 — 设计文档

日期：2026-06-27

## 目标

1. 为翻译管线新增两种 prompt/response 格式（xml_xml、json_json），与现有 xml_json 并列
2. 统合配置项：消除僵尸配置、移除功能重叠项、重新实现 fallback

---

## 一、配置统合

### 变更清单

| 配置项 | 当前状态 | 变更 |
|---|---|---|
| `is_text_format` | 布尔值，控制请求格式 | **移除**，由 `prompt_format` 取代 |
| `prompt_format` | 仅存在于 config.json，未接入代码 | **接入** `TranslateConfig`，值为 `"xml_json"` / `"xml_xml"` / `"json_json"` |
| `fallback` | 僵尸配置（存入但无代码读取） | **重新实现**：格式解析失败时按固定链回退 |
| `from_lang` | 非 LLM 路径使用 | **保留**，不变 |
| 其他全部配置项 | 均有明确消费者 | **不变** |

### 前端变更

- 移除 `is-text` 复选框
- 新增 `prompt-format` 下拉框，三个选项：
  - `xml_json` — "XML 请求 → JSON 响应（推荐）"
  - `json_json` — "JSON 请求 → JSON 响应"
  - `xml_xml` — "XML 请求 → XML 响应"
- `core.js` 字段映射：移除 `is-text`，新增 `prompt-format`

### 后端变更

- `TranslateConfig`：新增 `prompt_format: str = "xml_json"`，移除 `is_text_format`
- `from_config_manager()`：同步调整字段映射；缺失 `prompt_format` 时默认 `"xml_json"`

---

## 二、Prompt/Response 格式

### 三种格式

| 格式 | System prompt 结构 | Response 格式 |
|---|---|---|
| `xml_json` | XML 标签 | JSON |
| `xml_xml` | XML 标签 | XML |
| `json_json` | JSON | JSON |

不包含 `json_xml`（故意排除）。

### System prompt vs User prompt 分工

| | System prompt | User prompt |
|---|---|---|
| **内容** | role + rules + format 指令（固定模板） | glossary + skill_doc + role_styles + text_blocks（动态数据） |
| **格式** | 与 `prompt_format` 一致 | 与 `prompt_format` 一致 |

- `skill_doc` / `role_styles` 当前在两端都出现。改为**仅在 user prompt 中携带**。
- System prompt 精简为纯模板（同 file_type + stage + format 共享）。
- User prompt 格式由 `RequestBuilder` 按 `prompt_format` 渲染。

---

## 三、PromptFactory 格式扩展

### 模板维度

方法增加 `prompt_format` 参数，模板按 `(stage, format)` 二维 key 组织：

| Stage | xml_json / xml_xml 公共部分（role, rules） | json_json 公共部分 |
|---|---|---|
| 0/1/2 | XML 标签（共享） | JSON 结构 |

| Stage | format 指令 |
|---|---|
| 0 | xml_json: JSON disambiguations / xml_xml: XML disambiguations / json_json: JSON disambiguations |
| 1 | xml_json: JSON translations / xml_xml: XML translations / json_json: JSON translations |
| 2 | xml_json: JSON checked_translations / xml_xml: XML checked_translations / json_json: JSON checked_translations |

### 新增方法

- `render_text_blocks_json(blocks) → str` — JSON 格式的 text_blocks 渲染
- `render_glossary_json(terms) → str` — JSON 格式的 glossary 渲染
- `parse_response(text, stage, prompt_format) → list[dict]` — 按 format 分发：
  - `xml_json` / `json_json` → `json.loads()` 
  - `xml_xml` → `xml.etree.ElementTree` 解析

### `build_system_prompt()` 签名变更

```python
def build_system_prompt(
    self,
    file_type: FileType,
    stage: int,
    prompt_format: str,        # 新增
    # 移除 skill_doc, role_styles（移到 user prompt）
    examples: list[dict] | None = None,
) -> str:
```

---

## 四、RequestBuilder User Prompt 格式

`get_request_text()` 新增 `prompt_format` 参数：

```
get_request_text(prompt_format: str) → list[str]
```

- `xml_json` / `xml_xml` → 复用 `PromptFactory.render_glossary()` + `render_text_blocks()` 等 XML 渲染方法
- `json_json` → 新增 JSON 渲染，直接构建 `{glossary: [...], text_blocks: [...], skill_doc: "...", role_styles: [...]}`

`_make_text()` 纯文本路径不受影响（非 LLM 使用）。

---

## 五、Fallback 回退逻辑

### 触发条件

LLM 返回结果**解析失败**时触发（JSON 解析错误、XML 解析错误、或预期字段缺失）。网络/API 错误不回退。

### 回退链

`[用户选择的格式]` → `xml_json` → `json_json` → `xml_xml`

已尝试过的格式跳过，不重复。

### 实现位置

在 `FileProcessor._translate()` 中，对每个 request_part：

```
确定格式链
for fmt in formats_chain:
    try:
        result = translate_with_format(request_part, fmt)
        break
    except ParseError:
        log(f"{fmt} 解析失败，回退")
        continue
```

- 每次重试重新调用 LLM（使用不同 format 的 system prompt + user prompt）
- 待翻译数据不变，仅格式包装不同

### 全部格式失败

记录日志，返回原文（kr_text）作为翻译结果，ProcessOutcome 含低置信度标记。

---

## 六、`_build_translator()` 变更

移除 `translate_doc.py` 的旧 system prompt 硬编码：

```python
# 旧代码（移除）
api_settings["system_prompt"] = TEXT_SYSTEM_PROMPT if is_text_format else JSON_SYSTEM_PROMPT
```

改为 `system_prompt` 由调用方动态注入，`_build_translator()` 接受可选参数：

```python
def _build_translator(self, system_prompt: str = "") -> TranslatorBase:
```

---

## 七、translate_doc.py

- 移除 `JSON_SYSTEM_PROMPT` / `TEXT_SYSTEM_PROMPT`
- 保留 `SKILLL_DOC`、`ROLE_STYLE`、`RLOE_COMPARE`（数据常量）

---

## 八、完整流程

单个 request_part 的处理：

```
1. 确定格式链：[user_format] + fallback? ["xml_json","json_json","xml_xml"] : []
2. 对当前格式 fmt：
   a. PromptFactory.build_system_prompt(file_type, stage, fmt)  → system_prompt
   b. RequestBuilder.get_request_text(fmt)                        → user_prompt  
   c. _build_translator(system_prompt) → translator
   d. translator.translate(user_prompt, timeout) → raw_response
   e. PromptFactory.parse_response(raw_response, stage, fmt) → parsed_data
   f. 解析成功 → 返回
      解析失败 + 有下一格式 → fmt = next，回到 2a
      解析失败 + 无下一格式 → 记录错误，返回原文
```

---

## 九、错误处理

| 错误类型 | 处理 |
|---|---|
| `json.JSONDecodeError` | 触发格式回退 |
| `xml.etree.ElementTree.ParseError` | 触发格式回退 |
| 结构字段缺失 | 触发格式回退 |
| 全部格式失败 | 日志记录，回退为原文（kr_text） |
| 网络/API 错误 | 不触发格式回退，向上传播 |

非 LLM 路径（`is_llm=False`）不受 format/fallback 影响，保持现有行为。

---

## 十、向前兼容

- `TranslateConfig.from_config_manager()` 读取 `is_text` 旧键时忽略（不崩溃）
- 缺失 `prompt_format` 时默认 `"xml_json"`
- 旧 `config.json` 中 `is_text` 项可保留，不会导致错误

---

## 十一、变更文件清单

| 文件 | 变更类型 |
|---|---|
| `translateFunc/builder/prompt.py` | 修改 — 新增 format 参数 + json_json 模板 + XML/JSON 渲染 + 解析方法 |
| `translateFunc/builder/request.py` | 修改 — `get_request_text()` 新增 format 参数 + XML/JSON 输出 |
| `translateFunc/builder/stages.py` | 修改 — 透传 format，委托 PromptFactory |
| `translateFunc/processor.py` | 修改 — fallback 循环实现 |
| `translateFunc/pipeline.py` | 修改 — `_build_translator()` 接受 system_prompt 参数 |
| `translateFunc/config.py` | 修改 — `+prompt_format`, `-is_text_format` |
| `translateFunc/translate_doc.py` | 修改 — 移除旧 system prompt |
| `webui/index.html` | 修改 — is-text 复选框 → prompt-format 下拉框 |
| `webui/js/core.js` | 修改 — 字段映射更新 |
| `config.json` | 修改 — 添加 `prompt_format` 默认值 |
| `config_default.json` | 修改 — 同步 |
| `config_check.json` | 修改 — 同步 |
| `tests/` | 新增 — 格式生成 + 解析 + fallback 测试 |

---

## 十二、测试要点

- 三种格式的 system prompt 生成正确性
- 三种格式的 user prompt 生成正确性
- XML 响应解析：正确提取嵌套字段，处理缺失可选字段
- Fallback 链：单次失败 → 回退成功；全部失败 → 不崩溃，返回原文
- 旧配置兼容：加载含 `is_text` 的旧配置文件不报错
- 非 LLM 路径不受影响
