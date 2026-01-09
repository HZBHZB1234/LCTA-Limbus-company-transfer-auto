import json
import os
import sys
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
import logging
from dataclasses import dataclass
from collections import defaultdict

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 模拟C#项目中的SimpleJSON库结构
class JsonNode:
    def __init__(self, value=None):
        self.value = value
        self._type = type(value)
    
    @property
    def IsString(self):
        return isinstance(self.value, str)
    
    @property
    def IsNumber(self):
        return isinstance(self.value, (int, float))
    
    @property
    def IsArray(self):
        return isinstance(self.value, list)
    
    @property
    def IsObject(self):
        return isinstance(self.value, dict)
    
    def __str__(self):
        return str(self.value)
    
    def __getitem__(self, key):
        if isinstance(self.value, dict):
            return self.value.get(key, JsonNode(None))
        return JsonNode(None)
    
    @property
    def Count(self):
        if isinstance(self.value, (list, dict)):
            return len(self.value)
        return 0

class JsonObject(JsonNode):
    def __init__(self, value=None):
        if value is None:
            value = {}
        super().__init__(value)
        self.Dict = self.value
    
    def __getitem__(self, key):
        if isinstance(key, int):
            keys = list(self.Dict.keys())
            if key < len(keys):
                return keys[key]
            return ""
        return super().__getitem__(key)
    
    def get(self, key, default=None):
        return self.Dict.get(key, default)

class JsonArray(JsonNode):
    def __init__(self, value=None):
        if value is None:
            value = []
        super().__init__(value)
        self.List = self.value
    
    def __getitem__(self, index):
        if index < len(self.List):
            return JsonNode(self.List[index])
        return JsonNode(None)
    
    def Add(self, item):
        self.List.append(item)

def JsonParse(json_str: str) -> JsonNode:
    try:
        data = json.loads(json_str)
        if isinstance(data, dict):
            return JsonObject(data)
        elif isinstance(data, list):
            return JsonArray(data)
        else:
            return JsonNode(data)
    except:
        return JsonNode(None)

# C#项目中的工具函数
def ToDictionaryEx(source, key_selector, element_selector):
    """模拟C#中的ToDictionaryEx扩展方法"""
    result = {}
    for item in source:
        key = key_selector(item)
        element = element_selector(item)
        result[key] = element
    return result

def GetJsonPaths(token, current_path="$"):
    """模拟C#中的GetJsonPaths方法，但返回扁平化路径"""
    paths = {}
    
    if isinstance(token, dict):
        for key, value in token.items():
            path = f"{current_path}.{key}"
            if isinstance(value, (dict, list)):
                paths.update(GetJsonPaths(value, path))
            else:
                if not IsEmpty(value):
                    paths[path] = value
    elif isinstance(token, list):
        for i, item in enumerate(token):
            path = f"{current_path}[{i}]"
            if isinstance(item, (dict, list)):
                paths.update(GetJsonPaths(item, path))
            else:
                if not IsEmpty(item):
                    paths[path] = item
    else:
        if not IsEmpty(token):
            paths[current_path] = token
    
    return paths

def IsEmpty(token):
    """判断token是否为空"""
    if token is None:
        return True
    if isinstance(token, str):
        return token == "" or token == "-"
    if isinstance(token, (dict, list)):
        return len(token) == 0
    return False

