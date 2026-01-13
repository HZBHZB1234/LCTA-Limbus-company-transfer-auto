import translatekit as tkit
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
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
                new_key = current_key + (str(k),)
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

def unflatten_dict_enhanced(original_dict, flat_dict, ignore_types=None):
    """
    将扁平化的字典还原为嵌套字典
    
    参数:
        original_dict: 原始字典结构模板，用于确定字典/列表类型
        flat_dict: 扁平化的字典（键为元组）
        ignore_types: 要忽略的值的类型列表，与flatten_dict_enhanced中的一致
    
    返回:
        还原后的嵌套字典
    """
    # 创建原始结构的深拷贝
    result = deepcopy(original_dict)
    
    def _set_nested(obj, keys, value, original_template, index=0):
        """
        递归设置嵌套字典/列表中的值
        
        参数:
            obj: 当前处理的字典或列表
            keys: 剩余的键序列
            value: 要设置的值
            original_template: 原始结构模板中对应的部分
            index: 当前处理的键索引
        """
        if index >= len(keys):
            return
        
        key = keys[index]
        
        # 如果是最后一个键，直接设置值
        if index == len(keys) - 1:
            # 检查是否需要忽略该值
            if ignore_types:
                should_ignore = False
                for ignore_type in ignore_types:
                    if isinstance(ignore_type, type):
                        if isinstance(value, ignore_type):
                            should_ignore = True
                            break
                    else:
                        if value == ignore_type:
                            should_ignore = True
                            break
                
                if should_ignore:
                    return
            
            # 根据原始模板确定数据类型
            if isinstance(obj, dict):
                # 如果原始模板中该键不存在，使用字符串键
                if key not in original_template:
                    # 尝试将整数键转换为字符串
                    obj[str(key)] = value
                else:
                    obj[key] = value
            elif isinstance(obj, list):
                # 确保索引在列表范围内
                while len(obj) <= key:
                    if isinstance(original_template, list) and len(original_template) > len(obj):
                        # 使用原始模板中的对应值作为占位符
                        obj.append(deepcopy(original_template[len(obj)]))
                    else:
                        obj.append(None)
                obj[key] = value
            return
        
        # 如果不是最后一个键，继续递归
        if isinstance(obj, dict):
            # 检查原始模板中对应位置的数据类型
            if key in original_template:
                next_original = original_template[key]
            else:
                # 尝试将整数键转换为字符串
                str_key = str(key)
                if str_key in original_template:
                    next_original = original_template[str_key]
                    key = str_key  # 使用字符串键
                else:
                    # 如果原始模板中没有该键，根据下一个键的类型推断
                    if index + 1 < len(keys):
                        next_key = keys[index + 1]
                        if isinstance(next_key, int):
                            # 下一个键是整数，可能是列表
                            next_original = []
                        else:
                            # 下一个键是字符串，可能是字典
                            next_original = {}
                    else:
                        next_original = {}
            
            # 如果当前键不存在，根据原始模板或下一个键的类型创建
            if key not in obj:
                if isinstance(next_original, dict):
                    obj[key] = {}
                elif isinstance(next_original, list):
                    obj[key] = []
                else:
                    # 如果下一个键是整数，创建列表
                    if index + 1 < len(keys) and isinstance(keys[index + 1], int):
                        obj[key] = []
                    else:
                        obj[key] = {}
            
            _set_nested(obj[key], keys, value, next_original, index + 1)
            
        elif isinstance(obj, list):
            # 确保索引在列表范围内
            while len(obj) <= key:
                if isinstance(original_template, list) and len(original_template) > len(obj):
                    obj.append(deepcopy(original_template[len(obj)]))
                else:
                    # 根据下一个键的类型创建占位符
                    if index + 1 < len(keys):
                        next_key = keys[index + 1]
                        if isinstance(next_key, int):
                            obj.append([])
                        else:
                            obj.append({})
                    else:
                        obj.append(None)
            
            # 获取原始模板中对应位置的数据类型
            if isinstance(original_template, list) and key < len(original_template):
                next_original = original_template[key]
            else:
                next_original = {}
            
            _set_nested(obj[key], keys, value, next_original, index + 1)
    
    # 遍历扁平化字典，设置值
    for key_tuple, value in flat_dict.items():
        _set_nested(result, key_tuple, value, original_dict)
    
    return result

class ProcesserExit(Exception):
    def __init__(self, exit_type):
        self.exit_type = exit_type

