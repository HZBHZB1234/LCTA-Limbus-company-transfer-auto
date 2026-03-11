import re
from typing import List, Dict, Tuple

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """将十六进制颜色转换为RGB值"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    elif len(hex_color) == 3:
        r = int(hex_color[0]*2, 16)
        g = int(hex_color[1]*2, 16)
        b = int(hex_color[2]*2, 16)
    else:
        r, g, b = 255, 255, 255  # 默认白色
    return r, g, b

def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """将RGB值转换为十六进制颜色"""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

def interpolate_color(start_rgb: Tuple[int, int, int], end_rgb: Tuple[int, int, int], 
                     ratio: float) -> Tuple[int, int, int]:
    """在两个颜色之间插值"""
    r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio)
    g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio)
    b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio)
    return r, g, b

def is_white_color(rgb: Tuple[int, int, int]) -> bool:
    """检查颜色是否为白色"""
    return rgb == (255, 255, 255)

def extract_text_and_tags(text: str) -> List[Dict]:
    """提取文本和标签，将文本字符和HTML标签分开处理"""
    # 匹配HTML标签的正则表达式
    tag_pattern = r'(<[^>]+>)'
    parts = []
    
    # 分割文本和标签
    segments = re.split(tag_pattern, text)
    
    for segment in segments:
        if not segment:
            continue
        if segment.startswith('<') and segment.endswith('>'):
            # 这是HTML标签
            parts.append({'type': 'tag', 'content': segment})
        else:
            # 这是文本内容，需要区分普通字符和特殊字符
            for char in segment:
                # 检查是否为特殊字符（换行符、制表符、回车符等）
                if char in ['\n', '\t', '\r']:
                    parts.append({'type': 'special', 'content': char})
                else:
                    parts.append({'type': 'char', 'content': char})
    
    return parts

def apply_color_gradient_custom(text: str, start_color: str, end_color: str, gradient_rate: float = 2.0) -> str:
    """对文本应用颜色渐变效果（支持自定义起始和结束颜色）
    Args:
        text: 要处理的文本
        start_color: 起始颜色
        end_color: 结束颜色
        gradient_rate: 渐变度，越大渐变越快（默认2.0）
    """
    if not text:
        return text
    
    # 提取文本和标签
    parts = extract_text_and_tags(text)
    
    # 计算需要渐变的字符数量（不包括标签和特殊字符）
    char_count = sum(1 for part in parts if part['type'] == 'char')
    
    if char_count == 0:
        return f"<color={start_color}>{text}</color>"
    
    # 转换颜色
    start_rgb = hex_to_rgb(start_color)
    end_rgb = hex_to_rgb(end_color)
    
    # 构建渐变后的文本
    result_parts = []
    char_index = 0
    
    for part in parts:
        if part['type'] == 'tag' or part['type'] == 'special':
            # 直接添加标签和特殊字符
            result_parts.append(part['content'])
        else:
            # 对普通字符应用渐变
            if char_count > 1:
                # 使用指数函数控制渐变速度，gradient_rate越大渐变越快
                linear_ratio = char_index / (char_count - 1)
                # 应用渐变度参数：gradient_rate越大，ratio增长越快
                ratio = 1 - (1 - linear_ratio) ** gradient_rate
            else:
                ratio = 0  # 只有一个字符时使用起始颜色
            
            # 计算当前字符的颜色
            current_rgb = interpolate_color(start_rgb, end_rgb, ratio)
            current_color = rgb_to_hex(current_rgb)
            
            # 为每个字符单独包装颜色标签
            result_parts.append(f"<color={current_color}>{part['content']}</color>")
            char_index += 1
    
    # 合并所有部分
    return ''.join(result_parts)

def apply_color_gradient(text: str, start_color: str, gradient_rate: float = 2.0) -> str:
    """对文本应用颜色渐变效果（默认渐变到白色）
    Args:
        text: 要处理的文本
        start_color: 起始颜色
        gradient_rate: 渐变度，越大渐变越快（默认2.0）
    """
    return apply_color_gradient_custom(text, start_color, "#ffffff", gradient_rate)

def process_dlg_text(dlg_text: str, gradient_rate: float = 2.0) -> str:
    """处理dlg文本，提取颜色并应用渐变
    Args:
        dlg_text: 要处理的dlg文本
        gradient_rate: 渐变度，越大渐变越快（默认2.0）
    """
    # 匹配颜色标签 - 使用re.DOTALL标志来支持跨行匹配
    color_pattern = r'<color=#([a-fA-F0-9]{3,6})>(.*?)</color>'
    match = re.search(color_pattern, dlg_text, re.DOTALL)  # 添加re.DOTALL标志
    
    if not match:
        return dlg_text  # 没有颜色标签，直接返回
    
    color_code = match.group(1)
    text_content = match.group(2)
    
    # 应用颜色渐变
    processed_text = apply_color_gradient(text_content, color_code, gradient_rate)
    
    # 替换原始文本中的对应部分
    return dlg_text.replace(match.group(0), processed_text)
