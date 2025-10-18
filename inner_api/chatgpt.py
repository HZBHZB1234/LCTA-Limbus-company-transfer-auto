# -*- coding: utf-8 -*-
import requests
import json
import re
import time
import traceback

# ChatGPT默认话术
CHATGPT_PROMPT = "你是一个翻译引擎。\n根据原文逐行翻译，将每行原文翻译为简体中文。\n保留每行文本的原始格式，并根据所需格式输出翻译后的文本。\n在翻译文本时，请严格注意以下几个方面：\n首先，一些完整的文本可能会被分成不同的行。请严格按照每行的原始文本进行翻译，不要偏离原文。\n其次，无论句子的长度如何，每行都是一个独立的句子，确保不要将多行合并成一个翻译。\n第三，在每行文本中，转义字符（例如\, \r, 和\n）或非日语内容（例如数字、英文字母、特殊符号等）不需要翻译或更改，应保持原样。"

# 全局变量用于上下文管理
CHATGPT_CONTEXT_LIST = []

def trans_chatgpt(params, text, logger):
    """ChatGPT翻译服务"""
    try:
        api_key = params.get('api_key', '')
        proxy = params.get('proxy', '')
        url = params.get('api_url', 'https://api.openai.com/v1/chat/completions')
        model = params.get('model', 'gpt-3.5-turbo')
        prompt = params.get('prompt', CHATGPT_PROMPT)
        context_use = params.get('context_use', False)
        context_count = params.get('context_count', 5)
        delay_time = params.get('delay_time', 0)
        
        if not api_key:
            return False, "API密钥不能为空"

        # 上下文管理
        global CHATGPT_CONTEXT_LIST
        if context_use and len(CHATGPT_CONTEXT_LIST) > context_count * 2:
            CHATGPT_CONTEXT_LIST = CHATGPT_CONTEXT_LIST[-context_count * 2:]
            
        messages = [{"role": "system", "content": prompt}]
        if context_use:
            messages += CHATGPT_CONTEXT_LIST
        messages.append({"role": "user", "content": text})

        data = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 1000,
            "top_p": 1,
            "n": 1,
            "frequency_penalty": 1,
            "presence_penalty": 1,
            "stream": False,
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        proxies = {"http": None, "https": None}
        if proxy:
            proxies = {
                "http": f"http://{proxy}",
                "https": f"https://{proxy}"
            }

        try:
            # 延时控制
            if delay_time > 0:
                time.sleep(delay_time)

            response = requests.post(url, headers=headers, data=json.dumps(data), proxies=proxies, timeout=30)
            response.encoding = "utf-8"
            result = json.loads(response.text)
            response.close()

            if result.get("error", {}).get("message", ""):
                error = result.get("error", {}).get("message", "")
                error_messages = {
                    "Rate limit reached": "请求次数超限制, 请稍后重试, 或使用不带次数限制的密钥",
                    "You can find your API key": "无效的密钥, 请检查密钥是否正确", 
                    "You exceeded your current quota": "账户额度已耗尽, 请检查账户确保有额度后重试",
                    "Invalid URL": "请求失败, 无效的API接口地址, 请检查API接口地址是否正确",
                    "deactivated account": "账户已被停用, 请检查账户是否被封禁"
                }
                
                for key, msg in error_messages.items():
                    if key in error:
                        return False, f"ChatGPT错误: {msg}"
                        
                # 模型不存在错误
                model_match = re.match(r"The model .+? does not exist", error)
                if model_match:
                    return False, f"ChatGPT错误: 错误的模型, {model} 不存在"
                    
                return False, f"ChatGPT错误: {error}"
                
            else:
                # 翻译成功
                result_text = result["choices"][0]["message"]["content"]
                
                # 记录上下文
                if context_use:
                    CHATGPT_CONTEXT_LIST.append({"role": "user", "content": text})
                    CHATGPT_CONTEXT_LIST.append({"role": "assistant", "content": result_text})

                # 结果过滤
                content_length = len(text.split("\n"))
                if content_length == 1:
                    result_text = simple_chatgpt_filter(result_text, text)
                else:
                    result_text = multiple_chatgpt_filter(result_text, text)

                return True, result_text

        except requests.exceptions.ReadTimeout:
            return False, "ChatGPT翻译超时, 如有挂载代理, 请检查代理稳定性后重试"
        except requests.exceptions.ProxyError:
            return False, "ChatGPT代理访问错误, 请检查是否有开启代理, 且代理地址正确"
        except requests.exceptions.ConnectionError:
            return False, "ChatGPT网络连接错误, 无法访问到API"
            
    except Exception as e:
        logger.error(traceback.format_exc())
        return False, f"ChatGPT翻译异常: {str(e)}"

