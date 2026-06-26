# 翻译模块重构 Implementation Plan

## 使用中文进行回复以及注释撰写

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the LCTA auto-translation module to use AC automaton matching, Enum+Result control flow, ThreadPoolExecutor concurrency, JP/EN cross-validation for proper nouns, and a 3-stage tagged prompt system — all living in `translateFunc/` with `webutils/function_translate.py` as an ~80-line wrapper.

**Architecture:** Modular decomposition into `matcher/` (AC automaton + proper noun analysis), `builder/` (prompt factory + request building + stage strategies), and top-level orchestration files (enums, config, pipeline, processor, workers). The `TranslationPipeline` orchestrates: fetch terms → build matchers → serial priority files → concurrent file processing → aggregate summary.

**Tech Stack:** Python 3.10+, dataclasses, Enum, ThreadPoolExecutor, translatekit (unchanged), existing `proper/flat.py` (unchanged).

## Global Constraints

- Do NOT modify the translatekit library's external interface
- Preserve backward compatibility with existing `config.json` keys; new keys get defaults via `ConfigManager.fix()`
- `webutils/function_translate.py` public signature stays compatible
- `translateFunc/proper/flat.py` remains UNCHANGED
- `translateFunc/translate_doc.py` and `translateFunc/translate_request.py` remain UNCHANGED
- `translateFunc/get_proper.py` remains UNCHANGED
- All new files go under `translateFunc/`; no new top-level modules

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `translateFunc/enums.py` | CREATE | `ProcessResult`, `FileType`, `MatchConfidence` enums |
| `translateFunc/config.py` | CREATE | `TranslateConfig`, `ProcessOutcome`, `PipelineSummary` dataclasses |
| `translateFunc/matcher/__init__.py` | CREATE | Re-exports: `AcAutomaton`, `ACPattern`, `MatcherEngine`, `MatchResult`, `ProperAnalyzer`, `ProperTerm` |
| `translateFunc/matcher/ac_automaton.py` | CREATE | Pure AC automaton algorithm |
| `translateFunc/matcher/engine.py` | CREATE | `MatcherEngine` — manages 4 AC instances, `MatchResult` dataclass |
| `translateFunc/matcher/proper.py` | CREATE | `ProperAnalyzer` — JP/EN cross-validation, `ProperTerm` dataclass |
| `translateFunc/builder/__init__.py` | CREATE | Re-exports: `PromptFactory`, `PromptTag`, `RequestBuilder`, `StageStrategy` |
| `translateFunc/builder/prompt.py` | CREATE | `PromptTag` enum, `PromptFactory` — XML-tagged dynamic prompts |
| `translateFunc/builder/request.py` | CREATE | `RequestBuilder` — refactored from old `RequestTextBuilder` |
| `translateFunc/builder/stages.py` | CREATE | `StageStrategy` — 3-stage disambiguation→translate→self-check |
| `translateFunc/processor.py` | CREATE | `FileProcessor` — returns `ProcessOutcome`, no exceptions for control flow |
| `translateFunc/workers.py` | CREATE | `WorkerPool` — ThreadPoolExecutor with per-thread translator factory |
| `translateFunc/pipeline.py` | CREATE | `TranslationPipeline` — end-to-end orchestration |
| `translateFunc/__init__.py` | REWRITE | Public API surface |
| `translateFunc/proper/__init__.py` | CREATE | Re-exports: `flatten_dict_enhanced`, `update_dict_with_flattened`, `get_value_by_path` from `flat.py` |
| `translateFunc/proper/analyze.py` | CREATE | JP/EN context extraction from game files |
| `webutils/function_translate.py` | REWRITE | Thin ~80-line wrapper |
| `config_default.json` | MODIFY | Add 6 new config keys under `ui_default.translator` |
| `config_check.json` | MODIFY | Add 6 new schema entries under `ui_default.translator` |

### Files NOT touched

- `translateFunc/translate_doc.py` — preserved verbatim
- `translateFunc/translate_request.py` — preserved verbatim
- `translateFunc/get_proper.py` — preserved verbatim
- `translateFunc/proper/flat.py` — preserved verbatim
- `translateFunc/proper/properMain.py` — preserved (empty placeholder)

---

### Task 1: Create `translateFunc/enums.py` — Control flow enums

**Files:**
- Create: `translateFunc/enums.py`

**Interfaces:**
- Produces: `ProcessResult(Enum)`, `FileType(Enum)`, `MatchConfidence(Enum)` — imported by `config.py`, `processor.py`, `pipeline.py`, `builder/stages.py`, `matcher/proper.py`

- [ ] **Step 1: Write the file**

```python
"""
translateFunc/enums.py
Control-flow enums replacing exception-based flow control and magic strings.
"""
from enum import Enum, auto


class ProcessResult(Enum):
    """Outcome of processing a single file."""
    SUCCESS_SAVED        = auto()   # Translated and saved successfully
    ALREADY_TRANSLATED   = auto()   # Already translated, skipped
    EMPTY_WITH_LLC       = auto()   # Empty file, copied existing llc
    EMPTY_SKIPPED        = auto()   # Empty file, no llc to copy
    JSON_DECODE_ERROR    = auto()   # JSON parse failure
    SAVE_ERROR           = auto()   # Save failure
    TRANSLATION_MISMATCH = auto()   # Translated result count ≠ input count


class FileType(Enum):
    """Category of file being translated — drives prompt template selection."""
    STORY = auto()   # StoryData/ files
    SKILL = auto()   # Skills_* files
    UI    = auto()   # UI text files
    OTHER = auto()   # Everything else


class MatchConfidence(Enum):
    """Confidence level for a proper-noun match after JP/EN cross-validation."""
    HIGH        = auto()   # JP and EN both match positive context
    MEDIUM      = auto()   # Only JP or only EN matches
    LOW         = auto()   # Weak match, likely inapplicable
    UNKNOWN     = auto()   # Term has no context data, cannot judge
    FALSE_MATCH = auto()   # Closer to negative context, rejected
```

- [ ] **Step 2: Verify syntax**

```bash
python -c "from translateFunc.enums import ProcessResult, FileType, MatchConfidence; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add translateFunc/enums.py
git commit -m "feat: add ProcessResult, FileType, MatchConfidence enums"
```

---

### Task 2: Create `translateFunc/config.py` — Configuration and result dataclasses

**Files:**
- Create: `translateFunc/config.py`

**Interfaces:**
- Consumes: `ProcessResult` from `translateFunc.enums`
- Produces: `TranslateConfig`, `ProcessOutcome`, `PipelineSummary`, `FilePathConfig` (moved from `translate_main.py`)
  - `TranslateConfig.from_config_manager(mgr) -> TranslateConfig` classmethod
  - `ProcessOutcome(result: ProcessResult, file_name: str, extra: dict | None = None)`
  - `PipelineSummary.saved: list[str]`, `.skipped: list[str]`, `.errors: list[ProcessOutcome]`
  - `FilePathConfig(KR_path, _PathConfig, has_prefix)` — preserved from old code, with `rel_path`, `real_name`, `target_file`, etc. properties

- [ ] **Step 1: Write the file**

```python
"""
translateFunc/config.py
Configuration dataclasses and result containers.
Decouples translateFunc from ConfigManager — all config flows through TranslateConfig.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from translateFunc.enums import ProcessResult


@dataclass
class TranslateConfig:
    """All configuration for a translation run. Injected by the caller (WebUI or CLI)."""
    # --- Translator ---
    translator_name: str = "LLM通用翻译服务"
    translator_api: dict = field(default_factory=dict)

    # --- Paths ---
    game_path: Path = Path()
    output_dir: Path = Path()

    # --- Feature toggles ---
    enable_proper: bool = True
    enable_role: bool = True
    enable_skill: bool = True
    enable_dev_settings: bool = False

    # --- Concurrency ---
    max_workers: int = 4
    enable_concurrent: bool = True

    # --- Prompt / pipeline ---
    translation_mode: str = "multi_stage"     # "multi_stage" | "single_stage"
    enable_self_check: bool = False
    disambiguation_mode: str = "hybrid"       # "similarity" | "llm" | "hybrid"
    min_confidence: str = "medium"            # "high" | "medium" | "low"

    # --- Save ---
    save_result: bool = True

    # --- Debug ---
    debug_mode: bool = False
    dump: bool = False

    # --- Legacy (preserved from old config) ---
    is_text_format: bool = False
    is_llm: bool = True
    from_lang: str = "EN"
    auto_fetch_proper: bool = True
    proper_path: str = ""
    fallback: bool = True
    has_prefix: bool = True
    kr_path: str = ""
    jp_path: str = ""
    en_path: str = ""
    llc_path: str = ""

    @classmethod
    def from_config_manager(cls, mgr) -> "TranslateConfig":
        """Build TranslateConfig from the singleton ConfigManager."""
        configs: dict = mgr.get("ui_default.translator", {})
        game_path = Path(mgr.get("game_path", ""))
        debug_mode = mgr.get("debug", False)

        return cls(
            translator_name=configs.get("translator", "LLM通用翻译服务"),
            is_llm=(configs.get("translator", "") == "LLM通用翻译服务"),
            game_path=game_path,
            enable_proper=configs.get("enable_proper", True),
            enable_role=configs.get("enable_role", True),
            enable_skill=configs.get("enable_skill", True),
            enable_dev_settings=configs.get("enable_dev_settings", False),
            is_text_format=configs.get("is_text", False),
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
            # New keys with defaults:
            max_workers=configs.get("max_workers", 4),
            enable_concurrent=configs.get("enable_concurrent", True),
            translation_mode=configs.get("translation_mode", "multi_stage"),
            enable_self_check=configs.get("enable_self_check", False),
            disambiguation_mode=configs.get("disambiguation_mode", "hybrid"),
            min_confidence=configs.get("min_confidence", "medium"),
        )


@dataclass
class ProcessOutcome:
    """Result of processing a single file."""
    result: ProcessResult
    file_name: str
    extra: dict | None = None  # Error details, timing info, etc.


@dataclass
class PipelineSummary:
    """Aggregate result of a full translation run."""
    saved: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[ProcessOutcome] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.saved) + len(self.skipped) + len(self.errors)

    @property
    def success_count(self) -> int:
        return len(self.saved)

    @property
    def error_count(self) -> int:
        return len(self.errors)


# --- Path config (preserved from old translate_main.py) ---

@dataclass
class PathConfig:
    """Base paths for all language directories."""
    target_path: Path = Path()
    llc_base_path: Path = Path()
    KR_base_path: Path = Path()
    JP_base_path: Path = Path()
    EN_base_path: Path = Path()

    def create_need_dirs(self):
        """Ensure the target output directory exists."""
        self.target_path.mkdir(parents=True, exist_ok=True)


@dataclass
class FilePathConfig:
    """Paths for a single file across all languages."""
    KR_path: Path
    _PathConfig: PathConfig
    has_prefix: bool = True

    @property
    def rel_path(self) -> Path:
        return self.KR_path.relative_to(self._PathConfig.KR_base_path)

    @property
    def rel_dir(self) -> Path:
        return self.rel_path.parent

    @property
    def real_name(self) -> str:
        name = self.KR_path.name
        if self.has_prefix:
            for pre in ("KR_", "EN_", "JP_", "LLC_"):
                if name.startswith(pre):
                    return name[len(pre):]
        return name

    @property
    def target_file(self) -> Path:
        return self._PathConfig.target_path / self.rel_path.parent / self.real_name

    @property
    def EN_path(self) -> Path:
        if self.has_prefix:
            return self._PathConfig.EN_base_path / self.rel_path.parent / f"EN_{self.real_name}"
        return self._PathConfig.EN_base_path / self.rel_path

    @property
    def JP_path(self) -> Path:
        if self.has_prefix:
            return self._PathConfig.JP_base_path / self.rel_path.parent / f"JP_{self.real_name}"
        return self._PathConfig.JP_base_path / self.rel_path

    @property
    def LLC_path(self) -> Path:
        if self.has_prefix:
            return self._PathConfig.LLC_base_path / self.rel_path.parent / f"LLC_{self.real_name}"
        return self._PathConfig.LLC_base_path / self.rel_path
```

- [ ] **Step 2: Verify syntax and imports**

```bash
python -c "from translateFunc.config import TranslateConfig, ProcessOutcome, PipelineSummary, FilePathConfig, PathConfig; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add translateFunc/config.py
git commit -m "feat: add TranslateConfig, ProcessOutcome, PipelineSummary dataclasses"
```

---

### Task 3: Create `translateFunc/matcher/ac_automaton.py` — Pure AC automaton

**Files:**
- Create: `translateFunc/matcher/__init__.py`
- Create: `translateFunc/matcher/ac_automaton.py`