# 主处理类
class JsonFileProcessor:
    def __init__(self, game_path: str):
        self.game_path = Path(game_path)
        self.KrDic: Dict[str, JsonObject] = {}
        self.EnDic: Dict[str, JsonObject] = {}
        self.JpDic: Dict[str, JsonObject] = {}
        self.CnDic: Dict[str, JsonObject] = {}
        
        # 路径配置
        self.localize_path = self.game_path / "LimbusCompany_Data" / "Assets" / "Resources_moved" / "Localize"
        self.output_path = Path("./LLc-CN_LCTA")
        
        # 初始化
        self._init_paths()
    
    def _init_paths(self):
        """初始化路径"""
        if self.output_path.exists():
            shutil.rmtree(self.output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)
    
    def LoadGitHubWorks(self, directory: Path, dic: Dict[str, JsonObject]):
        """模拟C#中的LoadGitHubWroks方法"""
        if not directory.exists():
            return
        
        for file_path in directory.rglob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
                
                # 移除BOM
                if content.startswith('\ufeff'):
                    content = content[1:]
                
                # 转换为JsonObject
                json_obj = JsonParse(content)
                if json_obj.IsObject:
                    # 构建相对路径键
                    rel_path = file_path.relative_to(self.localize_path)
                    file_key = f"/{rel_path}".replace("\\", "/")
                    dic[file_key] = json_obj
            except Exception as e:
                logger.error(f"加载文件失败 {file_path}: {e}")
    
    def ProcessFiles(self):
        """处理所有文件"""
        # 加载数据
        logger.info("加载KR数据...")
        self.LoadGitHubWorks(self.localize_path / "kr", self.KrDic)
        
        logger.info("加载EN数据...")
        self.LoadGitHubWorks(self.localize_path / "en", self.EnDic)
        
        logger.info("加载JP数据...")
        self.LoadGitHubWorks(self.localize_path / "jp", self.JpDic)
        
        # 处理每个KR文件
        for kr_key, kr_value in self.KrDic.items():
            try:
                self._ProcessSingleFile(kr_key, kr_value)
            except Exception as e:
                logger.error(f"处理文件失败 {kr_key}: {e}")
        
        logger.info(f"处理完成！输出路径: {self.output_path}")
    
    def _ProcessSingleFile(self, kr_key: str, kr_obj: JsonObject):
        """处理单个文件"""
        # 跳过空文件
        if kr_obj.Count == 0:
            return
        
        # 获取对应的EN和JP数据
        en_obj = self.EnDic.get(kr_key, JsonObject({}))
        jp_obj = self.JpDic.get(kr_key, JsonObject({}))
        
        # 检查是否为StoryData
        is_story = kr_key.startswith("/StoryData") or "StoryData" in kr_key
        
        # 获取数据数组
        # 修复这里：使用键名 "dataList" 而不是索引 0
        krobjs = kr_obj["dataList"]
        if not krobjs.IsArray or krobjs.Count == 0:
            return
        
        krobjs_array = krobjs.value if krobjs.IsArray else []
        
        # 处理EN和JP数据
        en_objs_array = []
        jp_objs_array = []
        
        if is_story:
            # 修复这里：同样使用 "dataList" 键
            en_dataList = en_obj["dataList"]
            jp_dataList = jp_obj["dataList"]
            
            if en_dataList.IsArray:
                en_objs_array = en_dataList.value
            if jp_dataList.IsArray:
                jp_objs_array = jp_dataList.value
        else:
            # 非StoryData使用字典映射
            en_dict = {}
            jp_dict = {}
            
            # 修复这里：同样使用 "dataList" 键
            en_dataList = en_obj["dataList"]
            jp_dataList = jp_obj["dataList"]
            
            if en_dataList.IsArray:
                en_items = en_dataList.value
                for item in en_items:
                    if isinstance(item, list) and len(item) > 0:
                        key = str(item[0]) if item[0] is not None else ""
                        en_dict[key] = item[1] if len(item) > 1 else {}
            
            if jp_dataList.IsArray:
                jp_items = jp_dataList.value
                for item in jp_items:
                    if isinstance(item, list) and len(item) > 0:
                        key = str(item[0]) if item[0] is not None else ""
                        jp_dict[key] = item[1] if len(item) > 1 else {}
        
        # 创建输出结构
        output_data = []
        
        for i, krobj in enumerate(krobjs_array):
            if not isinstance(krobj, list) or len(krobj) < 2:
                continue
            
            object_id = str(krobj[0]) if krobj[0] is not None else ""
            krobj_dict = krobj[1] if len(krobj) > 1 and isinstance(krobj[1], dict) else {}
            
            # 获取对应的EN和JP对象
            if is_story:
                if i < len(en_objs_array):
                    en_item = en_objs_array[i]
                    enobj_dict = en_item[1] if isinstance(en_item, list) and len(en_item) > 1 and isinstance(en_item[1], dict) else {}
                else:
                    enobj_dict = {}
                
                if i < len(jp_objs_array):
                    jp_item = jp_objs_array[i]
                    jpobj_dict = jp_item[1] if isinstance(jp_item, list) and len(jp_item) > 1 and isinstance(jp_item[1], dict) else {}
                else:
                    jpobj_dict = {}
            else:
                enobj_dict = en_dict.get(object_id, {})
                jpobj_dict = jp_dict.get(object_id, {})
            
            # 跳过特定object_id
            if is_story and object_id == "-1":
                continue
            
            # 处理字段
            for field_key, field_value in krobj_dict.items():
                # 跳过数字字段和特定字段
                if isinstance(field_value, (int, float)) or field_key in ["id", "model", "usage"]:
                    continue
                
                if isinstance(field_value, str):
                    # 字符串字段
                    original = field_value
                    if not original or original == "-":
                        continue
                    
                    # 获取上下文
                    en_text = enobj_dict.get(field_key, "")
                    jp_text = jpobj_dict.get(field_key, "")
                    
                    # 生成输出项
                    output_id = str(i) if is_story else object_id
                    output_item = {
                        "id": len(output_data) + 1,
                        "key": f"{output_id}-{field_key}",
                        "original": original,
                        "translation": "",  # 初始为空，需要翻译
                        "context": f"EN :\n{en_text}\nJP :\n{jp_text}" if en_text or jp_text else ""
                    }
                    output_data.append(output_item)
                
                elif isinstance(field_value, list):
                    # 数组字段
                    kr_array = field_value
                    
                    # 获取对应的EN和JP数组
                    en_array = enobj_dict.get(field_key, [])
                    jp_array = jpobj_dict.get(field_key, [])
                    
                    # 展开数组
                    kr_paths = GetJsonPaths(kr_array, "$")
                    en_paths = GetJsonPaths(en_array, "$")
                    jp_paths = GetJsonPaths(jp_array, "$")
                    
                    for path, kr_value in kr_paths.items():
                        if not kr_value or kr_value == "-":
                            continue
                        
                        # 生成扁平化键
                        output_id = str(i) if is_story else object_id
                        flat_path = path.replace("$", "").replace(".", "").replace("[", "").replace("]", "")
                        output_key = f"{output_id}-{field_key}{flat_path}"
                        
                        # 获取上下文
                        en_value = en_paths.get(path, "")
                        jp_value = jp_paths.get(path, "")
                        
                        output_item = {
                            "id": len(output_data) + 1,
                            "key": output_key,
                            "original": kr_value,
                            "translation": "",
                            "context": f"EN :\n{en_value}\nJP :\n{jp_value}" if en_value or jp_value else ""
                        }
                        output_data.append(output_item)
        
        # 保存输出文件
        if output_data:
            self._SaveOutputFile(kr_key, output_data)    
    def _SaveOutputFile(self, original_key: str, data: List[Dict]):
        """保存输出文件"""
        # 构建输出路径
        file_name = original_key.split("/")[-1]
        
        # 如果是KR_开头的文件，去掉前缀
        if file_name.startswith("KR_"):
            file_name = file_name[3:]
        
        # 构建目录结构
        rel_dir = "/".join(original_key.split("/")[1:-1])  # 去掉第一个斜杠和文件名
        output_dir = self.output_path / rel_dir if rel_dir else self.output_path
        
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / file_name
        
        # 保存为JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"保存文件: {output_file}")

