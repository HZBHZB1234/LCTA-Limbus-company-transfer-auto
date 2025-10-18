# -*- coding: utf-8 -*-
import requests
import json
import datetime
import hashlib
import hmac
from urllib.parse import quote
import traceback

def norm_query(params):
    """规范化查询参数"""
    query = ""
    for key in sorted(params.keys()):
        if type(params[key]) == list:
            for k in params[key]:
                query = (query + quote(key, safe="-_.~") + "=" + quote(k, safe="-_.~") + "&")
        else:
            query = (query + quote(key, safe="-_.~") + "=" + quote(params[key], safe="-_.~") + "&")
    query = query[:-1]
    return query.replace("+", "%20")

def hmac_sha256(key: bytes, content: str):
    """sha256 非对称加密"""
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()

def hash_sha256(content: str):
    """sha256 hash算法"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def build_huoshan_headers(ak, sk, text):
    """构建火山翻译请求头"""
    credential = {
        "access_key_id": ak,
        "secret_access_key": sk,
        "service": "translate",
        "region": "cn-north-1",
    }
    
    request_param = {
        "body": json.dumps({
            "TargetLanguage": "zh",
            'TextList': text.split("\n"),
        }),
        "host": "translate.volcengineapi.com",
        "path": "/",
        "method": "POST",
        "content_type": "application/json",
        "date": datetime.datetime.utcnow(),
        "query": {"Action": "TranslateText", "Version": "2020-06-01"},
    }
    
    x_date = request_param["date"].strftime("%Y%m%dT%H%M%SZ")
    short_x_date = x_date[:8]
    x_content_sha256 = hash_sha256(request_param["body"])
    
    sign_result = {
        "Host": request_param["host"],
        "X-Content-Sha256": x_content_sha256,
        "X-Date": x_date,
        "Content-Type": request_param["content_type"],
    }
    
    signed_headers_str = ";".join(["content-type", "host", "x-content-sha256", "x-date"])
    canonical_request_str = "\n".join([
        request_param["method"].upper(),
        request_param["path"],
        norm_query(request_param["query"]),
        "\n".join([
            "content-type:" + request_param["content_type"],
            "host:" + request_param["host"],
            "x-content-sha256:" + x_content_sha256,
            "x-date:" + x_date,
        ]),
        "",
        signed_headers_str,
        x_content_sha256,
    ])
    
    hashed_canonical_request = hash_sha256(canonical_request_str)
    credential_scope = "/".join([short_x_date, credential["region"], credential["service"], "request"])
    string_to_sign = "\n".join(["HMAC-SHA256", x_date, credential_scope, hashed_canonical_request])

    k_date = hmac_sha256(credential["secret_access_key"].encode("utf-8"), short_x_date)
    k_region = hmac_sha256(k_date, credential["region"])
    k_service = hmac_sha256(k_region, credential["service"])
    k_signing = hmac_sha256(k_service, "request")
    signature = hmac_sha256(k_signing, string_to_sign).hex()

    sign_result["Authorization"] = "HMAC-SHA256 Credential={}, SignedHeaders={}, Signature={}".format(
        credential["access_key_id"] + "/" + credential_scope,
        signed_headers_str,
        signature,
    )

    return sign_result

def trans_huoshan(params, text, logger):
    """火山翻译服务"""
    try:
        ak = params.get('access_key', '')
        sk = params.get('secret_key', '')
        
        if not ak or not sk:
            return False, "Access Key和Secret Key不能为空"

        api_params = {
            "Action": "TranslateText",
            "Version": "2020-06-01"
        }
        
        body = {
            "TargetLanguage": "zh",
            "TextList": text.split("\n")
        }
        
        url = "https://translate.volcengineapi.com/"

        try:
            headers = build_huoshan_headers(ak, sk, text)
            response = requests.post(
                url=url,
                headers=headers,
                params=api_params,
                data=json.dumps(body),
                timeout=10
            )
            response_data = response.json()

            if "TranslationList" in response_data:
                text_list = []
                for val in response_data["TranslationList"]:
                    if val.get("Translation", ""):
                        text_list.append(val["Translation"])
                result = "\n".join(text_list)
                return True, result
            else:
                error_map = response_data.get("ResponseMetadata", {}).get("Error", {})
                code_n = error_map.get("CodeN", 0)
                code = error_map.get("Code", "")
                message = error_map.get("Message", "")
                if code_n and code and message:
                    return False, f"火山翻译错误: CodeN-{code_n}, Code-{code}, {message}"
                else:
                    return False, f"火山翻译错误: {response_data}"
                    
        except requests.exceptions.Timeout:
            return False, "火山翻译请求超时"
        except requests.exceptions.ConnectionError:
            return False, "火山翻译连接错误"
            
    except Exception as e:
        logger.error(traceback.format_exc())
        return False, f"火山翻译异常: {str(e)}"

def test_huoshan(params, logger):
    """测试火山翻译服务"""
    try:
        ak = params.get('access_key', '')
        sk = params.get('secret_key', '')
        
        if not ak or not sk:
            return False, "Access Key和Secret Key不能为空"
            
        test_result = trans_huoshan(params, "Hello, world!", logger)
        return test_result
        
    except Exception as e:
        return False, f"测试失败: {str(e)}"

SERVICE_DEFINITION = [
    {
        "name": "火山翻译",
        "service": "huoshan",
        "description": "火山引擎翻译服务",
        "api_params": [
            {"key": "access_key", "label": "Access Key", "type": "entry"},
            {"key": "secret_key", "label": "Secret Key", "type": "password"}
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
        "method": trans_huoshan,
        "test_function": test_huoshan,
        "init_function": None
    }
]