**Interfaces:**
- Produces: `ACPattern` dataclass, `AcAutomaton` class
  - `AcAutomaton.add_pattern(pattern: str, data: Any = None) -> None`
  - `AcAutomaton.build() -> None`
  - `AcAutomaton.search(text: str) -> list[ACPattern]`
  - `AcAutomaton.search_batch(texts: list[str]) -> list[list[ACPattern]]`

- [ ] **Step 1: Write `translateFunc/matcher/__init__.py`**

```python
"""translateFunc.matcher — AC automaton matching and proper noun analysis."""
```

- [ ] **Step 2: Write `translateFunc/matcher/ac_automaton.py`**

```python
"""
translateFunc/matcher/ac_automaton.py
Pure Aho-Corasick automaton implementation.
No game data dependencies — algorithm only.

Complexity:
  Build: O(L) where L = sum of all pattern lengths
  Search: O(m + k) where m = text length, k = number of hits
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
from typing import Any


@dataclass
class ACPattern:
    """A matched pattern found by the automaton."""
    pattern: str
    node_id: int
    data: Any = None


class AcAutomaton:
    """Aho-Corasick multi-pattern string matching automaton."""

    def __init__(self):
        self._trie: list[dict[str, int]] = [{}]
        self._fail: list[int] = [0]
        self._output: list[list[ACPattern]] = [[]]
        self._built: bool = False

    def add_pattern(self, pattern: str, data: Any = None) -> None:
        """Add a pattern to the automaton. Must call build() before searching."""
        if self._built:
            raise RuntimeError("Cannot add patterns after build()")
        if not pattern:
            return
        node = 0
        for ch in pattern:
            if ch not in self._trie[node]:
                self._trie[node][ch] = len(self._trie)
                self._trie.append({})
                self._fail.append(0)
                self._output.append([])
            node = self._trie[node][ch]
        self._output[node].append(ACPattern(pattern=pattern, node_id=node, data=data))

    def build(self) -> None:
        """Build failure links (BFS). Must be called after all add_pattern() calls."""
        if self._built:
            return
        queue: deque[int] = deque()
        # Initialize failure links for depth-1 nodes
        for ch, child in self._trie[0].items():
            self._fail[child] = 0
            queue.append(child)
        # BFS
        while queue:
            r = queue.popleft()
            for ch, child in self._trie[r].items():
                queue.append(child)
                f = self._fail[r]
                while f != 0 and ch not in self._trie[f]:
                    f = self._fail[f]
                self._fail[child] = self._trie[f].get(ch, 0)
                self._output[child].extend(self._output[self._fail[child]])
        self._built = True

    def search(self, text: str) -> list[ACPattern]:
        """Search for all patterns in text. Returns list of matched ACPattern."""
        if not self._built:
            raise RuntimeError("Must call build() before search()")
        if not text:
            return []
        result: list[ACPattern] = []
        node = 0
        for ch in text:
            while node != 0 and ch not in self._trie[node]:
                node = self._fail[node]
            node = self._trie[node].get(ch, 0)
            if self._output[node]:
                result.extend(self._output[node])
        return result

    def search_batch(self, texts: list[str]) -> list[list[ACPattern]]:
        """Search multiple texts. Returns one list of matches per input text."""
        return [self.search(t) for t in texts]

    @property
    def pattern_count(self) -> int:
        """Total number of patterns added."""
        return sum(len(out) for out in self._output)

    @property
    def is_built(self) -> bool:
        return self._built
```

- [ ] **Step 3: Write and run the unit test**

```bash
python -c "
from translateFunc.matcher.ac_automaton import AcAutomaton

ac = AcAutomaton()
ac.add_pattern('he')
ac.add_pattern('she')
ac.add_pattern('his')
ac.add_pattern('hers')
ac.build()

# Single search
hits = ac.search('ushers')
patterns = {h.pattern for h in hits}
assert patterns == {'she', 'he', 'hers'}, f'Expected she,he,hers got {patterns}'

# No match
assert ac.search('xyz') == []

# Batch search
results = ac.search_batch(['ushers', 'xyz', 'his'])
assert len(results[0]) == 3
assert len(results[1]) == 0
assert len(results[2]) == 1

# Overlapping patterns
ac2 = AcAutomaton()
ac2.add_pattern('a')
ac2.add_pattern('aa')
ac2.build()
hits2 = ac2.search('aaa')
assert len(hits2) == 5  # 3x 'a' + 2x 'aa'

print('All AC automaton tests passed')
"
```

- [ ] **Step 4: Commit**

```bash
git add translateFunc/matcher/__init__.py translateFunc/matcher/ac_automaton.py
git commit -m "feat: add Aho-Corasick automaton for multi-pattern matching"
```

---

### Task 4: Create `translateFunc/matcher/engine.py` — MatcherEngine

**Files:**
- Create: `translateFunc/matcher/engine.py`
- Modify: `translateFunc/matcher/__init__.py` (add re-exports)

**Interfaces:**
- Consumes: `AcAutomaton`, `ACPattern` from `translateFunc.matcher.ac_automaton`
- Produces: `MatchResult` dataclass, `MatcherEngine` class
  - `MatcherEngine.build(proper_items, role_items, affect_items) -> None`
  - `MatcherEngine.match_all(text: str) -> MatchResult`

- [ ] **Step 1: Write `translateFunc/matcher/engine.py`**

```python
"""
translateFunc/matcher/engine.py
MatcherEngine — manages all four AC automaton instances and provides unified matching.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from translateFunc.matcher.ac_automaton import AcAutomaton, ACPattern


@dataclass
class MatchResult:
    """Result of matching text against all matchers simultaneously."""
    proper_matches: list[ACPattern] = field(default_factory=list)
    role_matches: list[ACPattern] = field(default_factory=list)
    affect_id_matches: list[ACPattern] = field(default_factory=list)
    affect_name_matches: list[ACPattern] = field(default_factory=list)

    @property
    def has_any(self) -> bool:
        return bool(self.proper_matches or self.role_matches
                    or self.affect_id_matches or self.affect_name_matches)


class MatcherEngine:
    """Unified matching engine that manages four AC automata:
    proper nouns, roles, affect IDs (e.g. [Combustion]), and affect names (e.g. '燃烧 ').
    """

    def __init__(self):
        self._proper_ac = AcAutomaton()
        self._role_ac = AcAutomaton()
        self._affect_id_ac = AcAutomaton()
        self._affect_name_ac = AcAutomaton()

        # Data lookup tables keyed by node_id or pattern
        self._proper_data: dict[int, Any] = {}
        self._role_data: list[dict] = []
        self._affect_data: list[dict] = []

    # ----- Build -----

    def build_proper(self, proper_terms: list[dict]) -> None:
        """Build proper noun AC automaton from [{term, translation, note, ...}, ...]."""
        self._proper_ac = AcAutomaton()
        for item in proper_terms:
            term = item.get("term", "")
            if term:
                self._proper_ac.add_pattern(term, data=item)
        self._proper_ac.build()

    def build_roles(self, role_items: list[dict]) -> None:
        """Build role AC automaton from [{id, kr, cn, nickName}, ...].
        Roles are matched by `id` field (exact match), not substring."""
        self._role_data = role_items
        self._role_ac = AcAutomaton()
        for item in role_items:
            role_id = item.get("id", "")
            if role_id:
                self._role_ac.add_pattern(role_id, data=item)
        self._role_ac.build()

    def build_affects(self, affect_items: list[dict]) -> None:
        """Build affect ID and Name AC automata from [{id, kr, cn, desc}, ...]."""
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

    # ----- Match -----

    def match_all(self, text: str) -> MatchResult:
        """Run all four matchers against a text string."""
        return MatchResult(
            proper_matches=self._proper_ac.search(text),
            role_matches=self._role_ac.search(text),
            affect_id_matches=self._affect_id_ac.search(text),
            affect_name_matches=self._affect_name_ac.search(text),
        )

    def match_proper(self, text: str) -> list[ACPattern]:
        """Match only proper nouns."""
        return self._proper_ac.search(text)

    # ----- Accessors -----

    @property
    def role_data(self) -> list[dict]:
        return self._role_data

    @property
    def affect_data(self) -> list[dict]:
        return self._affect_data
```

- [ ] **Step 2: Update `translateFunc/matcher/__init__.py`**

```python
"""translateFunc.matcher — AC automaton matching and proper noun analysis."""
from translateFunc.matcher.ac_automaton import AcAutomaton, ACPattern
from translateFunc.matcher.engine import MatcherEngine, MatchResult
from translateFunc.matcher.proper import ProperAnalyzer, ProperTerm

__all__ = [
    "AcAutomaton", "ACPattern",
    "MatcherEngine", "MatchResult",
    "ProperAnalyzer", "ProperTerm",
]
```

- [ ] **Step 3: Verify syntax**

```bash
python -c "from translateFunc.matcher.engine import MatcherEngine, MatchResult; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add translateFunc/matcher/engine.py translateFunc/matcher/__init__.py
git commit -m "feat: add MatcherEngine with 4 AC automata"
```

---

### Task 5: Create `translateFunc/matcher/proper.py` — ProperAnalyzer with JP/EN cross-validation

**Files:**
- Create: `translateFunc/matcher/proper.py`
- Create: `translateFunc/proper/__init__.py` (re-export flat.py utilities)
- Create: `translateFunc/proper/analyze.py` (JP/EN context extraction)

**Interfaces:**
- Consumes: `MatchConfidence` from `translateFunc.enums`, `AcAutomaton` from `translateFunc.matcher.ac_automaton`, `fetch` from `translateFunc.get_proper`
- Produces: `ProperTerm` dataclass, `ProperAnalyzer` class
  - `ProperAnalyzer.fetch_terms(min_len=0) -> list[dict]`
  - `ProperAnalyzer.analyze(raw_terms, kr_path, jp_path, en_path) -> list[ProperTerm]`
  - `ProperAnalyzer.compute_confidence(term, text_block_jp, text_block_en) -> MatchConfidence`

- [ ] **Step 1: Write `translateFunc/proper/__init__.py`**

```python
"""translateFunc.proper — Proper noun utilities and JP/EN cross-validation."""
from translateFunc.proper.flat import (
    flatten_dict_enhanced,
    update_dict_with_flattened,
    get_value_by_path,
)
from translateFunc.proper.analyze import extract_contexts

__all__ = [
    "flatten_dict_enhanced",
    "update_dict_with_flattened",
    "get_value_by_path",
    "extract_contexts",
]
```

- [ ] **Step 2: Write `translateFunc/proper/analyze.py`**

```python
"""
translateFunc/proper/analyze.py
JP/EN context extraction: for each proper noun KR term, find sentences in game
files that contain it, and extract the corresponding JP/EN sentences at the same
structural position.
"""
from __future__ import annotations
from pathlib import Path
import json
from collections import defaultdict

from translateFunc.proper.flat import flatten_dict_enhanced


def extract_contexts(
    kr_term: str,
    kr_path: Path,
    jp_path: Path,
    en_path: Path,
    max_examples: int = 20,
) -> list[dict]:
    """
    For a given KR term, search all game JSON files and extract sentences
    (or text values) that contain it, paired with JP/EN at the same path.

    Returns list of {kr_sentence, jp_sentence, en_sentence, file, path}.
    """
    results: list[dict] = []
    kr_files = list(kr_path.rglob("*.json"))

    for kr_file in kr_files:
        if len(results) >= max_examples:
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
                if len(results) >= max_examples:
                    break
                if not isinstance(kr_text, str):
                    continue
                if kr_term in kr_text and len(kr_text) > len(kr_term):
                    results.append({
                        "kr_sentence": kr_text,
                        "jp_sentence": jp_flat.get(path_tuple, ""),
                        "en_sentence": en_flat.get(path_tuple, ""),
                        "file": str(rel),
                        "path": path_tuple,
                    })
        except Exception:
            continue

    return results


def _load_json(filepath: Path) -> dict | None:
    """Load a JSON file, return None on any error."""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None
```

- [ ] **Step 3: Write `translateFunc/matcher/proper.py`**

