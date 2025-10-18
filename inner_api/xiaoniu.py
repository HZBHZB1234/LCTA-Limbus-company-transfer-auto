# -*- coding: utf-8 -*-
import urllib.request
import urllib.parse
import json
import traceback

# 小牛错误码
XIAONIU_ERROR_CODE_MAP = {
    "10000": "输入为空",
    "10001": "请求频繁，超出QPS限制",
    "10003": "请求字符串长度超过限制",
    "10005": "源语编码有问题，非UTF-8",
    "13001": "字符流量不足或者没有访问权限",
    "13002": "apikey参数不可以是空",
    "13003": "内容过滤异常",
    "13007": "语言不支持",
    "13008": "请求处理超时",
    "14001": "分句异常",
    "14002": "分词异常",
    "14003": "后处理异常",
    "14004": "对齐失败，不能够返回正确的对应关系",
    "000000": "请求参数有误，请检查参数",
    "000001": "Content-Type不支持【multipart/form-data】"
}

def trans_xiaoniu(params, text, logger):
    """小牛翻译服务"""
    try:
        apikey = params.get('apikey', '')
        language = params.get('language', 'auto')
        
        if not apikey:
            return False, "API Key不能为空"

        url = "http://api.niutrans.com/NiuTransServer/translation?"
        
        # 语言映射
        language_map = {
            "JAP": "ja",
            "ENG": "en",
            "KOR": "ko", 
            "RU": "ru",
            "auto": "auto"
        }
        if language in language_map:
            language = language_map[language]

        data = {
            "from": language,
            "to": "zh",
            "apikey": apikey,
            "src_text": text
        }

        try:
            data_encoded = urllib.parse.urlencode(data)
            req_url = url + "&" + data_encoded
            response = urllib.request.urlopen(req_url, timeout=10)
            response_data = json.loads(response.read().decode())
            
            if "tgt_text" in response_data:
                result = response_data["tgt_text"]
                return True, result
            else:
                error_code = response_data.get("error_code", "unknown")
                error_msg = XIAONIU_ERROR_CODE_MAP.get(error_code, response_data.get("error_msg", "未知错误"))
                return False, f"小牛翻译错误: error_code-{error_code}, {error_msg}"
                
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                return False, "小牛翻译请求超时"
            else:
                return False, f"小牛翻译网络错误: {str(e)}"
                
    except Exception as e:
        logger.error(traceback.format_exc())
        return False, f"小牛翻译异常: {str(e)}"

def test_xiaoniu(params, logger):
    """测试小牛翻译服务"""
    try:
        apikey = params.get('apikey', '')
        
        if not apikey:
            return False, "API Key不能为空"
            
        test_result = trans_xiaoniu(params, "Hello, world!", logger)
        return test_result
        
    except Exception as e:
        return False, f"测试失败: {str(e)}"

SERVICE_DEFINITION = [
    {
        "name": "小牛翻译",
        "service": "xiaoniu",
        "description": "小牛翻译API服务",
        "api_params": [
            {"key": "apikey", "label": "API Key", "type": "password"},
            {"key": "language", "label": "源语言", "type": "entry"}
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
        "method": trans_xiaoniu,
        "test_function": test_xiaoniu,
        "init_function": None
    }
]