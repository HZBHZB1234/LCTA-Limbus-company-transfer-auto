import requests
import json
#测试用
def worm():
    c=[]
    for i in range(3):
        r=requests.get(f"https://paratranz.cn/api/projects/6860/terms?pageSize=800&page={i+1}")
        print(r.status_code)
        c=c+r.json()["results"]
    with open("c.json",'w',encoding='utf-8') as f:
        json.dump(c,f,ensure_ascii=False,indent=4)
def get_simple():
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
    with open("s.json",'w',encoding='utf-8') as f:
        json.dump(s,f,ensure_ascii=False,indent=4)
def make_baidu():
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
    with open("baidu.txt",'w',encoding='utf-8') as f:
        f.write(final)
make_baidu()