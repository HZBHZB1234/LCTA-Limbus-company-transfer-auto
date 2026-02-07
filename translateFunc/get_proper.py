import requests
import sys

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
        print('可能有更多数据，请增加页数', file=sys.stderr)
        exit(1)
        
    result =[
        {
            'term': i.get('term', ''),
            'translation': i.get('translation', ''),
            'note': i.get('note', '')
        } for i in data if len(i.get('term', '')) >= min_len
    ]
    return result
