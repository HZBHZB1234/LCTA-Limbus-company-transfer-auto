import requests
import random
from hashlib import md5
import re
#appids = '20250405002325015'
#appkeys = '5zNgTyqclEiOghg70Cx3'
def make_md5(s, encoding='utf-8'):
    return md5(s.encode(encoding)).hexdigest()
def translate_net(trans_ini,query):
    from_lang=trans_ini.lang_in
    to_lang='zh'
    intervene=0
    appids=trans_ini.keys['appids']
    appkeys=trans_ini.keys['appkeys']
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
    if not r.status_code == 200:
        print('网络错误')
        print('错误代码：', r.status_code)
        input()
        return 'error'
    result = r.json()
    return(result)
def translate_final(query,trans_ini):
    inputing=query
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
    while True:
        z=translate_net(trans_ini,final_input)
        try:
            if not z=='error':
                if z.get('trans_result') is not None:
                    break
                else:
                    print('翻译错误')
                    print('错误代码:'+z.get('error_code')+'\n'+z.get('error_msg'))
                    while True:
                        ask=input('重试,原文,退出(1,2,3)')
                        if ask=='1':
                            break
                        elif ask=='2':
                            if query[-1:]==('\n'):
                                query=query[:-1]
                            return query
                        elif ask=='3':
                            raise
                        else:
                            print('输入错误')
        except Exception as e:
            print('未知错误,错误代码:'+str(e))
            raise
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
def trans_team(query,trans_ini):
    querys=query.copy()
    ret=[]
    while True:
        output=''
        query_cache=querys.copy()
        output_cache=''
        for i in querys:
            output_cache=output_cache+i.replace('\n','\t')+'\n'
            if len(output_cache.encode())>=5000:
                break
            else:
                output=output_cache
                del query_cache[0]
                if  len(query_cache)==0:
                    break
        querys=query_cache
        inputing=translate_final(output,trans_ini)
        print(repr(inputing))
        inputing=inputing.split('\n')
        for i in inputing:
            ret.append(i.replace('\t','\n'))
        if  len(querys)==0:
            break
    return ret
#print(translate_final('kor','zh','[OnSucceedAttack] [MentalCrack] 1 부여',0,'20250405002325015','NMyimh3GSnQm0DUaum1C'))
if __name__=='__main__':
    class transform_json:
        using_self=False
        cache_trans=False
        lang_in=''
        keys={}
        exc=False
        team_trans=False
        trans_modue=''
        log=False
        json_error=''
    aaa=transform_json()
    aaa.lang_in='en'
    trans_team(['hello world','ok','[OnSucceedAttack] [MentalCrack] 1 부여'],aaa)