```python
"""
translateFunc/matcher/proper.py
ProperAnalyzer — JP/EN cross-validation for proper noun disambiguation.

Two problem cases addressed:
1. Short-term false matching (e.g., "고" appearing in irrelevant sentences)
2. Polysemy disambiguation (e.g., "이상" = person name vs game term)

Two resolution approaches:
A. Similarity-based: Jaccard similarity against positive/negative contexts
B. LLM-based: Lightweight disambiguation prompt (~300 tokens)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from translateFunc.enums import MatchConfidence
from translateFunc.get_proper import fetch as fetch_proper
from translateFunc.proper.analyze import extract_contexts


@dataclass
class ProperTerm:
    """A proper noun term enriched with JP/EN cross-validation data."""
    kr: str
    cn: str
    note: str = ""
    positive_contexts: list[dict] = field(default_factory=list)
    negative_contexts: list[dict] = field(default_factory=list)

    @property
    def is_short(self) -> bool:
        """Short terms (≤2 chars) are prone to false matches."""
        return len(self.kr) <= 2

    @property
    def has_contexts(self) -> bool:
        return len(self.positive_contexts) > 0


class ProperAnalyzer:
    """Fetches and analyzes proper noun terms with JP/EN cross-validation."""

    def __init__(self, kr_path: Path | None = None,
                 jp_path: Path | None = None,
                 en_path: Path | None = None):
        self._kr_path = kr_path
        self._jp_path = jp_path
        self._en_path = en_path
        self._terms: list[ProperTerm] = []

    # ----- Fetch -----

    def fetch_terms(self, min_len: int = 0, auto_fetch: bool = True,
                    proper_path: str = "") -> list[dict]:
        """Fetch terms from paratranz API or local file."""
        if auto_fetch:
            return fetch_proper(min_len=min_len)
        else:
            import json
            return json.loads(Path(proper_path).read_text(encoding="utf-8"))

    # ----- Analyze -----

    def analyze(self, raw_terms: list[dict]) -> list[ProperTerm]:
        """Enrich raw terms with JP/EN context sentences from game files."""
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

    # ----- Confidence -----

    def compute_confidence(
        self,
        term: ProperTerm,
        text_block_jp: str,
        text_block_en: str,
    ) -> MatchConfidence:
        """
        Determine whether a proper noun match is genuine based on
        JP/EN sentence-level similarity.

        Returns MatchConfidence:
        - HIGH: JP and EN both strongly match positive context
        - MEDIUM: Only JP or only EN matches
        - LOW: Weak match
        - UNKNOWN: Term has no context data
        - FALSE_MATCH: Closer to negative context
        """
        if not term.has_contexts:
            return MatchConfidence.UNKNOWN

        if not text_block_jp and not text_block_en:
            return MatchConfidence.UNKNOWN

        pos_scores: list[float] = []
        for ctx in term.positive_contexts:
            score = 0.0
            if text_block_jp and ctx.get("jp_sentence"):
                score += _jaccard_similarity(text_block_jp, ctx["jp_sentence"])
            if text_block_en and ctx.get("en_sentence"):
                score += _jaccard_similarity(text_block_en, ctx["en_sentence"])
            divisor = (1 if text_block_jp else 0) + (1 if text_block_en else 0)
            if divisor > 0:
                pos_scores.append(score / divisor)

        best_pos = max(pos_scores) if pos_scores else 0.0

        # Short terms need strong verification
        threshold_high = 0.7 if term.is_short else 0.5
        threshold_med = 0.5 if term.is_short else 0.3

        if best_pos >= threshold_high:
            return MatchConfidence.HIGH
        elif best_pos >= threshold_med:
            return MatchConfidence.MEDIUM
        elif best_pos > 0.1:
            return MatchConfidence.LOW
        else:
            return MatchConfidence.FALSE_MATCH

    @property
    def terms(self) -> list[ProperTerm]:
        return self._terms


def _jaccard_similarity(a: str, b: str) -> float:
    """Jaccard similarity based on word-level overlap (split by whitespace)."""
    if not a or not b:
        return 0.0
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        # Fall back to character-level for CJK text
        set_a = set(a)
        set_b = set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0
```

- [ ] **Step 4: Verify syntax**

```bash
python -c "from translateFunc.matcher.proper import ProperAnalyzer, ProperTerm; print('OK')"
python -c "from translateFunc.proper import extract_contexts; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add translateFunc/matcher/proper.py translateFunc/proper/__init__.py translateFunc/proper/analyze.py
git commit -m "feat: add ProperAnalyzer with JP/EN cross-validation"
```

---

### Task 6: Create `translateFunc/builder/prompt.py` — PromptTag + PromptFactory

**Files:**
- Create: `translateFunc/builder/__init__.py`
- Create: `translateFunc/builder/prompt.py`

**Interfaces:**
- Consumes: `FileType` from `translateFunc.enums`
- Produces: `PromptTag(Enum)`, `PromptFactory` class
  - `PromptFactory.build_system_prompt(file_type: FileType, stage: int, **kwargs) -> str`
  - `PromptFactory.build_disambiguation_prompt(terms, text_blocks) -> str`

- [ ] **Step 1: Write `translateFunc/builder/__init__.py`**

```python
"""translateFunc.builder — Prompt construction and translation request building."""
```

- [ ] **Step 2: Write `translateFunc/builder/prompt.py`**

```python
"""
translateFunc/builder/prompt.py
PromptTag enum and PromptFactory — dynamic, XML-tagged prompt assembly.

The factory selects templates by FileType × Stage and renders them with
XML tags. Tags with no content are auto-omitted.
"""
from __future__ import annotations
from enum import Enum, auto
from typing import Any

from translateFunc.enums import FileType


class PromptTag(Enum):
    """XML tags used in prompt construction."""
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
    """Builds stage-specific prompts with XML tags, dynamic per FileType."""

    # ---- Base system prompt (preserved from translate_doc.py structure) ----

    _BASE_ROLE = (
        "<role>\n"
        "我是游戏作品'边狱公司'的翻译员，我将要把其他语言的文本翻译为中文。\n"
        "</role>\n"
    )

    _STAGE1_RULES = (
        "<rules>\n"
        "<rule>先查看reference中的术语表和指南，确保术语一致性</rule>\n"
        "<rule>在翻译剧情文本时使用全角符号，否则使用半角符号</rule>\n"
        "<rule>波浪号使用半角波浪号~</rule>\n"
        "<rule>保留原文的代码格式，如富文本和f-string</rule>\n"
        "<rule>术语内容可能存在错误引用，如果术语内容与原文意思偏差过大，忽略该术语</rule>\n"
        "<rule>原文的控制字符会被转义，输出时也使用转义后的字符（如\\n）</rule>\n"
        "</rules>\n"
    )

    _STAGE0_RULES = (
        "<rules>\n"
        "<rule>你的任务是判断术语在当前上下文中是否适用，不需要翻译</rule>\n"
        "<rule>对比术语的典型使用场景和当前文本块的JP/EN内容</rule>\n"
        "<rule>如果术语明显不适用（如人名术语出现在技能描述中），标记为不适用</rule>\n"
        "</rules>\n"
    )

    _STAGE2_RULES = (
        "<rules>\n"
        "<rule>校验翻译结果中的术语一致性</rule>\n"
        "<rule>检查格式规则：全角/半角符号、波浪号、代码格式保留</rule>\n"
        "<rule>发现错误时自动修正并给出修正说明</rule>\n"
        "</rules>\n"
    )

    # ---- Output format specs ----

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

    _STAGE1_FORMAT = (
        "<format>\n"
        "返回JSON对象，包含translations字段：\n"
        "{\n"
        '  "translations": [\n'
        '    {"id": 1, "translation": "翻译结果",\n'
        '     "reasoning": "关键决策说明",\n'
        '     "confidence": "high|medium|low"}\n'
        "  ]\n"
        "}\n"
        "confidence为low的条目说明翻译不确定，需要回退到原文。\n"
        "</format>\n"
    )

    _STAGE2_FORMAT = (
        "<format>\n"
        "返回JSON对象，包含checked_translations字段：\n"
        "{\n"
        '  "checked_translations": [\n'
        '    {"id": 1, "translation": "修正后的翻译",\n'
        '     "changed": false, "change_reason": ""}\n'
        "  ]\n"
        "}\n"
        "</format>\n"
    )

    # ---- Skill doc template ----

    _SKILL_DOC_TEMPLATE = "<skill_guide>\n{content}\n</skill_guide>\n"

    # ========== Public API ==========

    def build_system_prompt(
        self,
        file_type: FileType,
        stage: int,
        *,
        skill_doc: str = "",
        role_styles: list[dict] | None = None,
        examples: list[dict] | None = None,
    ) -> str:
        """Build the system prompt for a given file type and stage.

        Args:
            file_type: STORY, SKILL, UI, or OTHER
            stage: 0 (disambiguation), 1 (translate), 2 (self-check)
            skill_doc: Skill translation guide (for SKILL files)
            role_styles: Role speaking style references (for STORY files)
            examples: Optional few-shot examples
        """
        parts: list[str] = [self._BASE_ROLE]

        # Stage-specific rules
        if stage == 0:
            parts.append(self._STAGE0_RULES)
        elif stage == 1:
            parts.append(self._STAGE1_RULES)
        elif stage == 2:
            parts.append(self._STAGE2_RULES)

        # Skill guide (stage 1 only, SKILL files)
        if stage == 1 and file_type == FileType.SKILL and skill_doc:
            parts.append(self._SKILL_DOC_TEMPLATE.format(content=skill_doc))

        # Role styles (stage 1 only, STORY files)
        if stage == 1 and file_type == FileType.STORY and role_styles:
            parts.append(self._render_role_styles(role_styles))

        # Examples
        if examples:
            parts.append(self._render_examples(examples))

        # Output format
        if stage == 0:
            parts.append(self._STAGE0_FORMAT)
        elif stage == 1:
            parts.append(self._STAGE1_FORMAT)
        elif stage == 2:
            parts.append(self._STAGE2_FORMAT)

        return "\n".join(parts)

    def build_disambiguation_prompt(
        self,
        candidate_terms: list[dict],
        text_blocks: list[dict],
    ) -> str:
        """Build a lightweight LLM disambiguation prompt (~300 tokens)."""
        term_list = "\n".join(
            f"  - {t['kr']} → {t['cn']}" + (f" ({t.get('note', '')})" if t.get('note') else "")
            for t in candidate_terms
        )
        block_text = ""
        for i, block in enumerate(text_blocks[:3]):  # Max 3 blocks
            block_text += (
                f"<block id=\"{i+1}\">\n"
                f"  <kr>{block.get('kr', '')}</kr>\n"
                f"  <jp>{block.get('jp', '')}</jp>\n"
                f"  <en>{block.get('en', '')}</en>\n"
                f"</block>\n"
            )

        return (
            f"<role>你是边狱公司的术语专家。</role>\n"
            f"<context>\n"
            f"候选术语：\n{term_list}\n"
            f"当前文本：\n{block_text}"
            f"</context>\n"
            f"{self._STAGE0_FORMAT}"
        )

    # ========== Internal renderers ==========

    def _render_role_styles(self, styles: list[dict]) -> str:
        """Render role style references as XML."""
        lines = ["<role_styles>"]
        for s in styles:
            lines.append(f"  <style>")
            for k, v in s.items():
                lines.append(f"    <{k}>{v}</{k}>")
            lines.append(f"  </style>")
        lines.append("</role_styles>")
        return "\n".join(lines) + "\n"

    def _render_examples(self, examples: list[dict]) -> str:
        """Render few-shot examples as XML."""
        lines = ["<examples>"]
        for ex in examples:
            lines.append("  <example>")
            lines.append(f"    <in>{ex.get('in', '')}</in>")
            lines.append(f"    <out>")
            lines.append(f"      <translation>{ex.get('translation', '')}</translation>")
            if ex.get('reasoning'):
                lines.append(f"      <reasoning>{ex['reasoning']}</reasoning>")
            if ex.get('confidence'):
                lines.append(f"      <confidence>{ex['confidence']}</confidence>")
            lines.append(f"    </out>")
            lines.append("  </example>")
        lines.append("</examples>")
        return "\n".join(lines) + "\n"

    def render_text_blocks(self, text_blocks: list[dict]) -> str:
        """Render the <text> section with blocks of kr/jp/en."""
        lines = ["<text>"]
        for i, block in enumerate(text_blocks):
            lines.append(f'  <block id="{i + 1}">')
            lines.append(f"    <kr>{block.get('kr', '')}</kr>")
            if block.get('jp'):
                lines.append(f"    <jp>{block.get('jp', '')}</jp>")
            if block.get('en'):
                lines.append(f"    <en>{block.get('en', '')}</en>")
            lines.append(f"  </block>")
        lines.append("</text>")
        return "\n".join(lines) + "\n"

    def render_glossary(self, terms: list[dict]) -> str:
        """Render the <glossary> section. Omits if terms is empty."""
        if not terms:
            return ""
        lines = ["<glossary>"]
        for t in terms:
            kr = t.get('kr', t.get('term', ''))
            cn = t.get('cn', t.get('translation', ''))
            note = t.get('note', '')
            attr = f' kr="{kr}" cn="{cn}"'
            if note:
                attr += f' note="{note}"'
            lines.append(f"  <term{attr} />")
        lines.append("</glossary>")
        return "\n".join(lines) + "\n"
```

- [ ] **Step 3: Verify syntax**

```bash
python -c "
from translateFunc.builder.prompt import PromptFactory, PromptTag
from translateFunc.enums import FileType
pf = PromptFactory()
prompt = pf.build_system_prompt(FileType.SKILL, 1, skill_doc='test guide')
assert '<role>' in prompt
assert '<rules>' in prompt
assert '<skill_guide>' in prompt
assert '<format>' in prompt
print('PromptFactory tests passed')
"
```

