# 四项缺陷修复——设计文档

日期：2026-06-27
状态：待实现
关联：[[2026-06-27-prompt-format-report]]（报告中记录的已知问题）

## 概述

一次性修复 prompt-format 重构后遗留的四项缺陷：

| # | 问题 | 严重度 | 文件 |
|---|------|--------|------|
| 1 | `enable_self_check` / `disambiguation_mode` 无消费者——阶段 0/2 未实现 | 高 | processor.py |
| 2 | per-block 引用字段（proper_refs/affect_refs/model）在 user prompt 中被丢弃 | 高 | request.py, prompt.py |
| 3 | `_split_by_length` 用 json.dumps 估算长度，XML 格式实际请求可能超限 | 中 | request.py |
| 4 | 全部格式失败时静默保存 KR 原文，默认无警告 | 中 | processor.py, enums.py |

---

## 1. 三阶段管线编排（Issue 1）

### 流程

```
_translate(request_text):
  builder.build(prompt_format=user_format)    # 传入主格式用于长度估算
  stage_strategy = StageStrategy(config)

  ╔══════════════════════════════════════════╗
  ║ 阶段 0：消歧（仅主格式，不回退）        ║
  ╚══════════════════════════════════════════╝
  if needs_disambiguation():
      收集模糊匹配术语 → 构建 prompt → 调用 LLM
      成功 → 消歧结果注入 builder 术语表
      失败 → logging.warning + 继续用原始术语表

  ╔══════════════════════════════════════════╗
  ║ 阶段 1：主翻译（格式回退链）            ║
  ╚══════════════════════════════════════════╝
  for part in split_parts:
      for fmt in [user_format, xml_json, json_json, xml_xml]:
          构建 system_prompt + user_prompt → 调用 LLM → 解析
          成功 → break
          失败 → 下一个格式
      全部失败 → logging.warning + 回退为 KR 原文（见 Issue 4）

  ╔══════════════════════════════════════════╗
  ║ 阶段 2：自校验（仅主格式，不回退）      ║
  ╚══════════════════════════════════════════╝
  if needs_self_check():
      构建原文+译文对 → 调用 LLM 校验
      成功 → 应用 changed=true 的修正
      失败 → logging.warning + 保持阶段 1 结果
```

### 关键决策

- **阶段 0 和阶段 2 仅使用用户选择的主格式**，不参与回退链
- **阶段 0/2 失败不中断管线**：分别 warning 后继续
- 阶段 0 的消歧结果在阶段 1 之前注入 builder 的术语表，阶段 1 自动受益
- 阶段 2 只应用 `changed=true` 的条目；`changed=false` 保留阶段 1 输出

### 涉及接口

已有的 `StageStrategy` 和 `PromptFactory` 方法：
- `needs_disambiguation()`, `build_stage_0_prompt()`, `parse_stage_0_result()`
- `build_stage_1_prompt()`, `parse_stage_1_result()`（已有，不变）
- `needs_self_check()`, `build_stage_2_prompt()`, `parse_stage_2_result()`

`processor.py` 新增：
- `_collect_ambiguous_terms(builder, stage_strategy) → list[dict]` — 遍历 `unified_request["text_blocks"]`，收集 `proper_refs` 中满足 `should_llm_disambiguate()` 的术语。返回 `[{term, cn, note, text_block_indices}]`
- `_apply_disambiguation(builder, result) → None` — 根据消歧结果：`applies=false` 的术语从 `unified_request["reference"]["proper_terms"]` 中移除，确保阶段 1 不会将其作为翻译参考
- `_apply_corrections(translations, checked) → list[dict]` — 遍历 checked 结果，对 `changed=true` 的条目用 `checked.translation` 替换阶段 1 对应输出

含糊匹配定义：由 `StageStrategy.should_llm_disambiguate(confidence)` 判断。`disambiguation_mode="llm"` 时全部匹配参与消歧；`"hybrid"` 时仅 LOW + UNKNOWN 匹配参与消歧。

`_translate()` 返回值从 `dict` 改为 `tuple[dict, bool]`，`bool` 表示是否发生了 all-formats-failed（见 Issue 4）。

---

## 2. Per-block 引用字段补充（Issue 2）

### XML 路径 (`PromptFactory.render_text_blocks`)

每个 `<block>` 在有引用时追加子元素：

```xml
<block id="1">
  <kr>원문</kr>
  <jp>日本語</jp>
  <en>English</en>
  <proper_refs>용어1, 용어2</proper_refs>
  <affect_refs>[1001]</affect_refs>
  <model>character_id</model>
</block>
```

字段仅在 `block` 中存在对应 key 时输出。

### JSON 路径（两处）

**`PromptFactory.render_text_blocks_json`** 和 **`RequestBuilder._make_json_user_prompt`** 中，每个条目追加可选字段：

```json
{
  "id": 1,
  "kr": "원문",
  "jp": "日本語",
  "en": "English",
  "proper_refs": ["용어1", "용어2"],
  "affect_refs": ["[1001]"],
  "model": "character_id"
}
```

### System prompt 规则微调

XML 和 JSON 的 Stage 1 规则第一条同步更新，提到 per-block refs：

