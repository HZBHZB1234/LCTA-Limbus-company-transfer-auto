import translatekit as tkit
from translatekit import (
    TranslationConfig, TranslationError, ConfigurationError, APIError
)

TRANSLATOR_TRANS = {
    '百度翻译服务': tkit.BaiduTranslator,
    'Google翻译服务': tkit.GoogleTranslator,
    'DeepL翻译服务': tkit.DeepLTranslator,
    'Microsoft翻译服务': tkit.MicrosoftTranslator,
    'Yandex Cloud翻译服务': tkit.YandexTranslator,
    'Libre翻译服务': tkit.LibreTranslator,
    'MyMemory翻译服务': tkit.MyMemoryTranslator,
    'Papago翻译服务': tkit.PapagoTranslator,
    'Linguee翻译服务': tkit.LingueeTranslator,
    'Qcri翻译服务': tkit.QcriTranslator,
    '腾讯翻译服务': tkit.TencentTranslator,
    '有道翻译服务': tkit.YoudaoTranslator,
    '思知对话翻译服务': tkit.SizhiTranslator,
    '空翻译器(使用原文)': tkit.NullTranslator
}
