# 自定义翻译服务脚本编写指南

本文档将指导您如何编写自定义翻译服务脚本，以便集成到翻译工具中。

## 脚本基本结构

每个自定义翻译脚本需要包含以下核心部分：

```python
import requests
# 一些必要的库...

# 自定义翻译函数
def your_translation_function(params, text, logger):
    """
    主要的翻译函数
    """
    # 您的翻译逻辑
    pass

# 服务定义
SERVICE_DEFINITION = [
    {
        # 服务配置信息
    }
]
```

## 服务定义详解

### 基本信息配置

```python
SERVICE_DEFINITION = [
    {
        # 显示名称
        "name": "您的翻译服务名称", 
        # 服务标识符，在调用时的标识，以下标识符为保留字段，不可使用
        # baidu tencent caiyun youdao xiaoniu aliyun huoshan google deepl custom
        "service": "service_id",
        # 服务功能描述，目前没什么用，随便写写注释
        "description": "服务描述",
        # API参数配置
        "api_params": [
            # 详见下文
        ],
        # 接受的数据类型,详见下文
        "accept": "text",
        # 传入术语设置,详见文档other_doc.md，需要在相关功能中独立设置
        "term": False,
        # 处理层级配置
        "layer": {   
            # 详见下文
        },
        # 指向翻译函数
        "method": your_translation_function,
        # 测试函数(可选)，详见下文
        "test_function": None,
        # 初始化函数(可选)，详见下文
        "init_function": None
    }
]
```

### API参数配置 (`api_params`)

```python
"api_params": [
    {
        # 参数键名，内部使用，传参时作为字典键名，建议使用英文
        "key": "appid",
        # 显示名称
        "label": "APP ID",
        # 输入类型：entry|password|checkbox
        "type": "entry"            #输入框，直接输入内容
    },
    {
        "key": "secret",
        "label": "密钥",
        "type": "password"                 # 密码框，输入内容会隐藏
    },
    {
        "key": "enable_feature",
        "label": "启用特性",
        "type": "checkbox"                 # 复选框，返回布尔值
    }
]
```

**输入类型说明：**
- `entry`: 普通文本输入框
- `password`: 密码输入框，预览部分显示*号 TODO:加密
- `checkbox`: 复选框（返回 True/False）

### 中间层配置配置 (`layer`)

```python
"layer": {
    "split": [True, "\n"],                 # [是否分割, 分割符]
    "need_transfer": True,                 # 是否需要去标记处理
    "using_inner_pool": True,              # 是否使用内部并发池
    "using_inner_test": True,              # 是否使用内部测试
    "need_init": False,                    # 是否需要初始化
    "max_text": {                          # 文本长度限制
        "able": True,                      # 是否启用限制
        "split_file": True,                  #是否根据文件进行分割
        "type": "character",               # 限制类型：character|byte
        "value": 5000                      # 限制值
    },
    "max_requests": {                      # 并发请求限制
        "able": True,                      # 是否启用限制
        "value": 5                         # 最大并发请求数
    },
    "retry_set": {                          #最大重试次数
        "able": True,                      #是否启用重试
        "value": 5,                        #最大重试次数
        "fall_lang": "en"                   #重试失败取值
    }
}
```
#### 参数详解
> **split** : 是否需要分割文本  
部分翻译服务允许使用特点符号将文本进行分割处理，  
启用该功能，会将原有的文本通过分割符号拼接后传入，同时将句子中原因的分隔符替换并标记  
仅在传入类别为text时允许启用，建议搭配max_text参数配合使用，除非你的翻译服务允许你一次性翻译几万字符  
例如百度翻译服务将文本通过\\n进行分句处理。

> **need_transfer** : 是否替换标记字符  
边狱的文本中含有部分标记符，比如 **<style=>** 或者是 **[buff名称]** ，将里面的文本翻译会导致无法识别对应内容  
启用该功能，会将原有句子中的标记符号替换为类似 **<0>** 之类的内容。  
本参数无依赖  
部分翻译服务允许保留符号内的内容，可能有帮助于理解上下文  
由于但丁说话会在头尾添加 **<>** ，该中间层不会对开头和结尾都是 **<>** 的句子进行替换  

> **using_inner_pool** & **max_requests** : 使用内建并发池  
大部分翻译服务都支持用户并发请求，并发请求可以大幅提升翻译速度  
启用该功能(需要同时启用**using_inner_pool**和**max_requests**)将会使用内建pool使用threading进行多线程并发  
本参数无依赖  