```
先查看reference中的术语表及每条文本块的proper_refs/affect_refs/model引用，确保术语一致性
```

`_make_xml_user_prompt` 中 `render_text_blocks()` 已包含 refs（通过 `PromptFactory`），无需额外改动。`_make_json_user_prompt` 内联的 text_blocks 构建直接补齐。

---

## 3. 格式感知长度估算（Issue 3）

### 变更

`RequestBuilder.build()` 增加 `prompt_format` 参数：

```python
def build(self, prompt_format: str = "xml_json") -> dict:
    ...
    self._split_by_length(prompt_format)
    return self.unified_request
```

`_split_by_length()` 内部改为调用 `_get_request_text()`（格式感知，已存在但为死代码）替代 `json.dumps()`：

```python
def _split_by_length(self, prompt_format: str = "xml_json") -> None:
    all_formats = ["xml_json", "xml_xml", "json_json"]
    
    def estimate(request_dict, fmt):
        return len(self._get_request_text(request_dict, fmt))
    
    # 不分割检查：用主格式估算
    if estimate(self.unified_request, prompt_format) <= self.max_length:
        self.split_requests = [self.unified_request]
        return
    
    # 需要分割时：每个 part 对三种格式均不超限
    for num_parts in range(2, min(10, total_blocks) + 1):
        parts = [...]
        if all(estimate(p, fmt) <= self.max_length 
               for p in parts for fmt in all_formats):
            self.split_requests = parts
            return
    
    # 回退分割
    ...
```

### 为何取三种格式的 max

分割发生在 `build()` 时，此时不知道后续回退链会用到哪些格式。一个 part 在 `json_json` 下可能 18KB → OK，但在 `xml_xml` 下 28KB → 超限。取 max 确保无论回退到何种格式都不会超出上下文窗口。

### 调用点

```python
# processor.py:_translate()
builder.build(prompt_format=self._config.prompt_format)
```

---

## 4. 全部格式失败提升为错误（Issue 4）

### 4.1 新增枚举值

```python
# translateFunc/enums.py
class ProcessResult(Enum):
    ...
    FALLBACK_TO_ORIGINAL = auto()  # 全部格式解析失败，回退保存为 KR 原文
```

### 4.2 无条件 warning

将 `logging.warning()` 从 `if self._dump:` 保护中移出：

```python
# processor.py:_translate()
if part_result is None:
    logging.warning(
        f"[{self.file_name}] 全部格式 ({', '.join(tried_formats)}) 解析失败，"
        f"第 {i + 1}/{len(builder.split_requests)} 部分回退为 KR 原文"
    )
    ...
```

### 4.3 返回值携带降级状态

`_translate()` 返回值改为 `tuple[dict, bool]`：

```python
# processor.py
def _translate(self, request_text: dict) -> tuple[dict, bool]:
    ...
    had_fallback = False
    ...
    if part_result is None:
        had_fallback = True
        ...
    return builder.deBuild(result), had_fallback
```

`process()` 中处理：

```python
translated_data, had_fallback = self._translate(request_text)
...
if had_fallback:
    self._save_result(result)
    return ProcessOutcome(ProcessResult.FALLBACK_TO_ORIGINAL, self.file_name)
```

### 4.4 错误分类

`pipeline.py:_record_outcome()` 中 else 分支已将非 SUCCESS/ALREADY/EMPTY 的结果归入 `summary.errors`。`FALLBACK_TO_ORIGINAL` 自动落入此分支，无需修改 pipeline。

---

## 影响范围

| 文件 | 改动说明 |
|------|----------|
| `translateFunc/enums.py` | 新增 `FALLBACK_TO_ORIGINAL` |
| `translateFunc/processor.py` | 实现三阶段编排；`_translate()` 返回 tuple；新增 3 个辅助方法；all-formats-failed 提升为 error |
| `translateFunc/builder/request.py` | `build()` 接受 `prompt_format`；`_split_by_length()` 格式感知；`_make_json_user_prompt()` 包含 refs |
| `translateFunc/builder/prompt.py` | `render_text_blocks()` / `render_text_blocks_json()` 输出 refs；stage rules 微调 |
| `translateFunc/builder/stages.py` | 可能无改动（已有接口足够） |
| `translateFunc/config.py` | 无改动（`enable_self_check` / `disambiguation_mode` 已有） |
| `translateFunc/pipeline.py` | 无改动（error 分类已有正确的兜底分支） |

## 测试要点

- 阶段 0：消歧结果注入后，阶段 1 术语表正确过滤
- 阶段 0 失败 → warning，不阻断阶段 1
- 阶段 2：修正 changed=true 的条目，保留 changed=false 的条目
- 阶段 2 失败 → warning，阶段 1 结果保持不变
- 阶段 0/2 LLM 调用仅在 `translation_mode=multi_stage` 时触发
- Per-block refs 在所有三种格式的 prompt 中正确渲染
- `_split_by_length` 对 xml_xml 触发分割（原不会触发）
- 全部格式失败 → `FALLBACK_TO_ORIGINAL` → 归入 `summary.errors`
- 全部格式失败 → `logging.warning()` 在 dump=False 时也输出
