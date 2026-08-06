# -*- coding: utf-8 -*-
"""LCTA_API 翻译相关：开始翻译、API 密钥测试、专有词汇抓取。"""
import os
import logging
from typing import TYPE_CHECKING

from globalManagers.ConfigManager import ConfigManager
from webutils.function_translate import translate_main
from webui.app_api.exceptions import CancelRunning

if TYPE_CHECKING:
    from translatekit.base import TranslatorBase

class TranslatorMixin:

    def start_translation(self, translator_config: dict, modal_id= "false"):
        """开始翻译"""
        try:
            self.add_modal_log("开始翻译...", modal_id)
            os.environ['DUMP'] = str(ConfigManager().get('ui_default.translator.dump', False)).lower()
            translate_main(modal_id,
                           translator_config,
                           formating_function=self.format_api_settings)
            self.add_modal_log("翻译完成", modal_id)
            return {"success": True, "message": "翻译完成"}
        except CancelRunning:
            self.log('用户已取消翻译流程')
            self.del_modal_list(modal_id)
            return {"success": False, "message": "已取消"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def format_api_settings(self, api_settings: dict, translator: 'TranslatorBase') -> dict:
        default_setting = translator.DEFAULT_API_KEY
        result_settings = default_setting.copy()
        for key, value in api_settings.items():
            if key in result_settings and value != "":
                result_settings[key] = value
        describe_settings = translator.DESCRIBE_API_KEY
        for i in describe_settings:
            setting_id = i.get('id')
            if setting_id in result_settings:
                setting_type = i.get('type')
                if setting_type == 'string':
                    result_settings[setting_id] = str(result_settings[setting_id])
                elif setting_type == 'number':
                    if isinstance(result_settings[setting_id], str):
                        if result_settings[setting_id].isdigit():
                            result_settings[setting_id] = int(result_settings[setting_id])
                        else:
                            result_settings[setting_id] = float(result_settings[setting_id])
        return result_settings

    def test_api(self, key: str, api_settings: dict) -> dict:
        """测试API密钥是否有效"""
        try:
            self.log(f"开始测试API密钥: {key}")
            translator: 'TranslatorBase' = self.TKIT_MACHINE[key]['translator']
            api_settings = self.format_api_settings(
                api_settings, translator)
            if not self.debug_mode:
                logger_c = logging.getLogger('translatekit')
                logger_c.setLevel(logging.INFO)
                self.log_manager.log('隐藏参数输出')
            translator = translator(
                api_setting=api_settings, debug_mode=True)
            if not self.debug_mode:
                logger_c.setLevel(logging.DEBUG)
            lang_dict = self.TKIT_MACHINE[key]['langCode']
            kr_result = translator.translate("안녕", lang_dict['kr'], lang_dict['zh']) if lang_dict['kr'] else '暂不支持该语言'
            en_result = translator.translate("Hello", lang_dict['en'], lang_dict['zh']) if lang_dict['en'] else '暂不支持该语言'
            jp_result = translator.translate("こんにちは", lang_dict['jp'], lang_dict['zh']) if lang_dict['jp'] else '暂不支持该语言'
            self.log("API密钥测试成功")
            result_dict = {
                'kr': kr_result,
                'en': en_result,
                'jp': jp_result
            }
            self.log(f'结果:{result_dict}')
            return {"success": True, "message": result_dict}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}

    def fetch_proper_nouns(self, modal_id= "false"):
        """获取专有词汇"""
        try:
            self.add_modal_log("开始抓取专有词汇...", modal_id)
            proper_config = ConfigManager().get('ui_default.proper', {})
            function_fetch_main(
                modal_id,
                **proper_config
            )
            self.add_modal_log("专有词汇抓取成功", modal_id)
            return {"success": True, "message": "专有词汇抓取成功"}
        except Exception as e:
            self.log_error(e)
            return {"success": False, "message": str(e)}
