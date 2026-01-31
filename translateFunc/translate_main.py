from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
import json
import sys
import shutil
import logging
from dataclasses import dataclass, field
from copy import deepcopy
if TYPE_CHECKING:
    from translatekit import TranslatorBase

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

print(sys.path)
project_root = Path(__file__).parent.parent
print(project_root)
sys.path.insert(0, str(project_root))

import translateFunc.translate_doc as translate_doc

EMPTY_DATA = [{'dataList': []}, {}, []]
EMPTY_DATA_LIST = [[], [{}]]
EMPTY_TEXT = ['', '-']
AVOID_PATH = ['usage', 'id', 'model']

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

def update_dict_with_flattened(original_dict, flat_updates):
    """
    使用扁平化字典更新原始字典
    
    参数:
        original_dict: 要更新的原始字典
        flat_updates: 扁平化字典，键为元组形式的路径，值为要更新的值
    
    返回:
        更新后的原始字典（原地更新）
    """
    for path, value in flat_updates.items():
        # 确保路径是元组
        if not isinstance(path, tuple):
            path = (path,)
        
        # 遍历到路径的倒数第二个元素
        current = original_dict
        for i, key in enumerate(path[:-1]):
            # 如果是列表/元组索引
            if isinstance(key, int):
                # 确保当前位置是列表或元组
                if isinstance(current, (list, tuple)):
                    # 如果是元组，需要转换为列表才能修改
                    if isinstance(current, tuple):
                        # 这里假设我们不允许修改元组，跳过或抛异常
                        # 但为了通用性，我们可以转换为列表
                        raise TypeError(f"Cannot update tuple at path {path[:i+1]}")
                    # 确保索引有效
                    if key < len(current):
                        current = current[key]
                    else:
                        raise IndexError(f"Index {key} out of range at path {path[:i+1]}")
                else:
                    raise TypeError(f"Expected list/tuple at {path[:i+1]}, got {type(current)}")
            # 如果是字典键
            else:
                if isinstance(current, dict):
                    if key not in current:
                        # 如果键不存在，创建新字典
                        current[key] = {}
                    current = current[key]
                else:
                    raise TypeError(f"Expected dict at {path[:i+1]}, got {type(current)}")
        
        # 设置最终值
        last_key = path[-1]
        if isinstance(last_key, int):
            if isinstance(current, (list, tuple)):
                if isinstance(current, tuple):
                    raise TypeError(f"Cannot update tuple at path {path}")
                if last_key < len(current):
                    current[last_key] = value
                else:
                    # 如果索引超出范围，扩展列表
                    if last_key >= len(current):
                        current.extend([None] * (last_key - len(current) + 1))
                    current[last_key] = value
            else:
                raise TypeError(f"Expected list/tuple at {path[:-1]}, got {type(current)}")
        else:
            if isinstance(current, dict):
                current[last_key] = value
            else:
                raise TypeError(f"Expected dict at {path[:-1]}, got {type(current)}")
    
    return original_dict

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
    max_length: int = 20000  # 最大允许长度
    is_text_format: bool = False  # 是否使用文本格式
    is_llm: bool = True
    translator: Optional['TranslatorBase'] = None  # 使用的翻译器实例
    from_lang: str = 'KR'
    save_result:bool = True

@dataclass
class PathConfig:
    target_path: Path = Path()
    llc_base_path: Path = Path()
    KR_base_path: Path = Path()
    EN_base_path: Path = Path()
    JP_base_path: Path = Path()
    
    def get_need_dirs(self):
        return [i.relative_to(self.KR_base_path)
                for i in self.KR_base_path.glob('*') if i.is_dir()]
    
    def create_need_dirs(self):
        for dir_path in self.get_need_dirs():
            target_dir = self.target_path / dir_path
            target_dir.mkdir(parents=True, exist_ok=True)
        

class FilePathConfig:
    def __init__(self, KR_path: Path, _PathConfig: PathConfig):
        self.KR_path = KR_path
        self.rel_path = Path(KR_path.relative_to(_PathConfig.KR_base_path))
        self.real_name = self.rel_path.name[3:]
        self.rel_dir = self.rel_path.parent
        self.real_name = self.rel_path.name[3:]
        self.EN_path = _PathConfig.EN_base_path / self.rel_dir / f"EN_{self.real_name}"
        self.JP_path = _PathConfig.JP_base_path / self.rel_dir / f"JP_{self.real_name}"
        self.LLC_path = _PathConfig.llc_base_path / self.rel_dir / self.real_name
        self.target_file = _PathConfig.target_path / self.rel_dir / self.real_name

