# pyright: reportMissingImports=false
import translatekit as tkit
from translatekit import kit
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import tempfile
import sys
import shutil
import os
import warnings
import jsonpointer
import logging
from dataclasses import dataclass
from copy import deepcopy

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

print(sys.path)
project_root = Path(__file__).parent.parent
print(project_root)
sys.path.insert(0, str(project_root))

from web_function.GithubDownload import asset
import webutils.functions as functions
import webutils.load as load_util
import _feature.translate_doc as translate_doc
import _feature.test_request as test_request

EMPTY_DATA = [{'dataList': []}, {}, []]
EMPTY_DATA_LIST = [[], [{}]]
EMPTY_TEXT = ['', '-']
AVOID_PATH = ['usage', 'id']

def flatten_dict_enhanced(d, parent_key=(), ignore_types=None, max_depth=None):
    """
    扁平化嵌套字典，使用元组作为键
    
    参数:
        d: 要扁平化的字典
        parent_key: 父键的元组，默认为空元组
        ignore_types: 要忽略的值的类型列表，例如 [None, ''] 或 [type(None), str]
        max_depth: 最大递归深度，None表示无限制
    """
    items = []
    
    def _flatten(obj, current_key, depth=0):
        if max_depth and depth > max_depth:
            items.append((current_key, obj))
            return
        
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_key = current_key + (k,)
                _flatten(v, new_key, depth + 1)
        elif isinstance(obj, (list, tuple)):
            for i, item in enumerate(obj):
                new_key = current_key + (i,)
                _flatten(item, new_key, depth + 1)
        else:
            # 检查是否需要忽略该值
            should_ignore = False
            if ignore_types:
                for ignore_type in ignore_types:
                    # 如果ignore_type是类型本身
                    if isinstance(ignore_type, type):
                        if isinstance(obj, ignore_type):
                            should_ignore = True
                            break
                    # 如果ignore_type是具体的值（如None, ''等）
                    else:
                        if obj == ignore_type:
                            should_ignore = True
                            break
            
            if not should_ignore:
                items.append((current_key, obj))
    
    _flatten(d, parent_key)
    return dict(items)

class ProcesserExit(Exception):
    def __init__(self, exit_type):
        self.exit_type = exit_type

@dataclass
class PathConfig:
    game_path: Path
    llc_base_path: Path
    target_path: Path
    assets_path: Path
    EN_path: Path
    KR_path: Path
    JP_path: Path
    LLC_path: Path
    rel_path: Path
    real_name: str
    target_file: Path
    def __post_init__(self):
        self.assets_path = self.game_path / "LimbusCompany_Data" / "Assets" / "Resources_moved" / "Localize"
        self.llc_base_path = self.game_path / "LimbusCompany_Data" / "lang" / "LLC_zh-CN"
        self.rel_path = self.KR_path.relative_to(self.assets_path)
        self.real_name = self.rel_path.name[3:]
        self.rel_path = self.rel_path.parent
        self.EN_path = self.assets_path / "en" / self.rel_path / f"EN_{self.real_name}"
        self.JP_path = self.assets_path / "jp" / self.rel_path / f"JP_{self.real_name}"
        self.llc_path = self.llc_base_path / self.rel_path / self.real_name
        self.target_file = self.target_path / self.rel_path / self.real_name

@dataclass
class TextMatcher:
    proper_matcher: kit.ProperNounMatcher
    role_list: List[str]
    affect_id_matcher: kit.SimpleMatcher
    affect_name_matcher: kit.SimpleMatcher

class RequestTextBuilder:
    def __init__(self, request_text: Dict[str, Dict[str, Dict[Tuple, str]]],
                 matcher: TextMatcher):
        self.en_text = request_text['en']
        self.kr_text = request_text['kr']
        self.jp_text = request_text['jp']
        self.matcher = matcher
        
    def build(self):
        request_text = list()

