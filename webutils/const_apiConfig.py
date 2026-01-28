import translatekit as tkit
from typing import Dict, List, Type, TYPE_CHECKING
from copy import deepcopy
if TYPE_CHECKING:
    from translatekit.base import Metadata

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

def get_dict_by_matadata(metadata: 'Metadata') -> Dict[str, str]:
    return {
        "console_url": metadata.console_url,
        "description": metadata.description,
        "documentation_url": metadata.documentation_url,
        "short_description": metadata.short_description,
        "usage_documentation": metadata.usage_documentation
    }

'''
api-setting示例
[
    {
        "id": "appid",
        "name": "百度翻译appid",
        "type": "string",
        "required": True,
        "description": "百度翻译appid"
    },
    {
        "id": "appkey",
        "name": "百度翻译appkey",
        "type": "string",
        "required": True,
        "description": "百度翻译appkey"
    },
    {
        "id": "needIntervene",
        "name": "是否需要使用术语库",
        "type": "boolean",
        "required": False,
        "description": "是否需要使用术语库，默认为False"
    }
]
参数ID：{describe["id"]}
参数名称：{describe["name"]}
参数是否必填：{describe["required"]}
参数类型：{describe["type"]}
参数描述：{describe["description"]}
'''

TKIT_MACHINE = {
    "百度翻译服务": {
        "metadata": get_dict_by_matadata(tkit.BaiduTranslator.METADATA),
        "api-setting": tkit.BaiduTranslator.DESCRIBE_API_KEY,
        "translator": tkit.BaiduTranslator,
        "langCode": {
            'zh': 'zh','en': 'en', 'kr': 'kor', 'jp': 'jp'
            }},
    "Google翻译服务": {
        "metadata": get_dict_by_matadata(tkit.GoogleTranslator.METADATA),
        "api-setting": tkit.GoogleTranslator.DESCRIBE_API_KEY,
        "translator": tkit.GoogleTranslator,
        "langCode": {
            'zh': 'zh-CN','en': 'en', 'kr': 'ko', 'jp': 'ja'
            }},
    "DeepL翻译服务": {
        "metadata": get_dict_by_matadata(tkit.DeepLTranslator.METADATA),
        "api-setting": tkit.DeepLTranslator.DESCRIBE_API_KEY,
        "translator": tkit.DeepLTranslator,
        "langCode": {
            'zh': 'zh','en': 'en', 'kr': 'ko', 'jp': 'ja'
            }},
    "Microsoft翻译服务": {
        "metadata": get_dict_by_matadata(tkit.MicrosoftTranslator.METADATA),
        "api-setting": tkit.MicrosoftTranslator.DESCRIBE_API_KEY,
        "translator": tkit.MicrosoftTranslator,
        "langCode": {
            'zh': 'zh-hans','en': 'en', 'kr': 'ko', 'jp': 'ja'
            }},
    "Yandex Cloud翻译服务": {
        "metadata": get_dict_by_matadata(tkit.YandexTranslator.METADATA),
        "api-setting": tkit.YandexTranslator.DESCRIBE_API_KEY,
        "translator": tkit.YandexTranslator,
        "langCode": {
            'zh': 'zh','en': 'en', 'kr': 'ko', 'jp': 'ja'
            }},
    "Libre翻译服务": {
        "metadata": get_dict_by_matadata(tkit.LibreTranslator.METADATA),
        "api-setting": tkit.LibreTranslator.DESCRIBE_API_KEY,
        "translator": tkit.LibreTranslator,
        "langCode": {
            'zh': 'zh-Hans','en': 'en', 'kr': 'ko', 'jp': 'ja'
            }},
    "MyMemory翻译服务": {
        "metadata": get_dict_by_matadata(tkit.MyMemoryTranslator.METADATA),
        "api-setting": tkit.MyMemoryTranslator.DESCRIBE_API_KEY,
        "translator": tkit.MyMemoryTranslator,
        "langCode": {
            'zh': 'zh-CN','en': 'en-GB', 'kr': 'ko-KR', 'jp': 'ja-JP'
            }},
    "Papago翻译服务": {
        "metadata": get_dict_by_matadata(tkit.PapagoTranslator.METADATA),
        "api-setting": tkit.PapagoTranslator.DESCRIBE_API_KEY,
        "translator": tkit.PapagoTranslator,
        "langCode": {
            'zh': 'zh-CN','en': 'en', 'kr': 'ko', 'jp': 'ja'
            }},
    "Linguee翻译服务": {
        "metadata": get_dict_by_matadata(tkit.LingueeTranslator.METADATA),
        "api-setting": tkit.LingueeTranslator.DESCRIBE_API_KEY,
        "translator": tkit.LingueeTranslator,
        "langCode": {
            'zh': 'chinese','en': 'english', 'kr': '', 'jp': ''
            }},
    "腾讯翻译服务": {
        "metadata": get_dict_by_matadata(tkit.TencentTranslator.METADATA),
        "api-setting": tkit.TencentTranslator.DESCRIBE_API_KEY,
        "translator": tkit.TencentTranslator,
        "langCode": {
            'zh': 'zh','en': 'en', 'ko': 'kor', 'jp': ''
            }},
    "有道翻译服务": {
        "metadata": get_dict_by_matadata(tkit.YoudaoTranslator.METADATA),
        "api-setting": tkit.YoudaoTranslator.DESCRIBE_API_KEY,
        "translator": tkit.YoudaoTranslator,
        "langCode": {
            'zh': 'zh-CHS','en': 'en', 'kr': 'ko', 'jp': 'ja'
            }},
    "思知对话翻译服务": {
        "metadata": get_dict_by_matadata(tkit.SizhiTranslator.METADATA),
        "api-setting": tkit.SizhiTranslator.DESCRIBE_API_KEY,
        "translator": tkit.SizhiTranslator,
        "langCode": {
            'zh': 'zh','en': 'en', 'kr': 'kor', 'jp': 'jp'
            }},
    "空翻译器(使用原文)": {
        "metadata": get_dict_by_matadata(tkit.NullTranslator.METADATA),
        "api-setting": tkit.NullTranslator.DESCRIBE_API_KEY,
        "translator": tkit.NullTranslator,
        "langCode": {
            'zh': 'zh','en': 'en', 'kr': 'kor', 'jp': 'jp'
            }},
    "LLM通用翻译服务": {
        "metadata": get_dict_by_matadata(tkit.LLMGeneralTranslator.METADATA),
        "api-setting": tkit.LLMGeneralTranslator.DESCRIBE_API_KEY,
        "translator": tkit.LLMGeneralTranslator,
        "langCode": {
            'zh': 'zh','en': 'en', 'kr': 'kor', 'jp': 'jp'
            }}
}