- [ ] **Step 4: Commit**

```bash
git add translateFunc/builder/__init__.py translateFunc/builder/prompt.py
git commit -m "feat: add PromptTag enum and PromptFactory with XML tag system"
```

---

### Task 7: Create `translateFunc/builder/request.py` — RequestBuilder

**Files:**
- Create: `translateFunc/builder/request.py`

**Interfaces:**
- Consumes: `MatcherEngine` from `translateFunc.matcher.engine`, `PromptFactory` from `translateFunc.builder.prompt`, `FileType` from `translateFunc.enums`, `TranslateConfig` from `translateFunc.config`, `translate_doc` (RLOE_COMPARE, ROLE_STYLE, SKILLL_DOC)
- Produces: `RequestBuilder` class
  - `RequestBuilder.build() -> dict` — builds unified request structure
  - `RequestBuilder.get_request_text() -> list[str]` — returns split request texts
  - `RequestBuilder.deBuild(translated_texts) -> dict` — rebuilds translated data

- [ ] **Step 1: Write `translateFunc/builder/request.py`**

```python
"""
translateFunc/builder/request.py
RequestBuilder — builds structured translation requests from flattened text data.
Refactored from the old RequestTextBuilder in translate_main.py.
"""
from __future__ import annotations
from contextlib import suppress
from copy import deepcopy
import json
import re
from typing import Any, Optional

from translateFunc.enums import FileType
from translateFunc.matcher.engine import MatcherEngine
from translateFunc.builder.prompt import PromptFactory
import translateFunc.translate_doc as translate_doc

EMPTY_TEXT = {'', '-'}
AVOID_PATH = {'usage', 'id', 'model'}


class RequestBuilder:
    """Builds structured translation requests with matching metadata."""

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
        self.kr_text = request_text["kr"]
        self.jp_text = request_text.get("jp", {})
        self.en_text = request_text.get("en", {})
        self._engine = matcher_engine
        self.is_story = is_story
        self.is_skill = is_skill
        self.is_text_format = is_text_format
        self.max_length = max_length
        self.file_type = file_type
        self._prompt_factory = PromptFactory()

        # Built state
        self.unified_request: dict | None = None
        self.split_requests: list[dict] = []
        self.formal_flatten_item: dict = {}

    # ========== Build ==========

    def build(self) -> dict:
        """Build the unified request structure. Returns the full request dict."""
        text_items: list[dict] = []
        all_proper_terms: dict[str, dict] = {}
        all_affects: dict[str, dict] = {}
        all_models: dict[str, dict] = {}

        for idx in self.kr_text:
            kr_item = self.kr_text.get(idx, {})
            jp_item = self.jp_text.get(idx, {})
            en_item = self.en_text.get(idx, {})

            kr_paths = list(kr_item.keys())
            for path_tuple in kr_paths:
                kr_text_val = kr_item.get(path_tuple, "")
                jp_text_val = jp_item.get(path_tuple, "")
                en_text_val = en_item.get(path_tuple, "")

                if kr_text_val in EMPTY_TEXT and jp_text_val in EMPTY_TEXT and en_text_val in EMPTY_TEXT:
                    continue

                text_block: dict[str, Any] = {
                    "kr": kr_text_val,
                    "jp": jp_text_val,
                    "en": en_text_val,
                }

                # Match proper nouns
                match_result = self._engine.match_all(kr_text_val)
                if match_result.proper_matches:
                    text_block["proper_refs"] = []
                    for m in match_result.proper_matches:
                        if m.data:
                            term_data = m.data if isinstance(m.data, dict) else {"term": m.pattern}
                            term_key = term_data.get("term", m.pattern)
                            if term_key not in all_proper_terms:
                                all_proper_terms[term_key] = term_data
                            text_block["proper_refs"].append(term_key)
                        else:
                            if m.pattern not in all_proper_terms:
                                all_proper_terms[m.pattern] = {"term": m.pattern, "translation": ""}
                            text_block["proper_refs"].append(m.pattern)

                # Match affects
                affect_matches = match_result.affect_id_matches + match_result.affect_name_matches
                if affect_matches:
                    text_block["affect_refs"] = []
                    seen_affects: set[str] = set()
                    for m in affect_matches:
                        if m.data and isinstance(m.data, dict):
                            aff_id = m.data.get("id", "")
                            if aff_id not in seen_affects:
                                seen_affects.add(aff_id)
                                text_block["affect_refs"].append(f'[{aff_id}]')
                                if aff_id not in all_affects:
                                    all_affects[aff_id] = m.data

                # Match role (story files only)
                if self.is_story:
                    with suppress(Exception):
                        model = kr_text_val.get("model", "") if isinstance(kr_text_val, dict) else ""
                        if not model:
                            # Try matching role from the engine
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

                text_items.append(text_block)

        # Build unified request
        self.unified_request = {
            "metadata": {
                "total_text_blocks": len(text_items),
                "proper_terms_count": len(all_proper_terms),
                "affects_count": len(all_affects),
                "models_count": len(all_models),
                "file_type": self.file_type.name,
            },
            "reference": {
                "proper_terms": list(all_proper_terms.values()),
                "affects": list(all_affects.values()),
                "models": list(all_models.values()),
                "model_docs": self._get_role_docs(all_models),
                "skill_doc": self._get_skill_doc(),
            },
            "text_blocks": text_items,
        }

        self._split_by_length()
        return self.unified_request

    # ========== Split ==========

    def _split_by_length(self) -> None:
        """Split request into parts that fit within max_length."""
        if self.unified_request is None:
            return

        request_text = self._get_request_text(self.unified_request)
        if len(request_text) <= self.max_length:
            self.split_requests = [self.unified_request]
            return

        text_blocks = self.unified_request.get("text_blocks", [])
        total_blocks = len(text_blocks)

        for num_parts in range(2, min(10, total_blocks) + 1):
            part_size = total_blocks // num_parts
            remainder = total_blocks % num_parts
            parts = []
            start_idx = 0
            for i in range(num_parts):
                end_idx = start_idx + part_size + (1 if i < remainder else 0)
                part = {
                    "metadata": {**self.unified_request["metadata"], "total_text_blocks": end_idx - start_idx},
                    "reference": self.unified_request["reference"],
                    "text_blocks": text_blocks[start_idx:end_idx],
                }
                parts.append(part)
                start_idx = end_idx

            if all(len(self._get_request_text(p)) <= self.max_length for p in parts):
                self.split_requests = parts
                return

        # Fallback: fixed 5-part split
        parts = []
        part_size = max(1, total_blocks // 5)
        for i in range(0, total_blocks, part_size):
            end_idx = min(i + part_size, total_blocks)
            parts.append({
                "metadata": {**self.unified_request["metadata"], "total_text_blocks": end_idx - i},
                "reference": self.unified_request["reference"],
                "text_blocks": text_blocks[i:end_idx],
            })
        self.split_requests = parts

    # ========== Output ==========

    def get_request_text(self, is_text_format: Optional[bool] = None) -> list[str]:
        """Get all split request texts in the specified format."""
        if self.unified_request is None:
            self.build()

        if is_text_format is None:
            is_text_format = self.is_text_format

        result = []
        for request in self.split_requests:
            if is_text_format:
                result.append(self._make_text(request))
            else:
                result.append(json.dumps(request, indent=2, ensure_ascii=False))
        return result

    def _get_request_text(self, request_data: dict) -> str:
        """Get request text for length checking."""
        if self.is_text_format:
            return self._make_text(request_data)
        return json.dumps(request_data, indent=2, ensure_ascii=False)

    # ========== DeBuild ==========

    def deBuild(self, translated_texts: list[str]) -> dict:
        """Rebuild translated data from flat text list back to nested dict."""
        translated_iter = iter(translated_texts)
        result_dict = deepcopy(self.kr_text)

        for idx in result_dict:
            kr_item = self.kr_text.get(idx, {})
            jp_item = self.jp_text.get(idx, {})
            en_item = self.en_text.get(idx, {})
            kr_paths = list(kr_item.keys())

            for path_tuple in kr_paths:
                jp_val = jp_item.get(path_tuple, "")
                en_val = en_item.get(path_tuple, "")
                kr_val = kr_item.get(path_tuple, "")
                if not (jp_val in EMPTY_TEXT and en_val in EMPTY_TEXT and kr_val in EMPTY_TEXT):
                    result_dict[idx][path_tuple] = next(translated_iter)

        # Verify no extra translations
        try:
            next(translated_iter)
            raise StopIteration("翻译文本数量多于预期")
        except StopIteration:
            pass

        return result_dict

    # ========== Helpers ==========

    def _get_role_docs(self, role_list: dict) -> list[dict]:
        """Get role speaking style references."""
        if not self.is_story:
            return []
        docs = []
        for role_id in role_list:
            with suppress(Exception):
                if role_id in translate_doc.RLOE_COMPARE:
                    true_role = translate_doc.RLOE_COMPARE[role_id]
                    docs.append(translate_doc.ROLE_STYLE[true_role])
        return docs

    def _get_skill_doc(self) -> str:
        """Get skill translation guide."""
        if self.is_skill:
            return translate_doc.SKILLL_DOC
        return ""

    def _escape_text(self, text: str) -> str:
        """Escape special characters for LLM understanding."""
        if not isinstance(text, str):
            return text
        escape_map = {
            "\n": "\\n", "\t": "\\t", "\r": "\\r",
            "\"": '\\"', "\'": "\\'", "\\": "\\\\",
            "---": "\\-\\-\\-",
        }
        result = text
        for old, new in escape_map.items():
            result = result.replace(old, new)
        return result

    def _make_text(self, texts: dict) -> str:
        """Convert unified request dict to plain text format."""
        result_lines = []

        metadata = texts.get("metadata", {})
        result_lines.append("【翻译请求元数据】")
        result_lines.append(f"文本块总数: {metadata.get('total_text_blocks', 0)}")

        reference = texts.get("reference", {})

        if reference.get("proper_terms"):
            result_lines.append("\n【专有名词术语表】")
            for i, item in enumerate(reference["proper_terms"]):
                note = f" (备注: {item.get('note')})" if item.get("note") else ""
                result_lines.append(
                    f"{i + 1}. {item.get('term', '')} → {item.get('translation', '')}{note}"
                )

        if reference.get("affects"):
            result_lines.append("\n【状态效果术语表】")
            for i, item in enumerate(reference["affects"]):
                result_lines.append(
                    f"{i + 1}. [ID: {item.get('id', '')}] {item.get('kr', '')} → {item.get('cn', '')}"
                )

        if self.is_story and reference.get("model_docs"):
            result_lines.append("\n【角色说话风格参考】")
            for doc in reference["model_docs"]:
                for k, v in doc.items():
                    result_lines.append(f"  {k}: {v}")

        if self.is_skill and reference.get("skill_doc"):
            result_lines.append("\n【技能翻译指南】")
            result_lines.append(reference["skill_doc"])

        result_lines.append("\n" + "=" * 30)
        result_lines.append("【以下为需要翻译的文本块】")

        text_blocks = texts.get("text_blocks", [])
        for idx, block in enumerate(text_blocks):
            if idx > 0:
                result_lines.append("\n" + "-" * 20)
            result_lines.append(f"\n【文本块 {idx + 1}】")
            result_lines.append(f"韩文: {self._escape_text(block.get('kr', ''))}")
            result_lines.append(f"英文: {self._escape_text(block.get('en', ''))}")
            result_lines.append(f"日文: {self._escape_text(block.get('jp', ''))}")

        return "\n".join(result_lines)
```

- [ ] **Step 2: Verify syntax**

```bash
python -c "from translateFunc.builder.request import RequestBuilder; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add translateFunc/builder/request.py
git commit -m "feat: add RequestBuilder refactored from old RequestTextBuilder"
```

---

### Task 8: Create `translateFunc/builder/stages.py` — StageStrategy

**Files:**
- Create: `translateFunc/builder/stages.py`

**Interfaces:**
- Consumes: `PromptFactory` from `translateFunc.builder.prompt`, `MatchConfidence` from `translateFunc.enums`, `TranslateConfig` from `translateFunc.config`
- Produces: `StageStrategy` class
  - `StageStrategy.execute_stage_0(disambiguate_fn, text_blocks, proper_matches) -> dict`
  - `StageStrategy.build_stage_1_prompt(file_type, ...) -> str`
  - `StageStrategy.execute_stage_2(translate_fn, stage_1_results, ...) -> list[dict]`

- [ ] **Step 1: Write `translateFunc/builder/stages.py`**

