# translateFunc 优化与错误修复 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化 translateFunc 模块的核心性能瓶颈（extract_contexts O(n²) File IO），添加性能剖析与阶段日志，修复 8 个 Bug，清理死代码。

**Architecture:** 任务按文件分组以最小化冲突。先建独立基础设施（profiler），再做简单 Bug 修复，然后是核心优化（extract_contexts_batch），最后集成日志与剖析。测试数据位于 `tests/example/`。

**Tech Stack:** Python 3.11+, pytest, AC 自动机（已有实现）

## Global Constraints

- 不改 `AcAutomaton` 算法核心
- 不改 `_translate()` 整体结构
- 不改 `_split_by_length` 格式估算逻辑
- 不改公共 API（`TranslationPipeline`、`TranslateConfig` 等对外接口）
- 不改 `WorkerPool` 并发模型
- 测试数据位于 `tests/example/LocalizeTemp_kr`、`LocalizeTemp_jp`、`LocalizeTemp_en`

---

### Task 1: 新增 TimingProfiler 性能剖析模块

**Files:**
- Create: `translateFunc/profiler.py`
- Create: `tests/test_profiler.py`

**Interfaces:**
- Produces: `TimingProfiler` 单例类，`phase(name)` context manager，`report()` 方法

- [ ] **Step 1: 编写 profiler 单元测试**

```python
# tests/test_profiler.py
"""TimingProfiler 单元测试。"""
import time
import pytest
from translateFunc.profiler import TimingProfiler


class TestTimingProfiler:
    """TimingProfiler 基础功能测试。"""

    def test_singleton(self):
        """多次获取返回同一实例。"""
        a = TimingProfiler.get()
        b = TimingProfiler.get()
        assert a is b

    def test_phase_records_elapsed(self):
        """phase context manager 正确记录耗时。"""
        profiler = TimingProfiler.get()
        profiler.reset()
        with profiler.phase("test_phase"):
            time.sleep(0.01)
        report = profiler.report()
        assert "test_phase" in report
        assert profiler._records["test_phase"] >= 0.01

    def test_multiple_phases(self):
        """多个阶段的耗时分别记录。"""
        profiler = TimingProfiler.get()
        profiler.reset()
        with profiler.phase("phase_a"):
            time.sleep(0.01)
        with profiler.phase("phase_b"):
            time.sleep(0.01)
        assert "phase_a" in profiler._records
        assert "phase_b" in profiler._records
        report = profiler.report()
        assert "phase_a" in report
        assert "phase_b" in report

    def test_nested_phases(self):
        """嵌套 phase：内层耗时计入外层。"""
        profiler = TimingProfiler.get()
        profiler.reset()
        with profiler.phase("outer"):
            time.sleep(0.01)
            with profiler.phase("inner"):
                time.sleep(0.01)
        # 内层和外层都应该有记录
        assert profiler._records["inner"] >= 0.01
        assert profiler._records["outer"] >= 0.02  # 包含 inner 时间

    def test_report_format(self):
        """report() 输出包含表头和关键列。"""
        profiler = TimingProfiler.get()
        profiler.reset()
        with profiler.phase("test"):
            time.sleep(0.005)
        report = profiler.report()
        assert "性能报告" in report
        assert "test" in report
        assert "耗时" in report or "s" in report

    def test_reset_clears_all(self):
        """reset() 清除所有记录。"""
        profiler = TimingProfiler.get()
        profiler.reset()
        with profiler.phase("test"):
            time.sleep(0.01)
        profiler.reset()
        assert len(profiler._records) == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_profiler.py -v
```

预期：全部 FAIL，因为 `translateFunc/profiler.py` 还不存在。

- [ ] **Step 3: 实现 TimingProfiler**

```python
# translateFunc/profiler.py
"""性能剖析基础设施 —— TimingProfiler 单例。"""
from __future__ import annotations
from contextlib import contextmanager
import time
from typing import Dict


class TimingProfiler:
    """单例性能剖析器。context manager 用法：

        profiler = TimingProfiler.get()
        with profiler.phase("获取专有名词"):
            ...
        print(profiler.report())
    """
    _instance: "TimingProfiler | None" = None

    def __init__(self):
        self._records: Dict[str, float] = {}
        self._stack: list[tuple[str, float]] = []

    @classmethod
    def get(cls) -> "TimingProfiler":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reset(self) -> None:
        """清除所有记录。"""
        self._records.clear()
        self._stack.clear()

    @contextmanager
    def phase(self, name: str):
        """记录一个命名阶段的耗时。支持嵌套——内层阶段耗时计入外层。

        用法:
            with profiler.phase("阶段名称"):
                do_work()
        """
        start = time.perf_counter()
        self._stack.append((name, start))
        try:
            yield
        finally:
            end = time.perf_counter()
            elapsed = end - start
            self._stack.pop()
            # 累计耗时（支持同一阶段多次调用）
            prev = self._records.get(name, 0.0)
            self._records[name] = prev + elapsed

    def report(self) -> str:
        """生成格式化的耗时报告。"""
        if not self._records:
            return "[性能报告] 无数据"

        total = sum(self._records.values())
        lines = [
            "========== 性能报告 ==========",
            f"{'阶段':<24} {'耗时':>10}  {'占比':>8}",
            "-" * 44,
        ]
        for name, elapsed in self._records.items():
            pct = (elapsed / total * 100) if total > 0 else 0.0
            lines.append(f"{name:<24} {elapsed:>8.2f}s  {pct:>6.1f}%")
        lines.append("-" * 44)
        lines.append(f"{'总计':<24} {total:>8.2f}s")
        lines.append("=" * 33)
        return "\n".join(lines)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_profiler.py -v
```

预期：全部 PASS。

- [ ] **Step 5: 提交**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && git add translateFunc/profiler.py tests/test_profiler.py && git commit -m "feat: 新增 TimingProfiler 性能剖析模块"
```

---

### Task 2: 修复 B1（exit 杀进程）和 B8（.get 保护）

**Files:**
- Modify: `translateFunc/get_proper.py`
- Modify: `translateFunc/matcher/engine.py`

**Interfaces:**
- Consumes: 无
- Produces: `fetch()` 不再调用 `exit(1)` 而是抛出 `RuntimeError`；`build_affects()` 对缺失键使用 `.get()` 安全访问

- [ ] **Step 1: 修复 get_proper.py — exit(1) → RuntimeError**

修改 `translateFunc/get_proper.py` 第 15 行：

```python
# 修改前：
#     else:
#         print('可能有更多数据，请增加页数', file=sys.stderr)
#         exit(1)

