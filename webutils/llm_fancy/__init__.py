"""
webutils/llm_fancy/
LLM 文本美化窗口的后端。

与翻译功能（translateFunc/）完全解耦：本包不 import 任何翻译模块，
仅依赖 translatekit（共享外部库）、webutils/fancy/（bus 引擎领域）与
webutils/function_fancy.py（规则集落盘）。LLM API 设置由前端解密 api_config 后注入。
"""

from webutils.llm_fancy.config import (
    DEFAULT_MAX_LENGTH,
    DEFAULT_MAX_WORKERS,
    LLMFancyConfig,
    load_config,
    save_config,
)
from webutils.llm_fancy.builder import (
    build_ruleset,
    enable_ruleset_in_config,
    save_ruleset,
)
from webutils.llm_fancy.exclude import (
    compile_exclusion_rulesets,
    excluded_paths,
)
from webutils.llm_fancy.llm import (
    DEFAULT_SYSTEM_PROMPT,
    build_system_prompt,
    build_translator,
    format_api_settings,
    parse_batch_response,
    strip_code_fence,
)
from webutils.llm_fancy.runner import (
    LLMFancyCancelled,
    LLMFancyRunResult,
    ScanResult,
    resolve_lang_dir,
    run_beautify,
    scan_preview,
)
from webutils.llm_fancy.scanner import (
    Candidate,
    CompiledSelection,
    compile_selection,
    dedup_candidates,
    scan_data,
    validate_selection,
)
from webutils.llm_fancy.splitter import (
    estimate_item_size,
    split_items,
)

__all__ = [
    "DEFAULT_MAX_LENGTH",
    "DEFAULT_MAX_WORKERS",
    "DEFAULT_SYSTEM_PROMPT",
    "LLMFancyCancelled",
    "LLMFancyConfig",
    "LLMFancyRunResult",
    "ScanResult",
    "Candidate",
    "CompiledSelection",
    "build_ruleset",
    "build_system_prompt",
    "build_translator",
    "compile_exclusion_rulesets",
    "compile_selection",
    "dedup_candidates",
    "enable_ruleset_in_config",
    "estimate_item_size",
    "excluded_paths",
    "format_api_settings",
    "load_config",
    "parse_batch_response",
    "resolve_lang_dir",
    "run_beautify",
    "save_config",
    "save_ruleset",
    "scan_data",
    "scan_preview",
    "split_items",
    "strip_code_fence",
    "validate_selection",
]