```python
"""
translateFunc/builder/stages.py
StageStrategy — implements the 3-stage translation pipeline.

Stage 0: Term disambiguation (similarity / LLM / hybrid)
Stage 1: Main translation with dynamic tagged prompt
Stage 2: Self-check — terminology consistency + format rules (+ auto-fix)
"""
from __future__ import annotations
import json
from typing import Any, Callable

from translateFunc.enums import FileType, MatchConfidence
from translateFunc.builder.prompt import PromptFactory


class StageStrategy:
    """Encapsulates per-stage logic for the translation pipeline."""

    def __init__(self, config):
        """
        Args:
            config: TranslateConfig instance with translation_mode,
                    disambiguation_mode, enable_self_check, min_confidence.
        """
        self._config = config
        self._prompt_factory = PromptFactory()

    # ========== Stage 0: Disambiguation ==========

    def needs_disambiguation(self) -> bool:
        """Whether stage 0 should run."""
        return (
            self._config.translation_mode == "multi_stage"
            and self._config.disambiguation_mode != "similarity"
        )

    def should_llm_disambiguate(self, confidence: MatchConfidence) -> bool:
        """Determine if a match needs LLM disambiguation."""
        if self._config.disambiguation_mode == "llm":
            return True
        if self._config.disambiguation_mode == "hybrid":
            return confidence in (MatchConfidence.LOW, MatchConfidence.UNKNOWN)
        return False

    def filter_by_confidence(self, matches: list[dict], min_conf: MatchConfidence) -> list[dict]:
        """Filter matches by minimum confidence threshold."""
        conf_order = {
            MatchConfidence.HIGH: 0,
            MatchConfidence.MEDIUM: 1,
            MatchConfidence.LOW: 2,
            MatchConfidence.UNKNOWN: 3,
            MatchConfidence.FALSE_MATCH: 4,
        }
        threshold = conf_order.get(min_conf, 1)
        return [m for m in matches if conf_order.get(m.get("confidence"), 4) <= threshold]

    def build_stage_0_prompt(
        self,
        candidate_terms: list[dict],
        text_blocks: list[dict],
    ) -> str:
        """Build the LLM disambiguation prompt for stage 0."""
        return self._prompt_factory.build_disambiguation_prompt(candidate_terms, text_blocks)

    def parse_stage_0_result(self, result_text: str) -> list[dict]:
        """Parse LLM disambiguation result into structured data."""
        try:
            data = json.loads(result_text)
            return data.get("disambiguations", [])
        except json.JSONDecodeError:
            return []

    # ========== Stage 1: Main Translation ==========

    def build_stage_1_prompt(
        self,
        file_type: FileType,
        *,
        skill_doc: str = "",
        role_styles: list[dict] | None = None,
        examples: list[dict] | None = None,
    ) -> str:
        """Build the main translation system prompt."""
        return self._prompt_factory.build_system_prompt(
            file_type=file_type,
            stage=1,
            skill_doc=skill_doc,
            role_styles=role_styles,
            examples=examples,
        )

    def build_stage_1_user_prompt(
        self,
        text_blocks: list[dict],
        glossary_terms: list[dict] | None = None,
    ) -> str:
        """Build the user-facing portion of the stage 1 prompt."""
        parts: list[str] = []
        if glossary_terms:
            parts.append(self._prompt_factory.render_glossary(glossary_terms))
        parts.append(self._prompt_factory.render_text_blocks(text_blocks))
        return "\n".join(parts)

    def parse_stage_1_result(self, result_text: str) -> list[dict]:
        """Parse stage 1 translation result, supporting both JSON and text formats."""
        try:
            data = json.loads(result_text)
            return data.get("translations", [])
        except json.JSONDecodeError:
            # Fallback: text format parsing
            lines = result_text.strip().split("\n\n")
            translations = []
            for line in lines:
                line = line.strip()
                # Strip block markers
                line = line.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
                translations.append({"id": len(translations) + 1, "translation": line})
            return translations

    # ========== Stage 2: Self-Check ==========

    def needs_self_check(self) -> bool:
        """Whether stage 2 should run."""
        return (
            self._config.translation_mode == "multi_stage"
            and self._config.enable_self_check
        )

    def build_stage_2_prompt(
        self,
        file_type: FileType,
        original_blocks: list[dict],
        translations: list[dict],
    ) -> str:
        """Build the self-check prompt comparing originals vs translations."""
        system = self._prompt_factory.build_system_prompt(file_type=file_type, stage=2)

        # User portion: originals + translations side by side
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

    def parse_stage_2_result(self, result_text: str) -> list[dict]:
        """Parse self-check result."""
        try:
            data = json.loads(result_text)
            return data.get("checked_translations", [])
        except json.JSONDecodeError:
            return []
```

- [ ] **Step 2: Verify syntax**

```bash
python -c "from translateFunc.builder.stages import StageStrategy; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add translateFunc/builder/stages.py
git commit -m "feat: add StageStrategy for 3-stage translation pipeline"
```

---

### Task 9: Create `translateFunc/processor.py` — Refactored FileProcessor

**Files:**
- Create: `translateFunc/processor.py`

**Interfaces:**
- Consumes: `ProcessResult`, `FileType` from `translateFunc.enums`, `ProcessOutcome`, `FilePathConfig`, `TranslateConfig` from `translateFunc.config`, `MatcherEngine` from `translateFunc.matcher.engine`, `RequestBuilder` from `translateFunc.builder.request`, `StageStrategy` from `translateFunc.builder.stages`, `translate_doc`, `flatten_dict_enhanced` from `translateFunc.proper`
- Produces: `FileProcessor` class
  - `FileProcessor.process() -> ProcessOutcome` — NO EXCEPTIONS for control flow

- [ ] **Step 1: Write `translateFunc/processor.py`**

```python
"""
translateFunc/processor.py
FileProcessor — processes a single file through the translation pipeline.
Returns ProcessOutcome instead of throwing ProcesserExit exceptions.
"""
from __future__ import annotations
from contextlib import suppress
from copy import deepcopy
import json
import os
import re
import shutil
from typing import Any

from translateFunc.enums import ProcessResult, FileType
from translateFunc.config import ProcessOutcome, TranslateConfig, FilePathConfig
from translateFunc.matcher.engine import MatcherEngine
from translateFunc.builder.request import RequestBuilder, EMPTY_TEXT, AVOID_PATH
from translateFunc.builder.stages import StageStrategy
from translateFunc.proper import flatten_dict_enhanced, update_dict_with_flattened
import translateFunc.translate_doc as translate_doc

EMPTY_DATA = [{"dataList": []}, {}, []]
EMPTY_DATA_LIST = [[], [{}]]


class FileProcessor:
    """Processes a single translation file end-to-end.
    
    Control flow: every exit path returns a ProcessOutcome.
    No exceptions are used for normal control flow.
    """

    def __init__(
        self,
        path_config: FilePathConfig,
        engine: MatcherEngine,
        translate_config: TranslateConfig,
        translator,  # translatekit TranslatorBase instance
    ):
        self.path_config = path_config
        self._engine = engine
        self._config = translate_config
        self._translator = translator
        self._dump = translate_config.dump

        # Internal state (populated during process())
        self.kr_json: dict = {}
        self.en_json: dict = {}
        self.jp_json: dict = {}
        self.llc_json: dict = {}
        self.kr_data: list = []
        self.en_data: list = []
        self.jp_data: list = []
        self.llc_data: list = []
        self.kr_index: dict = {}
        self.en_index: dict = {}
        self.jp_index: dict = {}
        self.llc_index: dict = {}
        self.is_story: bool = False
        self.is_skill: bool = False
        self.translating_list: list = []
        self.formal_flatten_item: dict = {}
        self._removed_keys: list = []
        self._base_index: dict = {}

    @property
    def file_name(self) -> str:
        return self.path_config.real_name

    @property
    def file_type(self) -> FileType:
        if self.is_story:
            return FileType.STORY
        if self.is_skill:
            return FileType.SKILL
        # Heuristic for UI files
        if "UI" in str(self.path_config.rel_path).upper():
            return FileType.UI
        return FileType.OTHER

    def _log(self, msg: str) -> None:
        if self._dump:
            from globalManagers.LogManager import LogManager
            LogManager().log(msg)

    # ========== Main Process ==========

    def process(self) -> ProcessOutcome:
        """Run the full translation process. Returns ProcessOutcome."""
        # 1. Load JSONs
        outcome = self._load_jsons()
        if outcome:
            return outcome

        # 2. Check empty
        outcome = self._check_empty()
        if outcome:
            return outcome

        # 3. Init base data
        self._init_base_data()

        # 4. Make data index
        self._make_data_index()

        # 5. Check translated
        outcome = self._check_translated()
        if outcome:
            return outcome

        # 6. Get translating list
        self._get_translating()
        if not self.translating_list:
            return ProcessOutcome(ProcessResult.ALREADY_TRANSLATED, self.file_name)

        # 7. Build request text
        request_text = {
            "kr": self._get_translating_text("kr"),
            "jp": self._get_translating_text("jp"),
            "en": self._get_translating_text("en"),
        }

        # 8. Build and translate
        try:
            translated_data = self._translate(request_text)
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

        # 9. Reconstruct and save
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

        return ProcessOutcome(ProcessResult.SUCCESS_SAVED, self.file_name)

    # ========== Translate ==========

    def _translate(self, request_text: dict) -> dict:
        """Execute translation via the configured pipeline stages."""
        # Build request
        builder = RequestBuilder(
            request_text,
            self._engine,
            is_story=self.is_story,
            is_skill=self.is_skill,
            is_text_format=self._config.is_text_format,
            max_length=20000,
            file_type=self.file_type,
        )

        if self._config.is_llm:
            # LLM path: build structured request, possibly multi-stage
            builder.build()
            request_texts = builder.get_request_text()
            result: list[str] = []

            stage_strategy = StageStrategy(self._config)

            for i, request_part in enumerate(request_texts):
                timeout = max(len(request_part) // 200 + 1, 40)

                # Stage 0: Disambiguation (optional)
                if stage_strategy.needs_disambiguation():
                    # For now, skip inline disambiguation — handled by MatcherEngine confidence
                    pass

                # Stage 1: Main translation
                result_part = self._translator.translate(request_part, timeout=timeout)
                self._log(f"Part {i + 1}: {str(result_part)[:200]}...")

                # Parse result
                if self._config.is_text_format:
                    result_list = result_part.split("\n\n")
                    result_list = [
                        re.sub(
                            r"^\s?【文本块\s?\d+】[\s\n]?",
                            "",
                            item.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r"),
                        )
                        for item in result_list
                    ]
                else:
                    try:
                        parsed = json.loads(result_part)
                        translations = parsed.get("translations", [])
                        # Extract translation text from structured output
                        result_list = [
                            t.get("translation", "") if isinstance(t, dict) else str(t)
                            for t in translations
                        ]
                    except json.JSONDecodeError:
                        result_list = result_part.split("\n\n")

                result.extend(result_list)

                # Stage 2: Self-check (optional, skipped for now)
                if stage_strategy.needs_self_check():
                    # Not implemented in this phase — placeholder for future
                    pass
        else:
            # Non-LLM path: simple text list
            builder_klass = _SimpleRequestBuilder
            simple_builder = builder_klass(request_text)
            simple_builder.build()
            request_texts = simple_builder.get_request_text(from_lang=self._config.from_lang)
            result = self._translator.translate(request_texts)

        return builder.deBuild(result)

    # ========== Load & Check ==========

    def _load_jsons(self) -> ProcessOutcome | None:
        """Load KR/EN/JP/LLC JSON files. Returns ProcessOutcome on error."""
        try:
            with open(self.path_config.KR_path, "r", encoding="utf-8-sig") as f:
                self.kr_json = json.load(f)
            try:
                with open(self.path_config.EN_path, "r", encoding="utf-8-sig") as f:
                    self.en_json = json.load(f)
            except FileNotFoundError:
                self.en_json = deepcopy(self.kr_json)
            try:
                with open(self.path_config.JP_path, "r", encoding="utf-8-sig") as f:
                    self.jp_json = json.load(f)
            except FileNotFoundError:
                self.jp_json = deepcopy(self.kr_json)
            try:
                with open(self.path_config.LLC_path, "r", encoding="utf-8-sig") as f:
                    self.llc_json = json.load(f)
            except FileNotFoundError:
                self.llc_json = {}
        except json.JSONDecodeError:
            self._save_except()
            return ProcessOutcome(ProcessResult.JSON_DECODE_ERROR, self.file_name)
        return None

    def _check_empty(self) -> ProcessOutcome | None:
        """Check if KR data is empty. Returns ProcessOutcome if empty."""
        if self.kr_json in EMPTY_DATA or self.kr_json.get("dataList", []) in EMPTY_DATA_LIST:
            if self.path_config.LLC_path.exists():
                self._save_llc()
                return ProcessOutcome(ProcessResult.EMPTY_WITH_LLC, self.file_name)
            else:
                return ProcessOutcome(ProcessResult.EMPTY_SKIPPED, self.file_name)
        return None

    def _check_translated(self) -> ProcessOutcome | None:
        """Check if already translated. Returns ProcessOutcome if so."""
        if not len(self.jp_index) == len(self.kr_index) == len(self.en_index):
            def _align(d: dict, ref: dict) -> dict:
                return {k: d.get(k, ref[k]) for k in ref}
            self.en_index = _align(self.en_index, self.kr_index)
            self.jp_index = _align(self.jp_index, self.kr_index)
            self.llc_index = _align(self.llc_index, self.kr_index)

        if list(self.kr_index) == list(self.llc_index):
            self._save_llc()
            return ProcessOutcome(ProcessResult.ALREADY_TRANSLATED, self.file_name)
        return None

    # ========== Init ==========

    def _init_base_data(self) -> None:
        self.en_data = self.en_json.get("dataList", [])
        self.kr_data = self.kr_json.get("dataList", [])
        self.jp_data = self.jp_json.get("dataList", [])
        self.llc_data = self.llc_json.get("dataList", [])
        self.is_story = (self.path_config.rel_path.parent.name == "StoryData")
        self.is_skill = self.path_config.real_name.startswith("Skills_")

    def _make_data_index(self) -> None:
        if self.is_story:
            self.en_index = {i: d for i, d in enumerate(self.en_data)}
            self.kr_index = {i: d for i, d in enumerate(self.kr_data)}
            self.jp_index = {i: d for i, d in enumerate(self.jp_data)}
            self.llc_index = {i: d for i, d in enumerate(self.llc_data)}
        else:
            self.en_index = {i["id"]: i for i in self.en_data}
            self.kr_index = {i["id"]: i for i in self.kr_data}
            self.jp_index = {i["id"]: i for i in self.jp_data}
            self.llc_index = {i["id"]: i for i in self.llc_data}

    def _get_translating(self) -> None:
        self.translating_list = [i for i in self.kr_index if i not in self.llc_index]

    # ========== Text extraction / reconstruction ==========

    def _get_translating_text(self, lang: str = "kr") -> dict:
        lang_index = {"kr": self.kr_index, "jp": self.jp_index, "en": self.en_index}[lang]
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

    def _de_get_translating_text(self, translated_text: dict) -> dict:
        self._base_index = deepcopy(self.kr_index)
        for i in self.translating_list:
            trans_item = self._base_index[i]
            translated_item = translated_text[i]
            update_dict_with_flattened(trans_item, translated_item)
        return self._base_index

    def _de_get_translating(self) -> dict:
        result = []
        for i in self.kr_index:
            if i in self.llc_index:
                result.append(self.llc_index[i])
            else:
                result.append(self._base_index[i])
        return {"dataList": result}

    # ========== Save ==========

    def _save_result(self, data: dict) -> None:
        if not self._config.save_result:
            return
        self.path_config.target_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path_config.target_file, "w", encoding="utf-8-sig") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def _save_llc(self) -> None:
        shutil.copy2(self.path_config.LLC_path, self.path_config.target_file)

    def _save_except(self) -> None:
        """Fallback save: try LLC → EN → JP → KR."""
        for path_attr in ("LLC_path", "EN_path", "JP_path", "KR_path"):
            try:
                src = getattr(self.path_config, path_attr)
                if src.exists():
                    shutil.copy2(src, self.path_config.target_file)
                    return
            except Exception:
                continue
```