# 修改后：
    else:
        raise RuntimeError(
            "专有名词数据超过 10 页限制（8000 条），请增加 get_proper.py 中的页数"
        )
```

同时删除不再需要的 `import sys`（若仅用于 `sys.stderr` 输出）。

修改后的完整文件：

```python
import requests

def fetch(min_len:int = 0):
    data = []
    for i in range(10):
        r=requests.get(f"https://paratranz.cn/api/projects/6860/terms?pageSize=800&page={i+1}",timeout=10)
        r.raise_for_status()
        r = r.json()
        if len(r.get('results', []))==0:
            break
        data.extend(r['results'])
    else:
        raise RuntimeError(
            "专有名词数据超过 10 页限制（8000 条），请增加 get_proper.py 中的页数"
        )
        
    result =[
        {
            'term': i.get('term', ''),
            'translation': i.get('translation', ''),
            'note': i.get('note', '')
        } for i in data if len(i.get('term', '')) >= min_len
    ]
    return result
```

- [ ] **Step 2: 修复 matcher/engine.py — build_affects .get() 保护 + 删除死变量**

修改 `translateFunc/matcher/engine.py`：

```python
# 第 38 行：删除 self._proper_data
# 修改前 __init__:
    def __init__(self):
        self._proper_ac = AcAutomaton()
        self._role_ac = AcAutomaton()
        self._affect_id_ac = AcAutomaton()
        self._affect_name_ac = AcAutomaton()

        # 以 node_id 或 pattern 为键的数据查找表
        self._proper_data: dict[int, Any] = {}   # <-- 删除此行
        self._role_data: list[dict] = []
        self._affect_data: list[dict] = []

# 修改后 __init__:
    def __init__(self):
        self._proper_ac = AcAutomaton()
        self._role_ac = AcAutomaton()
        self._affect_id_ac = AcAutomaton()
        self._affect_name_ac = AcAutomaton()

        self._role_data: list[dict] = []
        self._affect_data: list[dict] = []

# 第 64-75 行：build_affects 添加 .get() 保护
# 修改前：
    def build_affects(self, affect_items: list[dict]) -> None:
        """从 [{id, kr, cn, desc}, ...] 构建状态效果 ID 和名称 AC 自动机。"""
        self._affect_data = affect_items
        self._affect_id_ac = AcAutomaton()
        self._affect_name_ac = AcAutomaton()
        for item in affect_items:
            aff_id = f'[{item["id"]}]'
            aff_name = f'{item["kr"]} '
            self._affect_id_ac.add_pattern(aff_id, data=item)
            self._affect_name_ac.add_pattern(aff_name, data=item)
        self._affect_id_ac.build()
        self._affect_name_ac.build()

# 修改后：
    def build_affects(self, affect_items: list[dict]) -> None:
        """从 [{id, kr, cn, desc}, ...] 构建状态效果 ID 和名称 AC 自动机。"""
        self._affect_data = affect_items
        self._affect_id_ac = AcAutomaton()
        self._affect_name_ac = AcAutomaton()
        for item in affect_items:
            aff_id = f'[{item.get("id", "")}]'
            aff_name = f'{item.get("kr", "")} '
            if item.get("id"):
                self._affect_id_ac.add_pattern(aff_id, data=item)
            if item.get("kr"):
                self._affect_name_ac.add_pattern(aff_name, data=item)
        self._affect_id_ac.build()
        self._affect_name_ac.build()
```

- [ ] **Step 3: 运行已有测试确认不破坏**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_ac_automaton.py tests/test_pipeline.py -v
```

预期：全部 PASS。

- [ ] **Step 4: 提交**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && git add translateFunc/get_proper.py translateFunc/matcher/engine.py && git commit -m "fix: B1 exit→RuntimeError, B8 .get保护, C2 删除死变量"
```

---

### Task 3: 修复 B3/B4/B5 + C6（pipeline.py + config.py）

**Files:**
- Modify: `translateFunc/config.py`（新增 `_suppress_translatekit_log`）
- Modify: `translateFunc/pipeline.py`

**Interfaces:**
- Consumes: `PipelineSummary` 类型（已有），`ProperAnalyzer`（已有）
- Produces: `config._suppress_translatekit_log()` context manager（供 pipeline 和 processor 复用）；`_update_roles`/`_update_affects` 使用 `zip_longest` 不截断

**注意：** `_suppress_translatekit_log` 定义在 `config.py` 而非 `pipeline.py`，以避免 pipeline ↔ processor 循环导入。

- [ ] **Step 1: 编写 pipeline Bug 修复测试**

在 `tests/test_pipeline.py` 中添加：

```python
class TestPipelineBugFixes:
    """Tests for B3, B4, B5 bug fixes."""

    def test_zip_longest_prevents_truncation(self):
        """B5: zip_longest 在列表长度不匹配时不截断。"""
        from itertools import zip_longest
        kr = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        cn = [{"id": 1, "name": "甲"}]
        # 旧 zip 会截断为 1；zip_longest 保留全部
        result = []
        for k, c in zip_longest(kr, cn, fillvalue=None):
            if k is None or c is None:
                continue  # 跳过不匹配项
            result.append({"id": k["id"], "kr": k["name"], "cn": c["name"]})
        assert len(result) == 1  # 仅匹配的条目保留
        # 不崩溃、不截断

    def test_priority_files_checked_before_remove(self, tmp_path):
        """B4: 先检查文件存在再 remove。"""
        kr_path = tmp_path / "kr"
        kr_path.mkdir()
        # 创建 model 文件但不创建 keyword 文件
        model = kr_path / "KR_ScenarioModelCodes-AutoCreated.json"
        model.write_text("{}", encoding="utf-8")
        # keyword 不存在
        keyword = kr_path / "KR_BattleKeywords.json"

        has_prefix = True
        files = list(kr_path.rglob("*.json"))

        if model.exists() and keyword.exists():
            files.remove(model)
            files.remove(keyword)
            priority = [keyword, model]
        else:
            priority = []

        assert len(priority) == 0  # 两个都存在才进入优先处理
        assert len(files) == 1      # 文件未被错误移除
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_pipeline.py::TestPipelineBugFixes -v
```

预期：`test_priority_files_checked_before_remove` FAIL（当前代码先 remove 再检查）。

- [ ] **Step 3: 实施 pipeline.py 所有修复**

修改 `translateFunc/pipeline.py`：

**3a. 在 config.py 中添加 `_suppress_translatekit_log()` context manager（B3 + C6）**

在 `translateFunc/config.py` 末尾添加（独立函数，避免循环导入）：

```python
from contextlib import contextmanager
import logging as _logging

