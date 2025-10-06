import api
import logging

# 设置日志
logger = logging.getLogger(__name__)

def trans_baidu(params,text):
    """测试百度翻译API"""
    try:
        appid = params.get('appid', '')
        secret = params.get('secret', '')
        
        if not appid or not secret:
            return False, "APP ID和密钥不能为空"
        result = api.baidu(text, appid, secret, logger)
        if result and len(result) > 0:
            return True, result
        else:
            return False, "翻译返回为空"
    except Exception as e:
        return False, str(e)

def trans_tencent(params,text):
    """测试腾讯翻译API"""
    try:
        secret_id = params.get('secret_id', '')
        secret_key = params.get('secret_key', '')
        
        if not secret_id or not secret_key:
            return False, "SecretId和SecretKey不能为空"
        
        result = api.tencent(text, secret_id, secret_key, logger)
        if result and len(result) > 0:
            return True, result
        else:
            return False, "翻译返回为空"
    except Exception as e:
        return False, str(e)

def trans_caiyun(params,text):
    """测试彩云翻译API"""
    try:
        token = params.get('token', '')
        
        if not token:
            return False, "Token不能为空"
        
        result = api.caiyun(text, token, logger)
        if result and len(result) > 0:
            return True, result
        else:
            return False, "翻译返回为空"
    except Exception as e:
        return False, str(e)

def trans_youdao(params,text):
    """测试有道翻译API"""
    try:
        app_key = params.get('app_key', '')
        app_secret = params.get('app_secret', '')
        
        if not app_key or not app_secret:
            return False, "AppKey和密钥不能为空"
        
        success, result = api.youdao(text, app_key, app_secret, logger)
        if success:
            return True, result
        else:
            return False, result
    except Exception as e:
        return False, str(e)

def trans_xiaoniu(params,text):
    """测试小牛翻译API"""
    try:
        apikey = params.get('apikey', '')
        
        if not apikey:
            return False, "API Key不能为空"
        
        success, result = api.xiaoniu(apikey, text, "ENG", logger)
        if success:
            return True, result
        else:
            return False, result
    except Exception as e:
        return False, str(e)

def trans_aliyun(params,text):
    """测试阿里云翻译API"""
    try:
        access_key_id = params.get('access_key_id', '')
        access_key_secret = params.get('access_key_secret', '')
        
        if not access_key_id or not access_key_secret:
            return False, "AccessKeyId和AccessKeySecret不能为空"
        
        success, result = api.aliyun(access_key_id, access_key_secret, "ENG", text, logger)
        if success:
            return True, result
        else:
            return False, result
    except Exception as e:
        return False, str(e)

def trans_huoshan(params,text):
    """测试火山翻译API"""
    try:
        ak = params.get('ak', '')
        sk = params.get('sk', '')
        
        if not ak or not sk:
            return False, "Access Key和Secret Key不能为空"
        
        success, result = api.huoshan(ak, sk, text, logger)
        if success:
            return True, result
        else:
            return False, result
    except Exception as e:
        return False, str(e)

def trans_google(params,text):
    """测试Google翻译API"""
    try:
        key = params.get('key', '')
        
        if not key:
            return False, "API密钥不能为空"
        
        # 这里需要实现Google翻译的测试逻辑
        # 暂时返回成功，需要根据实际的api模块实现
        return True, result
    except Exception as e:
        return False, str(e)

def trans_deepl(params,text):
    """测试DeepL翻译API"""
    try:
        key = params.get('key', '')
        
        if not key:
            return False, "API密钥不能为空"
        
        import deepl

        auth_key = key
        translator = deepl.Translator(auth_key)

        # 要翻译的文本
        text_to_translate = text

        # 进行翻译，target_lang 指定目标语言
        try:
            result = translator.translate_text(text_to_translate, target_lang="ZH")
            if result.text:
                return True, result
            else:
                return False, "翻译失败"
        except Exception as e:
            return False, str(e)
    except Exception as e:
        return False, str(e)