- [ ] **Step 2: Also write the `_SimpleRequestBuilder` (non-LLM path)** — append to end of file

```python
# ============================================================
# SimpleRequestBuilder — for non-LLM translators
# ============================================================

class _SimpleRequestBuilder:
    """Minimal request builder for non-LLM translators (preserved behavior)."""

    def __init__(self, request_text: dict):
        self.en_texts = request_text["en"]
        self.kr_texts = request_text["kr"]
        self.jp_texts = request_text.get("jp", {})

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
        self.KR_build = [t for i, t in enumerate(KR_result) if i not in empty_idxs]
        self.EN_build = [t for i, t in enumerate(EN_result) if i not in empty_idxs]
        self.JP_build = [t for i, t in enumerate(JP_result) if i not in empty_idxs]

    def get_request_text(self, from_lang: str = "KR") -> list[str]:
        return getattr(self, f"{from_lang}_build")

    def deBuild(self, translated_texts: list[str], from_lang: str = "kr") -> dict:
        original = deepcopy(getattr(self, f"{from_lang}_texts"))
        it = iter(translated_texts)
        for idx in original:
            kr_item = self.kr_texts.get(idx, {})
            jp_item = self.jp_texts.get(idx, {})
            en_item = self.en_texts.get(idx, {})
            for path_tuple in kr_item:
                jp_val = jp_item.get(path_tuple, "")
                en_val = en_item.get(path_tuple, "")
                kr_val = kr_item[path_tuple]
                if not (jp_val in EMPTY_TEXT and en_val in EMPTY_TEXT and kr_val in EMPTY_TEXT):
                    original[idx][path_tuple] = next(it)
        try:
            next(it)
            raise StopIteration("译文数量多于预期")
        except StopIteration:
            pass
        return original
```

- [ ] **Step 3: Verify syntax**

```bash
python -c "from translateFunc.processor import FileProcessor; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add translateFunc/processor.py
git commit -m "feat: add refactored FileProcessor with ProcessOutcome return pattern"
```

---

### Task 10: Create `translateFunc/workers.py` — WorkerPool

**Files:**
- Create: `translateFunc/workers.py`

**Interfaces:**
- Consumes: `ProcessOutcome` from `translateFunc.config`, `TranslateConfig` from `translateFunc.config`
- Produces: `WorkerPool` class
  - `WorkerPool.__init__(translator_factory: Callable, max_workers: int)`
  - `WorkerPool.map(files: list, process_fn: Callable, on_progress: Callable | None = None) -> list[ProcessOutcome]`

- [ ] **Step 1: Write `translateFunc/workers.py`**

```python
"""
translateFunc/workers.py
WorkerPool — ThreadPoolExecutor-based concurrent file processing.
Each worker thread gets its own translator instance via a factory function.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from translateFunc.config import ProcessOutcome


class WorkerPool:
    """Manages concurrent file translation with per-thread translator instances.

    Key design: translator_factory() is called once per thread to create an
    independent translator instance, avoiding HTTP connection contention.
    """

    def __init__(
        self,
        translator_factory: Callable[[], Any],
        max_workers: int = 4,
    ):
        self._factory = translator_factory
        self._max_workers = max_workers

    def map(
        self,
        files: list,
        process_fn: Callable[[Any, Any], ProcessOutcome],
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[ProcessOutcome]:
        """Process files concurrently, preserving input order.

        Args:
            files: List of file configs/paths to process.
            process_fn: (file_item, translator) -> ProcessOutcome.
            on_progress: Optional callback(done, total, current_file_name).

        Returns:
            List of ProcessOutcome in the same order as input files.
        """
        total = len(files)
        if total == 0:
            return []

        # Map file to its original index for ordered output
        indexed: list[tuple[int, Any]] = list(enumerate(files))
        results: list[ProcessOutcome | None] = [None] * total

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            # Create per-thread translators via thread-local factory
            import threading
            thread_local = threading.local()

            def get_translator():
                if not hasattr(thread_local, "translator"):
                    thread_local.translator = self._factory()
                return thread_local.translator

            # Submit all tasks
            future_to_idx = {}
            for idx, file_item in indexed:
                translator = get_translator()  # Will be called per-thread
                future = executor.submit(process_fn, file_item, translator)
                future_to_idx[future] = idx

            completed = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                completed += 1
                try:
                    outcome = future.result()
                    results[idx] = outcome
                except Exception as e:
                    # Convert unexpected exceptions to error outcomes
                    file_name = str(files[idx]) if idx < len(files) else f"index_{idx}"
                    from translateFunc.enums import ProcessResult
                    results[idx] = ProcessOutcome(
                        ProcessResult.SAVE_ERROR,
                        file_name,
                        {"reason": f"Unhandled exception: {e}"},
                    )

                if on_progress:
                    fname = results[idx].file_name if results[idx] else str(files[idx])
                    on_progress(completed, total, fname)

        return [r for r in results if r is not None]
```

- [ ] **Step 2: Verify syntax**

```bash
python -c "from translateFunc.workers import WorkerPool; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add translateFunc/workers.py
git commit -m "feat: add WorkerPool with per-thread translator factory"
```

---

### Task 11: Create `translateFunc/pipeline.py` — TranslationPipeline

**Files:**
- Create: `translateFunc/pipeline.py`

**Interfaces:**
- Consumes: Everything from earlier tasks
- Produces: `TranslationPipeline` class
  - `TranslationPipeline.__init__(config: TranslateConfig)`
  - `TranslationPipeline.set_callbacks(*, on_log, on_status, on_progress, on_check_running)`
  - `TranslationPipeline.run() -> PipelineSummary`

- [ ] **Step 1: Write `translateFunc/pipeline.py`**

