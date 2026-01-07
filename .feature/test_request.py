import translatekit as tkit
from translatekit import kit
from pathlib import Path
from typing import List, Optional, Tuple
from translate_doc import *
import json

def make_text(texts):
    """
    将文本数据转换为纯文本格式，用于翻译请求
    
    Args:
        texts: 包含翻译文本和元数据的字典列表
    
    Returns:
        格式化后的纯文本字符串
    """
    texts = texts.get('textList', [])
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
            '---': r'\-\-\-',  # 转义分隔符
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
    
    for i, text_item in enumerate(texts):
        # 添加文本块分隔符（使用更明确的分隔符）
        if i > 0:
            result_lines.append("\n" + "=" * 60 + "\n")
        
        # 文本块标题
        result_lines.append(f"【文本块 {i+1}】")
        
        # 核心文本内容
        core_lines = []
        
        # 添加各语言文本（转义特殊字符）
        kr_text = escape_text(text_item.get('kr', ''))
        en_text = escape_text(text_item.get('en', ''))
        jp_text = escape_text(text_item.get('jp', ''))
        
        core_lines.append(f"韩文 (KR): {kr_text}")
        core_lines.append(f"英文 (EN): {en_text}")
        core_lines.append(f"日文 (JP): {jp_text}")
        
        result_lines.extend(format_section("原文内容", core_lines, level=2))
        
        # 专有名词信息
        if 'proper' in text_item and text_item['proper']:
            proper_lines = []
            for proper_item in text_item['proper']:
                term = escape_text(proper_item.get('term', ''))
                translation = escape_text(proper_item.get('translation', ''))
                note = escape_text(proper_item.get('note', ''))
                
                proper_line = f"- {term} → {translation}"
                if note:
                    proper_line += f" (备注: {note})"
                proper_lines.append(proper_line)
            
            result_lines.extend(format_section("专有名词参考", proper_lines, level=2))
        
        # 角色信息
        if 'model' in text_item and text_item['model']:
            model_lines = []
            for lang, model_info in text_item['model'].items():
                if model_info and model_info != '获取失败':
                    escaped_info = escape_text(model_info)
                    model_lines.append(f"{lang.upper()}: {escaped_info}")
            
            result_lines.extend(format_section("说话者信息", model_lines, level=2))
        
        # 效果信息
        if 'affect' in text_item and text_item['affect']:
            affect_lines = []
            for affect_item in text_item['affect']:
                affect_id = affect_item.get('id', '')
                kr_name = escape_text(affect_item.get('KR-data', {}).get('name', ''))
                zh_name = escape_text(affect_item.get('ZH-data', {}).get('name', ''))
                affect_lines.append(f"[ID: {affect_id}] {kr_name} → {zh_name}")
            
            result_lines.extend(format_section("效果参考", affect_lines, level=2))
        
        # 添加文本块结束标记
        result_lines.append(f"\n【文本块 {i+1} 结束】")
    
    # 添加整体结束标记
    if result_lines:
        result_lines.append("\n" + "*" * 60)
        result_lines.append("【所有文本块已列出，请开始翻译】")
    
    return "\n".join(result_lines)
is_text = False
config = tkit.TranslationConfig(
    api_setting={
        "api_key": "your_api_key",
        "response_format": "text" if is_text else "json_object",
        "system_prompt": TEXT_SYSTEM_PROMPT if is_text else JSON_SYSTEM_PROMPT
    },
    debug_mode=True,
    enable_metrics=True
)
translator = tkit.LLMGeneralTranslator(config=config,model='deepseek')

def translate_text(texts) -> List:
    """
    使用 LLM 翻译文本
    
    Args:
        texts: 待翻译的文本
    
    Returns:
        翻译后的文本
    """
    if is_text:
        request_text = make_text(texts)
    else:
        request_text = json.dumps(texts,indent=1,ensure_ascii=False)
    result = translator.translate(request_text)
    return result