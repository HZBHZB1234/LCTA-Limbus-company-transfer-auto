# -*- coding: utf-8 -*-
import requests
import json
import traceback

def trans_caiyun(params, text, logger):
    """彩云翻译服务"""
    try:
        token = params.get('token', '')
        
        if not token:
            return False, "Token不能为空"

        url = "http://api.interpreter.caiyunai.com/v1/translator"
        payload = {
            "source": text.split("\n"),
            "trans_type": "auto2zh",
            "request_id": "demo",
            "detect": True,
        }
        headers = {
            "content-type": "application/json",
            "x-authorization": "token " + token,
        }
        proxies = {"http": None, "https": None}

        try:
            resp = requests.request("POST", url, data=json.dumps(payload), headers=headers, proxies=proxies, timeout=10)
            resp_data = json.loads(resp.text)
            
            if "target" in resp_data:
                # 翻译成功
                result = "\n".join(resp_data["target"])
                return True, result
            else:
                # 翻译失败
                message = resp_data.get("message", "未知错误")
                if message == "Invalid token":
                    message = "无效的令牌"
                return False, f"彩云翻译错误: {message}"
                
        except requests.exceptions.Timeout:
            return False, "彩云翻译请求超时"
        except requests.exceptions.ConnectionError:
            return False, "彩云翻译连接错误"
            
    except Exception as e:
        logger.error(traceback.format_exc())
        return False, f"彩云翻译异常: {str(e)}"

def test_caiyun(params, logger):
    """测试彩云翻译服务"""
    try:
        token = params.get('token', '')
        
        if not token:
            return False, "Token不能为空"
            
        test_result = trans_caiyun(params, "Hello, world!", logger)
        return test_result
        
    except Exception as e:
        return False, f"测试失败: {str(e)}"

SERVICE_DEFINITION = [
    {
        "name": "彩云翻译", 
        "service": "caiyun",
        "description": "彩云小译API服务",
        "api_params": [
            {"key": "token", "label": "Token", "type": "password"}
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
                "value": 3
            },
            "retry_set": {
                "able": True,
                "value": 3,
                "fall_lang": "en"
            }
        },
        "method": trans_caiyun,
        "test_function": test_caiyun,
        "init_function": None
    }
]