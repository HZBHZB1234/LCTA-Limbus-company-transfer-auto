# translateFunc 优化与错误修复 — 设计文档

> 日期: 2026-06-27 | 状态: 设计完成

## 1. 背景与目标

对 `translateFunc/` 模块进行聚焦优化，解决核心性能瓶颈（专有名词上下文分析的 O(n²) File IO）、添加性能剖析基础设施、增强日志与注释，并修复扫描发现的关键 Bug。

**范围：聚焦核心** — 性能优化 + 剖析 + 日志注释 + Bug 修复。不做大规模架构重构。

## 2. 改动清单

### 2.1 核心优化：`extract_contexts()` 批量扫描

**文件：** `translateFunc/proper/analyze.py`、`translateFunc/matcher/proper.py`

**当前问题：** `extract_contexts()` 对每个术语（~800+）独立遍历全部文件（~100+），每次加载 JSON + 扁平化 + 搜索。O(术语 × 文件 × KV)，产生 M 级别的重复 File IO。

**修复方案：** 改为单次扫描 + AC 自动机批量匹配：

1. 收集全部术语 KR 文本 → 构建一个 `AcAutomaton`（一次性）
2. 遍历全部文件（仅一次）：加载 JSON → 扁平化 → 对每个文本值用自动机搜索 → 命中则记录上下文
3. 返回 term → contexts 映射

复杂度从 O(术语 × 文件 × KV) 降为 O(文件 × KV + 命中数)。

**接口变更：**
- 新增 `extract_contexts_batch(terms: list[str], kr_path, jp_path, en_path, max_examples=20) -> dict[str, list[dict]]`
- `ProperAnalyzer.analyze()` 改为先提取术语列表再调用 batch 版本
- 旧 `extract_contexts()` 保留但标记为内部方法

**进度日志：**
- 开始时：`开始专有名词上下文分析，共 {n} 个术语，{m} 个文件`
- 完成时：`专有名词上下文分析完成，命中 {hits} 处，覆盖 {matched} 个术语`

### 2.2 性能剖析基础设施

**新文件：** `translateFunc/profiler.py`

```python
class TimingProfiler:
    """单例。context manager 用法：
        with TimingProfiler.phase("名称"):
            ...
    """
    _instance = None

    @classmethod
    def get(cls) -> "TimingProfiler": ...
    @contextmanager
    def phase(cls, name: str): ...
    def report(cls) -> str: ...
```

**集成点（`pipeline.py:run()`）：**

- `phase("获取专有名词")` — `fetch_terms()` + `analyze()`
- `phase("构建匹配引擎")` — `build_proper/build_roles/build_affects`
- `phase("处理优先文件")` — keyword + model 串行
- `phase("并发翻译")` — `WorkerPool.map()`
- 运行结束时在 `PipelineSummary` 中附加报告文本

**报告格式：** 表格形式，列出各阶段耗时、占比。通过 `self._on_log` 回调输出。

### 2.3 阶段日志与注释

**Pipeline 层（`pipeline.py`）：**
- `run()` 各阶段切换处添加 `logging.info("=== 阶段 N/5: 名称 ===")` 及完成日志

**Processor 层（`processor.py`）：**
- `_translate()` 内阶段 0/1/2 切换处添加 `logging.debug()`
- 格式回退信息使用 `logging.info()`

**注释增强：**
- `_translate()` 内部关键流程添加行内注释
- `_build_format_chain`、`_collect_ambiguous_terms`、`_apply_corrections` 补充 docstring

### 2.4 Bug 修复

#### 🔴 严重（3 项）

| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| B1 | `get_proper.py:15` | `exit(1)` 会终止整个进程（含 WebUI） | `raise RuntimeError("术语数据超过 10 页限制")` |
| B2 | `processor.py:673-677` | `raise StopIteration(...)` 语义错误（StopIteration 是生成器协议信号） | `raise ValueError("译文数量多于预期")`；调用处 `except StopIteration` → `except ValueError` |
| B3 | `pipeline.py:270-275` / `processor.py:358-365` | translator 构造失败导致 logger 级别永久变为 INFO | 提取为 `@contextmanager _suppress_translatekit_log()` 或在 `try/finally` 中恢复 |