class FileProcessor:
    def __init__(self, path_config: PathConfig, matcher: TextMatcher,
                 logger: logging.Logger = logging.getLogger(__name__)):
        self.path_config = path_config
        self.matcher = matcher
        self.logger = logger

    def process_file(self):
        self._load_json()
        
        self._init_base_data()
        
        self._make_data_index()
        
        self._check_empty()
        
        self._check_translated()
        
        request_text = {
            "kr": self._get_translating_text('kr'),
            "jp": self._get_translating_text('jp'),
            "en": self._get_translating_text('en')
        }
        
        builder = RequestTextBuilder(request_text, self.matcher)
        request_text = builder.build()
    
    def _load_json(self):
        try:
            with open(self.path_config.KR_path, 'r', encoding='utf-8-sig') as f:
                self.kr_json:Dict = json.load(f)
            try:
                with open(self.path_config.EN_path, 'r', encoding='utf-8-sig') as f:
                    self.en_json:Dict = json.load(f)
            except FileNotFoundError:
                self.logger.warning(f"{self.path_config.real_name}不存在en文件，使用kr文件")
                self.en_json = self.kr_json.copy()
            try:
                with open(self.path_config.JP_path, 'r', encoding='utf-8-sig') as f:
                    self.jp_json: Dict = json.load(f)
            except FileNotFoundError:
                self.logger.warning(f"{self.path_config.real_name}不存在jp文件，跳过jp文件处理")
                self.jp_json = self.kr_json.copy()
            try:
                with open(self.path_config.LLC_path, 'r', encoding='utf-8-sig') as f:
                    self.llc_json = json.load(f)
            except FileNotFoundError:
                self.logger.warning(f"{self.path_config.real_name}不存在llc文件，使用空文件")
                self.llc_json = {}
        except json.JSONDecodeError:
            self.logger.warning(f"{self.path_config.real_name}文件解析错误，跳过")
            self._save_except()

    def _save_llc(self):
        shutil.copy2(self.path_config.LLC_path, self.path_config.target_file)
        
    def _save_en(self):
        shutil.copy2(self.path_config.EN_path, self.path_config.target_file)

    def _save_jp(self):
        shutil.copy2(self.path_config.JP_path, self.path_config.target_file)

    def _save_kr(self):
        shutil.copy2(self.path_config.KR_path, self.path_config.target_file)
        
    def _save_except(self):
        try:
            self._save_llc()
        except:
            try:
                self._save_en()
            except:
                try:
                    self._save_jp()
                except:
                    try:
                        self._save_kr()
                    except:
                        self.logger.error(f"保存文件{self.path_config.real_name}，请检查文件路径")
                        raise ProcesserExit("save_except_except")
    
    def _save_json(self, json_data):
        try:
            with open(self.path_config.target_file, 'w', encoding='utf-8-sig') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=4)
        except:
            raise ProcesserExit("save_json_except")
            
    def _check_empty(self):
        if self.kr_json in EMPTY_DATA or self.kr_json.get('dataList', []) in EMPTY_DATA_LIST:
            self.logger.warning(f"{self.path_config.real_name}文件为空，跳过")
            if self.path_config.llc_path.exists():
                self._save_llc()
                raise ProcesserExit("empty_llc")
            else:
                raise ProcesserExit("empty_no")

    def _init_base_data(self):
        self.en_data = self.en_json.get('dataList', [])
        self.kr_data = self.kr_json.get('dataList', [])
        self.jp_data = self.jp_json.get('dataList', [])
        self.llc_data = self.llc_json.get('dataList', [])
        
        if self.path_config.rel_path.name == 'StoryData':
            self.is_story = True
        else:
            self.is_story = False
            
    def _make_data_index(self):
        if self.is_story:
            self._make_data_index_story()
        else:
            self._make_data_index_default()
            
    def _make_data_index_default(self):
        self.en_index = {i['id']: i for i in self.en_data}
        self.kr_index = {i['id']: i for i in self.kr_data}
        self.jp_index = {i['id']: i for i in self.jp_data}
        self.llc_index = {i['id']: i for i in self.llc_data}
        
    def _make_data_index_story(self):
        self.en_index = {i: d for i, d in enumerate(self.en_data)}
        self.kr_index = {i: d for i, d in enumerate(self.kr_data)}
        self.jp_index = {i: d for i, d in enumerate(self.jp_data)}
        self.llc_index = {i: d for i, d in enumerate(self.llc_data)}
        
    def _check_translated(self):
        if not len(self.jp_index)==len(self.kr_index)==len(self.en_index):
            self.logger.warning(f"""{self.path_config.real_name}文件三语长度不同
                jp:{len(self.jp_index)} kr:{len(self.kr_index)} en:{len(self.en_index)}""")
            def change_len(dict_:dict, dict_kr:dict) -> dict:
                result = {}
                for i in dict_kr:
                    if i in dict_:
                        result[i] = dict_[i]
                    else:
                        result[i]=dict_kr[i]
                return result
            self.en_index = change_len(self.en_index, self.kr_index)
            self.jp_index = change_len(self.jp_index, self.kr_index)
            self.llc_index = change_len(self.llc_index, self.kr_index)
        
        if list(self.kr_index)==list(self.llc_index):
            self._save_llc()
            raise ProcesserExit("already_translated")
        
    def _get_translating(self):
        translating_list = list()
        for i in self.kr_index:
            if i not in self.llc_index:
                translating_list.append(i)
        self.translating_list = translating_list
                
    def _get_translating_text(self, lang='kr') -> Dict[str, Dict[Tuple, str]]:
        translating_text = dict()
        if lang == 'kr':
            lang_index = self.kr_index
        elif lang == 'jp':
            lang_index = self.jp_index
        else:
            lang_index = self.en_index
        for i in self.translating_list:
            flatten_item = flatten_dict_enhanced(lang_index[i],
                                         ignore_types=[None, int, float])
            for key in flatten_item:
                if key[-1] in AVOID_PATH:
                    del flatten_item[key]
            translating_text[i] = flatten_item
        
        return translating_text