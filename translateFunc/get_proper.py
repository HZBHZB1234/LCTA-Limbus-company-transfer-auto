import logging

import requests

_logger = logging.getLogger("LCTA")  # 与 LogManager 一致的 logger，确保日志正确路由

def fetch(min_len:int = 0):
    page_size = 800
    data = []
    for i in range(10):
        r=requests.get(f"https://paratranz.cn/api/projects/6860/terms?pageSize={page_size}&page={i+1}",timeout=10)
        r.raise_for_status()
        r = r.json()
        results = r.get('results', [])
        if len(results)==0:
            break
        data.extend(results)
        if len(results) < page_size:
            break
    else:
        _logger.warning(
            "专有名词数据超过 10 页限制（%d 条），仅保留已抓取的前 10 页",
            page_size * 10,
        )
        
    result =[
        {
            'term': i.get('term', ''),
            'translation': i.get('translation', ''),
            'note': i.get('note', '')
        } for i in data if len(i.get('term', '')) >= min_len
    ]
    return result
