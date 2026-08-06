"""美化规则编辑器窗口的 JS-API 桥接。"""

import json

from globalManagers.ConfigManager import ConfigManager

class RuleEditorAPI:
    def __init__(self):
        from webutils.rule_editor import (
            get_lang_files, get_file_content, search_files,
            get_ruleset_list, get_ruleset, save_ruleset,
            create_ruleset, delete_ruleset,
            build_rule_from_form, validate_rule, analyze_changes,
            analyze_changes_v2, analyze_changes_v3,
            save_file_content, apply_ruleset_to_content,
        )
        self.get_lang_files = get_lang_files
        self.get_file_content = get_file_content
        self.search_files = search_files
        self.get_ruleset_list = get_ruleset_list
        self.get_ruleset = get_ruleset
        self.save_ruleset = save_ruleset
        self.create_ruleset = create_ruleset
        self.delete_ruleset = delete_ruleset
        self.build_rule_from_form = build_rule_from_form
        self.validate_rule = validate_rule
        self.analyze_changes = analyze_changes
        self.analyze_changes_v2 = analyze_changes_v2
        self.analyze_changes_v3 = analyze_changes_v3
        self.save_file_content = save_file_content
        self.apply_ruleset_to_content = apply_ruleset_to_content

    def get_config_value(self, key_path, default_value=None):
        """规则编辑器查询主应用配置（如 theme）"""
        return ConfigManager().get(key_path, default_value)

    def apply_ruleset(self, name: str) -> dict:
        from webutils.function_fancy import fancy_main
        from pathlib import Path
        try:
            game_path = ConfigManager().get('game_path')
            lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
            config_lang = json.loads((lang_path / 'config.json').read_text(encoding='utf-8')).get('lang', '')
            from webutils.rule_editor import get_ruleset
            ruleset = get_ruleset(name)
            if 'error' in ruleset:
                return {"success": False, "message": ruleset['error']}
            fancy_main(game_path, config_lang, [ruleset])
            return {"success": True, "message": f"已应用"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_autocomplete_data(self) -> dict:
        from webutils.rule_editor.constants import CATEGORY_FILE_PATTERNS, COMMON_REPLACEMENTS
        return {
            "file_patterns": [{"label": k, "value": v} for k, v in CATEGORY_FILE_PATTERNS.items()],
            "common_replacements": COMMON_REPLACEMENTS,
        }

    def get_templates(self) -> list:
        from webutils.rule_editor.constants import TEMPLATES
        return TEMPLATES

    def get_editor_constants(self) -> dict:
        from webutils.rule_editor.constants import FILE_PREFIX_RULES, CATEGORY_FILE_PATTERNS, COMMON_REPLACEMENTS, TEMPLATES
        return {
            "file_prefix_rules": FILE_PREFIX_RULES,
            "category_file_patterns": {k: v for k, v in CATEGORY_FILE_PATTERNS.items()},
            "common_replacements": COMMON_REPLACEMENTS,
            "templates": TEMPLATES,
        }
