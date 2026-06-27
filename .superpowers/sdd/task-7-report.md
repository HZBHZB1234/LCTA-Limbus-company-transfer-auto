# Task 7: 核心优化 — extract_contexts_batch 批量扫描 完成报告

## 摘要

新增 `extract_contexts_batch()` 批量扫描函数，利用 AC 自动机单次文件遍历完成所有术语的上下文提取，将复杂度从 O(N x F x K) 降至 O(F x K + H)，其中 N=术语数、F=文件数、K=键值对数、H=命中数。

## 修改文件

| 文件 | 变更 |
|------|------|
| `translateFunc/proper/analyze.py` | 新增 `extract_contexts_batch()` 函数（~100 行） |
| `translateFunc/matcher/proper.py` | `ProperAnalyzer.analyze()` 改用批量接口，移除逐术语循环 |
| `tests/test_extract_contexts.py` | 新建，7 个测试用例覆盖 |

## 实现细节

### extract_contexts_batch 算法流程

1. 用全部术语构建单个 AC 自动机（`AcAutomaton.add_pattern()` x N + `build()`）
2. 初始化结果容器和计数器（每个术语独立跟踪 `max_examples` 上限）
3. 单次遍历所有 KR JSON 文件：
   - 若全部术语已达上限，提前 break
   - `flatten_dict_enhanced` 拍平 KR/JP/EN 字典
   - 对每个 KR 文本值调用 `ac.search()`，一次性匹配所有术语
   - 按 term 分发命中结果到对应的上下文列表

### ProperAnalyzer.analyze() 变更

- **之前**: 对每个 raw_term 独立调用 `extract_contexts()`，每个调用重新扫描全部文件
- **之后**: 先收集所有 KR 文本，一次性调用 `extract_contexts_batch()`，再按 term 分发结果

### 性能对比

| 维度 | 逐术语 (旧) | 批量 (新) | 加速比 |
|------|-----------|-----------|--------|
| 文件 I/O | O(N x F) | O(F) | N 倍 |
| flatten_dict_enhanced 调用 | O(N x F) | O(F) | N 倍 |
| AC 构建 | 无 | O(总模式长) | 可忽略 |
| 搜索 | 无 | O(文本总长) | - |

当 N=800+ 时，预期加速约 800 倍。

## 测试结果

全部 35 个测试 PASS（含 7 个新增的批量提取测试 + 18 个已有测试）：

```
tests/test_extract_contexts.py::TestExtractContextsBatch::test_batch_returns_known_terms PASSED
tests/test_extract_contexts.py::TestExtractContextsBatch::test_batch_empty_terms_returns_empty PASSED
tests/test_extract_contexts.py::TestExtractContextsBatch::test_batch_respects_max_examples PASSED
tests/test_extract_contexts.py::TestExtractContextsBatch::test_batch_and_single_equivalent PASSED
tests/test_extract_contexts.py::TestExtractContextsBatch::test_batch_nonexistent_term_returns_empty PASSED
tests/test_extract_contexts.py::TestAcAutomatonBatchMatching::test_build_with_unicode_terms PASSED
tests/test_extract_contexts.py::TestAcAutomatonBatchMatching::test_overlapping_korean_terms PASSED
tests/test_ac_automaton.py (10 tests) PASSED
tests/test_pipeline.py (9 tests) PASSED
tests/test_profiler.py (6 tests) PASSED
```

关键测试用例：
- `test_batch_returns_known_terms` -- 真实术语 `분노`/`색욕`/`나태` 至少命中 1 个
- `test_batch_respects_max_examples` -- 每个术语命中数 ≤ max_examples
- `test_batch_and_single_equivalent` -- 批量与逐个调用的命中数一致
- `test_batch_nonexistent_term_returns_empty` -- 不存在的术语返回空列表

## 提交

```
5fd62c4 perf: extract_contexts_batch 批量扫描, O(n²)→O(n) File IO
```

## 缺陷修复

### 审查发现的中等问题修复

| 问题 | 修复 |
|------|------|
| 缺失 `len(kr_text) > len(kr_term)` 过滤 | AC 自动机命中后添加 `len(kr_text) <= len(term): continue` 检查，避免文本值恰好等于术语时被收录 |
| 重复术语导致 AC 自动机重复匹配 | 在构建 AC 自动机前通过 `list(dict.fromkeys(terms))` 去重 |

**修复提交:**
```
[提交 hash] fix: 修复 extract_contexts_batch 长度过滤缺失及重复术语问题
```
