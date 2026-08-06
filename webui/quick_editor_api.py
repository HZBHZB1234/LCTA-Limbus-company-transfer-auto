# -*- coding: utf-8 -*-
"""简易翻译编辑器窗口的 JS-API 桥接。"""
from globalManagers.ConfigManager import ConfigManager

class QuickEditorAPI:
    """简易翻译编辑器的 JS-API 桥接"""

    def __init__(self):
        from webutils.rule_editor import (
            get_lang_files, get_file_content, search_files,
            save_file_content, get_category,
        )
        from webutils.rule_editor import (
            diff_json, load_quick_edits, save_quick_edits,
            apply_quick_edits,
        )
        self.get_lang_files = get_lang_files
        self.get_file_content = get_file_content
        self.search_files = search_files
        self.save_file_content = save_file_content
        self.get_category = get_category
        self.diff_json = diff_json
        self.load_quick_edits = load_quick_edits
        self.save_quick_edits = save_quick_edits
        self.apply_quick_edits = apply_quick_edits

    def get_config_value(self, key_path, default_value=None):
        """查询主应用配置（如 theme）"""
        return ConfigManager().get(key_path, default_value)