@dataclass
class MatcherData:
    role_data: Dict[str, Dict] = field(default_factory=dict)
    affect_data: List[Dict[str, Dict]] = field(default_factory=list)
    proper_data: List[Dict[str, str]] = field(default_factory=list)

@dataclass
class TextMatcher:
    proper_matcher: SimpleMatcher = SimpleMatcher([])
    role_list: SimpleMatcher = SimpleMatcher([])
    affect_id_matcher: SimpleMatcher = SimpleMatcher([])
    affect_name_matcher: SimpleMatcher = SimpleMatcher([])

class RequestTextBuilder:
    def __init__(self, request_text: Dict[str, Dict[str, Dict[Tuple, str]]],
                 matcher: TextMatcher, request_config: RequestConfig,
                 matcher_data: MatcherData):
        """
        初始化请求文本构建器
        
        Args:
            request_text: 包含en, jp, kr三种语言的文本字典，结构为 {lang: {id: {path_tuple: text}}}
            matcher: 文本匹配器，包含专有名词和状态效果匹配器
            request_config: 请求配置信息，包含is_story和is_skill等标志
            matcher_data: 匹配数据，包含角色数据，专有名词数据，状态效果数据
        """
        self.en_text = request_text['en']
        self.kr_text = request_text['kr']
        self.jp_text = request_text['jp']
        self.matcher = matcher
        self.request_config = request_config
        self.role_data = matcher_data.role_data
        self.proper_data = matcher_data.proper_data
        self.affect_data = matcher_data.affect_data
        
        # 用于存储构建结果
        self.unified_request = None
        self.split_requests = []
        
        # 角色信息缓存
        self.role_model_cache = {}
        
    def build(self) -> Dict[str, Any]:
        """
        构建统一请求结构
        
        Returns:
            统一结构化的请求字典
        """
        # 收集所有文本项
        text_items = []
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
            
            # 过滤空文本
            filtered_texts = []
            for i in range(len(jp_texts_item)):
                JP = jp_texts_item[i] if i < len(jp_texts_item) else ''
                EN = en_texts_item[i] if i < len(en_texts_item) else ''
                KR = kr_texts_item[i] if i < len(kr_texts_item) else ''
                if not (JP in EMPTY_TEXT and EN in EMPTY_TEXT and KR in EMPTY_TEXT):
                    filtered_texts.append({
                        'jp': JP,
                        'en': EN,
                        'kr': KR,
                        'index': i
                    })
            
            # 为每个非空文本创建文本块
            for i, text_info in enumerate(filtered_texts):
                text_block = {
                    'id': len(text_items) + 1,
                    'kr': text_info['kr'],
                    'en': text_info['en'],
                    'jp': text_info['jp']
                }
                
                # 专有名词匹配
                proper_matches = self.matcher.proper_matcher.match([text_info['kr']])[0]
                if proper_matches:
                    text_block['proper_refs'] = []
                    for match_idx in proper_matches:
                        if match_idx < len(self.proper_data):
                            term_info = self.proper_data[match_idx]
                            term = term_info.get('term', '')
                            if term:
                                text_block['proper_refs'].append(term)
                                # 添加到全局专有名词
                                if term not in all_proper_terms:
                                    all_proper_terms[term] = {
                                        'term': term,
                                        'translation': term_info.get('translation', ''),
                                        'note': term_info.get('note', '')
                                    }
                
                # 状态效果匹配（如果是技能文件）
                if self.request_config.is_skill and self.affect_data:
                    affect_id_matches = self.matcher.affect_id_matcher.match([text_info['kr']])[0]
                    affect_name_matches = self.matcher.affect_name_matcher.match([text_info['kr']])[0]
                    affect_matches = list(set(affect_id_matches + affect_name_matches))
                    
                    if affect_matches:
                        text_block['affect_refs'] = []
                        for match_idx in affect_matches:
                            if match_idx < len(self.affect_data):
                                affect_info = self.affect_data[match_idx]
                                affect_id = affect_info.get('id', '')
                                if affect_id:
                                    text_block['affect_refs'].append(affect_id)
                                    # 添加到全局状态效果
                                    if affect_id not in all_affects:
                                        all_affects[affect_id] = {
                                            'id': affect_id,
                                            'ZH-data': affect_info.get('ZH-data', {}),
                                            'KR-data': affect_info.get('KR-data', {})
                                        }
                
                # 角色信息（如果是故事文件）
                if self.request_config.is_story:
                    # 尝试从role_data中获取角色信息
                    model_key = str(idx)
                    if model_key in self.role_model_cache:
                        model_info = self.role_model_cache[model_key]
                    else:
                        # 尝试从role_data中查找
                        model_info = {}
                        for lang, lang_data in self.role_data.items():
                            if str(idx) in lang_data:
                                model_info[lang] = lang_data[str(idx)]
                            elif idx in lang_data:  # 尝试不转换idx为字符串的情况
                                model_info[lang] = lang_data[idx]
                        
                        # 如果没有找到，使用默认值
                        if not model_info:
                            model_info = {
                                'kr': '获取失败',
                                'en': '获取失败', 
                                'jp': '获取失败',
                                'zh': '获取失败'
                            }
                        
                        self.role_model_cache[model_key] = model_info
                    
                    text_block['model'] = model_info
                    
                    # 添加到全局模型
                    for lang, info in model_info.items():
                        if info and info != '获取失败' and info not in all_models:
                            all_models[info] = info
                
                text_items.append(text_block)
        
        # 构建统一的请求结构
        self.unified_request = {
            'metadata': {
                'total_text_blocks': len(text_items),
                'proper_terms_count': len(all_proper_terms),
                'affects_count': len(all_affects),
                'models_count': len(all_models)
            },
            'reference': {
                'proper_terms': list(all_proper_terms.values()) if all_proper_terms else [],
                'affects': list(all_affects.values()) if all_affects else [],
                'model_docs': self._get_role_docs(),
                'skill_doc': self._get_skill_doc()
            },
            'text_blocks': text_items
        }
        
        # 根据长度限制进行分割
        self._split_by_length()
        
        return self.unified_request
    
    def _split_by_length(self):
        """根据最大长度限制分割请求"""
        if self.unified_request is None:
            return
        
        max_length = self.request_config.max_length
        
        # 生成请求文本并检查长度
        request_text = self._get_request_text(self.unified_request)
        
        # 如果文本长度不超过限制，直接返回
        if len(request_text) <= max_length:
            self.split_requests = [self.unified_request]
            return
        
        # 获取文本块
        text_blocks = self.unified_request.get('text_blocks', [])
        total_blocks = len(text_blocks)
        
        # 尝试不同的分割方式
        for num_parts in range(2, min(10, total_blocks) + 1):  # 最多尝试分割成10部分
            # 计算每部分的大小
            part_size = total_blocks // num_parts
            remainder = total_blocks % num_parts
            
            parts = []
            start_idx = 0
            
            for i in range(num_parts):
                # 计算当前部分的结束索引
                end_idx = start_idx + part_size + (1 if i < remainder else 0)
                
                # 提取当前部分的文本块
                part_text_blocks = text_blocks[start_idx:end_idx]
                
                # 创建部分请求，包含完整的参考信息
                part_request = {
                    'metadata': {
                        'total_text_blocks': len(part_text_blocks),
                        'proper_terms_count': len(self.unified_request['reference']['proper_terms']),
                        'affects_count': len(self.unified_request['reference']['affects']),
                        'models_count': len(self.unified_request['reference']['model_docs'])
                    },
                    'reference': self.unified_request['reference'],  # 完整的参考信息
                    'text_blocks': part_text_blocks
                }
                
                parts.append(part_request)
                start_idx = end_idx
            
            # 检查所有部分是否都满足长度限制
            all_valid = True
            for part in parts:
                part_text = self._get_request_text(part)
                if len(part_text) > max_length:
                    all_valid = False
                    break
            
            if all_valid:
                logger.info(f"文本过长，已分割成 {num_parts} 部分")
                self.split_requests = parts
                return
        
        # 如果无法分割成满足条件的部分，尝试更激进的分割
        logger.warning(f"警告：文本过长且无法合理分割，尝试强制分割")
        
        # 简单按固定大小分割
        parts = []
        part_size = max(1, total_blocks // 5)  # 固定分成5部分
        for i in range(0, total_blocks, part_size):
            end_idx = min(i + part_size, total_blocks)
            part_text_blocks = text_blocks[i:end_idx]
            
            part_request = {
                'metadata': {
                    'total_text_blocks': len(part_text_blocks),
                    'proper_terms_count': len(self.unified_request['reference']['proper_terms']),
                    'affects_count': len(self.unified_request['reference']['affects']),
                    'models_count': len(self.unified_request['reference']['model_docs'])
                },
                'reference': self.unified_request['reference'],  # 完整的参考信息
                'text_blocks': part_text_blocks
            }
            
            parts.append(part_request)
        
        self.split_requests = parts
    
    def _get_request_text(self, request_data: Dict[str, Any]) -> str:
        """获取请求文本（根据配置返回文本或JSON格式）"""
        if self.request_config.is_text_format:
            return self._make_text(request_data)
        else:
            return json.dumps(request_data, indent=2, ensure_ascii=False)
    
    def _get_role_docs(self) -> List[str]:
        """获取角色说话风格参考文档"""
        if not self.request_config.is_story:
            return []
        
        # 从role_data中提取角色ID并生成文档
        role_docs = []
        kr_roles = self.role_data.get('kr', {})
        
        for role_id, role_info in kr_roles.items():
            if role_info and role_info != '获取失败':
                # 尝试从translate_doc中获取角色风格
                try:
                    # 检查是否有对应的角色
                    if hasattr(translate_doc, 'RLOE_COMPARE') and role_id in translate_doc.RLOE_COMPARE:
                        role_name = translate_doc.RLOE_COMPARE[role_id]
                        if hasattr(translate_doc, 'ROLE_STYLE') and role_name in translate_doc.ROLE_STYLE:
                            role_style = translate_doc.ROLE_STYLE[role_name]
                            role_doc = f"角色: {role_style.get('角色', role_name)}, " \
                                       f"语言风格: {role_style.get('语言风格', '无特殊说明')}, " \
                                       f"称呼习惯: {role_style.get('称呼习惯', '无特殊说明')}"
                            role_docs.append(role_doc)
                except Exception as e:
                    logger.warning(f"获取角色风格时出现错误: {e}")
                    # 退回到基本格式
                    role_doc = f"角色ID: {role_id}, 描述: {role_info}"
                    role_docs.append(role_doc)
        
        return role_docs
    
    def _get_skill_doc(self) -> str:
        """获取技能翻译指南"""
        if self.request_config.is_skill:
            try:
                return translate_doc.SKILLL_DOC
            except Exception as e:
                logger.warning(f"获取技能翻译指南时出现错误: {e}")
                return "技能翻译指南：请保持技能名称和描述的一致性，注意状态效果的准确翻译。"
        return ""
    
    def _escape_text(self, text: str) -> str:
        """转义文本中的特殊字符，方便LLM理解"""
        if not isinstance(text, str):
            return text
        # 转义特殊字符
        escape_map = {
            '\n': '\\n',
            '\t': '\\t',
            '\r': '\\r',
            '\"': '\\"',
            '\'': '\\\'',
            '\\': '\\\\',
            '---': r'\-\-\-',
        }
        result = text
        for old, new in escape_map.items():
            result = result.replace(old, new)
        return result
    
    def _format_section(self, title: str, content_lines: List[str], level: int = 1) -> List[str]:
        """格式化一个区块"""
        indent = "  " * (level - 1)
        section_lines = []
        section_lines.append(f"\n{indent}【{title}】")
        section_lines.extend(content_lines)
        return section_lines
    
    def _make_text(self, texts: Dict[str, Any]) -> str:
        """
        将统一结构的请求转换为纯文本格式，用于翻译请求
        
        Args:
            texts: 统一结构化的请求字典
        
        Returns:
            格式化后的纯文本字符串
        """
        result_lines = []
        
        # 添加元数据信息
        metadata = texts.get('metadata', {})
        result_lines.append("【翻译请求元数据】")
        result_lines.append(f"文本块总数: {metadata.get('total_text_blocks', 0)}")
        result_lines.append(f"专有名词数: {metadata.get('proper_terms_count', 0)}")
        result_lines.append(f"状态效果数: {metadata.get('affects_count', 0)}")
        result_lines.append(f"角色信息数: {metadata.get('models_count', 0)}")
        
        # 添加参考信息部分
        reference = texts.get('reference', {})
        
        # 专有名词参考
        if reference.get('proper_terms'):
            result_lines.extend(self._format_section("专有名词术语表", [
                f"{i+1}. {self._escape_text(item.get('term', ''))} → {self._escape_text(item.get('translation', ''))}" + 
                (f" (备注: {self._escape_text(item.get('note', ''))})" if item.get('note') else "")
                for i, item in enumerate(reference['proper_terms'])
            ]))
        
        # 状态效果参考
        if reference.get('affects'):
            result_lines.extend(self._format_section("状态效果术语表", [
                f"{i+1}. [ID: {item.get('id', '')}] {self._escape_text(item.get('KR-data', {}).get('name', ''))} → {self._escape_text(item.get('ZH-data', {}).get('name', ''))}"
                for i, item in enumerate(reference['affects'])
            ]))
        
        # 角色文档参考
        if reference.get('model_docs'):
            result_lines.extend(self._format_section("角色说话风格参考", [
                f"- {self._escape_text(str(doc))}" for doc in reference['model_docs']
            ]))
        
        # 技能文档参考
        if reference.get('skill_doc'):
            result_lines.extend(self._format_section("技能翻译指南", [
                self._escape_text(reference['skill_doc'])
            ]))
        
        # 添加分隔线
        result_lines.append("\n" + "=" * 80)
        result_lines.append("【以下为需要翻译的文本块】")
        result_lines.append("=" * 80)
        
        # 添加文本块
        text_blocks = texts.get('text_blocks', [])
        for block in text_blocks:
            # 添加文本块分隔符
            if block['id'] > 1:
                result_lines.append("\n" + "-" * 60 + "\n")
            
            result_lines.append(f"【文本块 {block['id']}】")
            
            # 核心文本内容
            core_lines = [
                f"韩文 (KR): {self._escape_text(block.get('kr', ''))}",
                f"英文 (EN): {self._escape_text(block.get('en', ''))}",
                f"日文 (JP): {self._escape_text(block.get('jp', ''))}"
            ]
            result_lines.extend(self._format_section("原文内容", core_lines, level=2))
            
            # 专有名词引用
            if 'proper_refs' in block and block['proper_refs']:
                ref_lines = [f"- 引用了术语表中的: {', '.join(block['proper_refs'])}"]
                result_lines.extend(self._format_section("专有名词引用", ref_lines, level=2))
            
            # 状态效果引用
            if 'affect_refs' in block and block['affect_refs']:
                ref_lines = [f"- 引用了状态效果: {', '.join(block['affect_refs'])}"]
                result_lines.extend(self._format_section("状态效果引用", ref_lines, level=2))
            
            # 角色信息
            if 'model' in block and block['model']:
                model_lines = []
                for lang, model_info in block['model'].items():
                    if model_info and model_info != '获取失败':
                        escaped_info = self._escape_text(model_info)
                        model_lines.append(f"{lang.upper()}: {escaped_info}")
                
                result_lines.extend(self._format_section("说话者信息", model_lines, level=2))
            
            result_lines.append(f"【文本块 {block['id']} 结束】")
        
        # 添加整体结束标记
        if text_blocks:
            result_lines.append("\n" + "*" * 80)
            result_lines.append("【所有文本块已列出，请开始翻译】")
            result_lines.append("【翻译时请参考上方的术语表和指南】")
        
        return "\n".join(result_lines)
    
    def get_request_text(self, is_text_format: Optional[bool] = None) -> str:
        """
        获取所有分割部分的请求文本列表
        
        Args:
            is_text_format: 是否返回纯文本格式，None则使用request_config中的配置
        
        Returns:
            分割后的请求文本列表
        """
        if self.unified_request is None:
            self.build()
            
        # 确定使用哪种格式
        if is_text_format is None:
            is_text_format = self.request_config.is_text_format
        
        result = []
        for request in self.split_requests:
            if is_text_format:
                result.append(self._make_text(request))
            else:
                result.append(json.dumps(request, indent=2, ensure_ascii=False))
        
        return result
    
    def deBuild(self, translated_texts: List[str]) -> Dict[str, Dict[Tuple, str]]:
        """
        将翻译后的文本列表还原为原始结构
        """
        translated_texts_iter = iter(translated_texts)
        result_dict = deepcopy(self.kr_text)
        # 实现还原逻辑
        for idx in result_dict.keys():
            # 获取当前ID对应的文本
            kr_item = self.kr_text.get(idx, {})
            en_item = self.en_text.get(idx, {})
            jp_item = self.jp_text.get(idx, {})
            
            # 合并所有路径的文本（用换行符连接）
            kr_paths_item = list(kr_item.keys())

            # 过滤空文本
            for i in kr_paths_item:
                JP = jp_item[i] if i in jp_item else ''
                EN = en_item[i] if i in en_item else ''
                KR = kr_item[i] if i in kr_item else ''
                if not (JP in EMPTY_TEXT and EN in EMPTY_TEXT and KR in EMPTY_TEXT):
                    result_dict[idx][i] = next(translated_texts_iter)
        
        ok_flag = True
        try:
            next(translated_texts_iter)
            logger.warning("警告：翻译文本数量多于预期，可能有多个多余的翻译文本")
            ok_flag = False
        except StopIteration:
            pass
        if not ok_flag:
            raise StopIteration("翻译文本数量少于预期，可能缺少翻译文本")
        return result_dict


class SimpleRequestTextBuilder():
    def __init__(self, request_text: Dict[str, Dict[str, Dict[Tuple, str]]]):
        """对于非LLM翻译器，无需添加描述和要求，直接返回需要翻译的文本列表"""
        self.en_texts = request_text['en']
        self.kr_texts = request_text['kr']
        self.jp_texts = request_text['jp']
    
    def build(self) -> List:
        """构建请求文本，返回需要翻译的文本列表"""
        EN_result = []
        KR_result = []
        JP_result = []
        
        # 遍历所有ID，将各个语言的文本合并到结果列表中
        for idx in self.kr_texts.keys():
            kr_item = self.kr_texts.get(idx, {})
            jp_item = self.jp_texts.get(idx, {})
            en_item = self.en_texts.get(idx, {})
            
            # 提取所有文本内容
            for path_tuple, text in kr_item.items():
                KR_result.append(text)
            for path_tuple, text in jp_item.items():
                JP_result.append(text)
            for path_tuple, text in en_item.items():
                EN_result.append(text)
        
        empty_texts: List[int] = []
        for index, KR, EN,JP in zip(range(len(KR_result)), KR_result, EN_result,JP_result):
            if KR in EMPTY_TEXT and EN in EMPTY_TEXT and JP in EMPTY_TEXT:
                empty_texts.append(index)
        
        self.KR_build = [i for idx, i in enumerate(KR_result) if idx not in empty_texts]
        self.EN_build = [i for idx, i in enumerate(EN_result) if idx not in empty_texts]
        self.JP_build = [i for idx, i in enumerate(JP_result) if idx not in empty_texts]
        
    def get_request_text(self, from_lang: str = 'KR') -> List[str]:
        """获取文本列表"""
        return getattr(self, f"{from_lang}_build")
    
    def deBuild(self, translated_texts: List[str], from_lang: str = 'kr') -> Dict[str, Dict[Tuple, str]]:
        """将翻译后的文本还原为原始结构"""
        original_texts: Dict[str, Dict[Tuple, str]] = deepcopy(getattr(self, f"{from_lang}_texts"))
        translated_iter = iter(translated_texts)
        
        # 实现还原逻辑
        for idx in original_texts.keys():
            # 获取当前ID对应的文本
            kr_item = self.kr_texts.get(idx, {})
            en_item = self.en_texts.get(idx, {})
            jp_item = self.jp_texts.get(idx, {})
            
            # 合并所有路径的文本（用换行符连接）
            kr_paths_item = list(kr_item.keys())

            # 过滤空文本
            for i in kr_paths_item:
                JP = jp_item[i] if i in jp_item else ''
                EN = en_item[i] if i in en_item else ''
                KR = kr_item[i] if i in kr_item else ''
                if not (JP in EMPTY_TEXT and EN in EMPTY_TEXT and KR in EMPTY_TEXT):
                    original_texts[idx][i] = next(translated_iter)
        
        ok_flag = True
        try:
            next(translated_iter)
            logger.warning("警告：翻译文本数量多于预期，可能有多个多余的翻译文本")
            ok_flag = False
        except StopIteration:
            pass
        if not ok_flag:
            raise StopIteration("翻译文本数量少于预期，可能缺少翻译文本")
        return original_texts

class FileProcessor:
    
    def __init__(self, path_config: FilePathConfig, matcher: TextMatcher,
                 request_config: RequestConfig = RequestConfig(),
                 matcher_data: MatcherData = MatcherData(),
                 logger: logging.Logger = logging.getLogger(__name__)):
        self.path_config = path_config
        self.matcher = matcher
        self.logger = logger
        self.request_config = request_config
        self.matcher_data = matcher_data

    def process_file(self):
        # 1. 加载JSON文件
        # 创建成员变量：self.kr_json, self.en_json, self.jp_json, self.llc_json
        # 格式：字典类型，存储从对应语言JSON文件加载的数据
        self._load_json()
        
        # 2. 检查空文件
        # 如果韩文数据为空，根据是否有llc文件进行不同处理
        # 可能抛出ProcesserExit异常并终止处理
        self._check_empty()
        
        # 3. 初始化基础数据
        # 创建成员变量：self.en_data, self.kr_data, self.jp_data, self.llc_data
        # 格式：列表类型，从JSON中提取的dataList字段内容
        # 创建成员变量：self.is_story, self.is_skill
        # 格式：布尔类型，根据文件路径判断是否为故事文件或技能文件
        # 修改成员变量：self.request_config.is_story, self.request_config.is_skill
        # 格式：布尔类型，更新请求配置中的故事和技能标志
        self._init_base_data()
        
        # 4. 创建数据索引
        # 创建成员变量：self.en_index, self.kr_index, self.jp_index, self.llc_index
        # 格式：字典类型，将数据列表转换为字典索引，便于快速查找
        # 如果是故事文件：键为列表索引(i)，值为对应数据项
        # 如果不是故事文件：键为数据项中的id字段，值为对应数据项
        self._make_data_index()
        
        # 5. 检查翻译状态
        # 检查各语言文件长度是否一致，如果不一致则进行适配
        # 检查是否已经翻译过（llc_index与kr_index的键是否完全一致）
        # 如果已经翻译，保存llc文件并抛出ProcesserExit异常
        self._check_translated()
        
        # 6. 获取需要翻译的条目
        # 创建成员变量：self.translating_list
        # 格式：列表类型，包含所有在kr_index中存在但不在llc_index中的键
        # 这些是需要翻译的数据项标识
        self._get_translating()
        
        # 7. 构建翻译请求文本
        # 创建变量：request_text
        # 格式：字典类型，包含kr、jp、en三种语言的翻译文本
        # 结构：{"kr": {id: {path_tuple: text}}, "jp": ..., "en": ...}
        # path_tuple是扁平化后的路径元组，text是对应的文本内容
        request_text = {
            "kr": self._get_translating_text('kr'),
            "jp": self._get_translating_text('jp'),
            "en": self._get_translating_text('en')
        }
        
        # 8. 根据配置选择翻译构建器并进行翻译
        # 创建变量：builder, request_texts, result
        if self.request_config.is_llm:
            # 使用LLM翻译器
            # 创建RequestTextBuilder实例，用于构建结构化翻译请求
            builder = RequestTextBuilder(request_text, self.matcher,
                                        self.request_config, self.matcher_data)
            # 构建统一请求结构
            request_text = builder.build()
        
            # 获取分割后的请求文本（可能因文本过长而分割成多个部分）
            request_texts = builder.get_request_text()
            result = list()
            
            # 遍历每个分割部分进行翻译
            for i, request_part in enumerate(request_texts):                
                # 根据文本长度计算超时时间
                timeout = max(len(request_part) // 200 + 1, 40)
                
                # 调用翻译器进行翻译
                # result_part: 字符串类型，翻译器返回的翻译结果
                result_part = self.request_config.translator.translate(
                    request_part, timeout=timeout)
                
                # 根据格式解析结果
                if self.request_config.is_text_format:
                    # 文本格式：按双换行符分割，处理转义字符
                    result_list = result_part.split('\n\n')
                    result_list = [item.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r') for item in result_list]
                else:
                    # JSON格式：解析JSON并提取translations字段
                    result_list = json.loads(result_part).get('translations', [])
                
                # 将当前部分的结果添加到总结果中
                result.extend(result_list)
                
                self.logger.info(f"第 {i+1} 部分翻译完成，获得 {len(result_list)} 条结果")
            
        else:
            # 使用非LLM翻译器
            # 创建SimpleRequestTextBuilder实例，用于构建简单文本列表
            builder = SimpleRequestTextBuilder(request_text)
            # 构建文本列表
            builder.build()
            # 获取指定语言的文本列表
            request_texts = builder.get_request_text(
                from_lang=self.request_config.from_lang)
            # 调用翻译器进行批量翻译
            result = self.request_config.translator.translate(request_texts)
            self.logger.info(f"获得 {len(result)} 条结果")
            
        try:
            translated_text = builder.deBuild(result)
        except StopIteration:
            self.logger.warning(f"翻译结果还原时出现问题：返回值长度问题")
            raise ProcesserExit("translation_length_error")
        
        self._de_get_translating_text(translated_text)
        
        result = self._de_get_translating()
        
        self._save_result(result)
          
    def _load_json(self):
        try:
            with open(self.path_config.KR_path, 'r', encoding='utf-8-sig') as f:
                self.kr_json:Dict = json.load(f)
            try:
                with open(self.path_config.EN_path, 'r', encoding='utf-8-sig') as f:
                    self.en_json:Dict = json.load(f)
            except FileNotFoundError:
                self.logger.warning(f"{self.path_config.real_name}不存在en文件，使用kr文件")
                self.en_json = deepcopy(self.kr_json)
            try:
                with open(self.path_config.JP_path, 'r', encoding='utf-8-sig') as f:
                    self.jp_json: Dict = json.load(f)
            except FileNotFoundError:
                self.logger.warning(f"{self.path_config.real_name}不存在jp文件，跳过jp文件处理")
                self.jp_json = deepcopy(self.kr_json)
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
        if not self.request_config.save_result:
            raise ProcesserExit("no_save_except")
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
        raise ProcesserExit("save_except_success")
    
    def _save_result(self, json_data):
        if not self.request_config.save_result:
            raise ProcesserExit("no_save_success")
        try:
            with open(self.path_config.target_file, 'w', encoding='utf-8-sig') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=4)
        except:
            raise ProcesserExit("success_save")
            
    def _check_empty(self):
        if self.kr_json in EMPTY_DATA or self.kr_json.get('dataList', []) in EMPTY_DATA_LIST:
            self.logger.warning(f"{self.path_config.real_name}文件为空，跳过")
            if self.path_config.LLC_path.exists():
                self._save_llc()
                raise ProcesserExit("empty_llc")
            else:
                raise ProcesserExit("empty_no")

    def _init_base_data(self):
        self.en_data = self.en_json.get('dataList', [])
        self.kr_data = self.kr_json.get('dataList', [])
        self.jp_data = self.jp_json.get('dataList', [])
        self.llc_data = self.llc_json.get('dataList', [])
        
        if self.path_config.rel_dir.name == 'StoryData':
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
            keys_to_delete = []
            for key in flatten_item:
                if key[-1] in AVOID_PATH:
                    keys_to_delete.append(key)
            self.get_translating_removement = keys_to_delete
            for key in keys_to_delete:
                del flatten_item[key]
            translating_text[i] = flatten_item
        
        return translating_text
    
    def _de_get_translating_text(self, translated_text: Dict[str, Dict[Tuple, str]]):
        """
        返回值说明:
            {
                "key的内容，大概率是id":{
                  ("索引", "格式", "元组"): "字符串信息"
                }
            }
        """
        self._base_index = deepcopy(self.kr_index)
        for i in self.translating_list:
            trans_item = self._base_index[i]
            translated_item = translated_text[i]
            update_dict_with_flattened(trans_item, translated_item)
        return self._base_index
    
    def _de_get_translating(self):
        result = list()
        for i in self.kr_index:
            if i in self.llc_index:
                result.append(self.llc_index[i])
            else:
                result.append(self._base_index[i])
                
        result = {"dataList": result}
            
        return result