@contextmanager
def _suppress_translatekit_log(debug_mode: bool):
    """在 translator 构造期间临时抑制 translatekit 的 debug 日志。

    使用 try/finally 确保即使构造失败也恢复日志级别。
    修复 B3：translator 构造异常时 logger 级别永久泄漏。

    定义在 config.py 而非 pipeline.py，避免 pipeline ↔ processor 循环导入。
    """
    if not debug_mode:
        _logging.getLogger("translatekit").setLevel(_logging.INFO)
    try:
        yield
    finally:
        if not debug_mode:
            _logging.getLogger("translatekit").setLevel(_logging.DEBUG)
```

**3b. 修复 B3 — `_build_translator` 使用 context manager**

在 `pipeline.py` 顶部添加导入：
```python
from translateFunc.config import _suppress_translatekit_log
```

修改 `_build_translator` 方法（第 269-275 行）：

```python
# 修改前 (_build_translator 第 269-275 行):
        if not self._config.debug_mode:
            logging.getLogger("translatekit").setLevel(logging.INFO)

        translator = translator_cls(tkit_config)

        if not self._config.debug_mode:
            logging.getLogger("translatekit").setLevel(logging.DEBUG)

        return translator

# 修改后:
        with _suppress_translatekit_log(self._config.debug_mode):
            translator = translator_cls(tkit_config)

        return translator
```

**3c. 修复 B4 — 优先文件先检查再 remove**

```python
# 修改前 (第 126-136 行):
        try:
            model_name = "KR_ScenarioModelCodes-AutoCreated.json" if has_prefix else "ScenarioModelCodes-AutoCreated.json"
            keyword_name = "KR_BattleKeywords.json" if has_prefix else "BattleKeywords.json"
            model_file = kr_path / model_name
            keyword_file = kr_path / keyword_name
            target_files.remove(model_file)
            target_files.remove(keyword_file)
            priority_files = [keyword_file, model_file]
        except Exception:
            self._on_log("警告: 无法找到特殊文件，按原始顺序处理")
            priority_files = []

# 修改后:
        model_name = "KR_ScenarioModelCodes-AutoCreated.json" if has_prefix else "ScenarioModelCodes-AutoCreated.json"
        keyword_name = "KR_BattleKeywords.json" if has_prefix else "BattleKeywords.json"
        model_file = kr_path / model_name
        keyword_file = kr_path / keyword_name
        if model_file.exists() and keyword_file.exists():
            target_files.remove(model_file)
            target_files.remove(keyword_file)
            priority_files = [keyword_file, model_file]
        else:
            if not model_file.exists():
                self._on_log(f"警告: 未找到模型文件 {model_name}，跳过优先处理")
            if not keyword_file.exists():
                self._on_log(f"警告: 未找到关键字文件 {keyword_name}，跳过优先处理")
            priority_files = []
```

**3d. 修复 B5 — `_update_roles`/`_update_affects` 用 zip_longest**

```python
# 在文件顶部添加导入:
from itertools import zip_longest

# 修改 _update_roles (第 207-222 行):
    def _update_roles(self, model_file: Path, base_pc: PathConfig, has_prefix: bool) -> None:
        """从 ScenarioModelCodes 更新 MatcherEngine 中的角色数据。"""
        try:
            kr_data = json.loads(model_file.read_text(encoding="utf-8-sig"))
            target = FilePathConfig(KR_path=model_file, _PathConfig=base_pc, has_prefix=has_prefix).target_file
            cn_data = json.loads(target.read_text(encoding="utf-8-sig")) if target.exists() else kr_data
            kr_list = kr_data.get("dataList", kr_data if isinstance(kr_data, list) else [])
            cn_list = cn_data.get("dataList", cn_data if isinstance(cn_data, list) else [])

            if len(kr_list) != len(cn_list):
                logging.warning(
                    f"角色数据 KR/CN 列表长度不匹配: KR={len(kr_list)}, CN={len(cn_list)}，"
                    f"将按较短列表配对"
                )

            roles = []
            for k, c in zip_longest(kr_list, cn_list):
                if k is None or c is None:
                    continue
                roles.append({
                    "id": k["id"], "kr": k["name"], "cn": c["name"],
                    "nickName": c.get("nickName", ""),
                })
            self._engine.build_roles(roles)
            self._on_log(f"已加载 {len(roles)} 个角色信息")
        except Exception as e:
            self._on_log(f"加载角色信息失败: {e}")

# 同理修改 _update_affects (第 224-239 行):
    def _update_affects(self, keyword_file: Path, base_pc: PathConfig, has_prefix: bool) -> None:
        """从 BattleKeywords 更新 MatcherEngine 中的状态效果数据。"""
        try:
            kr_data = json.loads(keyword_file.read_text(encoding="utf-8-sig"))
            target = FilePathConfig(KR_path=keyword_file, _PathConfig=base_pc, has_prefix=has_prefix).target_file
            cn_data = json.loads(target.read_text(encoding="utf-8-sig")) if target.exists() else kr_data
            kr_list = kr_data.get("dataList", kr_data if isinstance(kr_data, list) else [])
            cn_list = cn_data.get("dataList", cn_data if isinstance(cn_data, list) else [])

            if len(kr_list) != len(cn_list):
                logging.warning(
                    f"状态效果数据 KR/CN 列表长度不匹配: KR={len(kr_list)}, CN={len(cn_list)}，"
                    f"将按较短列表配对"
                )

            affects = []
            for k, c in zip_longest(kr_list, cn_list):
                if k is None or c is None:
                    continue
                affects.append({
                    "id": k["id"], "kr": k["name"], "cn": c["name"],
                    "desc": c.get("desc", ""),
                })
            self._engine.build_affects(affects)
            self._on_log(f"已加载 {len(affects)} 个状态效果")
        except Exception as e:
            self._on_log(f"加载状态效果失败: {e}")
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_pipeline.py -v
```

预期：全部 PASS。

- [ ] **Step 5: 提交**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && git add translateFunc/config.py translateFunc/pipeline.py tests/test_pipeline.py && git commit -m "fix: B3 logger泄漏, B4 优先文件检查, B5 zip_longest, C6 提取公共context manager到config"
```

---

### Task 4: 修复 B2/B6 + C4/C5（processor.py 集中修复）

**Files:**
- Modify: `translateFunc/processor.py`

**Interfaces:**
- Consumes: `_suppress_translatekit_log` context manager（从 `translateFunc.config` 导入，Task 3 定义）
- Produces: `_translate` 中 `_build_translator_for_format` 使用 context manager；`_SimpleRequestBuilder` 不再滥用 StopIteration

