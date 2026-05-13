"""翻译插件 —— AI 辅助翻译游戏文本。"""

import os
import logging
from typing import TYPE_CHECKING

from webui.app import api_expose, CancelRunning
from globalManagers.logManager import logManager
from globalManagers.configManager import configManager
from webutils.function_translate import translate_main
from webutils.const_apiConfig import TKIT_MACHINE

if TYPE_CHECKING:
    from translatekit.base import TranslatorBase


@api_expose
def start_translation(framework, translator_config: dict, modal_id: str = None):
    """开始翻译流程。"""
    os.environ['DUMP'] = str(
        configManager.get("ui_default.translator.dump", False)
    ).lower()
    translate_main(
        modal_id, logManager,
        configManager.config, translator_config,
        formating_function=format_api_settings
    )


@api_expose
def test_api(framework, key: str, api_settings: dict) -> dict:
    """测试 API 密钥是否有效。"""
    try:
        translator_info = TKIT_MACHINE[key]
        translator_cls = translator_info['translator']
        api_settings = format_api_settings(framework, api_settings, translator_cls)

        debug_mode = configManager.get("debug", False)
        if not debug_mode:
            logger_c = logging.getLogger('translatekit')
            logger_c.setLevel(logging.INFO)

        translator = translator_cls(api_setting=api_settings, debug_mode=True)

        if not debug_mode:
            logger_c.setLevel(logging.DEBUG)

        lang_dict = translator_info['langCode']
        kr_result = translator.translate("안녕", lang_dict['kr'], lang_dict['zh']) if lang_dict.get('kr') else '暂不支持该语言'
        en_result = translator.translate("Hello", lang_dict['en'], lang_dict['zh']) if lang_dict.get('en') else '暂不支持该语言'
        jp_result = translator.translate("こんにちは", lang_dict['jp'], lang_dict['zh']) if lang_dict.get('jp') else '暂不支持该语言'

        result_dict = {'kr': kr_result, 'en': en_result, 'jp': jp_result}
        logManager.info(f'API测试结果: {result_dict}')
        return {"success": True, "message": result_dict}
    except Exception as e:
        logManager.exception(e)
        return {"success": False, "message": str(e)}


@api_expose
def format_api_settings(framework, api_settings: dict, translator: 'TranslatorBase') -> dict:
    """将前端传来的 API 设置格式化为翻译器需要的格式。"""
    default_setting = translator.DEFAULT_API_KEY.copy()
    result_settings = default_setting.copy()
    for key, value in api_settings.items():
        if key in result_settings and value != "":
            result_settings[key] = value

    describe_settings = translator.DESCRIBE_API_KEY
    for item in describe_settings:
        setting_id = item.get('id')
        if setting_id in result_settings:
            setting_type = item.get('type')
            if setting_type == 'string':
                result_settings[setting_id] = str(result_settings[setting_id])
            elif setting_type == 'number':
                if isinstance(result_settings[setting_id], str):
                    if result_settings[setting_id].isdigit():
                        result_settings[setting_id] = int(result_settings[setting_id])
                    else:
                        result_settings[setting_id] = float(result_settings[setting_id])
    return result_settings