#### 🟡 中等（5 项）

| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| B4 | `pipeline.py:131-133` | `remove(model_file)` 成功 + `remove(keyword_file)` 失败 → `target_files` 损坏 | 先 `if model_file.exists() and keyword_file.exists():` 再同时 remove |
| B5 | `pipeline.py:215-219,232-236` | `zip(kr_list, cn_list)` 静默截断不匹配的数据 | 用 `zip_longest` + 长度校验 + `logging.warning` 对不匹配警告 |
| B6 | `processor.py:648-654` | `_SimpleRequestBuilder.build()` 中 `zip` 静默截断 | 添加断言或显式长度检查 |
| B7 | `request.py:122-127` | 每次匹配都 O(n) 线性查找角色数据 | `MatcherEngine` 新增 `_role_by_id: dict` 做 O(1) 查找 |
| B8 | `matcher/engine.py:70-71` | `item["id"]`、`item["kr"]` 无 `.get()` 保护 | 改为 `item.get("id", "")`、`item.get("kr", "")` |

### 2.5 代码清理

| # | 位置 | 内容 |
|---|------|------|
| C1 | `translate_doc.py:1` | `SKILLL_DOC` → `SKILL_DOC`（拼写修正），同步更新 `request.py:308` 引用 |
| C2 | `matcher/engine.py:38` | 删除死变量 `self._proper_data` |
| C3 | `builder/stages.py:46` | 删除未被调用的 `filter_by_confidence` 方法 |
| C4 | `processor.py:44-60` | 删除死实例变量 `self.formal_flatten_item`、`self._removed_keys` 及相关赋值 |
| C5 | `processor.py:175-176` | 移除废弃参数 `is_text_format`（`RequestBuilder` 构造函数中） |
| C6 | `pipeline.py` / `processor.py` | 提取重复 logger 抑制逻辑为 `_suppress_translatekit_log()` context manager |

## 3. 文件改动汇总

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `translateFunc/profiler.py` | **新增** | 性能剖析单例 |
| `translateFunc/proper/analyze.py` | 重写核心逻辑 | `extract_contexts` → `extract_contexts_batch` |
| `translateFunc/matcher/proper.py` | 修改调用 | `analyze()` 适配批量接口 |
| `translateFunc/pipeline.py` | 日志 + 剖析集成 + Bug 修复 | 阶段日志、profiler phase、B3/B4/B5 修复 |
| `translateFunc/processor.py` | 注释 + Bug 修复 + 清理 | 阶段日志、B2/B6 修复、C4/C5 清理 |
| `translateFunc/get_proper.py` | Bug 修复 | B1: `exit(1)` → `raise RuntimeError` |
| `translateFunc/builder/request.py` | 性能 + 清理 | B7: 角色 O(1) 查找、C1 引用更新 |
| `translateFunc/matcher/engine.py` | Bug 修复 + 清理 | B7/B8 修复、C2 清理 |
| `translateFunc/builder/stages.py` | 清理 | C3: 删除死代码 |
| `translateFunc/translate_doc.py` | 清理 | C1: 拼写修正 |

## 4. 不变项

- 不改 `AcAutomaton` 算法核心
- 不改 `_translate()` 整体结构
- 不改 `_split_by_length` 格式估算逻辑
- 不改公共 API（`TranslationPipeline`、`TranslateConfig` 等对外接口保持不变）
- 不改 `WorkerPool` 并发模型

## 5. 测试要点

- `extract_contexts_batch` 结果与旧 `extract_contexts` 逐个调用结果一致性
- AC 自动机对韩文 Unicode 的匹配正确性
- 剖析报告在正常完成和异常中断时均能输出
- `exit(1)` 替换后在 WebUI 中的错误展示
- `zip` → `zip_longest` 后不匹配数据的处理不崩溃
