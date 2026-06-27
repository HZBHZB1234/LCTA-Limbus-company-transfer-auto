# 四项缺陷修复 — 工作报告

日期：2026-06-27
状态：已完成（未推送，保留在本地 main 分支）

## 概述

一次性修复 prompt-format 重构（2026-06-27）后遗留的四项缺陷，实现了完整的三阶段翻译管线、per-block 引用字段补充、格式感知长度估算，以及将全部格式失败从静默保存提升为显式错误。

## 修复的问题

| # | 问题 | 严重度 | 修复方式 |
|---|------|--------|----------|
| 1 | `enable_self_check` / `disambiguation_mode` 无消费者 | 高 | 实现阶段 0（消歧）和阶段 2（自校验）编排逻辑 |
| 2 | per-block 引用字段在 user prompt 中被丢弃 | 高 | 在 XML/JSON 渲染路径中追加 `proper_refs`、`affect_refs`、`model` 字段 |
| 3 | `_split_by_length` 对 XML 格式长度估算不准确 | 中 | 恢复格式感知估算，对三种格式取 max 确保安全 |
| 4 | 全部格式失败时静默回退为 KR 原文 | 中 | 新增 `FALLBACK_TO_ORIGINAL` 错误状态 + 无条件 `logging.warning` |

## 提交记录（9 commits）

```
8ed905e test: per-block refs 渲染 + 格式感知分片测试
a889338 feat: 全部格式失败 → FALLBACK_TO_ORIGINAL 错误 + 无条件 logging.warning
031445b feat: 阶段 2 自校验编排 — changed=true 自动修正翻译
0bb3e7f fix: 审查修复 — 移除冗余 import logging + 清理未使用参数
365e54f feat: 阶段 0 消歧编排 — 主格式 LLM 消歧注入术语表
d6b1136 feat: user prompt 补充 per-block 引用字段（proper_refs/affect_refs/model）
632adc3 fix: 审查修复 — 非分割检查改用三格式 max + 回退路径格式长度校验
f80b6ca fix: _split_by_length 恢复格式感知长度估算，build() 接受 prompt_format 参数
e58277c feat: ProcessResult 新增 FALLBACK_TO_ORIGINAL 枚举值
```

## 变更统计

```
5 files changed, 415 insertions(+), 26 deletions(-)
```

| 文件 | 变更 |
|------|------|
| `translateFunc/processor.py` | +223/-9 — 三阶段编排、fallback 错误化 |
| `translateFunc/builder/request.py` | +63/-10 — 格式感知分片、JSON refs |
| `translateFunc/builder/prompt.py` | +24/-5 — XML/JSON refs 渲染、规则微调 |
| `translateFunc/enums.py` | +1 — `FALLBACK_TO_ORIGINAL` 枚举 |
| `tests/test_prompt_format.py` | +130 — per-block refs + 分片测试 |

## 架构变更

### 三阶段翻译管线

```
_translate(request_text):
  阶段 0（消歧）: needs_disambiguation() → LLM 判断术语适用性 → 注入术语表
  阶段 1（主翻译）: 现有格式回退链 [主格式, xml_json, json_json, xml_xml]
  阶段 2（自校验）: needs_self_check() → 原文+译文对 → LLM 校验 → 应用修正
```

- 阶段 0 和阶段 2 仅使用用户选择的主格式，不参与回退链
- 阶段 0/2 失败 → `logging.warning` + 管线继续，不中断
- 阶段 2 仅在阶段 1 全部成功（无 KR 原文回退）时执行

### 格式感知长度估算

- `_split_by_length()` 恢复使用 `_get_request_text()`（格式感知）替代 `json.dumps()`
- 不分割检查：三种格式均不超限才不分割
- 多份分割校验：每个 part 对三种格式均不超限
- 回退分割后追加格式校验 + `logging.warning`

### 错误处理提升

- 全部格式失败 → 无条件 `logging.warning()`（不受 `dump` 控制）
- 返回 `ProcessResult.FALLBACK_TO_ORIGINAL`
- `PipelineSummary` 自动将其归入 `summary.errors`

## 测试结果

**62/62 全部通过**（1.58s）：

- `test_ac_automaton.py`: 12 passed
- `test_pipeline.py`: 8 passed
- `test_prompt_format.py`: 42 passed（原有 36 + 新增 6）

新增 6 个测试用例：
- `TestPerBlockRefs` (4 cases) — XML/JSON 引用字段渲染 + 省略
- `TestFormatAwareSplit` (2 cases) — xml_xml 更早触发分割，json_json 更紧凑

## 已知限制

以下为最终全分支审查中记录的非阻塞性发现，建议后续迭代处理：

1. `_apply_corrections` 中 `int(item.get("id", 0))` 对非整型 `id` 会触发 `ValueError`——单条数据异常会导致整个阶段 2 降级
2. 阶段 2 `translate("", timeout=120)` 发送空 user prompt——依赖特定 LLM API 行为
3. 阶段 0 user prompt 仅发送第一个 split part——分片场景下后续 part 的术语上下文可能不足
4. 阶段 0 `hybrid` 消歧模式暂未集成 `ProperAnalyzer` 置信度过滤——当前收集全部匹配术语
