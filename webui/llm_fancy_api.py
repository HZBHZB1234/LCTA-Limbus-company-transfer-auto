# -*- coding: utf-8 -*-
"""LLM 文本美化窗口的 JS-API 桥接。"""
import threading
import json
from pathlib import Path

from globalManagers.ConfigManager import ConfigManager

class LLMFancyAPI:
    """LLM 文本美化窗口的 JS-API 桥接。

    后端逻辑位于 webutils/llm_fancy/（与翻译功能完全解耦）。
    长任务在后台线程执行，通过窗口 evaluate_js 分发 log/progress/done 事件。
    """

    def __init__(self):
        self._window = None
        self._cancel_event = None
        self._busy = False
        self._thread = None

    def set_window(self, window):
        self._window = window

    def get_config_value(self, key_path, default_value=None):
        return ConfigManager().get(key_path, default_value)

    def _push(self, payload: dict):
        if self._window is None:
            return
        try:
            import json as _json
            serialized = _json.dumps(payload, ensure_ascii=False)
            self._window.evaluate_js(
                f"window.__llmFancyDispatch && window.__llmFancyDispatch({serialized})"
            )
        except Exception:
            pass

    def _make_config(self, payload: dict):
        from webutils.llm_fancy.config import LLMFancyConfig
        config = payload.get('config') or payload
        return LLMFancyConfig(
            selection=config.get('selection'),
            exclusions=config.get('exclusions') or [],
            custom_prompt=config.get('custom_prompt') or '',
            custom_prompt_enabled=bool(config.get('custom_prompt_enabled')),
            max_length=int(config.get('max_length') or 20000),
            max_workers=int(config.get('max_workers') or 4),
            dedup_enabled=bool(config.get('dedup_enabled', True)),
        )

    def get_initial_state(self):
        """窗口初始数据：语言包信息、fancy 规则集列表、API 配置快照、持久化窗口配置。"""
        try:
            from webutils.llm_fancy.config import load_config
            from webutils.function_fancy import load_fancy_folder_rules
            from webutils.fancy.bus import is_bus_ruleset
            mgr = ConfigManager()
            game_path = mgr.get('game_path', '')
            package_name = ''
            try:
                lang_path = Path(game_path) / 'LimbusCompany_Data' / 'Lang'
                config_json = lang_path / 'config.json'
                if config_json.exists():
                    package_name = json.loads(
                        config_json.read_text(encoding='utf-8')
                    ).get('lang', '')
            except Exception:
                package_name = ''
            rulesets = []
            for ruleset in load_fancy_folder_rules():
                rulesets.append({
                    'name': ruleset.get('name', ''),
                    'rules': len(ruleset.get('rules', [])),
                    'is_bus': bool(is_bus_ruleset(ruleset)),
                })
            saved = load_config(mgr)
            return {
                'success': True,
                'game_configured': bool(game_path),
                'package_name': package_name,
                'rulesets': rulesets,
                'api': {
                    'raw': mgr.get('api_config', ''),
                    'encrypted': bool(mgr.get('api_crypto', False)),
                },
                'config': {
                    'selection': saved.selection,
                    'exclusions': saved.exclusions,
                    'custom_prompt': saved.custom_prompt,
                    'custom_prompt_enabled': saved.custom_prompt_enabled,
                    'max_length': saved.max_length,
                    'max_workers': saved.max_workers,
                    'dedup_enabled': saved.dedup_enabled,
                },
            }
        except Exception as exc:
            self.log_error(exc)
            return {'success': False, 'message': str(exc)}

    def validate_selection(self, selection: dict):
        from webutils.llm_fancy import validate_selection
        errors = validate_selection(selection)
        if errors:
            return {'success': False, 'message': '；'.join(errors)}
        return {'success': True}

    def save_window_config(self, payload: dict):
        try:
            from webutils.llm_fancy.config import save_config
            save_config(ConfigManager(), self._make_config(payload))
            return {'success': True}
        except Exception as exc:
            self.log_error(exc)
            return {'success': False, 'message': str(exc)}

    def scan_preview(self, payload: dict):
        """后台线程执行扫描预览，进度经事件推送，完成后分发 scan_done 事件。"""
        if self._busy:
            return {'success': False, 'message': '已有任务在执行中'}
        self._busy = True
        self._cancel_event = threading.Event()
        config = self._make_config(payload)

        def worker():
            try:
                from webutils.llm_fancy import scan_preview as _scan_preview
                result = _scan_preview(
                    config,
                    on_log=lambda msg: self._push({'type': 'log', 'message': msg}),
                    on_progress=lambda pct, msg: self._push(
                        {'type': 'progress', 'pct': pct, 'message': msg}
                    ),
                    cancel_event=self._cancel_event,
                )
                self._push({'type': 'scan_done', 'payload': {
                    'lang_dir': str(result.lang_dir),
                    'files_scanned': result.files_scanned,
                    'candidates': len(result.candidates),
                    'excluded': result.excluded,
                    'deduped': result.deduped,
                    'errors': list(result.errors),
                }})
            except Exception as exc:
                self.log_error(exc)
                self._push({'type': 'log', 'message': f'扫描失败: {exc}'})
                self._push({'type': 'scan_done', 'payload': {
                    'lang_dir': '', 'files_scanned': 0,
                    'candidates': 0, 'excluded': 0, 'deduped': 0, 'errors': [],
                    'failed': True, 'message': str(exc),
                }})
            finally:
                self._busy = False

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
        return {'success': True}

    def run_beautify(self, payload: dict):
        """后台线程执行 LLM 美化，进度经事件推送，完成后分发 run_done 事件。"""
        if self._busy:
            return {'success': False, 'message': '已有任务在执行中'}
        api_settings = payload.get('api_settings') or {}
        if not api_settings:
            return {'success': False, 'message': '缺少 LLM API 设置'}
        self._busy = True
        self._cancel_event = threading.Event()
        config = self._make_config(payload)

        def worker():
            try:
                from webutils.llm_fancy import run_beautify as _run_beautify
                result = _run_beautify(
                    config,
                    api_settings,
                    on_log=lambda msg: self._push({'type': 'log', 'message': msg}),
                    on_progress=lambda pct, msg: self._push(
                        {'type': 'progress', 'pct': pct, 'message': msg}
                    ),
                    cancel_event=self._cancel_event,
                )
                self._push({'type': 'run_done', 'payload': {
                    'success': True,
                    'candidates': result.candidates,
                    'excluded': result.excluded,
                    'deduped': result.deduped,
                    'batches': result.batches,
                    'llm_failed': result.llm_failed,
                    'unchanged': result.unchanged,
                    'changed': result.changed,
                    'ruleset_name': result.ruleset_name,
                    'ruleset_path': result.ruleset_path,
                }})
            except Exception as exc:
                from webutils.llm_fancy import LLMFancyCancelled
                if isinstance(exc, LLMFancyCancelled):
                    self._push({'type': 'run_done', 'payload': {
                        'success': True, 'cancelled': True,
                    }})
                else:
                    self.log_error(exc)
                    self._push({'type': 'run_done', 'payload': {
                        'success': False, 'message': str(exc),
                    }})
            finally:
                self._busy = False

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
        return {'success': True}

    def cancel_beautify(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
        return {'success': True}

    def log_error(self, exc):
        try:
            from globalManagers.LogManager import LogManager
            LogManager().log_error(exc)
        except Exception:
            pass
