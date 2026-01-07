import translatekit as tkit
from translatekit import kit
from pathlib import Path
from typing import List, Optional, Tuple
import json
import tempfile
import sys
import shutil
import os
import warnings
import jsonpointer
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

print(sys.path)
project_root = Path(__file__).parent.parent
print(project_root)
sys.path.insert(0, str(project_root))

import webutils.functions as functions
import webutils.load as load_util
import _feature.translate_doc as translate_doc
import _feature.test_request as test_request

config = load_util.load_config()
game_path = config['game_path']

FILT_CONFIG = (['.*'],
               ['.*/id', '.*/model', '.*/usage'],
               ['remove'],
               [int, float]
               )

EMPTY_DATA = {'dataList': []}

def get_list_id(input_list: List) -> List[int]:
    return [i.get('id', 999) for i in input_list]

def get_item_id(input_list: List, item_id: int) -> int:
    for i, item in enumerate(input_list):
        if item.get('id', 999)==item_id:
            return i

def change_len(input_list: List, lenth: int) ->List:
    if len(input_list)>=lenth:
        return input_list[:lenth]
    else:
        return input_list + ['无']*(lenth-len(input_list))
    
def fallback_len(raw_list: List,input_list: List) -> List:
    if (len_raw_list := len(raw_list)) >= (len_input_list := len(input_list)):
        result = raw_list.copy()
        result[:len_input_list] = input_list
        return result
    else:
        return input_list[:len_raw_list]

def make_model_patch(_jsonpatch: List, _json) -> List:
    '''从JSON补丁中提取值说话者'''
    list_jsonpatch = [i['path'] for i in _jsonpatch if i['op'] in ['add', 'replace']]
    list_jsonpatch = [i for i in list_jsonpatch if isinstance(i, str)]
    
    results = []
    for path_str in list_jsonpatch:
        # 将路径字符串转换为jsonpointer对象
        ptr = jsonpointer.JsonPointer(path_str)
        # 获取路径的各个部分
        parts = ptr.parts
        
        # 获取父路径（去掉最后一个部分，即当前路径的同级目录）
        if parts:
            # 获取当前路径的父路径部分（即同级目录）
            parent_parts = parts[:-1] if len(parts) > 0 else []
            
            # 构造model路径（在同级目录下查找model字段）
            model_parts = parent_parts + ['model']
            
            try:
                # 尝试获取同级目录下的model值
                model_ptr = jsonpointer.JsonPointer.from_parts(model_parts)
                model_value = model_ptr.resolve(_json)
                results.append(model_value)
            except jsonpointer.JsonPointerException:
                results.append('获取失败')
    
    return results

def get_text_model(models: List[str], model_def: List[dict],
                   model_id: List[str]) -> List[str]:
    results = ['']*len(models)
    for index, model in enumerate(models):
        if not model in model_id:
            results[index] = '获取失败'
            continue
        index_model = model_id.index(model)
        model_dict = model_def[index_model]
        results[index] = f'{model_dict.get("name", "无")} / {model_dict.get("desc", "无")}'
    return results