LLM_TRANSLATOR: Dict[str, dict] = {
    # 官方平台
    "OpenAI 官方": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o"
    },
    # 微软 Azure 托管 OpenAI
    "Azure OpenAI": {
        "base_url": "https://{your-resource-name}.openai.azure.com/openai/deployments/{your-deployment-name}/v1",
        "model": "gpt-4o"
    },
    # 国内主流平台
    "智谱 AI（ChatGLM）": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4"
    },
    "字节跳动 火山引擎（豆包）": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-pro"
    },
    "百度 文心一言（千帆平台）": {
        "base_url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions",
        "model": "ernie-4.0-turbo"
    },
    "阿里云 通义千问（灵积平台）": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-turbo"
    },
    "腾讯云 混元大模型": {
        "base_url": "https://hunyuan.cloud.tencent.com/v1",
        "model": "hunyuan-pro"
    },
    "DeepSeek（深度求索）": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat"
    },
    # 国外其他知名平台
    "Anthropic（Claude）": {
        "base_url": "https://api.anthropic.com/v1",  # 注：原生API略有差异，第三方兼容层可使用 https://api.chatanywhere.tech/v1
        "model": "claude-3-opus"
    },
    "Groq（高速推理）": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama3-70b-8192"
    }
}

TKIT_MACHINE_OBJECT = deepcopy(TKIT_MACHINE)

for value in TKIT_MACHINE_OBJECT.values():
    value.pop("translator")