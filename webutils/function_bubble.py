import os
import zipfile
import tempfile
import json
import re
import shutil
from pathlib import Path
from typing import List, Optional
from collections import Counter
from contextlib import suppress

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from webutils.log_manage import LogManager
from webutils.functions import download_with
from webFunc.LanzouFolder import GetAllFileListByUrl

BASE_LANZOU_URL = "https://wwyi.lanzoub.com/"
BASE_DIRECT = "http://lz.qaiu.top/parser?url="

def check_bubble(modal_id, logger_: LogManager, filelists):
    logger_.log_modal_process("开始检查气泡", modal_id)
    if not filelists:
        logger_.log_modal_process("无法获取文件列表", modal_id)
        return ''
    r = []
    for file in filelists:
        file_name:str = file['name_all']
        file_name = file_name.rstrip('...')
        file_split = file_name.split('.')
        file_split.pop()
        file_split = file_split[-3:]
        with suppress(Exception):
            file_split[-3] = file_split[-3][-2:]
        if all(i.isdigit() for i in file_split):
            r.append('.'.join(file_split))
    if not r:
        logger_.log_modal_process("无法获取文件列表", modal_id)
        return ''
    r = Counter(r)
    return r.most_common(1)[0][0]

def get_direct_download(file_id):
    return f'{BASE_DIRECT}{BASE_LANZOU_URL}{file_id}'
    
def download_bubble(modal_id, logger_: LogManager, save_path: Path, color, filelists):
    color = '彩色' if color else '无色'
    file = [i for i in filelists if (color in i['name_all'] and '替换' in i['name_all'])][0]
    url = get_direct_download(file['id'])
    download_with(url, save_path / 'bubble_mod.zip', logger_=logger_,
                    modal_id=modal_id, validate=False)
                    
def install_bubble_mod(mod_path: Path, lang_path: Path):
    config_path = lang_path / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    target_lang = lang_path / config['lang']
    with zipfile.ZipFile(mod_path, 'r') as zip_ref:
        zip_ref.extractall(target_lang) 

def fetch_file_list():
    return GetAllFileListByUrl("https://wwyi.lanzoub.com/b014wpn02j",'fib6')

def function_bubble_main(modal_id, logger_: LogManager, whole_config):
    bubble_config = whole_config.get('ui_default', {}).get('bubble', {})
    color = bubble_config.get('color', False)
    install = bubble_config.get('install', False)
    lang_path = Path(whole_config.get('game_path')) / 'LimbusCompany_Data' / 'lang'
    enable_cache = whole_config.get('enable_cache', True)
    cache_path = Path(whole_config.get('cache_path')) if enable_cache else Path('.')
    
    file_list = fetch_file_list()
    
    mod_ = Path('.') / 'bubble_mod.zip'
    if mod_.exists():
        mod_.unlink()
    
    if enable_cache:
        version = check_bubble(modal_id, logger_, file_list)
        cache_key = color
        version = f'{version}\n{cache_key}'
        version_config = cache_path / 'version.txt'
        cache_mod = cache_path / 'bubble_mod.zip'
        if version_config.exists() and version == version_config.read_text(encoding='utf-8'):
            logger_.log_modal_process("缓存已存在，无需下载", modal_id)
            shutil.copy(cache_mod, './')
        else:
            download_bubble(modal_id, logger_, Path('.'), color, file_list)
    else:
        download_bubble(modal_id, logger_, Path('.'), color, file_list)
        
    if install:
        install_bubble_mod(mod_, lang_path)
        
    if enable_cache:
        if cache_mod.exists():
            cache_mod.unlink()
        shutil.copy(mod_, cache_mod)
        version_config.write_text(version, encoding='utf-8')
    
    
if __name__ == '__main__':
    files = fetch_file_list()
    logger = LogManager()
    print(files)
    print(check_bubble('', logger, files))