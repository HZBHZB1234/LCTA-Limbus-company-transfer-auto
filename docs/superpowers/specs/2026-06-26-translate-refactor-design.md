# 翻译模块重构设计

日期: 2026-06-26
版本: 1.0

## 概述

重构 LCTA 自动翻译模块，解决控制流混乱、匹配效率低、提示词质量不足、缺少并发和术语消歧等问题。

## 目标

1. 所有翻译核心逻辑放入 `translateFunc/`，`webutils/function_translate.py` 退化为薄封装
2. 用 `Enum` + Result 模式替代 `ProcesserExit(Exception)` 控制流
3. AC 自动机替换全部 4 个 `SimpleMatcher`，O(n×m) → O(m+k)
4. 专有名词 JP/EN 交叉验证，消除子串误匹配和一词多义
5. ThreadPoolExecutor 并发翻译文件
6. 三阶段翻译（消歧→翻译→校验）+ 动态模板 + 标签体系 + 严格输出格式

## 约束

- 不更改 `translatekit` 库的外部接口
- 兼容现有 `config.json` 配置结构，新增配置项有默认值
- `webutils/function_translate.py` 的对外签名保持兼容
- `proper/flat.py` 的扁平化工具函数保留不改

---

## 一、模块结构

```
translateFunc/
├── __init__.py              # 公开 API
├── enums.py                 # ProcessResult, FileType, MatchConfidence
├── config.py                # TranslateConfig, FilePathConfig 等 dataclass
├── pipeline.py              # TranslationPipeline — 编排整个翻译流程
├── processor.py             # FileProcessor — 单文件处理
├── workers.py               # WorkerPool — ThreadPoolExecutor 并发调度
│
├── matcher/
│   ├── __init__.py
│   ├── ac_automaton.py      # AC 自动机（纯算法，无游戏数据依赖）
│   ├── engine.py            # MatcherEngine — 统一管理所有匹配器
│   └── proper.py            # ProperAnalyzer — JP/EN 交叉验证
│
├── builder/
│   ├── __init__.py
│   ├── request.py           # RequestBuilder — 构建翻译请求结构
│   ├── prompt.py            # PromptFactory — 动态提示词 + 标签体系
│   └── stages.py            # StageStrategy — 阶段化翻译策略
│
├── proper/
│   ├── __init__.py
│   ├── flat.py              # 保留不改：扁平化/还原工具
│   └── analyze.py           # 新增：拉取 paratranz 术语 + JP/EN 分析
│
├── translate_doc.py         # 保留：技能文档、角色风格、基础提示词
└── translate_request.py     # 保留：TRANSLATOR_TRANS 注册表
```

### 调用链路

```
webutils/function_translate.py (薄封装)
    │
    └──→ translateFunc.pipeline.TranslationPipeline.run()
            │
            ├── 1. ProperAnalyzer.fetch_and_build()
            │       └── 拉取术语 → 游戏文件中查找 JP/EN 对应
            │       　　　　 → 构建 AC 自动机 + positive/negative contexts
            │
            ├── 2. MatcherEngine.build(proper_data)
            │       └── 构建所有 matcher 的 AC 自动机
            │
            ├── 3. 特殊文件串行处理 (ScenarioModelCodes, BattleKeywords)
            │       └── 更新 MatcherEngine 中的角色/状态效果数据
            │
            ├── 4. WorkerPool.map(process_file, remaining_files)
            │       │
            │       └──→ FileProcessor.process() → ProcessResult
            │               ├── Load JSONs
            │               ├── Check empty / already translated
            │               ├── Build Request (PromptFactory + RequestBuilder)
            │               ├── Stage 0: 术语消歧 (similarity/llm/hybrid)
            │               ├── Stage 1: 主翻译 (动态标签化 prompt)
            │               ├── Stage 2: 自校验 (可选)
            │               └── Save & return result
            │
            └── 5. 汇总 PipelineSummary → 返回
```

---

## 二、控制流 —— Result Enum

### 枚举定义 (`enums.py`)

