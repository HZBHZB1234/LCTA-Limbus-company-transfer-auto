"""
文本美化 Handler
处理文本美化规则的获取和执行
"""

import json
from pathlib import Path
from . import BaseHandler


class FancyHandler(BaseHandler):
    """文本美化处理器"""

    @property
    def _builtin_fancy_config(self):
        from webutils.builtinFancy import fancy as builtinFancyConfig
        return builtinFancyConfig

    def get_rulesets(self) -> dict:
        """获取美化规则集"""
        user_fancy_raw = self.config.get('user_fancy', '[]')
        fancy_allow_raw = self.config.get('fancy_allow', '{}')

        try:
            user_fancy = json.loads(user_fancy_raw) if isinstance(user_fancy_raw, str) else user_fancy_raw
        except (json.JSONDecodeError, TypeError):
            user_fancy = []

        try:
            fancy_allow = json.loads(fancy_allow_raw) if isinstance(fancy_allow_raw, str) else fancy_allow_raw
        except (json.JSONDecodeError, TypeError):
            fancy_allow = {
                "技能文本美化(FL Like)": True,
                "气泡文本渐变(FL Like)": True,
                "EGO文本渐变(FL Like)": True
            }

        return {
            'success': True,
            'data': {
                'builtin': self._builtin_fancy_config,
                'user': user_fancy,
                'enabled': fancy_allow
            }
        }

    def execute(self, config_list: list, enable_map: dict) -> dict:
        """执行文本美化"""
        from webutils.function_fancy import fancy_main

        game_path = self.config.get('game_path', '')
        if not game_path:
            return {"success": False, "message": "请先设置游戏路径"}

        lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang'
        try:
            config_lang = json.loads(
                (lang_path / 'config.json').read_text(encoding='utf-8')
            ).get('lang', '')
        except Exception:
            return {"success": False, "message": "获取当前安装汉化包失败"}

        fancy_main(
            game_path, config_lang,
            [i for i in config_list if enable_map.get(i.get('name', ''), False)]
        )
        return {"success": True, "message": "文本美化完成"}