> **using_inner_test** : 使用内建测试函数  
配置好apiKey后有可以并需要测试服务是否可正常调用  
启用该功能后无需独立创建测试函数。如不启用该功能，测试函数构建见下文  
本参数无依赖  
建议启用该功能，可以最大程度模拟翻译流程，且具有独立ui

> **need_init** : 启用init函数进行初始化  
部分服务需要单独进行初始化  
启用该功能将启用初始化函数，初始化函数见下文  
本参数无依赖  

> **max_text** : 文本长度限制  
几乎所有翻译服务具有最大长度限制  
启用该功能将会对传入文本长度进行限制  
仅在type为text时允许以文本长度限制，在type为json时允许启用**split_file**  
**split_file** : 根据文件进行分割，防止污染上下文，没有上下文的不用开  
**type** : 分割的依据，可选character和byte，代表字符长度和比特大小，byte以小byte计数  

> **retry_set** : 错误重试设置  
翻译可能有不规则的报错  
启用该选项将使用内建重试  
本参数无依赖  
**value** : 最大重试次数  
**fall_lang** : 失败后使用什么，可选择使用语言"en","kr","jp"原文，也可以填入其他内容  
不建议使用，还是建议自己写一个

### 传入数据类别 ("accept")  
允许的类别 : "text","json"  
#### 传入字符 ("text")
将会以字符方式传入数据，不是很推荐，无法自定义很多内容，但是配置简单
#### 传入json ("json")  
将会以json格式传入数据
传入json格式  
```json
[
    {
        "original": {
            "kr" : "",
            "en" : "",
            "jp" : ""
        },
        "key": {
            "type": "A",
            "key": ""
        },
        "context": {
            "story": True,
            "might_from": "ishmael"
        }
        "term": [
            {
                "original": "",
                "zh": "",
                "note"
            },
            {
                
            }
        ]
    },
    {
        
    }
]
```  

返回json格式  
```json
[
    {
        "trans": "",
        "key": {
            "type": "A",
            "key": ""
        }
    }
]
```
## 翻译函数编写规范

### 函数格式

```python
def your_translation_function(params, text, logger):
    """
    翻译主函数
    
    Args:
        params: dict - 包含用户在api_params中配置的所有参数
        text: str - 需要翻译的文本
        logger: 日志记录器，用于记录运行日志
    
    Returns:
        tuple: (success: bool, result: str)
               成功状态, 翻译结果或错误信息
    """
```

### 返回值规范

- **成功时**: `return True, "翻译结果"`
- **失败时**: `return False, "错误描述"`

### 示例实现

```python
def your_translation_function(params, text, logger):
    try:
        # 从params获取配置参数
        api_key = params.get('api_key', '')
        endpoint = params.get('endpoint', '')
        
        if not api_key:
            return False, "API密钥不能为空"
        
        # 调用翻译API
        result = call_translation_api(api_key, endpoint, text)
        
        # 记录日志
        logger(f"翻译完成，字符数: {len(text)}")
        
        return True, result
        
    except Exception as e:
        # 记录错误日志
        logger(f"翻译出错: {str(e)}")
        return False, f"翻译服务错误: {str(e)}"
```

### 测试函数 & 初始化函数  
返回True或False，不举例了  
TODO: 允许初始化函数传回需要的全局变量

## 实用工具函数

### 错误处理模式

```python
def handle_api_response(params, text, logger):
    """
    统一处理API响应
    """
    for i in range(5):     #填入你的最大重试次数
        try:
            ok,msg=translate_function(params, text, logger)
            if ok:
                return ok,msg
        except:
            None
    #以text传入
    return False text
    #以json传入
    return False [{"trans":i['original'],"key":i['key']} for i in text]
```

### 文本预处理

```python
import re

def preprocess_text(text):
    """
    预处理文本，保护特殊格式内容
    """
    # 保护尖括号内容和方括号内容 <content> [content]
    protected_content = {}
    pattern_jian=re.findall(r'\<(.*?)\>',text)
    pattern_fang=re.findall(r'\[(.*?)\]',text)
    change_time=0
    for i in pattern_jian:
        text=text.replace(f'<{i}>',f'<{str(ran)}>',1)
        protected_content[f'<{str(ran)}>']=f'<{i}>'
        ran=ran+1
    for i in pattern_fang:
        text=text.replace(f'[{i}]',f'[{str(ran)}]',1)
        protected_content[f'[{str(ran)}]']=f'[{i}]'
        ran=ran+1
    return text, protected_content

def postprocess_text(text, protected_content):
    """
    后处理文本，恢复保护的内容
    """
    for placeholder, original in protected_content.items():
        text = text.replace(placeholder, original)
    return text
```

