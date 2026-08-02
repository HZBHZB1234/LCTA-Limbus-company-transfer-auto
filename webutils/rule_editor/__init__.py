"""规则编辑器后端 API — 文件浏览、规则 CRUD、智能生成、快速编辑。"""

from __future__ import annotations

from .browser import get_category, get_file_content, get_lang_files, save_file_content, search_files
from .constants import (
    CATEGORY_FILE_PATTERNS,
    COMMON_REPLACEMENTS,
    FILE_PREFIX_RULES,
    TEMPLATES,
)
from .generate import analyze_changes, analyze_changes_v2, analyze_changes_v3
from .quick import apply_quick_edits, diff_json, load_quick_edits, save_quick_edits
from .rules import (
    apply_ruleset_to_content,
    build_rule_from_form,
    create_ruleset,
    delete_ruleset,
    get_ruleset,
    get_ruleset_list,
    save_ruleset,
    validate_rule,
)

__all__ = [
    'get_lang_files',
    'get_file_content',
    'search_files',
    'get_category',
    'save_file_content',
    'get_ruleset_list',
    'get_ruleset',
    'save_ruleset',
    'create_ruleset',
    'delete_ruleset',
    'build_rule_from_form',
    'validate_rule',
    'apply_ruleset_to_content',
    'analyze_changes',
    'analyze_changes_v2',
    'analyze_changes_v3',
    'diff_json',
    'load_quick_edits',
    'save_quick_edits',
    'apply_quick_edits',
    'FILE_PREFIX_RULES',
    'CATEGORY_FILE_PATTERNS',
    'COMMON_REPLACEMENTS',
    'TEMPLATES',
]