- [ ] **Step 1: 修复 processor.py — B2（StopIteration→ValueError）**

修改 `translateFunc/processor.py` `_SimpleRequestBuilder.deBuild` 方法（第 673-677 行附近）：

```python
# 修改前:
        try:
            next(it)
        except StopIteration:
            pass  # 正常 —— 没有多余的翻译结果
        else:
            raise StopIteration("译文数量多于预期")

# 修改后:
        try:
            next(it)
        except StopIteration:
            pass  # 正常 —— 没有多余的翻译结果
        else:
            raise ValueError("译文数量多于预期")
```

同时修改调用处（`_translate` 第 123 行）：

```python
# 修改前:
        except StopIteration:
            self._save_except()
            return ProcessOutcome(
                ProcessResult.TRANSLATION_MISMATCH,
                self.file_name,
                {"reason": "译文数量与原文不匹配"},
            )

# 修改后:
        except ValueError:
            self._save_except()
            return ProcessOutcome(
                ProcessResult.TRANSLATION_MISMATCH,
                self.file_name,
                {"reason": "译文数量与原文不匹配"},
            )
```

- [ ] **Step 2: 修复 B6 — `_SimpleRequestBuilder.build` zip 截断保护**

在 `_SimpleRequestBuilder.build()` 中（第 638-654 行附近）添加长度一致性断言：

```python
# 修改前:
    def build(self) -> list:
        EN_result, KR_result, JP_result = [], [], []
        for idx in self.kr_texts:
            for text in self.kr_texts[idx].values():
                KR_result.append(text)
            for text in self.jp_texts.get(idx, {}).values():
                JP_result.append(text)
            for text in self.en_texts.get(idx, {}).values():
                EN_result.append(text)

        empty_idxs = {
            i for i, (kr, en, jp) in enumerate(zip(KR_result, EN_result, JP_result))
            if kr in EMPTY_TEXT and en in EMPTY_TEXT and jp in EMPTY_TEXT
        }

# 修改后:
    def build(self) -> list:
        EN_result, KR_result, JP_result = [], [], []
        for idx in self.kr_texts:
            for text in self.kr_texts[idx].values():
                KR_result.append(text)
            for text in self.jp_texts.get(idx, {}).values():
                JP_result.append(text)
            for text in self.en_texts.get(idx, {}).values():
                EN_result.append(text)

        if not (len(KR_result) == len(EN_result) == len(JP_result)):
            raise ValueError(
                f"语言文本长度不一致: KR={len(KR_result)}, "
                f"EN={len(EN_result)}, JP={len(JP_result)}"
            )

        empty_idxs = {
            i for i, (kr, en, jp) in enumerate(zip(KR_result, EN_result, JP_result))
            if kr in EMPTY_TEXT and en in EMPTY_TEXT and jp in EMPTY_TEXT
        }
```

- [ ] **Step 3: 修复 C4 — 删除死实例变量**

在 `FileProcessor.__init__` 中（第 43-61 行）删除 `self.formal_flatten_item` 和 `self._removed_keys`：

```python
# 修改前 __init__ 末尾:
        self.translating_list: list = []
        self.formal_flatten_item: dict = {}
        self._removed_keys: list = []
        self._base_index: dict = {}

# 修改后 __init__ 末尾:
        self.translating_list: list = []
        self._base_index: dict = {}
```

同时删除 `_get_translating_text`（第 572-583 行）中对这两个变量的赋值：

```python
# 修改前 _get_translating_text 循环体:
        translating_text = {}
        for i in self.translating_list:
            flat = flatten_dict_enhanced(lang_index[i], ignore_types=[None, int, float])
            self.formal_flatten_item = deepcopy(flat)
            to_delete = [k for k in flat if k[-1] in AVOID_PATH]
            self._removed_keys = to_delete
            for k in to_delete:
                del flat[k]
            translating_text[i] = flat
        return translating_text

# 修改后:
        translating_text = {}
        for i in self.translating_list:
            flat = flatten_dict_enhanced(lang_index[i], ignore_types=[None, int, float])
            to_delete = [k for k in flat if k[-1] in AVOID_PATH]
            for k in to_delete:
                del flat[k]
            translating_text[i] = flat
        return translating_text
```

- [ ] **Step 4: 修复 C5 — 移除废弃参数 `is_text_format`**

修改 `RequestBuilder.__init__`（`builder/request.py` 第 25-41 行）：

```python
# 修改前:
    def __init__(
        self,
        request_text: dict,
        matcher_engine: MatcherEngine,
        is_story: bool = False,
        is_skill: bool = False,
        is_text_format: bool = False,
        max_length: int = 20000,
        file_type: FileType = FileType.OTHER,
    ):

# 修改后:
    def __init__(
        self,
        request_text: dict,
        matcher_engine: MatcherEngine,
        is_story: bool = False,
        is_skill: bool = False,
        max_length: int = 20000,
        file_type: FileType = FileType.OTHER,
    ):
```

同时修改 `self.is_text_format = is_text_format` 为删除（`request.py` 第 41 行附近）。

修改 `processor.py` 中的调用处（第 170-179 行）：

```python
# 修改前:
        builder = RequestBuilder(
            request_text,
            self._engine,
            is_story=self.is_story,
            is_skill=self.is_skill,
            is_text_format=False,  # 废弃，由 prompt_format 控制
            max_length=20000,
            file_type=self.file_type,
        )

# 修改后:
        builder = RequestBuilder(
            request_text,
            self._engine,
            is_story=self.is_story,
            is_skill=self.is_skill,
            max_length=20000,
            file_type=self.file_type,
        )
```

- [ ] **Step 5: 修复 B3（processor.py 部分）— `_build_translator_for_format` 使用 context manager**

修改 `_build_translator_for_format`，从 config 导入 context manager：

```python
# 在文件顶部添加导入:
from translateFunc.config import _suppress_translatekit_log

# 修改 _build_translator_for_format:
# 替换第 358-365 行（logger 抑制部分）:
        with _suppress_translatekit_log(self._config.debug_mode):
            translator = translator_cls(tkit_config)

        return translator
```

删除原有的手动 logger 抑制代码（4 行）。

- [ ] **Step 6: 运行已有测试确认不破坏**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_pipeline.py tests/test_prompt_format.py -v
```

预期：全部 PASS。

- [ ] **Step 7: 提交**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && git add translateFunc/processor.py translateFunc/builder/request.py && git commit -m "fix: B2 StopIteration→ValueError, B6 zip断言, B3 logger泄漏(processor侧), C4/C5 清理死代码"
```

---

### Task 5: 修复 B7 — 角色 O(1) 查找