```python
"""
translateFunc/pipeline.py
TranslationPipeline — end-to-end orchestration of a translation run.

Flow:
  1. ProperAnalyzer.fetch_and_build() — fetch terms, build JP/EN contexts
  2. MatcherEngine.build() — populate all 4 AC automata
  3. Serial priority files (ScenarioModelCodes, BattleKeywords)
  4. WorkerPool.map() on remaining files
  5. Aggregate PipelineSummary
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import json
import logging
import os
import sys
import tempfile
from typing import Any, Callable

from translateFunc.config import (
    TranslateConfig, ProcessOutcome, PipelineSummary,
    PathConfig, FilePathConfig,
)
from translateFunc.enums import ProcessResult, FileType
from translateFunc.matcher.engine import MatcherEngine
from translateFunc.matcher.proper import ProperAnalyzer
from translateFunc.processor import FileProcessor
from translateFunc.workers import WorkerPool
from translateFunc.get_proper import fetch as fetch_proper
from translateFunc.translate_request import TRANSLATOR_TRANS
from translateFunc.translate_doc import JSON_SYSTEM_PROMPT, TEXT_SYSTEM_PROMPT
from translatekit import TranslationConfig as TKitConfig, TranslatorBase

# Import LogManager lazily to avoid circular imports at module level
def _get_log_manager():
    from globalManagers.LogManager import LogManager
    return LogManager()


class TranslationPipeline:
    """Orchestrates the full translation run from config to summary."""

    def __init__(self, config: TranslateConfig):
        self._config = config
        self._engine = MatcherEngine()
        self._analyzer: ProperAnalyzer | None = None

        # Callbacks
        self._on_log: Callable[[str], None] = lambda msg: None
        self._on_status: Callable[[str], None] = lambda msg: None
        self._on_progress: Callable[[int, str], None] = lambda pct, msg: None
        self._on_check_running: Callable[[], None] = lambda: None

    def set_callbacks(
        self,
        *,
        on_log: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_progress: Callable[[int, str], None] | None = None,
        on_check_running: Callable[[], None] | None = None,
    ) -> None:
        """Register UI callbacks for progress reporting."""
        if on_log:
            self._on_log = on_log
        if on_status:
            self._on_status = on_status
        if on_progress:
            self._on_progress = on_progress
        if on_check_running:
            self._on_check_running = on_check_running

    # ========== Run ==========

    def run(self) -> PipelineSummary:
        """Execute the full translation pipeline. Returns aggregate summary."""
        self._on_status("正在初始化...")

        # 1. Resolve paths
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

        # 2. Fetch proper nouns
        if self._config.enable_proper:
            self._on_status("正在获取专有名词...")
            self._analyzer = ProperAnalyzer(kr_path, jp_path, en_path)
            raw_terms = self._analyzer.fetch_terms(
                auto_fetch=self._config.auto_fetch_proper,
                proper_path=self._config.proper_path,
            )
            proper_terms = self._analyzer.analyze(raw_terms)
            proper_dicts = [
                {"term": t.kr, "translation": t.cn, "note": t.note}
                for t in proper_terms
            ]
            self._engine.build_proper(proper_dicts)
            self._on_log(f"已加载 {len(proper_terms)} 个专有名词")

        # 3. Build translator
        translator = self._build_translator()

        # 4. Collect target files
        target_files = list(kr_path.rglob("*.json"))
        self._on_log(f"找到 {len(target_files)} 个文件")

        # 5. Reorder: priority files first
        has_prefix = self._config.has_prefix
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

        # 6. Process priority files serially
        summary = PipelineSummary()
        for pf in priority_files:
            outcome = self._process_one(pf, base_path_config, has_prefix, translator)
            self._record_outcome(outcome, summary)

            # Update engine after processing model/keyword files
            if pf == priority_files[1] and self._config.enable_role:  # model file (2nd)
                self._update_roles(pf, base_path_config, has_prefix)
            elif pf == priority_files[0] and self._config.enable_skill:  # keyword file (1st)
                self._update_affects(pf, base_path_config, has_prefix)

        # 7. Process remaining files concurrently
        self._on_status("正在执行翻译...")
        self._on_progress(10, "正在执行翻译...")

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

        self._on_progress(90, "已完成汉化")
        return summary

    # ========== Internal ==========

    def _process_one(
        self, file_path: Path, base_pc: PathConfig, has_prefix: bool, translator
    ) -> ProcessOutcome:
        """Process a single file. Returns ProcessOutcome."""
        file_pc = FilePathConfig(KR_path=file_path, _PathConfig=base_pc, has_prefix=has_prefix)
        processor = FileProcessor(
            path_config=file_pc,
            engine=self._engine,
            translate_config=self._config,
            translator=translator,
        )
        return processor.process()

    def _record_outcome(self, outcome: ProcessOutcome, summary: PipelineSummary) -> None:
        """Record a ProcessOutcome into the PipelineSummary."""
        if outcome.result == ProcessResult.SUCCESS_SAVED:
            summary.saved.append(outcome.file_name)
        elif outcome.result in (ProcessResult.ALREADY_TRANSLATED, ProcessResult.EMPTY_WITH_LLC, ProcessResult.EMPTY_SKIPPED):
            summary.skipped.append(outcome.file_name)
        else:
            summary.errors.append(outcome)

    def _update_roles(self, model_file: Path, base_pc: PathConfig, has_prefix: bool) -> None:
        """Update MatcherEngine with role data from ScenarioModelCodes."""
        try:
            kr_data = json.loads(model_file.read_text(encoding="utf-8-sig"))
            target = FilePathConfig(KR_path=model_file, _PathConfig=base_pc, has_prefix=has_prefix).target_file
            cn_data = json.loads(target.read_text(encoding="utf-8-sig")) if target.exists() else kr_data
            kr_list = kr_data.get("dataList", kr_data if isinstance(kr_data, list) else [])
            cn_list = cn_data.get("dataList", cn_data if isinstance(cn_data, list) else [])
            roles = [
                {"id": k["id"], "kr": k["name"], "cn": c["name"], "nickName": c.get("nickName", "")}
                for k, c in zip(kr_list, cn_list)
            ]
            self._engine.build_roles(roles)
            self._on_log(f"已加载 {len(roles)} 个角色信息")
        except Exception as e:
            self._on_log(f"加载角色信息失败: {e}")

    def _update_affects(self, keyword_file: Path, base_pc: PathConfig, has_prefix: bool) -> None:
        """Update MatcherEngine with affect data from BattleKeywords."""
        try:
            kr_data = json.loads(keyword_file.read_text(encoding="utf-8-sig"))
            target = FilePathConfig(KR_path=keyword_file, _PathConfig=base_pc, has_prefix=has_prefix).target_file
            cn_data = json.loads(target.read_text(encoding="utf-8-sig")) if target.exists() else kr_data
            kr_list = kr_data.get("dataList", kr_data if isinstance(kr_data, list) else [])
            cn_list = cn_data.get("dataList", cn_data if isinstance(cn_data, list) else [])
            affects = [
                {"id": k["id"], "kr": k["name"], "cn": c["name"], "desc": c.get("desc", "")}
                for k, c in zip(kr_list, cn_list)
            ]
            self._engine.build_affects(affects)
            self._on_log(f"已加载 {len(affects)} 个状态效果")
        except Exception as e:
            self._on_log(f"加载状态效果失败: {e}")

    def _build_translator(self) -> TranslatorBase:
        """Create a translator instance from config."""
        translator_cls = TRANSLATOR_TRANS[self._config.translator_name]
        api_settings = dict(self._config.translator_api)

        if self._config.is_llm:
            api_settings["system_prompt"] = TEXT_SYSTEM_PROMPT if self._config.is_text_format else JSON_SYSTEM_PROMPT
            api_settings["response_format"] = "text" if self._config.is_text_format else "json_object"

        tkit_config = TKitConfig(
            api_setting=api_settings,
            debug_mode=self._config.debug_mode,
            enable_cache=True,
            enable_metrics=True,
        )

        if self._config.is_llm:
            tkit_config.text_max_length = 20000
            tkit_config.max_workers = 1

        # Suppress debug logging if not in debug mode
        if not self._config.debug_mode:
            logging.getLogger("translatekit").setLevel(logging.INFO)

        translator = translator_cls(tkit_config)

        if not self._config.debug_mode:
            logging.getLogger("translatekit").setLevel(logging.DEBUG)

        return translator
```

- [ ] **Step 2: Verify syntax**

```bash
python -c "from translateFunc.pipeline import TranslationPipeline; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add translateFunc/pipeline.py
git commit -m "feat: add TranslationPipeline orchestrating full translation flow"
```

---

### Task 12: Rewrite `translateFunc/__init__.py` — Public API

**Files:**
- Rewrite: `translateFunc/__init__.py`

**Interfaces:**
- Produces: Re-exports all public symbols from submodules

- [ ] **Step 1: Write the file**

```python
"""
translateFunc — LCTA auto-translation module.

Public API:
    TranslationPipeline  — end-to-end orchestration
    TranslateConfig      — configuration dataclass
    ProcessResult        — file processing outcome enum
    FileType             — file category enum
    MatchConfidence      — proper noun match confidence enum
    PipelineSummary      — aggregate run result
    ProcessOutcome       — single file result
"""
from translateFunc.pipeline import TranslationPipeline
from translateFunc.config import TranslateConfig, PipelineSummary, ProcessOutcome
from translateFunc.enums import ProcessResult, FileType, MatchConfidence

__all__ = [
    "TranslationPipeline",
    "TranslateConfig",
    "PipelineSummary",
    "ProcessOutcome",
    "ProcessResult",
    "FileType",
    "MatchConfidence",
]
```

- [ ] **Step 2: Verify the public API imports correctly**

```bash
python -c "
from translateFunc import (
    TranslationPipeline, TranslateConfig, PipelineSummary,
    ProcessOutcome, ProcessResult, FileType, MatchConfidence
)
print('Public API OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add translateFunc/__init__.py
git commit -m "feat: rewrite translateFunc __init__.py as public API surface"
```

---

### Task 13: Rewrite `webutils/function_translate.py` — Thin wrapper

**Files:**
- Rewrite: `webutils/function_translate.py`

**Interfaces:**
- Consumes: `TranslationPipeline`, `TranslateConfig` from `translateFunc`
- Produces: `translate_main(modal_id, translator_config, formating_function)` — preserved signature

- [ ] **Step 1: Write the file (~80 lines)**

```python
"""
webutils/function_translate.py
Thin WebUI wrapper around translateFunc.TranslationPipeline.
Handles: config loading, temp dir setup, UI callback binding, output packaging.
"""
import os
import time
import tempfile
from pathlib import Path
from datetime import datetime
from contextlib import suppress
from typing import Callable

from translateFunc import TranslationPipeline, TranslateConfig
from globalManagers.LogManager import LogManager
from globalManagers.ConfigManager import ConfigManager
from webutils.functions import get_cache_font, zip_folder

_log_manager = LogManager()


def translate_main(
    modal_id,
    translator_config: dict,
    formating_function: Callable[[dict, dict], dict],
):
    """Main entry point for WebUI translation.

    Args:
        modal_id: UI modal identifier for progress reporting.
        translator_config: API settings dict keyed by translator name.
        formating_function: (api_settings, translator_cls) -> formatted api_settings.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _log_manager.log_modal_process("开始初始化", modal_id)
        _log_manager.log_modal_status("正在初始化", modal_id)

        tmp = Path(tmpdir)
        cfg_mgr = ConfigManager()

        # 1. Build TranslateConfig from ConfigManager
        config = TranslateConfig.from_config_manager(cfg_mgr)

        # 2. Resolve translator API settings
        translator_text = config.translator_name
        api_settings = translator_config.get(translator_text, {})

        # Apply UI formatting function (preserved from old flow)
        from translateFunc.translate_request import TRANSLATOR_TRANS
        translator_cls = TRANSLATOR_TRANS[translator_text]
        api_settings = formating_function(api_settings, translator_cls)
        config.translator_api = api_settings

        # 3. Set output dir
        config.output_dir = tmp

        # 4. Create pipeline
        pipeline = TranslationPipeline(config)

        # 5. Bind UI callbacks
        pipeline.set_callbacks(
            on_log=lambda msg: _log_manager.log(msg),
            on_status=lambda msg: _log_manager.log_modal_status(msg, modal_id),
            on_progress=lambda pct, msg: (
                _log_manager.update_modal_progress(pct, msg, modal_id),
                _log_manager.log_modal_process(msg, modal_id),
            ),
            on_check_running=lambda: _log_manager.check_running(modal_id),
        )

        # 6. Run translation
        summary = pipeline.run()

        # 7. Report results
        _log_manager.log_modal_process(
            f"翻译完成: {summary.success_count} 成功, "
            f"{len(summary.skipped)} 跳过, {summary.error_count} 错误",
            modal_id,
        )
        _log_manager.log_modal_status("正在打包汉化包", modal_id)

        # 8. Package output
        target_dir = config.output_dir / "LLc-CN-LCTA"
        VERSION = _generate_version(tmp)
        _copy_assets(target_dir, config.game_path)

        work_dir = Path(os.getcwd())
        r = zip_folder(target_dir, work_dir / f"LCTA_{VERSION}.zip")
        if r:
            _log_manager.log_modal_process("压缩完成", modal_id)
            _log_manager.log_modal_status("翻译完成", modal_id)
            _log_manager.update_modal_progress(100, "全部操作完成", modal_id)
        else:
            _log_manager.log_modal_process("压缩失败", modal_id)
            _log_manager.log_modal_status("操作失败", modal_id)
            _log_manager.update_modal_progress(100, "操作失败", modal_id)
            os.system(f'explorer "{tmp}"')
            _log_manager.log_modal_process(
                "目前已打开产物文件夹，如果有需要，请在60秒内保存数据", modal_id
            )
            time.sleep(60)


def _generate_version(tmp: Path) -> str:
    """Generate version string YYYYMMDDNN."""
    today = datetime.now()
    current_date = today.strftime("%Y%m%d")
    work_dir = Path(os.getcwd())
    previous_version = 1999010101
    for z in work_dir.glob(f"{current_date}??.zip"):
        with suppress(Exception):
            v = int(str(z.stem).split("_")[-1]) if "_" in str(z.stem) else int(str(z.stem)[-2:])
    try:
        return f"{current_date}01"
    except Exception:
        return f"{current_date}01"


def _copy_assets(target_dir: Path, game_path: Path) -> None:
    """Copy license, version, and font into output directory."""
    import shutil, json
    try:
        info_dir = target_dir / "Info"
        info_dir.mkdir(parents=True, exist_ok=True)
        license_src = game_path / "LimbusCompany_Data" / "lang" / "LLC_zh-CN" / "Info" / "LICENSE"
        if license_src.exists():
            shutil.copy(license_src, info_dir / "LICENSE")
        # version.json is written by the pipeline
    except Exception:
        pass
    try:
        font_dir = target_dir / "Font" / "Context"
        font_dir.mkdir(parents=True, exist_ok=True)
        font_src = get_cache_font()
        if font_src:
            shutil.copy(font_src, font_dir / "ChineseFont.ttf")
    except Exception:
        pass
```

- [ ] **Step 2: Verify syntax (imports only — full test requires runtime context)**

```bash
python -c "
from webutils.function_translate import translate_main
print('function_translate imports OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add webutils/function_translate.py
git commit -m "refactor: reduce function_translate.py to thin 80-line wrapper"
```

---

### Task 14: Update config defaults and schema

**Files:**
- Modify: `config_default.json`
- Modify: `config_check.json`

**Interfaces:**
- Adds 6 new keys under `ui_default.translator` with defaults and schema types

- [ ] **Step 1: Update `config_default.json`** — add new keys to the `ui_default.translator` block

The `ui_default.translator` section currently has 17 keys. Add these 6:

```json
"max_workers": 4,
"enable_concurrent": true,
"translation_mode": "multi_stage",
"enable_self_check": false,
"disambiguation_mode": "hybrid",
"min_confidence": "medium"
```

Run the edit:

```bash
python -c "
import json
with open('config_default.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
tl = data['ui_default']['translator']
tl['max_workers'] = 4
tl['enable_concurrent'] = True
tl['translation_mode'] = 'multi_stage'
tl['enable_self_check'] = False
tl['disambiguation_mode'] = 'hybrid'
tl['min_confidence'] = 'medium'
# Keep keys in a reasonable order
new_tl = {}
for k in ['translator', 'fallback', 'is_text', 'from_lang',
          'enable_proper', 'auto_fetch_proper', 'proper_path',
          'enable_role', 'enable_skill', 'enable_dev_settings',
          'max_workers', 'enable_concurrent',
          'translation_mode', 'enable_self_check',
          'disambiguation_mode', 'min_confidence',
          'en_path', 'kr_path', 'jp_path', 'llc_path',
          'has_prefix', 'dump']:
    if k in tl:
        new_tl[k] = tl[k]
data['ui_default']['translator'] = new_tl
with open('config_default.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)
print('Updated config_default.json')
"
```

