import translatekit as tkit
from translatekit import (
    TranslationConfig, TranslationError, ConfigurationError, APIError
)


TKIT_SERVER = [
    'BaiduTranslator',
    'GoogleTranslator',
    'DeepLTranslator',
    'MicrosoftTranslator',
    'YandexTranslator',
    'LibreTranslator',
    'MyMemoryTranslator',
    'PapagoTranslator',
    'LingueeTranslator',
    'QcriTranslator',
    'TencentTranslator',
    'YoudaoTranslator',
    'SizhiTranslator',
    'LLMGeneralTranslator',
    'NullTranslator',
]

TKIT_MACHINE = {
    "百度翻译服务": {
        "metadata": tkit.BaiduTranslator.METADATA,
        "translator": tkit.BaiduTranslator},
    "Google翻译服务": {
        "metadata": tkit.GoogleTranslator.METADATA,
        "translator": tkit.GoogleTranslator},
    "DeepL翻译服务": {
        "metadata": tkit.DeepLTranslator.METADATA,
        "translator": tkit.DeepLTranslator},
    "Microsoft翻译服务": {
        "metadata": tkit.MicrosoftTranslator.METADATA,
        "translator": tkit.MicrosoftTranslator},
    "Yandex Cloud翻译服务": {
        "metadata": tkit.YandexTranslator.METADATA,
        "translator": tkit.YandexTranslator},
    "Libre翻译服务": {
        "metadata": tkit.LibreTranslator.METADATA,
        "translator": tkit.LibreTranslator},
    "MyMemory翻译服务": {
        "metadata": tkit.MyMemoryTranslator.METADATA,
        "translator": tkit.MyMemoryTranslator},
    "Papago翻译服务": {
        "metadata": tkit.PapagoTranslator.METADATA,
        "translator": tkit.PapagoTranslator},
    "Linguee翻译服务": {
        "metadata": tkit.LingueeTranslator.METADATA,
        "translator": tkit.LingueeTranslator},
    "Qcri翻译服务": {
        "metadata": tkit.QcriTranslator.METADATA,
        "translator": tkit.QcriTranslator},
    "腾讯翻译服务": {
        "metadata": tkit.TencentTranslator.METADATA,
        "translator": tkit.TencentTranslator},
    "有道翻译服务": {
        "metadata": tkit.YoudaoTranslator.METADATA,
        "translator": tkit.YoudaoTranslator},
    "思知对话翻译服务": {
        "metadata": tkit.SizhiTranslator.METADATA,
        "translator": tkit.SizhiTranslator},
    "空翻译器(使用原文)": {
        "metadata": tkit.NullTranslator.METADATA,
        "translator": tkit.NullTranslator}
}
