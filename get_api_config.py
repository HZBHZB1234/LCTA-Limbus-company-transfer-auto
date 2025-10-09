TRANSLATION_SERVICES = {
    "baidu": [
        {"key": "appid", "label": "APP ID", "type": "entry"},
        {"key": "secret", "label": "密钥", "type": "password"}
    ],
    "tencent": [
        {"key": "secret_id", "label": "SecretId", "type": "entry"},
        {"key": "secret_key", "label": "SecretKey", "type": "password"}
    ],
    "caiyun": [
        {"key": "token", "label": "Token", "type": "password"}
    ],
    "youdao": [
        {"key": "app_key", "label": "AppKey", "type": "entry"},
        {"key": "app_secret", "label": "密钥", "type": "password"}
    ],
    "xiaoniu": [
        {"key": "apikey", "label": "API Key", "type": "password"}
    ],
    "aliyun": [
        {"key": "access_key_id", "label": "AccessKeyId", "type": "entry"},
        {"key": "access_key_secret", "label": "AccessKeySecret", "type": "password"}
    ],
    "huoshan": [
        {"key": "ak", "label": "Access Key", "type": "entry"},
        {"key": "sk", "label": "Secret Key", "type": "password"}
    ],
    "google": [
        {"key": "key", "label": "API密钥", "type": "password"}
    ],
    "deepl": [
        {"key": "key", "label": "API密钥", "type": "password"}
    ],
    # 为LLM翻译预留的多行参数配置示例
    "llm_custom": [
        {"key": "api_key", "label": "API密钥", "type": "password"},
        {"key": "base_url", "label": "API地址", "type": "entry"},
        {"key": "model", "label": "模型名称", "type": "entry"},
        {
            "key": "prompt", 
            "label": "系统提示词", 
            "type": "entry", 
            "multiline": True,
            "description": "定义AI的翻译行为和要求"
        },
        {
            "key": "parameters", 
            "label": "额外参数", 
            "type": "entry", 
            "multiline": True,
            "description": "JSON格式的额外参数配置"
        }
    ]
}

services_ = [
    ("百度翻译", "baidu"),
    ("腾讯翻译", "tencent"),
    ("彩云翻译", "caiyun"),
    ("有道翻译", "youdao"),
    ("小牛翻译", "xiaoniu"),
    ("阿里云翻译", "aliyun"),
    ("火山翻译", "huoshan"),
    ("Google翻译", "google"),
    ("DeepL翻译", "deepl"),
    ("LLM翻译", "llm_custom")  # 添加LLM翻译选项
]

custom_=[
    ('自定义','custom')
]

default_service_list=[i for (_,i) in services_]