**Files:**
- Modify: `translateFunc/matcher/engine.py`
- Modify: `translateFunc/builder/request.py`

**Interfaces:**
- Consumes: `MatcherEngine.role_data`（已有）
- Produces: `MatcherEngine` 新增 `role_by_id` 属性（返回 `dict`）；`RequestBuilder.build()` 使用 O(1) 查找

- [ ] **Step 1: 在 MatcherEngine 中添加 `role_by_id` 属性**

修改 `translateFunc/matcher/engine.py`：

```python
# 在第 93-96 行后添加新属性:
    # ----- 访问器 -----

    @property
    def role_data(self) -> list[dict]:
        return self._role_data

    @property
    def role_by_id(self) -> dict[str, dict]:
        """以角色 ID 为键的 O(1) 查找表。"""
        if not hasattr(self, "_role_by_id_cache") or self._role_by_id_cache is None:
            self._role_by_id_cache = {r.get("id", ""): r for r in self._role_data}
        return self._role_by_id_cache
```

在 `build_roles` 中清除缓存：

```python
# 修改 build_roles:
    def build_roles(self, role_items: list[dict]) -> None:
        """从 [{id, kr, cn, nickName}, ...] 构建角色 AC 自动机。
        角色通过 `id` 字段精确匹配，非子串匹配。"""
        self._role_data = role_items
        self._role_by_id_cache = None  # 清除缓存
        self._role_ac = AcAutomaton()
        for item in role_items:
            role_id = item.get("id", "")
            if role_id:
                self._role_ac.add_pattern(role_id, data=item)
        self._role_ac.build()
```

- [ ] **Step 2: 修改 request.py 使用 O(1) 查找**

修改 `translateFunc/builder/request.py` 第 112-130 行（角色匹配部分）：

```python
# 修改前:
                # 匹配角色（仅剧情文件）
                if self.is_story:
                    with suppress(Exception):
                        model = kr_text_val.get("model", "") if isinstance(kr_text_val, dict) else ""
                        if not model:
                            # 尝试从引擎匹配角色
                            for rm in match_result.role_matches:
                                model = rm.pattern
                                break
                        if model:
                            model_idx = None
                            for i, rd in enumerate(self._engine.role_data):
                                if rd.get("id") == model:
                                    model_idx = i
                                    break
                            if model_idx is not None:
                                model_info = self._engine.role_data[model_idx]
                                all_models[model] = model_info
                                text_block["model"] = model

# 修改后:
                # 匹配角色（仅剧情文件）
                if self.is_story:
                    with suppress(Exception):
                        model = kr_text_val.get("model", "") if isinstance(kr_text_val, dict) else ""
                        if not model:
                            # 尝试从引擎匹配角色
                            for rm in match_result.role_matches:
                                model = rm.pattern
                                break
                        if model:
                            model_info = self._engine.role_by_id.get(model)
                            if model_info is not None:
                                all_models[model] = model_info
                                text_block["model"] = model
```

- [ ] **Step 3: 运行测试确认通过**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_pipeline.py tests/test_ac_automaton.py -v
```

预期：全部 PASS。

- [ ] **Step 4: 提交**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && git add translateFunc/matcher/engine.py translateFunc/builder/request.py && git commit -m "perf: B7 角色O(1)查找 role_by_id"
```

---

### Task 6: 代码清理 C1 + C3

**Files:**
- Modify: `translateFunc/translate_doc.py`
- Modify: `translateFunc/builder/request.py`
- Modify: `translateFunc/builder/stages.py`

**Interfaces:**
- Consumes: 无
- Produces: `SKILL_DOC`（修正拼写）替代 `SKILLL_DOC`；删除 `filter_by_confidence`

- [ ] **Step 1: 修复 C1 — 拼写修正 SKILLL_DOC → SKILL_DOC**

修改 `translateFunc/translate_doc.py`：

```python
# 修改前:
SKILLL_DOC = """

# 修改后:
SKILL_DOC = """
```

修改 `translateFunc/builder/request.py` 第 308 行引用：

```python
# 修改前:
            return translate_doc.SKILLL_DOC

# 修改后:
            return translate_doc.SKILL_DOC
```

- [ ] **Step 2: 修复 C3 — 删除死方法 `filter_by_confidence`**

修改 `translateFunc/builder/stages.py`，删除第 46-56 行：

```python
# 删除以下方法:
    def filter_by_confidence(self, matches: list[dict], min_conf: MatchConfidence) -> list[dict]:
        """按最低置信度阈值过滤匹配。"""
        conf_order = {
            MatchConfidence.HIGH: 0,
            MatchConfidence.MEDIUM: 1,
            MatchConfidence.LOW: 2,
            MatchConfidence.UNKNOWN: 3,
            MatchConfidence.FALSE_MATCH: 4,
        }
        threshold = conf_order.get(min_conf, 1)
        return [m for m in matches if conf_order.get(m.get("confidence"), 4) <= threshold]
```

同时检查 `MatchConfidence` 导入是否仍被其他方法使用：`should_llm_disambiguate` 仍使用 `MatchConfidence.LOW` 和 `MatchConfidence.UNKNOWN`，因此保留导入。

- [ ] **Step 3: 运行测试确认不破坏**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_prompt_format.py -v
```

预期：全部 PASS。

- [ ] **Step 4: 提交**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && git add translateFunc/translate_doc.py translateFunc/builder/request.py translateFunc/builder/stages.py && git commit -m "chore: C1 SKILLL_DOC→SKILL_DOC, C3 删除死方法filter_by_confidence"
```

---

### Task 7: 核心优化 — extract_contexts_batch 批量扫描

**Files:**
- Modify: `translateFunc/proper/analyze.py`（新增 `extract_contexts_batch`）
- Modify: `translateFunc/matcher/proper.py`（`analyze()` 改用 batch）
- Create: `tests/test_extract_contexts.py`（对比测试）

**Interfaces:**
- Consumes: `AcAutomaton`（已有）、`flatten_dict_enhanced`（已有）
- Produces: `extract_contexts_batch(terms, kr_path, jp_path, en_path, max_examples) -> dict[str, list[dict]]`

- [ ] **Step 1: 编写 extract_contexts_batch 测试**

