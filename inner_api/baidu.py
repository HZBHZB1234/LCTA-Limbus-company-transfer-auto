import requests
import random
from hashlib import md5

def make_md5(s, encoding='utf-8'):
    return md5(s.encode(encoding)).hexdigest()

def translate_net(from_lang, to_lang, query, intervene, appids, appkeys):
    endpoint = 'http://api.fanyi.baidu.com'
    path = '/api/trans/vip/translate'
    url = endpoint + path

    salt = random.randint(32768, 65536)
    sign = make_md5(appids + query + str(salt) + appkeys)
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    payload = {'appid': appids, 'q': query, 'from': from_lang, 'to': to_lang, 'salt': salt, 'sign': sign, "needIntervene": intervene}

    r = requests.post(url, params=payload, headers=headers)
    result = r.json()
    return result

def translate_final(from_lang2, to_lang2, intervene2, query2, appids2, appkeys2):
    # 不再需要手动处理标记保护，中间层会自动处理
    z = translate_net(from_lang2, to_lang2, query2, intervene2, appids2, appkeys2)
    
    try:
        trans = z['trans_result']
    except Exception:
        error_code = z["error_code"]
        if error_code == "54003":
            string = "百度api: 未知错误, 请尝试重新翻译!"
        elif error_code == "52001":
            string = "百度api: 请求超时, 请重试"
        elif error_code == "52002":
            string = "百度api: 系统错误, 请重试"
        elif error_code == "52003":
            string = "百度api: APPID 或 密钥 不正确"
        elif error_code == "54001":
            string = "百度api: APPID 或 密钥 不正确"
        elif error_code == "54004":
            string = "百度api: 账户余额不足"
        elif error_code == "54005":
            string = "百度api: 请降低长query的发送频率，3s后再试"
        elif error_code == "58000":
            string = "百度api: 客户端IP非法, 注册时错误填入服务器地址, 请前往开发者信息-基本信息修改, 服务器地址必须为空"
        elif error_code == "90107":
            string = "百度api: 认证未通过或未生效"
        else:
            string = "百度api: %s, %s" % (error_code, z["error_msg"])
        return False, string

    # 拼接翻译结果
    ret = ''
    for i in range(len(trans)):
        returns = trans[i]
        returnz = returns['dst']
        if i:
            ret = ret + '\n'
        ret = ret + returnz
    return True, ret

def trans_baidu(params, text, logger):
    """进行百度翻译"""
    try:
        appid = params.get('appid', '')
        secret = params.get('secret', '')
        intervene = params.get('intervene', '0')
        
        if not appid or not secret:
            return False, "APP ID和密钥不能为空"
            
        result = translate_final('en', 'zh', intervene, text, appid, secret)
        return result
    except Exception as e:
        return False, str(e)


SERVICE_DEFINITION = [
    {
        "name": "百度翻译",
        "service": "baidu",
        "description": "百度翻译API服务",
        "api_params": [
            {"key": "appid", "label": "APP ID", "type": "entry"},
            {"key": "secret", "label": "密钥", "type": "password"},
            {"key": "intervene", "label": "是否开启词典", "type": "checkbox"}
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
        "method": trans_baidu,
        "test_function":None,
        "init_function": None
    }
]