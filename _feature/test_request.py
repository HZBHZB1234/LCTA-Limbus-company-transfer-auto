import translatekit as tkit
from translatekit import kit
from pathlib import Path
from typing import List, Optional, Tuple
from translate_doc import *
import json

def make_unified_request(texts_data):
    """
    创建统一的请求结构，将专有名词和状态效果提取到顶部
    
    Args:
        texts_data: 包含翻译文本和元数据的字典
    
    Returns:
        统一结构化的请求字典
    """
    texts = texts_data.get('textList', [])
    
    # 提取所有专有名词（去重）
    all_proper_terms = {}
    # 提取所有状态效果（去重）
    all_affects = {}
    # 提取所有角色信息（去重）
    all_models = {}
    
    # 收集所有文本块的信息
    text_items = []
    for i, text_item in enumerate(texts):
        # 收集专有名词
        if 'proper' in text_item and text_item['proper']:
            for proper_item in text_item['proper']:
                term = proper_item.get('term', '')
                if term and term not in all_proper_terms:
                    all_proper_terms[term] = {
                        'term': term,
                        'translation': proper_item.get('translation', ''),
                        'note': proper_item.get('note', '')
                    }
        
        # 收集状态效果
        if 'affect' in text_item and text_item['affect']:
            for affect_item in text_item['affect']:
                affect_id = affect_item.get('id', '')
                if affect_id and affect_id not in all_affects:
                    all_affects[affect_id] = {
                        'id': affect_id,
                        'ZH-data': affect_item.get('ZH-data', {}),
                        'KR-data': affect_item.get('KR-data', {})
                    }
        
        # 收集角色信息
        if 'model' in text_item and text_item['model']:
            for lang, model_info in text_item['model'].items():
                if model_info and model_info != '获取失败':
                    if model_info not in all_models:
                        all_models[model_info] = model_info
        
        # 创建简化的文本块
        text_block = {
            'id': i + 1,
            'kr': text_item.get('kr', ''),
            'en': text_item.get('en', ''),
            'jp': text_item.get('jp', '')
        }
        
        # 添加专有名词引用
        if 'proper' in text_item and text_item['proper']:
            text_block['proper_refs'] = [item.get('term', '') for item in text_item['proper']]
        
        # 添加状态效果引用
        if 'affect' in text_item and text_item['affect']:
            text_block['affect_refs'] = [item.get('id', '') for item in text_item['affect']]
        
        # 添加角色引用
        if 'model' in text_item and text_item['model']:
            text_block['model'] = text_item['model']
        
        text_items.append(text_block)
    
    # 构建统一的请求结构
    unified_request = {
        'metadata': {
            'total_text_blocks': len(text_items),
            'proper_terms_count': len(all_proper_terms),
            'affects_count': len(all_affects),
            'models_count': len(all_models)
        },
        'reference': {
            'proper_terms': list(all_proper_terms.values()) if all_proper_terms else [],
            'affects': list(all_affects.values()) if all_affects else [],
            'model_docs': texts_data.get('doc_modal', []),
            'skill_doc': texts_data.get('doc_skill', '')
        },
        'text_blocks': text_items
    }
    
    return unified_request

def make_text(texts):
    """
    将统一结构的请求转换为纯文本格式，用于翻译请求
    
    Args:
        texts: 统一结构化的请求字典
    
    Returns:
        格式化后的纯文本字符串
    """
    result_lines = []
    
    def escape_text(text):
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
    
    def format_section(title, content_lines, level=1):
        """格式化一个区块"""
        indent = "  " * (level - 1)
        section_lines = []
        section_lines.append(f"\n{indent}【{title}】")
        section_lines.extend(content_lines)
        return section_lines
    
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
        result_lines.extend(format_section("专有名词术语表", [
            f"{i+1}. {escape_text(item.get('term', ''))} → {escape_text(item.get('translation', ''))}" + 
            (f" (备注: {escape_text(item.get('note', ''))})" if item.get('note') else "")
            for i, item in enumerate(reference['proper_terms'])
        ]))
    
    # 状态效果参考
    if reference.get('affects'):
        result_lines.extend(format_section("状态效果术语表", [
            f"{i+1}. [ID: {item.get('id', '')}] {escape_text(item.get('KR-data', {}).get('name', ''))} → {escape_text(item.get('ZH-data', {}).get('name', ''))}"
            for i, item in enumerate(reference['affects'])
        ]))
    
    # 角色文档参考
    if reference.get('model_docs'):
        result_lines.extend(format_section("角色说话风格参考", [
            f"- {escape_text(str(doc))}" for doc in reference['model_docs']
        ]))
    
    # 技能文档参考
    if reference.get('skill_doc'):
        result_lines.extend(format_section("技能翻译指南", [
            escape_text(reference['skill_doc'])
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
            f"韩文 (KR): {escape_text(block.get('kr', ''))}",
            f"英文 (EN): {escape_text(block.get('en', ''))}",
            f"日文 (JP): {escape_text(block.get('jp', ''))}"
        ]
        result_lines.extend(format_section("原文内容", core_lines, level=2))
        
        # 专有名词引用
        if 'proper_refs' in block and block['proper_refs']:
            ref_lines = [f"- 引用了术语表中的: {', '.join(block['proper_refs'])}"]
            result_lines.extend(format_section("专有名词引用", ref_lines, level=2))
        
        # 状态效果引用
        if 'affect_refs' in block and block['affect_refs']:
            ref_lines = [f"- 引用了状态效果: {', '.join(block['affect_refs'])}"]
            result_lines.extend(format_section("状态效果引用", ref_lines, level=2))
        
        # 角色信息
        if 'model' in block and block['model']:
            model_lines = []
            for lang, model_info in block['model'].items():
                if model_info and model_info != '获取失败':
                    escaped_info = escape_text(model_info)
                    model_lines.append(f"{lang.upper()}: {escaped_info}")
            
            result_lines.extend(format_section("说话者信息", model_lines, level=2))
        
        result_lines.append(f"【文本块 {block['id']} 结束】")
    
    # 添加整体结束标记
    if text_blocks:
        result_lines.append("\n" + "*" * 80)
        result_lines.append("【所有文本块已列出，请开始翻译】")
        result_lines.append("【翻译时请参考上方的术语表和指南】")
    
    return "\n".join(result_lines)

is_text = False
with open('.env/llm.json', 'r', encoding='utf-8') as f:
    llm_config = json.load(f)
    
config = tkit.TranslationConfig(
    api_setting={
        "api_key": llm_config['deepseek'],
        "response_format": "text" if is_text else "json_object",
        "system_prompt": TEXT_SYSTEM_PROMPT if is_text else JSON_SYSTEM_PROMPT,
        "max_tokens": 4000
    },
    debug_mode=True,
    enable_metrics=True,
    text_max_length=30000
)
translator = tkit.LLMGeneralTranslator(config=config, model='deepseek')

def translate_text(texts) -> List:
    """
    使用 LLM 翻译文本
    
    Args:
        texts: 待翻译的文本
    
    Returns:
        翻译后的文本
    """
    # 创建统一结构的请求
    unified_request = make_unified_request(texts)
    
    if is_text:
        request_text = make_text(unified_request)
    else:
        request_text = json.dumps(unified_request, indent=2, ensure_ascii=False)
    
    result = translator.translate(request_text)
    
    if is_text:
        result_list = result.split('\n\n')
        result_list = [item.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r') for item in result_list]
    else:
        result_list = json.loads(result).get('translations')
    return result_list