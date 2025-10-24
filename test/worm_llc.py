import requests
import json
#测试用
def worm(logger):
    c=[]
    for i in range(10):
        r=requests.get(f"https://paratranz.cn/api/projects/6860/terms?pageSize=800&page={i+1}",timeout=10)
        if r.status_code!=200:
            logger("请求失败") 
            return
        logger('获取第%d页成功'%(i+1))
        if len(r.json()["results"])==0: 
            logger("没有更多数据了") 
            break
        if i==9: 
            logger("未知原因导致超出限额")
            return
        c=c+r.json()["results"]
    return c
def get_simple(logger,c=None):
    logger('开始简化')
    if c==None:
        with open("c.json",'r',encoding='utf-8') as f:
            c=json.load(f)
    s=[]
    for i in c:
        s.append(
            {
                "term":i["term"],
                "translation":i["translation"],
                "note":i["note"]
            }
        )
    return s
def make_baidu(logger,s=None):
    logger('开始制作百度翻译词库')
    if not s:
        with open("s.json",'r',encoding='utf-8') as f:
            s=json.load(f)
    times=0
    final=''
    for i in s:
        if not ' ' in i["term"]:
            times+=1
            if times==500:
                break
            final+=i["term"]+'|||'+i["translation"]+'\n'
    return final
def make_two(logger,s=None):
    logger('开始制作双份词库')
if __name__=='__main__':
    with open("s.json",'w',encoding='utf-8') as f:
        json.dump(get_simple(print,worm(print)),f,indent=4)