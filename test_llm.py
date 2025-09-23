import json
from openai import OpenAI
import json
#测试用
with open("secret.json", "r", encoding="utf-8") as file:
    api_key = json.load(file)["deepseek"]
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
)
with open("llm_example\\en.json", "r", encoding="utf-8") as file:
    sample_en=file.read()
with open("llm_example\\cn.json", "r", encoding="utf-8") as file:
    sample_cn=file.read()
system_prompt = f"""
你需要为游戏边狱公司制作翻译，用户会提交一个json格式文本，语言可能为英语、韩语或日语，你需要输出一个经过翻译的json文件。请注意，部分内容为游戏代码标识符，请自行辨认
在游戏中有一些特殊名词，以下是一个列表
1.수감자 sinner 罪人 意为游戏中主角团中个体的称呼

用户示例输入:
{sample_en}

你的示例输出:
{sample_cn}
"""

user_prompt =''
messages = [{"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}]

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,
    response_format={
        'type': 'json_object'
    }
)

print(json.loads(response.choices[0].message.content))