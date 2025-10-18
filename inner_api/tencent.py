# -*- coding: utf-8 -*-
import traceback
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.tmt.v20180321 import tmt_client, models
import re

def trans_tencent(params, text, logger):
    """腾讯翻译服务"""
    try:
        secret_id = params.get('secret_id', '')
        secret_key = params.get('secret_key', '')
        
        if not secret_id or not secret_key:
            return False, "Secret ID和Secret Key不能为空"
            
        # 如果未注册
        if not secret_id or not secret_key:
            return False, "还未注册私人腾讯API, 不可使用"

        cred = credential.Credential(secret_id, secret_key)
        httpProfile = HttpProfile()
        httpProfile.endpoint = "tmt.tencentcloudapi.com"

        clientProfile = ClientProfile()
        clientProfile.httpProfile = httpProfile
        client = tmt_client.TmtClient(cred, "ap-guangzhou", clientProfile)

        req = models.TextTranslateRequest()
        processed_text = text.replace('"', "'")
        params_str = '''{"SourceText":"%s","Source":"auto","Target":"zh","ProjectId":0}''' % processed_text
        params_str = params_str.replace('\r', '\\r').replace('\n', '\\n')
        req.from_json_string(params_str)

        resp = client.TextTranslate(req)
        result = re.findall(r'"TargetText": "(.+?)"', resp.to_json_string())[0]
        result = result.replace('\\r', '\r').replace('\\n', '\n')
        
        return True, result

    except TencentCloudSDKException as err:
        try:
            err_str = str(err)
            code = re.findall(r'code:(.*?) message', err_str)[0] if 'code:' in err_str else "Unknown"
            error = re.findall(r'message:(.+?) requestId', err_str)[0] if 'message:' in err_str else str(err)
            
            error_messages = {
                "MissingParameter": "缺少必要参数",
                "FailedOperation.NoFreeAmount": "本月免费额度已经用完",
                "FailedOperation.ServiceIsolate": "账号欠费停止服务", 
                "FailedOperation.UserNotRegistered": "还没有开通机器翻译服务",
                "InternalError": "内部错误",
                "InternalError.BackendTimeout": "后台服务超时，请稍后重试",
                "InternalError.ErrorUnknown": "未知错误",
                "LimitExceeded": "超过配额限制",
                "UnsupportedOperation": "操作不支持",
                "InvalidCredential": "secretId或secretKey错误",
                "AuthFailure.SignatureFailure": "secretKey错误",
                "AuthFailure.SecretIdNotFound": "secretId错误",
                "AuthFailure.SignatureExpire": "签名过期，请将电脑系统时间调整至准确的时间后重试"
            }
            
            message = error_messages.get(code, f"{code}, {error}")
            return False, f"腾讯翻译错误: {message}"
            
        except Exception:
            logger.error(traceback.format_exc())
            return False, "腾讯翻译: 处理错误时发生异常"

    except Exception as e:
        logger.error(traceback.format_exc())
        return False, f"腾讯翻译异常: {str(e)}"

def test_tencent(params, logger):
    """测试腾讯翻译服务"""
    try:
        secret_id = params.get('secret_id', '')
        secret_key = params.get('secret_key', '')
        
        if not secret_id or not secret_key:
            return False, "Secret ID和Secret Key不能为空"
            
        # 使用简单的测试文本
        test_result = trans_tencent(params, "Hello, world!", logger)
        return test_result
        
    except Exception as e:
        return False, f"测试失败: {str(e)}"

SERVICE_DEFINITION = [
    {
        "name": "腾讯翻译",
        "service": "tencent",
        "description": "腾讯云翻译API服务",
        "api_params": [
            {"key": "secret_id", "label": "Secret ID", "type": "entry"},
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
                "value": 2000
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
        "method": trans_tencent,
        "test_function": test_tencent,
        "init_function": None
    }
]