with tempfile.TemporaryDirectory() as temp_dir:
    llc_path = Path(game_path) / "LimbusCompany_Data" / "lang" / "LLC_zh-CN"
    assets_path = Path(game_path) / "LimbusCompany_Data" / "Assets" / "Resources_moved" / "Localize"
    final_path = Path(temp_dir) / "LLc-CN"
    os.makedirs(final_path, exist_ok=True)

    EN_path = assets_path / "en"
    KR_path = assets_path / "kr"
    JP_path = assets_path / "jp"
    
    proper_path = 'proper.json'
    with open(proper_path, 'r', encoding='utf-8-sig') as f:
        proper_data = json.load(f)
        proper_term = [i.get('term') for i in proper_data]
    proper_fetcher = kit.ProperNounMatcher(proper_term)
        
    KR_affect_path = KR_path / "KR_BattleKeywords.json"
    with open(KR_affect_path, 'r', encoding='utf-8-sig') as KR_file:
        KR_affect_data = json.load(KR_file).get('dataList', [])
    llc_affect_path = llc_path / "BattleKeywords.json"
    with open(llc_affect_path, 'r', encoding='utf-8-sig') as f:
        affect_data = json.load(f).get('dataList', [])
    llc_affect_list = get_list_id(affect_data)
    KR_affect_list = get_list_id(KR_affect_data)
    sub_affect = set(KR_affect_list) - set(llc_affect_list)
    if sub_affect:
        for i in sub_affect:
            index_affect = get_item_id(KR_affect_data, i)
            affect_data.append(KR_affect_data[index_affect])
    affect_data = [
        {'id': affect.get('id', 'aaa'), 'ZH-data': {'name': affect.get('name', 'aaa'), 'desc': affect.get('desc', 'aaa')},
         'KR-data': {'name': KR.get('name', 'aaa'), 'desc': KR.get('desc', 'aaa')}
    } for affect, KR in zip(affect_data, KR_affect_data)
    ]
    affect_data_id = get_list_id(affect_data)
    affect_data_id = [f'[{i}]' for i in affect_data_id]
    affect_data_name = [i.get('KR-data', {}).get('name', 'aaa') for i in affect_data]
    affect_data_name = [f'{i} ' for i in affect_data_name]
    affect_data_id_matcher = kit.SimpleMatcher(affect_data_id)
    affect_data_name_matcher = kit.SimpleMatcher(affect_data_name)
    llc_model_path = llc_path / "ScenarioModelCodes-AutoCreated.json"
    KR_model_path = KR_path / "KR_ScenarioModelCodes-AutoCreated.json"
    EN_model_path = EN_path / "EN_ScenarioModelCodes-AutoCreated.json"
    JP_model_path = JP_path / "JP_ScenarioModelCodes-AutoCreated.json"
    with open(llc_model_path, 'r', encoding='utf-8-sig') as llc_file, \
         open(KR_model_path, 'r', encoding='utf-8-sig') as KR_file, \
         open(EN_model_path, 'r', encoding='utf-8-sig') as EN_file, \
         open(JP_model_path, 'r', encoding='utf-8-sig') as JP_file:
        llc_model_data = json.load(llc_file).get('dataList', [])
        KR_model_data = json.load(KR_file).get('dataList', [])
        EN_model_data = json.load(EN_file).get('dataList', [])
        JP_model_data = json.load(JP_file).get('dataList', [])
        
    llc_model_list = get_list_id(llc_model_data)
    KR_model_list = get_list_id(KR_model_data)
    EN_model_list = get_list_id(EN_model_data)
    JP_model_list = get_list_id(JP_model_data)
    
    for root, dirs, files in os.walk(KR_path):
        for file in files:
            if not file.endswith(".json"):
                print('跳过非json文件:', file)
                continue
            true_file_name = file[3:]
            relative_path = os.path.relpath(root, KR_path)
            try:
                with open(f'{root}/{file}', 'r', encoding='utf-8-sig') as f:
                    KR_data = json.load(f).get('dataList', [])
                llc_data_path = f'{llc_path}/{relative_path}/{true_file_name}'
                if not os.path.exists(llc_data_path):
                    LLC_data = {}
                else:
                    with open(llc_data_path, 'r', encoding='utf-8-sig') as f:
                        LLC_data = json.load(f).get('dataList', [])
                if len(KR_data) == len(LLC_data):
                    continue
                logger.info(f'开始翻译文件: {file}')
                EN_data_path = f'{EN_path}/{relative_path}/EN_{true_file_name}'
                JP_data_path = f'{JP_path}/{relative_path}/JP_{true_file_name}'
                try:
                    with open(EN_data_path, 'r', encoding='utf-8-sig') as f:
                        EN_data = json.load(f).get('dataList', [])
                    with open(JP_data_path, 'r', encoding='utf-8-sig') as f:
                        JP_data = json.load(f).get('dataList', [])
                except FileNotFoundError:
                    logger.warning(f'文件: {file} 缺少EN或JP文件, 跳过')
                    continue
            except json.decoder.JSONDecodeError:
                logger.warning(f'文件: {file} 解析时错误, 跳过')
                continue
            EN_patch = kit.compare_json([], EN_data)
            EN_patch = kit.deoptimize_patch(EN_patch)
            JP_patch = kit.compare_json([], JP_data)
            JP_patch = kit.deoptimize_patch(JP_patch)
            KR_patch = kit.compare_json([], KR_data)
            KR_patch = kit.deoptimize_patch(KR_patch)
            llc_patch = kit.compare_json([], LLC_data)
            llc_patch = kit.deoptimize_patch(llc_patch)
            EN_clean_patch = kit.filted_patchs(EN_patch, *FILT_CONFIG)
            JP_clean_patch = kit.filted_patchs(JP_patch, *FILT_CONFIG)
            KR_clean_patch = kit.filted_patchs(KR_patch, *FILT_CONFIG)
            llc_clean_patch = kit.filted_patchs(llc_patch, *FILT_CONFIG)
            if not len(EN_clean_patch)==len(JP_clean_patch)==len(KR_clean_patch):
                logger.warning(f'文件: {file} 翻译后长度不一致')
                if len(KR_clean_patch) >= len(EN_clean_patch) or len(KR_clean_patch) >= len(JP_clean_patch):
                    logger.info(f'文件: {file} 韩文翻译长于其他语言')
            EN_text = kit.make_list_patch(EN_clean_patch)
            JP_text = kit.make_list_patch(JP_clean_patch)
            KR_text = kit.make_list_patch(KR_clean_patch)
            LLC_text = kit.make_list_patch(llc_clean_patch)
            len_KR = len(KR_text)
            EN_ok = change_len(EN_text, len_KR)
            JP_ok = change_len(JP_text, len_KR)
            proper = proper_fetcher.match_multiple(KR_text, 'sequential')
            proper = [[proper_data[index] for index in i] for i in proper]
            
            # 修改构建请求的部分
            request = {}
            if root.endswith('StoryData'):
                KR_models = make_model_patch(KR_clean_patch, KR_data)
                EN_models = make_model_patch(EN_clean_patch, EN_data)
                JP_models = make_model_patch(JP_clean_patch, JP_data)
                KR_model_texts = get_text_model(KR_models, KR_model_data, KR_model_list)
                EN_model_texts = get_text_model(EN_models, EN_model_data, EN_model_list)
                JP_model_texts = get_text_model(JP_models, JP_model_data, JP_model_list)
                texts = [{'en': EN,'jp': JP, 'kr': KR,
                          'proper': PR, 'model': {
                                'kr': MDKR, 'en': MDEN, 'jp': MDJP}} 
                        for EN, JP, KR, PR, MDKR, MDEN, MDJP in zip(EN_ok, JP_ok, KR_text, proper,
                                                                    KR_model_texts, EN_model_texts, JP_model_texts)]                
                modal_doc = []
                modal_add = set(KR_models)
                for i in modal_add:
                    if i in translate_doc.RLOE_COMPARE:
                        modal_doc.append(translate_doc.ROLE_STYLE[translate_doc.RLOE_COMPARE[i]])
                if modal_doc:
                    request['doc_modal'] = modal_doc
            else:
                texts = [{'en': EN,'jp': JP, 'kr': KR,
                          'proper': PR} for EN, JP, KR, PR in zip(EN_ok, JP_ok, KR_text, proper)]

            if true_file_name.startswith('Skills'):
                affect_id_match = affect_data_id_matcher.match_multiple(KR_text)
                affect_name_match = affect_data_name_matcher.match_multiple(KR_text)
                affect_index_match = [list(set(a)|set(b)) for a, b in zip(affect_id_match, affect_name_match)]
                affects = [[affect_data[i] for i in index] for index in affect_index_match]
                texts = [{**i, 'affect': b} for i, b in zip(texts, affects)]
                request['doc_skill'] = translate_doc.SKILLL_DOC

            r_texts = texts[len(LLC_text):]
            request['textList'] = r_texts
            
            logger.info(f'请求数据: {request}')
            response = test_request.translate_text(request)