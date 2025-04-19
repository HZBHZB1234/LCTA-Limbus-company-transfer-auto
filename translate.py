import requests
import random
from hashlib import md5
import re
#appids = '20250405002325015'
#appkeys = 'NMyimh3GSnQm0DUaum1C'
def make_md5(s, encoding='utf-8'):
    return md5(s.encode(encoding)).hexdigest()
def translate_net(from_lang,to_lang,query,intervene,appids,appkeys):
    #from_lang = 'en'
    #to_lang =  'zh'

    endpoint = 'http://api.fanyi.baidu.com'
    path = '/api/trans/vip/translate'
    url = endpoint + path

    #query = 'hello world'
    salt = random.randint(32768, 65536)
    sign = make_md5(appids + query + str(salt) + appkeys)
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    payload = {'appid': appids, 'q': query, 'from': from_lang, 'to': to_lang, 'salt': salt, 'sign': sign,"needIntervene":intervene}

    r = requests.post(url, params=payload, headers=headers)
    result = r.json()
    return(result)
def translate_final(from_lang2,to_lang2,query2,intervene2,appids2,appkeys2):
    inputing=query2
    cant_trans_jian=re.findall(r'\<(.*?)\>',inputing)
    cant_trans_fang=re.findall(r'\[(.*?)\]',inputing)
    final_input=inputing
    ran=0
    changing_list={}
    for i in cant_trans_jian:
        final_input=final_input.replace(i,str(ran))
        changing_list['<'+str(ran)+'>']='<'+i+'>'
        ran=ran+1
    for i in cant_trans_fang:
        final_input=final_input.replace(i,str(ran))
        changing_list['['+str(ran)+']']='['+i+']'
        ran=ran+1
    z=translate_net(from_lang2,to_lang2,final_input,intervene2,appids2,appkeys2)
    trans=z.get('trans_result')
    ret=''
    for i in range(len(trans)):
        returns=trans[i]
        returnz=returns['dst']
        for key in changing_list:
            returnz=returnz.replace(key,changing_list[key])
        if i:
            ret=ret+'\n'
        ret=ret+returnz
    return ret
#print(translate_final('kor','zh','[OnSucceedAttack] [MentalCrack] 1 부여',0,'20250405002325015','NMyimh3GSnQm0DUaum1C'))