```python
class ProcessResult(Enum):
    SUCCESS_SAVED          = auto()   # 成功翻译并保存
    ALREADY_TRANSLATED     = auto()   # 已翻译，跳过
    EMPTY_WITH_LLC         = auto()   # 空文件，已复制 llc
    EMPTY_SKIPPED          = auto()   # 空文件，无 llc 可复制
    JSON_DECODE_ERROR      = auto()   # JSON 解析失败
    SAVE_ERROR             = auto()   # 保存失败
    TRANSLATION_MISMATCH   = auto()   # 翻译结果数量不匹配

class FileType(Enum):
    STORY    = auto()   # 剧情文件 (StoryData/)
    SKILL    = auto()   # 技能文件 (Skills_*)
    UI       = auto()   # UI 文本
    OTHER    = auto()   # 其他

class MatchConfidence(Enum):
    HIGH         = auto()   # JP 和 EN 都与 positive context 匹配
    MEDIUM       = auto()   # 仅 JP 或仅 EN 匹配
    LOW          = auto()   # 弱匹配，可能不适用
    UNKNOWN      = auto()   # 术语无上下文数据，无法判断
    FALSE_MATCH  = auto()   # 与 negative context 更接近，判定为假阳性
```

### 处理结果数据类 (`config.py`)

```python
@dataclass
class ProcessOutcome:
    """单个文件的处理结果"""
    result: ProcessResult
    file_name: str
    extra: dict | None = None  # 错误详情等附加信息

@dataclass
class PipelineSummary:
    """一次翻译运行的汇总结果"""
    saved: list[str]          # 成功翻译的文件名
    skipped: list[str]        # 跳过的文件名（已翻译/空文件）
    errors: list[ProcessOutcome]  # 失败的文件及原因
```

### FileProcessor 返回 Result

```python
class FileProcessor:
    def process(self) -> ProcessOutcome:
        # 加载 JSON
        if not self._load_jsons():
            return ProcessOutcome(ProcessResult.JSON_DECODE_ERROR, ...)
        # 空文件检查
        outcome = self._check_empty()
        if outcome:
            return outcome
        # 已翻译检查
        if self._already_translated():
            self._copy_llc()
            return ProcessOutcome(ProcessResult.ALREADY_TRANSLATED, ...)
        # 构建 → 翻译 → 保存
        ...
        return ProcessOutcome(ProcessResult.SUCCESS_SAVED, ...)
```

### Pipeline 汇总

```python
class TranslationPipeline:
    def run(self) -> PipelineSummary:
        results = self.worker_pool.map(...)
        summary = PipelineSummary([], [], [])
        for r in results:
            if r.result == ProcessResult.SUCCESS_SAVED:
                summary.saved.append(r.file_name)
            elif r.result == ProcessResult.ALREADY_TRANSLATED:
                summary.skipped.append(r.file_name)
            elif r.result in {JSON_DECODE_ERROR, SAVE_ERROR, TRANSLATION_MISMATCH}:
                summary.errors.append(r)
        return summary
```

---

## 三、AC 自动机 + 匹配系统

### AC 自动机 (`matcher/ac_automaton.py`)

纯算法实现，不依赖游戏数据：

```python
@dataclass
class ACPattern:
    pattern: str
    node_id: int
    data: Any = None

class AcAutomaton:
    def __init__(self):
        self._trie: list[dict[str, int]] = [{}]
        self._fail: list[int] = [0]
        self._output: list[list[ACPattern]] = [[]]
        self._built = False

    def add_pattern(self, pattern: str, data: Any = None) -> None: ...
    def build(self) -> None: ...
    def search(self, text: str) -> list[ACPattern]: ...
    def search_batch(self, texts: list[str]) -> list[list[ACPattern]]: ...
```

复杂度：
- 构建: O(L)，L=所有模式字符数总和，一次调用
- 搜索: O(m + k)，m=文本长度，k=命中数

### MatcherEngine (`matcher/engine.py`)

统一管理 4 个 AC 自动机实例：

```python
class MatcherEngine:
    def __init__(self):
        self._proper_ac = AcAutomaton()
        self._role_ac = AcAutomaton()
        self._affect_id_ac = AcAutomaton()
        self._affect_name_ac = AcAutomaton()

    def build(self, proper_items, role_items, affect_items) -> None: ...
    def match_proper(self, text: str) -> list[ProperTerm]: ...
    def match_all(self, text: str) -> MatchResult: ...
```

对外通过 `MatchResult` 返回一次匹配的所有维度结果。

---

## 四、专有名词 JP/EN 交叉验证

### 核心问题

1. **短术语误匹配**：如 `고`（膏）出现在大量无关句子中
2. **一词多义**：如 `이상` 既是人名"李箱"又是"不低于"

### 数据构建

翻译初始化时，对每个术语在游戏 KR 文件中搜索包含它的句子，提取同位置的 JP/EN 文本：

