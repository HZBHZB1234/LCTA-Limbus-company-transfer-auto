# -*- coding: utf-8 -*-
import time
import urllib.parse
import hashlib
import hmac
import base64
import requests
import traceback

def trans_aliyun(params, text, logger):
    """阿里云翻译服务"""
    try:
        access_key_id = params.get('access_key_id', '')
        access_key_secret = params.get('access_key_secret', '')
        source_language = params.get('source_language', 'auto')
        
        if not access_key_id or not access_key_secret:
            return False, "Access Key ID和Secret不能为空"

        # 语种映射
        source_language_map = {
            "JAP": "ja",
            "ENG": "en", 
            "KOR": "ko",
            "RU": "ru",
            "auto": "auto"
        }
        if source_language in source_language_map:
            source_language = source_language_map[source_language]

        # 请求参数
        api_url = "https://mt.aliyuncs.com"
        api_version = "2018-10-12"
        format_type = "text"
        
        # 构建请求参数
        request_params = {
            "AccessKeyId": access_key_id,
            "Action": "Translate",
            "FormatType": format_type,
            "Version": api_version,
            "SourceLanguage": source_language,
            "TargetLanguage": "zh",
            "SourceText": text,
            "Scene": "general",
            "Format": "JSON",
            "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "SignatureMethod": "HMAC-SHA1",
            "SignatureVersion": "1.0",
            "SignatureNonce": str(time.time()),
        }

        # 生成签名
        try:
            sorted_params = sorted(request_params.items(), key=lambda x: x[0])
            canonicalized_query_string = ""
            for k, v in sorted_params:
                canonicalized_query_string += "&" + urllib.parse.quote(k, safe="") + "=" + urllib.parse.quote(v, safe="")
            
            string_to_sign = "GET&%2F&" + urllib.parse.quote(canonicalized_query_string[1:], safe="")
            hmac_sha1 = hmac.new((access_key_secret + "&").encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1)
            signature = base64.b64encode(hmac_sha1.digest()).decode("utf-8")
            request_params["Signature"] = signature
            
        except Exception as e:
            return False, f"生成签名失败: {str(e)}"

        # 发送请求
        try:
            response = requests.get(api_url, params=request_params, timeout=10)
            response_data = response.json()
            
            if response_data.get("Code", "") == "200":
                result = response_data.get("Data", {}).get("Translated", "")
                return True, result
            else:
                error_msg = response_data.get("Message", "未知错误")
                return False, f"阿里云翻译错误: {error_msg}"
                
        except requests.exceptions.Timeout:
            return False, "阿里云翻译请求超时"
        except requests.exceptions.ConnectionError:
            return False, "阿里云翻译连接错误"
            
    except Exception as e:
        logger.error(traceback.format_exc())
        return False, f"阿里云翻译异常: {str(e)}"

def test_aliyun(params, logger):
    """测试阿里云翻译服务"""
    try:
        access_key_id = params.get('access_key_id', '')
        access_key_secret = params.get('access_key_secret', '')
        
        if not access_key_id or not access_key_secret:
            return False, "Access Key ID和Secret不能为空"
            
        test_result = trans_aliyun(params, "Hello, world!", logger)
        return test_result
        
    except Exception as e:
        return False, f"测试失败: {str(e)}"

SERVICE_DEFINITION = [
    {
        "name": "阿里云翻译",
        "service": "aliyun",
        "description": "阿里云机器翻译服务",
        "api_params": [
            {"key": "access_key_id", "label": "Access Key ID", "type": "entry"},
            {"key": "access_key_secret", "label": "Access Key Secret", "type": "password"},
            {"key": "source_language", "label": "源语言", "type": "entry"}
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
        "method": trans_aliyun,
        "test_function": test_aliyun,
        "init_function": None
    }
]