## 完整示例模板

```python
import requests
import json
import re
import random

def my_translator(params, text, logger):
    """
    我的自定义翻译服务
    """
    try:
        # 获取配置参数
        api_key = params.get('api_key', '')
        api_url = params.get('api_url', '')
        enable_feature = params.get('enable_feature', False)
        
        # 参数验证
        if not api_key:
            return False, "API密钥不能为空"
        if not api_url:
            return False, "API地址不能为空"
        
        # 文本预处理 - 保护特殊标记
        protected_content = {}
        if isinstance(text, str):
            processed_text = text
            # 保护<style=>标签和[buff]标记等内容
            pattern_style = re.findall(r'\<(.*?)\>', text)
            pattern_buff = re.findall(r'\[(.*?)\]', text)
            
            ran = 0
            for i in pattern_style:
                placeholder = f'<{ran}>'
                processed_text = processed_text.replace(i, placeholder, 1)
                protected_content[placeholder] = i
                ran += 1
                
            for i in pattern_buff:
                placeholder = f'[{ran}]'
                processed_text = processed_text.replace(i, placeholder, 1)
                protected_content[placeholder] = i
                ran += 1
        
        # 准备请求
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'text': processed_text if protected_content else text,
            'source_lang': 'en',
            'target_lang': 'zh',
            'enable_feature': enable_feature
        }
        
        # 发送请求
        logger(f"发送翻译请求到: {api_url}")
        response = requests.post(
            api_url, 
            headers=headers, 
            data=json.dumps(data),
            timeout=30
        )
        
        # 处理响应
        if response.status_code == 200:
            result_data = response.json()
            result_text = result_data.get('translation', '')
            
            # 文本后处理 - 恢复被保护的内容
            if protected_content and result_text:
                for placeholder, original in protected_content.items():
                    result_text = result_text.replace(placeholder, original)
            
            logger(f"翻译成功，处理字符数: {len(text)}")
            return True, result_text
        else:
            error_msg = f"API请求失败: {response.status_code}"
            if response.text:
                error_msg += f" - {response.text}"
            return False, error_msg
            
    except requests.exceptions.Timeout:
        return False, "请求超时"
    except requests.exceptions.ConnectionError:
        return False, "连接错误，请检查API地址"
    except Exception as e:
        logger(f"翻译异常: {str(e)}")
        return False, f"翻译服务异常: {str(e)}"

def test_my_translator(params, logger):
    """
    测试函数 - 验证服务配置是否正确
    """
    try:
        # 获取配置参数
        api_key = params.get('api_key', '')
        api_url = params.get('api_url', '')
        
        if not api_key:
            return False, "API密钥不能为空"
        if not api_url:
            return False, "API地址不能为空"
        
        # 发送测试请求
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        test_data = {
            'text': 'Hello, world!',
            'source_lang': 'en',
            'target_lang': 'zh'
        }
        
        response = requests.post(
            api_url, 
            headers=headers, 
            data=json.dumps(test_data),
            timeout=10
        )
        
        if response.status_code == 200:
            return True, "测试成功，服务可用"
        else:
            return False, f"测试失败: {response.status_code}"
            
    except Exception as e:
        return False, f"测试异常: {str(e)}"

def init_my_translator(params, logger):
    """
    初始化函数 - 可选，用于服务初始化
    """
    try:
        logger("初始化我的翻译服务...")
        # 这里可以添加初始化逻辑，比如验证凭据、建立连接等
        return True, "初始化成功"
    except Exception as e:
        return False, f"初始化失败: {str(e)}"

# 服务定义
SERVICE_DEFINITION = [
    {
        "name": "我的翻译API",
        "service": "my_translator",
        "description": "基于自定义API的翻译服务",
        "api_params": [
            {
                "key": "api_key",
                "label": "API密钥",
                "type": "password"
            },
            {
                "key": "api_url", 
                "label": "API地址",
                "type": "entry"
            },
            {
                "key": "enable_feature",
                "label": "启用特性",
                "type": "checkbox"
            }
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
                "value": 4000
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
        "method": my_translator,
        "test_function": test_my_translator,
        "init_function": init_my_translator
    }
]
```

按照这个指南，您就可以创建符合规范的自定义翻译服务脚本了。