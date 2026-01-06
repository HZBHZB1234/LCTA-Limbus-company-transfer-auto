import os
from pathlib import Path
import json
import requests

from .log_manage import LogManager

def function_fetch_main(modal_id, logger_: LogManager, **kwargs):
    logger_.log_modal_process("成功链接后端", modal_id)
    logger_.log_modal_status("正在抓取数据", modal_id)
    data = []
    for i in range(10):
        r=requests.get(f"https://paratranz.cn/api/projects/6860/terms?pageSize=800&page={i+1}",timeout=10)
        r.raise_for_status()
        logger_.log_modal_process(f"正在获取第{i+1}页数据", modal_id)
        r = r.json()
        if len(r.get('results', []))==0:
            break
        data.extend(r['results'])
    logger_.log_modal_process("数据获取完成", modal_id)
    logger_.log_modal_process("开始处理数据", modal_id)
    logger_.log_modal_status("正在处理数据", modal_id)
    json_data = [
        {
            'term': i.get('term', ''),
            'translation': i.get('translation', ''),
            'note': i.get('note', '')
        } for i in data
    ]
    if kwargs.get('disable_space', False):
        json_data = [i for i in json_data if ' ' not in i['term']]
    if (max_lenth:=int(kwargs.get('max_lenth', 0))) and max_lenth>0:
        json_data = json_data[:max_lenth]
    logger_.log_modal_process("数据处理完成", modal_id)
    logger_.log_modal_status("正在保存数据", modal_id)
    logger_.log_modal_process("开始保存数据", modal_id)
    output_type = kwargs.get('output_type', 'json')
    if output_type == 'json':
        logger_.log_modal_process("正在保存为json文件", modal_id)
        with open(f"proper.json", "w", encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=4)
    elif output_type == 'single' or output_type == 'double':
        logger_.log_modal_process("正在保存为单词表文件", modal_id)
        data_term = [i.get('term', '') for i in json_data]
        data_translation = [i.get('translation', '') for i in json_data]
        if output_type == 'double':
            with open(f"term.txt", "w", encoding='utf-8') as f:
                f.write('\n'.join(data_term))
            with open(f"translation.txt", "w", encoding='utf-8') as f:
                f.write('\n'.join(data_translation))
        else:
            with open(f"term_translation.txt", "w", encoding='utf-8') as f:
                join_char = kwargs.get('join_char', ',')
                f.write('\n'.join([f"{t}{join_char}{d}" for t, d in zip(data_term, data_translation)]))
    logger_.log_modal_process("数据保存完成", modal_id)
    logger_.log_modal_status("数据保存完成", modal_id)
