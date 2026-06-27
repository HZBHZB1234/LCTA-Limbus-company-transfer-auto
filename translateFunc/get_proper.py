import requests

def fetch(min_len:int = 0):
    data = []
    for i in range(10):
        r=requests.get(f"https://paratranz.cn/api/projects/6860/terms?pageSize=800&page={i+1}",timeout=10)
        r.raise_for_status()
        r = r.json()
        if len(r.get('results', []))==0:
            break
        data.extend(r['results'])
    else:
        raise RuntimeError(
            "专有名词数据超过 10 页限制（8000 条），请增加 get_proper.py 中的页数"
        )
        
    result =[
        {
            'term': i.get('term', ''),
            'translation': i.get('translation', ''),
            'note': i.get('note', '')
        } for i in data if len(i.get('term', '')) >= min_len
    ]
    return result