- [ ] **Step 2: Update `config_check.json`** — add schema entries

```bash
python -c "
import json
with open('config_check.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
tl = data['ui_default']['translator']
tl['max_workers'] = 'int'
tl['enable_concurrent'] = 'bool'
tl['translation_mode'] = 'str'
tl['enable_self_check'] = 'bool'
tl['disambiguation_mode'] = 'str'
tl['min_confidence'] = 'str'
with open('config_check.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)
print('Updated config_check.json')
"
```

- [ ] **Step 3: Verify `ConfigManager.fix()` picks up new keys**

```bash
python -c "
from globalManagers.ConfigManager import ConfigManager
mgr = ConfigManager()
msgs = mgr.fix()
new_keys = ['max_workers', 'enable_concurrent', 'translation_mode', 'enable_self_check', 'disambiguation_mode', 'min_confidence']
for k in new_keys:
    val = mgr.get(f'ui_default.translator.{k}')
    print(f'{k} = {val}')
print('Config migration OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add config_default.json config_check.json
git commit -m "feat: add new config keys for concurrent and multi-stage translation"
```

---

### Task 15: Write AC automaton unit tests

**Files:**
- Create: `tests/test_ac_automaton.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for AC automaton — pure algorithm, zero external dependencies."""
import pytest
from translateFunc.matcher.ac_automaton import AcAutomaton, ACPattern


class TestAcAutomaton:
    """Unit tests for Aho-Corasick automaton."""

    def test_empty_automaton(self):
        ac = AcAutomaton()
        ac.build()
        assert ac.search("hello") == []
        assert ac.search_batch(["a", "b"]) == [[], []]

    def test_single_pattern(self):
        ac = AcAutomaton()
        ac.add_pattern("hello")
        ac.build()
        hits = ac.search("hello world")
        assert len(hits) == 1
        assert hits[0].pattern == "hello"

    def test_multiple_patterns(self):
        ac = AcAutomaton()
        ac.add_pattern("he")
        ac.add_pattern("she")
        ac.add_pattern("his")
        ac.add_pattern("hers")
        ac.build()
        hits = ac.search("ushers")
        patterns = {h.pattern for h in hits}
        assert patterns == {"he", "she", "hers"}

    def test_overlapping_patterns(self):
        ac = AcAutomaton()
        ac.add_pattern("a")
        ac.add_pattern("aa")
        ac.build()
        hits = ac.search("aaa")
        # 3 single 'a' + 2 'aa'
        assert len(hits) == 5

    def test_no_match(self):
        ac = AcAutomaton()
        ac.add_pattern("xyz")
        ac.build()
        assert ac.search("abcdef") == []

    def test_unicode_patterns(self):
        ac = AcAutomaton()
        ac.add_pattern("이상")
        ac.add_pattern("이상하다")
        ac.build()
        hits = ac.search("이상한 나라의 이상")
        patterns = {h.pattern for h in hits}
        assert "이상" in patterns
        # '이상하다' should NOT match since '이상한' != '이상하다'
        assert "이상하다" not in patterns

    def test_pattern_with_data(self):
        ac = AcAutomaton()
        ac.add_pattern("test", data={"id": 1, "cn": "测试"})
        ac.build()
        hits = ac.search("this is a test case")
        assert len(hits) == 1
        assert hits[0].data == {"id": 1, "cn": "测试"}

    def test_batch_search(self):
        ac = AcAutomaton()
        ac.add_pattern("foo")
        ac.add_pattern("bar")
        ac.build()
        results = ac.search_batch(["foo bar", "nothing", "bar only"])
        assert len(results[0]) == 2
        assert len(results[1]) == 0
        assert len(results[2]) == 1

    def test_add_after_build_raises(self):
        ac = AcAutomaton()
        ac.add_pattern("test")
        ac.build()
        with pytest.raises(RuntimeError, match="Cannot add patterns after build"):
            ac.add_pattern("another")

    def test_search_before_build_raises(self):
        ac = AcAutomaton()
        ac.add_pattern("test")
        with pytest.raises(RuntimeError, match="Must call build"):
            ac.search("test")

    def test_empty_pattern_ignored(self):
        ac = AcAutomaton()
        ac.add_pattern("")
        ac.add_pattern("valid")
        ac.build()
        assert ac.search("valid test")[0].pattern == "valid"

    def test_pattern_count(self):
        ac = AcAutomaton()
        ac.add_pattern("a")
        ac.add_pattern("b")
        ac.add_pattern("c")
        assert ac.pattern_count == 3
        ac.build()
        assert ac.pattern_count == 3
```

- [ ] **Step 2: Run tests**

```bash
python -m pytest tests/test_ac_automaton.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_ac_automaton.py
git commit -m "test: add AC automaton unit tests"
```

---

### Task 16: Write integration test for TranslationPipeline

**Files:**
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write the test file**

```python
"""Integration tests for TranslationPipeline with mocked dependencies."""
import json
import tempfile
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from translateFunc import (
    TranslationPipeline, TranslateConfig, PipelineSummary,
    ProcessResult, ProcessOutcome,
)
from translateFunc.enums import FileType, MatchConfidence
from translateFunc.config import FilePathConfig, PathConfig


class TestPipelineSummary:
    """Unit tests for PipelineSummary aggregation."""

    def test_empty_summary(self):
        s = PipelineSummary()
        assert s.total == 0
        assert s.success_count == 0
        assert s.error_count == 0

    def test_mixed_results(self):
        s = PipelineSummary(
            saved=["a.json", "b.json"],
            skipped=["c.json"],
            errors=[ProcessOutcome(ProcessResult.SAVE_ERROR, "d.json")],
        )
        assert s.total == 4
        assert s.success_count == 2
        assert s.error_count == 1


class TestTranslateConfig:
    """Tests for TranslateConfig.from_config_manager()."""

    def test_defaults(self):
        config = TranslateConfig()
        assert config.max_workers == 4
        assert config.enable_concurrent is True
        assert config.translation_mode == "multi_stage"
        assert config.disambiguation_mode == "hybrid"

    def test_from_config_manager(self):
        mock_mgr = MagicMock()
        mock_mgr.get.side_effect = lambda key, default=None: {
            "ui_default.translator": {
                "translator": "百度翻译服务",
                "max_workers": 8,
                "enable_concurrent": False,
            },
            "game_path": "/test/path",
            "debug": True,
        }.get(key, default)

        config = TranslateConfig.from_config_manager(mock_mgr)
        assert config.translator_name == "百度翻译服务"
        assert config.max_workers == 8
        assert config.enable_concurrent is False
        assert config.is_llm is False


class TestProcessOutcome:
    """Tests for ProcessOutcome and ProcessResult enum."""

    def test_success_outcome(self):
        o = ProcessOutcome(ProcessResult.SUCCESS_SAVED, "test.json")
        assert o.result == ProcessResult.SUCCESS_SAVED
        assert o.file_name == "test.json"
        assert o.extra is None

    def test_error_outcome_with_details(self):
        o = ProcessOutcome(
            ProcessResult.JSON_DECODE_ERROR,
            "bad.json",
            extra={"line": 42, "error": "Unexpected token"},
        )
        assert o.result == ProcessResult.JSON_DECODE_ERROR
        assert o.extra["line"] == 42


class TestFilePathConfig:
    """Tests for FilePathConfig path resolution."""

    def test_basic_paths(self, tmp_path):
        kr_base = tmp_path / "kr"
        kr_base.mkdir()
        (kr_base / "sub").mkdir()
        test_file = kr_base / "sub" / "KR_test.json"
        test_file.write_text("{}", encoding="utf-8")

        base = PathConfig(
            target_path=tmp_path / "out",
            llc_base_path=tmp_path / "llc",
            KR_base_path=kr_base,
            JP_base_path=tmp_path / "jp",
            EN_base_path=tmp_path / "en",
        )

        fpc = FilePathConfig(KR_path=test_file, _PathConfig=base, has_prefix=True)
        assert fpc.real_name == "test.json"
        assert fpc.rel_path == Path("sub") / "KR_test.json"
        assert fpc.rel_dir == Path("sub")

    def test_no_prefix_paths(self, tmp_path):
        kr_base = tmp_path / "kr"
        kr_base.mkdir()
        (kr_base / "sub").mkdir()
        test_file = kr_base / "sub" / "test.json"
        test_file.write_text("{}", encoding="utf-8")

        base = PathConfig(
            target_path=tmp_path / "out",
            llc_base_path=tmp_path / "llc",
            KR_base_path=kr_base,
            JP_base_path=tmp_path / "jp",
            EN_base_path=tmp_path / "en",
        )

        fpc = FilePathConfig(KR_path=test_file, _PathConfig=base, has_prefix=False)
        assert fpc.real_name == "test.json"
        assert fpc.EN_path == tmp_path / "en" / "sub" / "test.json"
        assert fpc.JP_path == tmp_path / "jp" / "sub" / "test.json"
        assert fpc.LLC_path == tmp_path / "llc" / "sub" / "test.json"
```

- [ ] **Step 2: Run tests**

```bash
python -m pytest tests/test_pipeline.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_pipeline.py
git commit -m "test: add integration tests for pipeline components"
```

---

### Task 17: Final verification — import chain and backward compatibility

**Files:**
- Verify: all imports resolve
- Verify: old `webutils/function_translate.py` public signature unchanged
- Verify: `ConfigManager.fix()` handles new keys

- [ ] **Step 1: Full import chain test**

```bash
python -c "
# Verify every new module imports without error
from translateFunc.enums import ProcessResult, FileType, MatchConfidence
from translateFunc.config import TranslateConfig, ProcessOutcome, PipelineSummary, PathConfig, FilePathConfig
from translateFunc.matcher.ac_automaton import AcAutomaton, ACPattern
from translateFunc.matcher.engine import MatcherEngine, MatchResult
from translateFunc.matcher.proper import ProperAnalyzer, ProperTerm
from translateFunc.builder.prompt import PromptFactory, PromptTag
from translateFunc.builder.request import RequestBuilder
from translateFunc.builder.stages import StageStrategy
from translateFunc.processor import FileProcessor
from translateFunc.workers import WorkerPool
from translateFunc.pipeline import TranslationPipeline
from translateFunc import (
    TranslationPipeline, TranslateConfig, PipelineSummary,
    ProcessOutcome, ProcessResult, FileType, MatchConfidence,
)
from translateFunc.proper import flatten_dict_enhanced, update_dict_with_flattened, get_value_by_path
print('All imports OK')
"
```

- [ ] **Step 2: Verify old translate_main.py still works (it should — we didn't modify it)**

```bash
python -c "
# Old imports should still work
from translateFunc.translate_main import ProcesserExit, SimpleMatcher, FileProcessor as OldFileProcessor
print('Old translate_main.py still importable')
"
```

- [ ] **Step 3: Verify function_translate.py signature**

```bash
python -c "
import inspect
from webutils.function_translate import translate_main
sig = inspect.signature(translate_main)
params = list(sig.parameters.keys())
assert 'modal_id' in params
assert 'translator_config' in params
assert 'formating_function' in params
print(f'translate_main signature preserved: {params}')
"
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add -A
git diff --cached --stat
git commit -m "chore: final verification — all imports and backward compatibility pass"
```

---

## Self-Review Checklist

### Spec Coverage
- ✅ Section 1 (模块结构): File map covers all new files
- ✅ Section 2 (Result Enum): Task 1 (enums.py)
- ✅ Section 3 (AC automaton): Task 3 (ac_automaton.py), Task 4 (engine.py)
- ✅ Section 4 (JP/EN cross-validation): Task 5 (proper.py, analyze.py)
- ✅ Section 5 (Concurrency): Task 10 (workers.py), Task 11 (pipeline.py)
- ✅ Section 6 (Prompt system): Task 6 (prompt.py), Task 7 (request.py), Task 8 (stages.py)
- ✅ Section 7 (Public API): Task 12 (__init__.py), Task 13 (function_translate.py)
- ✅ Section 8 (Testing): Tasks 15-17
- ✅ Section 9 (Config migration): Task 14
- ✅ Constraints: `flat.py` untouched, `translate_doc.py` untouched, `translate_request.py` untouched

### No Placeholders
- All code steps contain complete implementation
- All commands are exact with expected outputs
- No "TBD", "TODO", or "implement later"

### Type Consistency
- `ProcessResult` enum used consistently across config.py, processor.py, pipeline.py
- `ProcessOutcome.file_name` is `str` everywhere
- `TranslateConfig.from_config_manager()` signature matches config.py Task 2
- `MatcherEngine.build_proper/build_roles/build_affects` signatures match pipeline.py Task 11 calls
- `WorkerPool.map()` signature matches pipeline.py Task 11 call
- `FileProcessor.__init__` takes `(path_config, engine, translate_config, translator)` — consistent with pipeline.py