def multiple_chatgpt_filter(text, original):
    """多句子ChatGPT结果过滤"""
    new_text = text
    for v in original.split("\n"):
        new_text = re.sub(re.escape(v), "", new_text)
    if new_text.split("\n") == text.split("\n"):
        text = new_text
    text = re.sub(r"\n{2,}", "\n", text)
    return text

def simple_chatgpt_filter(text, original):
    """单句子ChatGPT结果过滤"""
    text = re.sub(r"\n", "", text)
    if "请提供更多详细" in text:
        text = original
    return text

def test_chatgpt(params, logger):
    """测试ChatGPT翻译服务"""
    try:
        api_key = params.get('api_key', '')
        
        if not api_key:
            return False, "API密钥不能为空"
            
        test_result = trans_chatgpt(params, "Hello, world!", logger)
        return test_result
        
    except Exception as e:
        return False, f"测试失败: {str(e)}"

def get_chatgpt_models(params, logger):
    """获取ChatGPT可用模型列表"""
    try:
        api_key = params.get('api_key', '')
        proxy = params.get('proxy', '')
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        proxies = {"http": None, "https": None}
        if proxy:
            proxies = {
                "http": f"http://{proxy}",
                "https": f"https://{proxy}"
            }
            
        url = "https://api.openai.com/v1/models"
        response = requests.get(url, headers=headers, proxies=proxies, timeout=30)
        result = json.loads(response.text)
        
        models = []
        for val in result.get("data", []):
            model = val.get("id", "")
            if model and "gpt-" in model:
                models.append(model)
                
        return True, models
        
    except Exception as e:
        return False, f"获取模型列表失败: {str(e)}"

SERVICE_DEFINITION = [
    {
        "name": "ChatGPT翻译",
        "service": "chatgpt", 
        "description": "OpenAI ChatGPT翻译服务",
        "api_params": [
            {"key": "api_key", "label": "API密钥", "type": "password"},
            {"key": "api_url", "label": "API地址", "type": "entry"},
            {"key": "model", "label": "模型", "type": "entry"},
            {"key": "proxy", "label": "代理地址", "type": "entry"},
            {"key": "prompt", "label": "提示词", "type": "entry"},
            {"key": "context_use", "label": "使用上下文", "type": "checkbox"},
            {"key": "context_count", "label": "上下文数量", "type": "entry"},
            {"key": "delay_time", "label": "请求延迟(秒)", "type": "entry"}
        ],
        "accept": "text",
        "term": False,
        "layer": {
            "split": [True, "\n"],
            "need_transfer": True,
            "using_inner_pool": False,  # ChatGPT通常不支持高并发
            "using_inner_test": True,
            "need_init": False,
            "max_text": {
                "able": True,
                "split_file": True,
                "type": "character", 
                "value": 2000
            },
            "max_requests": {
                "able": True,
                "value": 1  # ChatGPT通常限制并发
            },
            "retry_set": {
                "able": True,
                "value": 3,
                "fall_lang": "en"
            }
        },
        "method": trans_chatgpt,
        "test_function": test_chatgpt,
        "init_function": None
    }
]