class SimpleMatcher:
    def __init__(self, patterns: List[str]):
        self.patterns = patterns
        
    def match(self, texts: list) -> List[List[int]]:
        result = list()
        for text in texts:
            result.append([i for i, p in enumerate(self.patterns) if p in text])
        return result
    
    def match_equal(self, texts: list) -> List[int]:
        result = list()
        for text in texts:
            try:
                result.append(self.patterns.index(text))
            except ValueError:
                result.append('')
        return result

@dataclass
class RequestConfig:
    is_skill: bool = False
    is_story: bool = False
    enable_proper: bool = True
    enable_role: bool = True
    enable_skill: bool = True

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
class MatcherData:
    role_data: Dict[str, Dict]
    affect_data: List[Dict[str, Dict]]
    proper_data: List[Dict[str, str]]

@dataclass
class TextMatcher:
    proper_matcher: SimpleMatcher
    role_list: SimpleMatcher
    affect_id_matcher: SimpleMatcher
    affect_name_matcher: SimpleMatcher

class RequestTextBuilder:
    def __init__(self, request_text: Dict[str, Dict[str, Dict[Tuple, str]]],
                 matcher: TextMatcher, file_type_info: Dict[str, bool],
                 role_data: Dict[str, List[Dict]], proper_data: List[Dict]):
        """
        初始化请求文本构建器
        
        Args:
            request_text: 包含en, jp, kr三种语言的文本字典
            matcher: 文本匹配器，包含专有名词和状态效果匹配器
            file_type_info: 文件类型信息，包含is_story和is_skill等标志
            role_data: 角色数据，用于构建角色参考
            proper_data: 专有名词数据
        """
        self.en_text = request_text['en']
        self.kr_text = request_text['kr']
        self.jp_text = request_text['jp']
        self.matcher = matcher
        self.file_type_info = file_type_info
        self.role_data = role_data
        self.proper_data = proper_data
        
        # 用于存储构建结果
        self.unified_request = None
        
    def build(self) -> Dict[str, Any]:
        """
        构建统一请求结构
        
        Returns:
            统一结构化的请求字典
        """
        # 提取所有文本项
        EN_texts = []
        KR_texts = []
        JP_texts = []
        all_proper_terms = {}
        all_affects = {}
        all_models = {}
        
        # 遍历所有翻译项（按ID）
        for idx in self.kr_text.keys():
            # 获取当前ID对应的文本
            kr_item = self.kr_text.get(idx, {})
            en_item = self.en_text.get(idx, {})
            jp_item = self.jp_text.get(idx, {})
            
            # 合并所有路径的文本（用换行符连接）
            kr_texts_item = list(kr_item.values())
            en_texts_item = list(en_item.values())
            jp_texts_item = list(jp_item.values())
            
            for i in range(len(jp_texts_item) - 1, -1, -1):
                JP = jp_texts_item[i]
                EN = en_texts_item[i]
                KR = kr_texts_item[i]
                if JP in EMPTY_TEXT and EN in EMPTY_TEXT and KR in EMPTY_TEXT:
                    jp_texts_item.pop(i)
                    en_texts_item.pop(i)
                    kr_texts_item.pop(i)
                        
            KR_texts.extend(kr_texts_item)
            EN_texts.extend(en_texts_item)
            JP_texts.extend(jp_texts_item)
        
        return self.unified_request
    
    def get_request_text(self, is_text_format: bool = False) -> str:
        """
        获取请求文本（JSON或纯文本格式）
        
        Args:
            is_text_format: 是否返回纯文本格式
        
        Returns:
            格式化后的请求文本
        """
        if self.unified_request is None:
            self.build()
            
        if is_text_format:
            # 调用test_request.py中的make_text函数
            import _feature.test_request as test_request
            return test_request.make_text(self.unified_request)
        else:
            return json.dumps(self.unified_request, indent=2, ensure_ascii=False)

class FileProcessor:
    def __init__(self, path_config: PathConfig, matcher: TextMatcher,
                 request_config: RequestConfig,
                 logger: logging.Logger = logging.getLogger(__name__)):
        self.path_config = path_config
        self.matcher = matcher
        self.logger = logger
        self.request_config = request_config

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
        
        builder = RequestTextBuilder(request_text, self.matcher, self.request_config)
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
            
        if self.path_config.real_name.startswith('Skills_'):
            self.is_skill = True
        else:
            self.is_skill = False
        
        self.request_config.is_story = self.is_story
        self.request_config.is_skill = self.is_skill
            
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
        """
        返回值说明:
          {
              "key的内容，大概率是id":{
                  ("索引", "格式", "元组"): "字符串信息"
              }
          }
        """
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