# 翻译应用类（PTG逻辑）
class TranslationApplier:
    def __init__(self, game_path: str, translation_path: str):
        self.game_path = Path(game_path)
        self.translation_path = Path(translation_path)
        
        self.KrDic: Dict[str, JsonObject] = {}
        self.TranslationDic: Dict[str, Dict[str, str]] = {}  # file_key -> {translation_key: text}
        
    def LoadData(self):
        """加载数据"""
        # 加载KR数据
        kr_path = self.game_path / "LimbusCompany_Data" / "Assets" / "Resources_moved" / "Localize" / "kr"
        
        processor = JsonFileProcessor(str(self.game_path))
        processor.LoadGitHubWorks(kr_path, self.KrDic)
        
        # 加载翻译数据
        self._LoadTranslations()
    
    def _LoadTranslations(self):
        """加载翻译数据"""
        for file_path in self.translation_path.rglob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    translations = json.load(f)
                
                # 构建相对路径键
                rel_path = file_path.relative_to(self.translation_path)
                file_key = f"/{rel_path}".replace("\\", "/")
                
                # 提取翻译映射
                trans_dict = {}
                for item in translations:
                    if isinstance(item, dict):
                        key = item.get("key", "")
                        translation = item.get("translation", "")
                        if key and translation:
                            trans_dict[key] = translation
                
                self.TranslationDic[file_key] = trans_dict
                
            except Exception as e:
                logger.error(f"加载翻译文件失败 {file_path}: {e}")
    
    def ApplyTranslations(self, output_path: str):
        """应用翻译"""
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        for kr_key, kr_obj in self.KrDic.items():
            try:
                # 获取对应的翻译
                translation_dict = self.TranslationDic.get(kr_key, {})
                
                if not translation_dict:
                    logger.warning(f"没有找到翻译: {kr_key}")
                    continue
                
                # 应用翻译
                translated_data = self._ApplyToSingleFile(kr_key, kr_obj, translation_dict)
                
                if translated_data:
                    # 保存文件
                    file_name = kr_key.split("/")[-1]
                    if file_name.startswith("KR_"):
                        file_name = file_name[3:]
                    
                    rel_dir = "/".join(kr_key.split("/")[1:-1])
                    output_dir = output_path / rel_dir if rel_dir else output_path
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                    output_file = output_dir / file_name
                    
                    # 格式化为游戏JSON格式
                    game_format = self._ConvertToGameFormat(translated_data)
                    
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(game_format, f, ensure_ascii=False, indent=2)
                    
                    logger.info(f"生成翻译文件: {output_file}")
                    
            except Exception as e:
                logger.error(f"应用翻译失败 {kr_key}: {e}")
    
    def _ApplyToSingleFile(self, kr_key: str, kr_obj: JsonObject, translation_dict: Dict[str, str]) -> List:
        """将翻译应用到单个文件"""
        if kr_obj.Count == 0:
            return []
        
        is_story = kr_key.startswith("/StoryData") or "StoryData" in kr_key
        
        # 获取原始数据
        # 修复这里：使用 "dataList" 键
        krobjs = kr_obj["dataList"]
        if not krobjs.IsArray:
            return []
        
        krobjs_array = krobjs.value if krobjs.IsArray else []
        
        # 创建输出数据
        output_data = []
        
        for i, krobj in enumerate(krobjs_array):
            if not isinstance(krobj, list) or len(krobj) < 2:
                output_data.append(krobj)
                continue
            
            object_id = str(krobj[0]) if krobj[0] is not None else ""
            krobj_dict = krobj[1] if len(krobj) > 1 and isinstance(krobj[1], dict) else {}
            
            # 跳过特定object_id
            if is_story and object_id == "-1":
                output_data.append(krobj)
                continue
            
            # 复制字典以便修改
            translated_dict = krobj_dict.copy() if krobj_dict else {}
            
            for field_key, field_value in list(translated_dict.items()):
                # 跳过数字字段和特定字段
                if isinstance(field_value, (int, float)) or field_key in ["id", "model", "usage"]:
                    continue
                
                if isinstance(field_value, str):
                    # 字符串字段
                    output_id = str(i) if is_story else object_id
                    translation_key = f"{output_id}-{field_key}"
                    
                    translation = translation_dict.get(translation_key)
                    if translation:
                        translated_dict[field_key] = translation.replace("\\n", "\n")
                
                elif isinstance(field_value, list):
                    # 数组字段
                    # 展开数组路径
                    paths = GetJsonPaths(field_value, "$")
                    
                    for path, _ in paths.items():
                        output_id = str(i) if is_story else object_id
                        flat_path = path.replace("$", "").replace(".", "").replace("[", "").replace("]", "")
                        translation_key = f"{output_id}-{field_key}{flat_path}"
                        
                        translation = translation_dict.get(translation_key)
                        if translation:
                            # 应用翻译到数组路径
                            self._ApplyToArrayPath(field_value, path, translation.replace("\\n", "\n"))
                    
                    translated_dict[field_key] = field_value
            
            # 构建输出项
            output_item = [object_id, translated_dict]
            output_data.append(output_item)
        
        return output_data    
    def _ApplyToArrayPath(self, array_data: List, path: str, translation: str):
        """应用翻译到数组路径"""
        # 简化路径处理
        try:
            # 解析路径
            if path.startswith("$["):
                # 简单索引路径
                import re
                indices = re.findall(r'\[(\d+)\]', path)
                current = array_data
                
                for i, index_str in enumerate(indices):
                    index = int(index_str)
                    
                    if i == len(indices) - 1:
                        # 最后一个索引，直接赋值
                        if index < len(current):
                            current[index] = translation
                    else:
                        # 中间索引，继续深入
                        if index < len(current) and isinstance(current[index], list):
                            current = current[index]
                        else:
                            break
        except:
            pass
    
    def _ConvertToGameFormat(self, data: List) -> Dict:
        """转换为游戏JSON格式"""
        # 根据C#项目，原始格式是包含dataList的
        return {"dataList": data}

