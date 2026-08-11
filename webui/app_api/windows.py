# -*- coding: utf-8 -*-
"""LCTA_API 辅助窗口：简易编辑器 / LLM 美化 / 翻译日志查看器 / 主题同步。"""
import os
from pathlib import Path
import webview

from globalManagers.ConfigManager import ConfigManager
from webui.quick_editor_api import QuickEditorAPI
from webui.llm_fancy_api import LLMFancyAPI
from webui.translation_log_api import TranslationLogViewerAPI
from webui.aria2_downloader_api import Aria2DownloaderAPI

class WindowMixin:

    def startTest(self):
        self._window_test = webview.create_window("模组下载测试窗口", url="https://www.nexusmods.com/games/limbuscompany")

    def eval_skip(self):
        self.log_manager.log('开始执行js')
        js_path = Path(os.getenv('path_')) / 'webui' / 'nexus'
        self._window_test.run_js(f"window.DICTIONARY_URL = 'http://127.0.0.1:{self.http_port}/nexus/dict.js'")
        #jss = list(js_path.glob('*.js'))
        jss = [js_path / 'simulation.js', js_path / 'dict.js', js_path / 'cn.js', js_path / 'skip.js']
        for i in jss:
            js_code = i.read_text(encoding='utf-8')
            self._window_test.run_js(js_code)

    def sign_eval_js(self):
        self.log_manager.log('已订阅事件')
        self._window_test.events.loaded += self.eval_skip

    def open_quick_editor(self):
        """打开简易翻译编辑器窗口"""
        html_path = os.path.join(os.getenv('path_'), "webui/quick-editor.html")
        current_theme = ConfigManager().get('theme', 'light')
        window = webview.create_window(
            "LCTA - 简易翻译编辑器", url=html_path,
            width=1100, height=700, resizable=True, text_select=True,
            js_api=QuickEditorAPI()
        )
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
        if not hasattr(self, '_quick_editor_windows'):
            self._quick_editor_windows = []
        self._quick_editor_windows.append(window)

        def remove_window(*_args):
            if getattr(self, '_quick_editor_windows', None):
                try:
                    self._quick_editor_windows.remove(window)
                except ValueError:
                    pass

        window.events.closed += remove_window

    def open_llm_fancy(self):
        """打开 LLM 文本美化独立窗口"""
        html_path = os.path.join(os.getenv('path_'), "webui/llm-fancy.html")
        current_theme = ConfigManager().get('theme', 'light')
        api = LLMFancyAPI()
        window = webview.create_window(
            "LCTA - LLM 文本美化", url=html_path,
            width=1000, height=860, resizable=True, text_select=True,
            js_api=api,
        )
        api.set_window(window)
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
        if not hasattr(self, '_llm_fancy_windows'):
            self._llm_fancy_windows = []
        self._llm_fancy_windows.append(window)

        def remove_window(*_args):
            if getattr(self, '_llm_fancy_windows', None):
                try:
                    self._llm_fancy_windows.remove(window)
                except ValueError:
                    pass

        window.events.closed += remove_window

    def sync_theme_to_llm_fancy(self, theme):
        """推送主题变更到所有 LLM 文本美化窗口"""
        for w in getattr(self, '_llm_fancy_windows', []):
            try:
                w.evaluate_js(f"""
                    if (typeof applyTheme === 'function') {{
                        applyTheme('{theme}');
                    }}
                """)
            except Exception:
                pass

    def sync_theme_to_quick_editor(self, theme):
        """推送主题变更到所有打开的简易编辑器窗口"""
        if not hasattr(self, '_quick_editor_windows'):
            return
        for w in self._quick_editor_windows:
            try:
                w.evaluate_js(f"""
                    if (typeof applyTheme === 'function') {{
                        applyTheme('{theme}');
                    }}
                """)
            except Exception:
                pass

    def open_translation_log_viewer(self):
        """打开翻译诊断日志查看器。"""
        existing = getattr(self, '_translation_log_window', None)
        if existing is not None:
            try:
                existing.restore()
                existing.show()
                return {"success": True, "message": "日志查看器已打开"}
            except Exception:
                self._translation_log_window = None

        html_path = os.path.join(os.getenv('path_'), "webui/translation-log-viewer.html")
        current_theme = ConfigManager().get('theme', 'light')
        api = TranslationLogViewerAPI()
        window = webview.create_window(
            "LCTA - 翻译诊断日志", url=html_path,
            width=1400, height=850, resizable=True, text_select=True,
            js_api=api,
        )
        api.set_window(window)
        self._translation_log_window = window

        def clear_window_reference(*_args):
            if getattr(self, '_translation_log_window', None) is window:
                self._translation_log_window = None

        window.events.closed += clear_window_reference
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
        return {"success": True, "message": "日志查看器已打开"}

    def sync_theme_to_translation_log_viewer(self, theme):
        """推送主题变更到翻译诊断日志查看器。"""
        window = getattr(self, '_translation_log_window', None)
        if window is None:
            return
        try:
            window.evaluate_js(f"""
                if (typeof applyTheme === 'function') {{
                    applyTheme('{theme}');
                }}
            """)
        except Exception:
            self._translation_log_window = None

    def open_aria2_downloader(self):
        """打开泛用高速下载器独立窗口。"""
        from webutils import aria2_manager
        existing = getattr(self, '_aria2_downloader_window', None)
        if existing is not None:
            try:
                existing.restore()
                existing.show()
                return {"success": True, "message": "高速下载器已打开"}
            except Exception:
                self._aria2_downloader_window = None

        html_path = os.path.join(os.getenv('path_'), "webui/aria2-downloader.html")
        current_theme = ConfigManager().get('theme', 'light')
        api = Aria2DownloaderAPI()
        window = webview.create_window(
            "LCTA - 高速下载器", url=html_path,
            width=980, height=760, resizable=True, text_select=True,
            js_api=api,
        )
        api.set_window(window)
        self._aria2_downloader_window = window

        def on_closed(*_args):
            if getattr(self, '_aria2_downloader_window', None) is window:
                self._aria2_downloader_window = None
            try:
                aria2_manager.stop()
            except Exception:
                pass

        window.events.closed += on_closed
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
        return {"success": True, "message": "高速下载器已打开"}

    def sync_theme_to_aria2_downloader(self, theme):
        """推送主题变更到高速下载器窗口。"""
        window = getattr(self, '_aria2_downloader_window', None)
        if window is None:
            return
        try:
            window.evaluate_js(f"""
                if (typeof applyTheme === 'function') {{
                    applyTheme('{theme}');
                }}
            """)
        except Exception:
            self._aria2_downloader_window = None
