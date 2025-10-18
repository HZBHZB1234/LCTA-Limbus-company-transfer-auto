# -*- coding: utf-8 -*-
import requests
import json
import hashlib
import random
import traceback

# 有道翻译错误码对照
YOUDAO_ERROR_CODE_MAP = {
    '101': '缺少必填的参数',
    '102': '不支持的语言类型',
    '103': '翻译文本过长',
    '104': '不支持的API类型',
    '105': '不支持的签名类型',
    '106': '不支持的响应类型',
    '107': '不支持的传输加密类型',
    '108': 'appKey无效',
    '109': 'batchLog格式不正确',
    '110': '无相关服务的有效实例',
    '111': '开发者账号无效',
    '201': '解密失败，可能为DES,BASE64,URLDecode的错误',
    '202': '签名检验失败',
    '203': '访问IP地址不在可访问IP列表',
    '205': '请求的接口与应用的平台类型不一致',
    '206': '因为时间戳无效导致签名错误',
    '207': '重放请求',
    '301': '辞典查询失败',
    '302': '翻译查询失败',
    '303': '服务端的其他异常',
    '401': '账户已经欠费停',
    '411': '访问频率受限,请稍后访问',
    '412': '长请求过于频繁，请稍后访问',
}

def trans_youdao(params, text, logger):
    """有道翻译服务"""
    try:
        app_key = params.get('app_key', '')
        app_secret = params.get('app_secret', '')
        
        if not app_key or not app_secret:
            return False, "App Key和App Secret不能为空"

        url = "https://openapi.youdao.com/api"
        salt = random.randint(1, 65536)
        sign_str = app_key + text + str(salt) + app_secret
        sign = hashlib.md5(sign_str.encode()).hexdigest()
        
        params_data = {
            "q": text,
            "from": "auto",
            "to": "zh-CHS",
            "appKey": app_key,
            "salt": salt,
            "sign": sign
        }

        try:
            resp = requests.get(url, params=params_data, timeout=10)
            resp_data = json.loads(resp.text)
            error_code = resp_data.get("errorCode", "-1")

            if error_code == "0":
                result = "\n".join(resp_data["translation"])
                return True, result
            elif error_code in YOUDAO_ERROR_CODE_MAP:
                error_msg = YOUDAO_ERROR_CODE_MAP[error_code]
                return False, f"有道翻译错误: errorCode-{error_code}, {error_msg}"
            else:
                return False, f"有道翻译错误: errorCode-{error_code}"
                
        except requests.exceptions.Timeout:
            return False, "有道翻译请求超时"
        except requests.exceptions.ConnectionError:
            return False, "有道翻译连接错误"
            
    except Exception as e:
        logger.error(traceback.format_exc())
        return False, f"有道翻译异常: {str(e)}"

def test_youdao(params, logger):
    """测试有道翻译服务"""
    try:
        app_key = params.get('app_key', '')
        app_secret = params.get('app_secret', '')
        
        if not app_key or not app_secret:
            return False, "App Key和App Secret不能为空"
            
        test_result = trans_youdao(params, "Hello, world!", logger)
        return test_result
        
    except Exception as e:
        return False, f"测试失败: {str(e)}"

SERVICE_DEFINITION = [
    {
        "name": "有道翻译",
        "service": "youdao",
        "description": "有道智云翻译服务",
        "api_params": [
            {"key": "app_key", "label": "App Key", "type": "entry"},
            {"key": "app_secret", "label": "App Secret", "type": "password"}
        ],
        "accept": "text",
        "term": False,
        "layer": {
            "split": [True, "\n"],
            "need_transfer": True,
            "using_inner_pool": True,
            "using_inner_test": True,
            "need_init": False,
            "max_text": {
                "able": True,
                "split_file": False,
                "type": "character",
                "value": 5000
            },
            "max_requests": {
                "able": True,
                "value": 5
            },
            "retry_set": {
                "able": True,
                "value": 3,
                "fall_lang": "en"
            }
        },
        "method": trans_youdao,
        "test_function": test_youdao,
        "init_function": None
    }
]