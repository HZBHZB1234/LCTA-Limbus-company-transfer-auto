"""
翻译编排 Handler
负责翻译流程的完整编排，委托 translateFunc 和 function_translate 执行
"""

import os
import json
from . import BaseHandler


class TranslateHandler(BaseHandler):
    """翻译编排处理器"""

    def start(self, translator_config: dict, modal_id: str) -> dict:
        """开始翻译流程"""
        from webutils.function_translate import translate_main
        from webui.decorators import CancelRunning

        dump_flag = self.config.get('ui_default.translator.dump', False)
        os.environ['DUMP'] = str(dump_flag).lower()

        translate_main(
            modal_id, self.log,
            self.config.raw, translator_config,
            formating_function=self.format_api_settings
        )
        return {"success": True, "message": "翻译完成"}

    def format_api_settings(self, api_settings: dict, translator) -> dict:
        """格式化API设置，补全缺失字段并转换类型"""
        default_setting = translator.DEFAULT_API_KEY.copy() if hasattr(translator, 'DEFAULT_API_KEY') else {}
        result_settings = default_setting.copy()

        for key, value in api_settings.items():
            if key in result_settings and value != "":
                result_settings[key] = value

        describe_settings = getattr(translator, 'DESCRIBE_API_KEY', [])
        for item in describe_settings:
            setting_id = item.get('id')
            if setting_id in result_settings:
                setting_type = item.get('type')
                val = result_settings[setting_id]
                if setting_type == 'string':
                    result_settings[setting_id] = str(val)
                elif setting_type == 'number':
                    if isinstance(val, str):
                        if val.isdigit():
                            result_settings[setting_id] = int(val)
                        else:
                            result_settings[setting_id] = float(val)

        return result_settings

    def test_api(self, key: str, api_settings: dict) -> dict:
        """测试API密钥是否有效"""
        import logging
        from webutils.const_apiConfig import TKIT_MACHINE

        translator_class = TKIT_MACHINE[key]['translator']
        api_settings = self.format_api_settings(api_settings, translator_class)

        if not self.config.is_debug:
            logger_c = logging.getLogger('translatekit')
            logger_c.setLevel(logging.INFO)

        translator = translator_class(api_setting=api_settings, debug_mode=True)

        if not self.config.is_debug:
            logger_c.setLevel(logging.DEBUG)

        lang_dict = TKIT_MACHINE[key]['langCode']
        kr_result = translator.translate("안녕", lang_dict['kr'], lang_dict['zh']) if lang_dict['kr'] else '暂不支持该语言'
        en_result = translator.translate("Hello", lang_dict['en'], lang_dict['zh']) if lang_dict['en'] else '暂不支持该语言'
        jp_result = translator.translate("こんにちは", lang_dict['jp'], lang_dict['zh']) if lang_dict['jp'] else '暂不支持该语言'

        result_dict = {'kr': kr_result, 'en': en_result, 'jp': jp_result}
        self.log.log(f'API测试结果: {result_dict}')
        return {"success": True, "message": result_dict}