```python
# tests/test_extract_contexts.py
"""extract_contexts 批量扫描对比测试。使用 tests/example 真实数据。"""
import json
from pathlib import Path
import pytest
from translateFunc.proper.analyze import extract_contexts, extract_contexts_batch
from translateFunc.matcher.ac_automaton import AcAutomaton

EXAMPLE_DIR = Path(__file__).parent / "example"
KR_PATH = EXAMPLE_DIR / "LocalizeTemp_kr"
JP_PATH = EXAMPLE_DIR / "LocalizeTemp_jp"
EN_PATH = EXAMPLE_DIR / "LocalizeTemp_en"


class TestExtractContextsBatch:
    """extract_contexts_batch 正确性测试。"""

    @pytest.fixture(autouse=True)
    def _require_example_data(self):
        if not KR_PATH.exists():
            pytest.skip("tests/example 数据不存在")

    def test_batch_returns_known_terms(self):
        """已知的韩文术语应在批量扫描中被找到。"""
        terms = ["분노", "색욕", "나태"]  # 来自 KR_AttributeText.json
        results = extract_contexts_batch(terms, KR_PATH, JP_PATH, EN_PATH, max_examples=20)
        assert len(results) > 0
        # 至少某个术语被匹配到
        matched = sum(1 for v in results.values() if v)
        assert matched > 0

    def test_batch_empty_terms_returns_empty(self):
        """空术语列表返回空字典。"""
        results = extract_contexts_batch([], KR_PATH, JP_PATH, EN_PATH)
        assert results == {}

    def test_batch_respects_max_examples(self):
        """max_examples 限制每个术语的上下文条数。"""
        # 使用一个常见术语（可能出现很多次）
        results = extract_contexts_batch(["분노"], KR_PATH, JP_PATH, EN_PATH, max_examples=3)
        for term, contexts in results.items():
            assert len(contexts) <= 3

    def test_batch_and_single_equivalent(self):
        """batch 模式与逐个 extract_contexts 结果一致。"""
        terms = ["분노", "나태", "탐식"]
        batch_results = extract_contexts_batch(terms, KR_PATH, JP_PATH, EN_PATH, max_examples=5)
        individual_results = {}
        for term in terms:
            individual_results[term] = extract_contexts(
                term, KR_PATH, JP_PATH, EN_PATH, max_examples=5
            )
        # 每个术语的命中数应一致
        for term in terms:
            assert len(batch_results.get(term, [])) == len(individual_results.get(term, []))

    def test_batch_nonexistent_term_returns_empty(self):
        """不存在的术语返回空列表。"""
        results = extract_contexts_batch(["不存在的术语XYZ123"], KR_PATH, JP_PATH, EN_PATH)
        assert results.get("不存在的术语XYZ123", []) == [0] or results.get("不存在的术语XYZ123") == []
        # 如果 term 不在任何文件中，可能不在 keys 中，也可能在但值为空列表


class TestAcAutomatonBatchMatching:
    """AC 自动机在批量上下文提取中的行为测试。"""

    def test_build_with_unicode_terms(self):
        """韩文术语正确构建 AC 自动机。"""
        terms = ["이상", "파우스트", "돈키호테"]
        ac = AcAutomaton()
        for t in terms:
            ac.add_pattern(t)
        ac.build()
        hits = ac.search("파우스트는 조용히 있었다")
        assert len(hits) == 1
        assert hits[0].pattern == "파우스트"

    def test_overlapping_korean_terms(self):
        """重叠韩文术语匹配。"""
        terms = ["이상", "이상하다"]
        ac = AcAutomaton()
        for t in terms:
            ac.add_pattern(t)
        ac.build()
        hits = ac.search("이상한 나라의 이상")
        patterns = {h.pattern for h in hits}
        assert "이상" in patterns
        assert "이상하다" not in patterns  # '이상한' ≠ '이상하다'
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_extract_contexts.py -v
```

预期：`test_batch_*` 测试 FAIL（`extract_contexts_batch` 尚不存在）。

- [ ] **Step 3: 实现 `extract_contexts_batch`**

修改 `translateFunc/proper/analyze.py`，在 `extract_contexts` 之后添加新函数：

```python
def extract_contexts_batch(
    terms: list[str],
    kr_path: Path,
    jp_path: Path,
    en_path: Path,
    max_examples: int = 20,
) -> dict[str, list[dict]]:
    """
    批量提取多个术语的 JP/EN 上下文。单次文件扫描 + AC 自动机匹配。

    复杂度 O(文件数 × 键值对数 + 命中数)，对比逐术语调用的
    O(术语数 × 文件数 × 键值对数)，在 800+ 术语时约快 800 倍。

    Args:
        terms: 要搜索的 KR 术语文本列表
        kr_path: KR 游戏文件目录
        jp_path: JP 游戏文件目录
        en_path: EN 游戏文件目录
        max_examples: 每个术语最多收集的上下文条数

    Returns:
        {term: [{kr_sentence, jp_sentence, en_sentence, file, path}, ...], ...}
    """
    import logging
    from translateFunc.matcher.ac_automaton import AcAutomaton

    if not terms:
        return {}

    # 1. 构建包含所有术语的 AC 自动机
    ac = AcAutomaton()
    for term in terms:
        if term:  # 跳过空术语
            ac.add_pattern(term)
    ac.build()

    # 2. 初始化结果容器
    results: dict[str, list[dict]] = {term: [] for term in terms if term}
    # term_counts 跟踪每个术语已找到的上下文数
    term_counts: dict[str, int] = {term: 0 for term in terms if term}

    kr_files = list(kr_path.rglob("*.json"))
    logging.info(f"开始专有名词上下文分析，共 {len(terms)} 个术语，{len(kr_files)} 个文件")

    total_hits = 0

    # 3. 单次扫描所有文件
    for kr_file in kr_files:
        # 检查是否所有术语都已达到上限
        if all(count >= max_examples for count in term_counts.values()):
            break

        try:
            rel = kr_file.relative_to(kr_path)
            jp_file = jp_path / rel
            en_file = en_path / rel

            kr_data = _load_json(kr_file)
            if kr_data is None:
                continue
            jp_data = _load_json(jp_file) if jp_file.exists() else None
            en_data = _load_json(en_file) if en_file.exists() else None

            kr_flat = flatten_dict_enhanced(kr_data, ignore_types=[None, int, float])
            jp_flat = flatten_dict_enhanced(jp_data, ignore_types=[None, int, float]) if jp_data else {}
            en_flat = flatten_dict_enhanced(en_data, ignore_types=[None, int, float]) if en_data else {}

            for path_tuple, kr_text in kr_flat.items():
                if not isinstance(kr_text, str):
                    continue

                # 用 AC 自动机搜索当前文本值
                hits = ac.search(kr_text)
                for hit in hits:
                    term = hit.pattern
                    if term_counts.get(term, 0) >= max_examples:
                        continue

                    results[term].append({
                        "kr_sentence": kr_text,
                        "jp_sentence": jp_flat.get(path_tuple, ""),
                        "en_sentence": en_flat.get(path_tuple, ""),
                        "file": str(rel),
                        "path": path_tuple,
                    })
                    term_counts[term] = term_counts.get(term, 0) + 1
                    total_hits += 1

        except Exception:
            continue

    matched_terms = sum(1 for v in results.values() if v)
    logging.info(
        f"专有名词上下文分析完成，命中 {total_hits} 处，"
        f"覆盖 {matched_terms}/{len(terms)} 个术语"
    )
    return results
```