```python
@dataclass
class ProperTerm:
    kr: str
    cn: str
    note: str
    positive_contexts: list[dict]   # {kr_sentence, jp_sentence, en_sentence}
    negative_contexts: list[dict]   # 同结构，包含但不匹配的上下文

class ProperAnalyzer:
    def fetch_terms(self) -> list[dict]: ...
    def analyze(self, raw_terms: list[dict]) -> list[ProperTerm]: ...
    def build_index(self, terms: list[ProperTerm]) -> ProperIndex: ...
```

短术语（≤2 字符）只有 JP/EN 明确验证通过才加入 `positive_contexts`。

### 方案 A：相似度消歧

```python
def compute_confidence(self, term: ProperTerm,
                       text_block_jp: str,
                       text_block_en: str) -> MatchConfidence:
    """基于句级相似度判断术语是否真正适用"""
    pos_score = max(similarity(text_block_jp/en, ctx.jp/en) 
                    for ctx in term.positive_contexts)
    neg_score = max(similarity(text_block_jp/en, ctx.jp/en)
                    for ctx in term.negative_contexts)
    
    if pos_score > 0.6 and pos_score > neg_score:
        return MatchConfidence.HIGH
    elif neg_score > pos_score:
        return MatchConfidence.FALSE_MATCH
    elif pos_score > 0.3:
        return MatchConfidence.MEDIUM
    else:
        return MatchConfidence.FALSE_MATCH
```

相似度 = Jaccard 词汇重叠 × 0.6 + 字符重叠 × 0.4

### 方案 B：LLM 消歧

在主翻译前插入轻量消歧阶段：

- Prompt: 系统角色 + 当前文本块(kr,jp,en) + 候选术语列表
- 输出: `{term, applies(bool), actual_meaning, reason}[]`
- 特点: 轻量（~300 tokens），专注判断不做翻译

### 运行模式

通过 `disambiguation_mode` 配置：
- `"similarity"`: 仅本地相似度，零额外 LLM 调用
- `"llm"`: 仅 LLM 消歧，高准确率
- `"hybrid"`: 相似度高置信的直接过，低置信的交 LLM 判断

---

## 五、并发模型

### WorkerPool (`workers.py`)

```python
class WorkerPool:
    def __init__(self, translator_factory, max_workers: int = 4):
        self._factory = translator_factory  # 每个线程创建独立 translator
        self._max_workers = max_workers
    
    def map(self, files, process_fn, on_progress=None) -> list[ProcessOutcome]:
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            # 提交所有任务，保持结果顺序
            # as_completed 汇总，通过 on_progress 回调上报
```

### 关键设计

- **独立 translator 实例**：每个线程通过工厂函数创建独立实例，避免 HTTP 连接竞争
- **特殊文件串行**：`ScenarioModelCodes` 和 `BattleKeywords` 先串行处理并更新 MatcherEngine，其余文件并发
- **配置控制**：`max_workers`（默认 4），`enable_concurrent`（默认 true），非 LLM 翻译器强制 `max_workers=1`

---

## 六、提示词系统

### 三层架构

| 层 | 内容 | 来源 |
|---|---|---|
| 模板层 | system / examples / output_format | `builder/prompt.py` JSON 模板 |
| 规则层 | 术语表 / 角色风格 / 技能指南 | `translate_doc.py` 保留 |
| 上下文层 | 当前文本块 + 消歧结果 | 运行时动态注入 |

### 三阶段翻译

| 阶段 | 名称 | 描述 | 可选 |
|---|---|---|---|
| 0 | 术语消歧 | AC 命中 → 交叉验证过滤假阳性 | 通过 `disambiguation_mode` 控制 |
| 1 | 主翻译 | 标签化 prompt + 动态模板 + 严格 JSON 输出 | 必须 |
| 2 | 自校验 | 术语一致性 + 格式规则检查 + 自动修正 | 通过 `enable_self_check` 控制 |

### XML 标签体系

所有提示词使用统一的 XML 标签：

```
<role> ... </role>
<rules>
  <rule> ... </rule>
</rules>
<glossary>
  <term kr="..." cn="..." note="..."> ... </term>
</glossary>
<examples>
  <example>
    <in> ... </in>
    <out>
      <translation> ... </translation>
      <reasoning> ... </reasoning>
      <confidence> ... </confidence>
    </out>
  </example>
</examples>
<context> ... </context>
<text>
  <block id="1">
    <kr> ... </kr>
    <jp> ... </jp>
    <en> ... </en>
  </block>
</text>
<format> ... </format>
```

