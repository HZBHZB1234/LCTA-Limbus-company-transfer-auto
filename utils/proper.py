import requests
import json

def worm(logger):
    c=[]
    for i in range(10):
        r=requests.get(f"https://paratranz.cn/api/projects/6860/terms?pageSize=800&page={i+1}",timeout=10)
        if r.status_code!=200:
            logger("请求失败") 
            return False
        logger('获取第%d页成功'%(i+1))
        if len(r.json()["results"])==0: 
            logger("没有更多数据了") 
            break
        if i==9: 
            logger("未知原因导致超出限额")
            return False
        c=c+r.json()["results"]
    return c
def get_simple(logger,c=None):
    logger('开始简化')
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
def make_proper(logger, output_type="json", output_path=".\\", input_file="proper.json", split_char="|||", skip_space=False, max_count=None):
    if output_type != "json" and input_file:
        with open(input_file, 'r', encoding='utf-8') as f:
            c = json.load(f)
    else:
        c = worm(logger)
        if not c: 
            logger("获取数据失败") 
            return False
        c = get_simple(logger, c)
    
    if max_count is not None:
        c = c[:max_count]
    
    if output_type == "json":
        with open(output_path + "\\proper.json", 'w', encoding='utf-8') as f:
            json.dump(c, f, indent=4, ensure_ascii=False)
            logger("完成")
            return True
    if output_type == "single":
        with open(output_path + "\\proper.txt", 'w', encoding='utf-8') as f:
            for i in c:
                if skip_space:
                    if ' ' in i["term"]:
                        continue
                    if ' ' in i["translation"]:
                        continue
                f.write(i["term"] + split_char + i["translation"] + '\n')
            logger("完成")
            return True
    elif output_type == "double":
        with open(output_path + "\\proper_cn.txt", 'w', encoding='utf-8') as f:
            for i in c:
                if skip_space:
                    if ' ' in i["term"]:
                        continue
                    if ' ' in i["translation"]:
                        continue
                f.write(i["translation"] + '\n')
        with open(output_path + "\\proper_kr.txt", 'w', encoding='utf-8') as f:
            for i in c:
                if skip_space:
                    if ' ' in i["term"]:
                        continue
                    if ' ' in i["translation"]:
                        continue
                f.write(i["term"] + '\n')
        logger("完成")
        return True
if __name__=='__main__':
    with open("s.json",'w',encoding='utf-8') as f:
        json.dump(get_simple(print,worm(print)),f,indent=4)