- [ ] **Step 4: 修改 `ProperAnalyzer.analyze()` 使用批量接口**

修改 `translateFunc/matcher/proper.py` 的 `analyze` 方法（第 65-90 行）：

```python
# 修改前:
    def analyze(self, raw_terms: list[dict]) -> list[ProperTerm]:
        """从游戏文件中提取 JP/EN 上下文句子，增强原始术语。"""
        terms: list[ProperTerm] = []
        for item in raw_terms:
            kr = item.get("term", "")
            cn = item.get("translation", "")
            note = item.get("note", "")
            if not kr:
                continue

            positive_contexts: list[dict] = []
            if self._kr_path and self._jp_path and self._en_path:
                positive_contexts = extract_contexts(
                    kr, self._kr_path, self._jp_path, self._en_path, max_examples=20
                )

            term = ProperTerm(
                kr=kr,
                cn=cn,
                note=note,
                positive_contexts=positive_contexts,
            )
            terms.append(term)

        self._terms = terms
        return terms

# 修改后:
    def analyze(self, raw_terms: list[dict]) -> list[ProperTerm]:
        """从游戏文件中提取 JP/EN 上下文句子，增强原始术语。

        使用批量 AC 自动机扫描：一次文件遍历处理全部术语，
        对比逐术语扫描快约 N 倍（N = 术语数量）。
        """
        # 收集所有有效的 KR 术语文本
        raw_term_list: list[dict] = []
        kr_texts: list[str] = []
        for item in raw_terms:
            kr = item.get("term", "")
            if not kr:
                continue
            raw_term_list.append(item)
            kr_texts.append(kr)

        # 批量提取上下文
        contexts_map: dict[str, list[dict]] = {}
        if self._kr_path and self._jp_path and self._en_path and kr_texts:
            from translateFunc.proper.analyze import extract_contexts_batch
            contexts_map = extract_contexts_batch(
                kr_texts, self._kr_path, self._jp_path, self._en_path, max_examples=20
            )

        # 构建 ProperTerm 列表
        terms: list[ProperTerm] = []
        for item in raw_term_list:
            kr = item.get("term", "")
            cn = item.get("translation", "")
            note = item.get("note", "")
            positive_contexts = contexts_map.get(kr, [])
            term = ProperTerm(
                kr=kr,
                cn=cn,
                note=note,
                positive_contexts=positive_contexts,
            )
            terms.append(term)

        self._terms = terms
        return terms
```

- [ ] **Step 5: 运行所有测试确认通过**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_extract_contexts.py tests/test_ac_automaton.py tests/test_pipeline.py tests/test_profiler.py -v
```

预期：全部 PASS。

- [ ] **Step 6: 提交**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && git add translateFunc/proper/analyze.py translateFunc/matcher/proper.py tests/test_extract_contexts.py && git commit -m "perf: extract_contexts_batch 批量扫描, O(n²)→O(n) File IO"
```

---

### Task 8: 阶段日志 + Profiler 集成

**Files:**
- Modify: `translateFunc/pipeline.py`
- Modify: `translateFunc/processor.py`

**Interfaces:**
- Consumes: `TimingProfiler`（Task 1）、所有已有模块
- Produces: pipeline 阶段日志、processor 阶段注释、运行结束剖析报告

- [ ] **Step 1: 在 pipeline.py 中添加阶段日志和 profiler phase**

修改 `translateFunc/pipeline.py` 的 `run()` 方法，在每个阶段添加日志和剖析：

