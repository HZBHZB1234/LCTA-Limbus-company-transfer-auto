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
    ("DeepL翻译", "deepl")
]
custom_=[
    ('自定义','custom')
]