- `PromptTag` 枚举定义所有标签
- `PromptFactory` 按 `FileType` + `Stage` 动态组装
- 无内容的标签块自动省略，不留空标题
- 自定义渲染器可切换标签风格（XML / 纯文本）

### 输出格式

统一 JSON schema，包含 reasoning 和 confidence：

```json
{
  "translations": [
    {
      "id": 1,
      "translation": "翻译结果",
      "reasoning": "关键决策说明",
      "confidence": "high|medium|low"
    }
  ]
}
```

- `confidence=low` 的翻译默认返回原文（可选择配置）
- 废弃纯文本分隔符解析方式

---

## 七、对外 API

### 公开入口 (`translateFunc/__init__.py`)

```python
from translateFunc.pipeline import TranslationPipeline
from translateFunc.enums import ProcessResult, FileType, MatchConfidence
from translateFunc.config import TranslateConfig, PipelineSummary
```

### TranslationPipeline

```python
class TranslationPipeline:
    def __init__(self, config: TranslateConfig): ...
    def set_callbacks(self, *, on_log, on_status, on_progress, on_check_running): ...
    def run(self) -> PipelineSummary: ...
```

### webutils/function_translate.py 退化

重构后 ~80 行，只做：
1. 从 ConfigManager 读取配置 → TranslateConfig
2. 创建临时目录
3. 绑定 WebUI 回调
4. 调用 `pipeline.run()`
5. 打包产物 + 版本号

### TranslateConfig

`translateFunc` 不依赖 `ConfigManager`，所有配置通过 `TranslateConfig` dataclass 注入：

```python
@dataclass
class TranslateConfig:
    # 翻译器
    translator_name: str = "LLM通用翻译服务"
    translator_api: dict = field(default_factory=dict)
    # 路径
    game_path: Path = Path()
    output_dir: Path = Path()
    # 功能开关
    enable_proper: bool = True
    enable_role: bool = True
    enable_skill: bool = True
    # 并发
    max_workers: int = 4
    enable_concurrent: bool = True
    # 提示词
    translation_mode: str = "multi_stage"
    enable_self_check: bool = False
    disambiguation_mode: str = "hybrid"
    min_confidence: str = "medium"
    # 调试
    debug_mode: bool = False
    dump: bool = False
    
    @classmethod
    def from_config_manager(cls, mgr) -> "TranslateConfig": ...
```

---

## 八、测试策略

### 单元测试

| 模块 | 测试内容 | 独立性 |
|---|---|---|
| `ac_automaton.py` | 构建、搜索、多模式、重叠模式、空文本 | 纯算法，零依赖 |
| `matcher/engine.py` | 多自动机构建、match_all 聚合 | mock AC 自动机 |
| `matcher/proper.py` | 上下文构建、置信度计算、短术语过滤 | mock 文件数据 |
| `enums.py` | 枚举值唯一性 | 零依赖 |
| `config.py` | from_config_manager 映射正确性 | mock ConfigManager |
| `builder/prompt.py` | 模板选择、标签组装、阶段切换 | mock TranslateConfig |
| `processor.py` | process() 各分支返回正确 Result | mock 文件系统和 translator |

### 集成测试

- `TranslationPipeline.run()` 端到端：mock 翻译文件 + mock translator → 验证 PipelineSummary
- 并发正确性：多文件并发 → 验证结果顺序和完整性
- 消歧正确性：准备已知的一词多义输入 → 验证 FALSE_MATCH 被正确过滤

---

## 九、配置迁移

新增配置项（写入 `config_default.json` 的 `ui_default.translator`）：

```json
{
  "max_workers": 4,
  "enable_concurrent": true,
  "translation_mode": "multi_stage",
  "enable_self_check": false,
  "disambiguation_mode": "hybrid",
  "min_confidence": "medium"
}
```

旧配置项全部保留，通过 `ConfigManager.fix()` 自动补全缺失键。

---

## 十、风险和缓解

| 风险 | 缓解 |
|---|---|
| AC 自动机构建慢（800+ 术语 × 多文件扫描） | 构建结果序列化缓存到 `tmp/`，术语未变则直接加载 |
| LLM 消歧增加翻译延迟 | `hybrid` 模式下大部分由相似度处理，仅低置信度走 LLM |
| 并发下 translator HTTP 连接竞争 | 每个线程独立 translator 实例 |
| 三阶段模式增加 API 调用成本 | `single_stage` 兼容模式保留，用户可选择 |
| 重构期间功能回归 | 旧代码保留在分支，逐模块替换 + 测试覆盖 |