```python
# 在文件顶部添加导入:
from translateFunc.profiler import TimingProfiler

# 修改 run() 方法:
    def run(self) -> PipelineSummary:
        """执行完整的翻译管道。返回聚合的 PipelineSummary。"""
        profiler = TimingProfiler.get()
        profiler.reset()

        self._on_status("正在初始化...")
        logging.info("=== 阶段 1/5: 解析路径配置 ===")

        # 1. 解析路径
        game_path = self._config.game_path
        assets_path = game_path / "LimbusCompany_Data" / "Assets" / "Resources_moved" / "Localize"
        lang_path = game_path / "LimbusCompany_Data" / "lang"

        kr_path = Path(self._config.kr_path) if self._config.kr_path and self._config.enable_dev_settings else assets_path / "kr"
        jp_path = Path(self._config.jp_path) if self._config.jp_path and self._config.enable_dev_settings else assets_path / "jp"
        en_path = Path(self._config.en_path) if self._config.en_path and self._config.enable_dev_settings else assets_path / "en"
        llc_path = Path(self._config.llc_path) if self._config.llc_path and self._config.enable_dev_settings else lang_path / "LLC_zh-CN"

        output_dir = self._config.output_dir / "LLc-CN-LCTA"
        output_dir.mkdir(parents=True, exist_ok=True)

        base_path_config = PathConfig(
            target_path=output_dir,
            llc_base_path=llc_path,
            KR_base_path=kr_path,
            JP_base_path=jp_path,
            EN_base_path=en_path,
        )

        # 2. 获取专有名词
        logging.info("=== 阶段 2/5: 获取专有名词 ===")
        with profiler.phase("获取专有名词"):
            if self._config.enable_proper:
                self._on_status("正在获取专有名词...")
                self._analyzer = ProperAnalyzer(kr_path, jp_path, en_path)
                raw_terms = self._analyzer.fetch_terms(
                    auto_fetch=self._config.auto_fetch_proper,
                    proper_path=self._config.proper_path,
                )
                logging.info(f"专有名词获取完成，共 {len(raw_terms)} 条")

                proper_terms = self._analyzer.analyze(raw_terms)
                proper_dicts = [
                    {"term": t.kr, "translation": t.cn, "note": t.note}
                    for t in proper_terms
                ]
                self._engine.build_proper(proper_dicts)
                self._on_log(f"已加载 {len(proper_terms)} 个专有名词")
            else:
                self._on_log("专有名词分析已跳过（enable_proper=False）")

        # 3. 构建翻译器
        logging.info("=== 阶段 3/5: 构建匹配引擎与翻译器 ===")
        with profiler.phase("构建匹配引擎"):
            translator = self._build_translator()

        # 4. 收集目标文件
        target_files = list(kr_path.rglob("*.json"))
        self._on_log(f"找到 {len(target_files)} 个文件")

        # 5. 重排序：优先文件放在前面
        has_prefix = self._config.has_prefix
        model_name = "KR_ScenarioModelCodes-AutoCreated.json" if has_prefix else "ScenarioModelCodes-AutoCreated.json"
        keyword_name = "KR_BattleKeywords.json" if has_prefix else "BattleKeywords.json"
        model_file = kr_path / model_name
        keyword_file = kr_path / keyword_name
        if model_file.exists() and keyword_file.exists():
            target_files.remove(model_file)
            target_files.remove(keyword_file)
            priority_files = [keyword_file, model_file]
            logging.info(f"优先文件: {keyword_name}, {model_name}")
        else:
            if not model_file.exists():
                self._on_log(f"警告: 未找到模型文件 {model_name}，跳过优先处理")
            if not keyword_file.exists():
                self._on_log(f"警告: 未找到关键字文件 {keyword_name}，跳过优先处理")
            priority_files = []

        # 6. 串行处理优先文件
        logging.info("=== 阶段 4/5: 处理优先文件 ===")
        summary = PipelineSummary()
        with profiler.phase("处理优先文件"):
            for pf in priority_files:
                outcome = self._process_one(pf, base_path_config, has_prefix, translator)
                self._record_outcome(outcome, summary)

                # 处理完优先文件后更新引擎
                if pf == priority_files[1] and self._config.enable_role:  # model 文件
                    self._update_roles(pf, base_path_config, has_prefix)
                elif pf == priority_files[0] and self._config.enable_skill:  # keyword 文件
                    self._update_affects(pf, base_path_config, has_prefix)

        # 7. 并发处理剩余文件
        logging.info(f"=== 阶段 5/5: 并发翻译 ({len(target_files)} 个文件) ===")
        self._on_status("正在执行翻译...")
        self._on_progress(10, "正在执行翻译...")

        with profiler.phase("并发翻译"):
            if self._config.enable_concurrent and len(target_files) > 1:
                worker_pool = WorkerPool(
                    translator_factory=lambda: self._build_translator(),
                    max_workers=self._config.max_workers,
                )

                def process_fn(file_path, translator):
                    return self._process_one(file_path, base_path_config, has_prefix, translator)

                def progress_cb(done, total, fname):
                    pct = 10 + int((done / total) * 80)
                    self._on_progress(pct, f"处理 {fname} ({done}/{total})")
                    self._on_check_running()

                outcomes = worker_pool.map(target_files, process_fn, on_progress=progress_cb)
            else:
                outcomes = []
                for i, file_path in enumerate(target_files):
                    outcome = self._process_one(file_path, base_path_config, has_prefix, translator)
                    outcomes.append(outcome)
                    pct = 10 + int(((i + 1) / len(target_files)) * 80)
                    self._on_progress(pct, f"处理 {outcome.file_name} ({i + 1}/{len(target_files)})")

        for o in outcomes:
            self._record_outcome(o, summary)

        # 8. 输出剖析报告
        self._on_progress(90, "已完成汉化")
        report = profiler.report()
        self._on_log(report)
        logging.info(report)

        return summary
```

- [ ] **Step 2: 在 processor.py 中添加阶段切换日志**

修改 `translateFunc/processor.py` 的 `_translate` 方法，在阶段 0/1/2 处添加日志：

在 `_translate` 方法中（第 184-196 行附近）添加：

```python
            # ====== 阶段 0：消歧（仅主格式） ======
            user_format = self._config.prompt_format
            if stage_strategy.needs_disambiguation():
                logging.debug(f"[{self.file_name}] 阶段 0: 术语消歧 (mode={self._config.disambiguation_mode})")
                # ... 阶段 0 逻辑保持不变 ...
```

在格式回退循环入口添加（第 213-216 行附近）：

```python
            # 确定格式回退链
            formats_chain = self._build_format_chain()
            if len(formats_chain) > 1:
                logging.info(
                    f"[{self.file_name}] 阶段 1: 主翻译 "
                    f"(格式链: {' → '.join(formats_chain)})"
                )
            else:
                logging.debug(f"[{self.file_name}] 阶段 1: 主翻译 ({formats_chain[0]})")
```

在阶段 2 入口添加（第 283-284 行附近）：

```python
            # ====== 阶段 2：自校验（仅主格式，阶段 1 全部成功时执行） ======
            if stage_strategy.needs_self_check() and not had_fallback:
                logging.debug(f"[{self.file_name}] 阶段 2: 自校验")
                # ... 阶段 2 逻辑保持不变 ...
```

- [ ] **Step 3: 添加关键方法 docstring**

为 `processor.py` 中缺少文档的方法补充 docstring：

`_build_format_chain`（第 322-331 行）已有隐式文档，在其上方添加：

```python
    def _build_format_chain(self) -> list[str]:
        """构建格式回退链：[用户选择] + fallback? [xml_json, json_json, xml_xml] : [].

        用户选择的格式排在最前，回退格式按 xml_json → json_json → xml_xml
        顺序追加（跳过重复）。当 fallback=False 时仅返回用户格式。
        """
```

`_collect_ambiguous_terms`（已有完整 docstring，保持不变）。

`_apply_corrections`（已有完整 docstring，保持不变）。

- [ ] **Step 4: 运行测试确认通过**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_pipeline.py tests/test_profiler.py tests/test_prompt_format.py -v
```

预期：全部 PASS。

- [ ] **Step 5: 提交**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && git add translateFunc/pipeline.py translateFunc/processor.py && git commit -m "feat: 阶段日志 + profiler集成 + 注释增强"
```

---

### Task 9: 最终集成测试

**Files:**
- 全部已修改文件

**Interfaces:**
- Consumes: 所有 Task 1-8 的产物

- [ ] **Step 1: 运行全部测试套件**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/ -v
```

预期：全部 PASS。

- [ ] **Step 2: 用 tests/example 数据运行 extract_contexts_batch 正确性验证**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -m pytest tests/test_extract_contexts.py -v
```

预期：全部 PASS。

- [ ] **Step 3: 检查是否有 import 错误**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && python -c "from translateFunc import TranslationPipeline, TranslateConfig, PipelineSummary; from translateFunc.profiler import TimingProfiler; print('All imports OK')"
```

预期：`All imports OK`。

- [ ] **Step 4: 提交最终确认**

```bash
cd E:\desktop\work\LCTA-Limbus-company-transfer-auto && git status
```

确认没有未提交的更改（除计划文件本身）。
