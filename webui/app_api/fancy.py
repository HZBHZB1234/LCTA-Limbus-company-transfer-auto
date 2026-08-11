# -*- coding: utf-8 -*-
"""LCTA_API 文本美化：规则集读写、Bus 规则导入、美化引擎、规则编辑器窗口。"""
import os
import json
from pathlib import Path
import webview

from globalManagers.ConfigManager import ConfigManager
from webutils.fancy.builtin_data import fancy as builtinFancyConfig
from webutils.function_fancy import fancy_main
from webui.rule_editor_api import RuleEditorAPI
from webui.app_api.exceptions import CancelRunning

class FancyMixin:

    def get_fancy_rulesets(self):
        from webutils.function_fancy import load_fancy_folder_rules
        return {'success': True, 'data': {
            'builtin': builtinFancyConfig,
            'user': load_fancy_folder_rules(),
            'enabled': json.loads(ConfigManager().get('fancy_allow',
                 "{\"技能文本美化(FL Like)\": true,\"气泡文本渐变(FL Like)\": true,\"EGO文本渐变(FL Like)\": true}"))
        }}

    def save_ruleset(self, name: str, data: dict) -> dict:
        """将规则集保存到 fancy/ 文件夹（主窗口文本美化页保存当前/全部）"""
        from webutils.rule_editor import save_ruleset as _save_ruleset
        return _save_ruleset(name, data)

    def import_bus_rules(self, name=None):
        from webutils.function_fancy import import_bus_rules_file

        selected = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=("JSON Files (*.json)",),
        )
        if not selected:
            return {"success": False, "cancelled": True, "imported": [], "errors": []}
        imported = []
        errors = []
        for file_path in selected:
            try:
                imported.append(import_bus_rules_file(file_path, name=name))
            except Exception as exc:
                errors.append({"file": Path(file_path).name, "error": str(exc)})
        return {
            "success": not errors,
            "imported": imported,
            "errors": errors,
        }

    def fancy_main(self, config_list, enableMap, modal_id="false"):
        try:
            gamePath = ConfigManager().get('game_path')
            lang_path = Path(gamePath) / 'LimbusCompany_Data' / 'lang'
            config_lang = json.loads((lang_path / 'config.json').read_text(encoding='utf-8')).get('lang', '')
        except Exception as e:
            self.log_manager.log_error(e)
            raise RuntimeError('获取当前安装汉化包失败')
        try:
            fancy_main(gamePath, config_lang, config_list, enableMap, modal_id=modal_id)
        except CancelRunning:
            self.log('美化任务已取消')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        return {"success": True, "message": "美化完成"}

    def check_fancy_marker(self) -> dict:
        """检查当前语言包目录是否存在美化标记文件"""
        try:
            from webutils.function_fancy import has_fancy_marker
            gamePath = ConfigManager().get('game_path')
            lang_path = Path(gamePath) / 'LimbusCompany_Data' / 'lang'
            config_lang = json.loads((lang_path / 'config.json').read_text(encoding='utf-8')).get('lang', '')
            return {'success': True, 'beautified': has_fancy_marker(gamePath, config_lang)}
        except Exception as e:
            self.log_manager.log_error(e)
            return {'success': False, 'beautified': False}

    def open_rule_editor(self):
        html_path = os.path.join(os.getenv('path_'), "webui/rule-editor.html")
        # 读取当前主题，注入到新窗口
        current_theme = ConfigManager().get('theme', 'light')
        window = webview.create_window(
            "LCTA - 美化规则编辑器", url=html_path,
            width=1200, height=800, resizable=True, text_select=True,
            js_api=RuleEditorAPI()
        )
        # 窗口创建后立即注入主题（在 JS init 之前执行）
        try:
            window.evaluate_js(f"""
                (function() {{
                    if (document.body) {{
                        document.body.className = 'theme-{current_theme}';
                        document.body.setAttribute('data-injected-theme', '{current_theme}');
                    }}
                }})();
            """)
        except Exception:
            pass
        if not hasattr(self, '_rule_editor_windows'):
            self._rule_editor_windows = []
        self._rule_editor_windows.append(window)

        def remove_window(*_args):
            if getattr(self, '_rule_editor_windows', None):
                try:
                    self._rule_editor_windows.remove(window)
                except ValueError:
                    pass

        window.events.closed += remove_window

    def sync_theme_to_rule_editor(self, theme):
        """推送主题变更到所有打开的规则编辑器窗口"""
        for w in getattr(self, '_rule_editor_windows', []):
            try:
                w.evaluate_js(f"""
                    if (typeof applyTheme === 'function') {{
                        applyTheme('{theme}');
                    }}
                """)
            except Exception:
                pass
        # 同时同步到简易编辑器窗口
        self.sync_theme_to_quick_editor(theme)
        self.sync_theme_to_translation_log_viewer(theme)
        self.sync_theme_to_llm_fancy(theme)
        self.sync_theme_to_aria2_downloader(theme)
