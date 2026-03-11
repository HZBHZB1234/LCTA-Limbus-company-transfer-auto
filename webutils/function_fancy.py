import json
import re
import logging
from pathlib import Path
from copy import deepcopy
from typing import List, Dict, Optional, Union

# 导入颜色渐变处理函数
from Faust_fancy import process_dlg_text

logger = logging.getLogger('fancy')

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

def get_value_by_path(data, path):
    """
    根据元组路径从嵌套的字典/列表中获取值。

    参数:
        data: 嵌套的字典/列表结构（通常是 JSON 解析后的数据）
        path: 由字符串和整数组成的元组，表示访问路径。
              例如 ('a', 'b', 0) 表示 data['a']['b'][0]。

    返回:
        路径对应的值。

    异常:
        KeyError: 如果字典键不存在。
        IndexError: 如果列表索引越界。
        TypeError: 如果路径中的某部分与数据类型不匹配
                   （例如在列表上使用字符串键，或在字典上使用整数索引）。
    """
    if not path:  # 空路径返回原数据
        return data

    current = data
    for key in path:
        if isinstance(key, int):
            # 预期当前节点是列表或元组
            if isinstance(current, (list, tuple)):
                try:
                    current = current[key]
                except IndexError:
                    raise IndexError(f"Index {key} out of range for path {path}")
            else:
                raise TypeError(f"Expected list/tuple at path segment {key}, got {type(current)}")
        else:
            # 预期当前节点是字典
            if isinstance(current, dict):
                try:
                    current = current[key]
                except KeyError:
                    raise KeyError(f"Key '{key}' not found at path {path}")
            else:
                raise TypeError(f"Expected dict at path segment {key}, got {type(current)}")
    return current

def path_tuple_to_str(path_tuple):
    """将元组路径转换为点分隔字符串（用于正则匹配）"""
    return '.'.join(str(part) for part in path_tuple)

def transform_path(source_path: tuple, aim_str: str) -> tuple:
    """
    根据 aim 字符串对源路径进行转换。
    aim_str 由点分隔，支持 [back] 回退一级，其余部分作为新路径段添加。
    数字字符串（如 "123"）会被转换为整数，以便作为列表索引。
    """
    if not aim_str:
        return source_path
    new_parts = list(source_path)  # 复制一份可变列表
    for token in aim_str.split('.'):
        if token == '[back]':
            if new_parts:
                new_parts.pop()
        else:
            # 尝试将纯数字字符串转为整数
            try:
                int_token = int(token)
                new_parts.append(int_token)
            except ValueError:
                new_parts.append(token)
    return tuple(new_parts)

def apply_operations(value: str, operations: list) -> str:
    """
    依次应用 operations 中的操作。
    支持的操作类型（通过字典内容自动识别）：
      - 正则替换：包含 'from' 和 'to' 键
      - 颜色渐变：包含 'rate' 键（可选，默认 2.0）
    若值不是字符串，则直接返回原值（无法处理）。
    """
    if not isinstance(value, str):
        logger.debug(f"值不是字符串，跳过操作: {value}")
        return value

    for op in operations:
        if not isinstance(op, dict):
            logger.warning(f"操作不是字典，忽略: {op}")
            continue

        # 正则替换操作
        if 'from' in op and 'to' in op:
            from_re = op.get('from')
            to_str = op.get('to')
            if from_re is not None and to_str is not None:
                try:
                    value = re.sub(from_re, to_str, value)
                except Exception as e:
                    logger.warning(f"正则替换出错 (from={from_re}, to={to_str}): {e}")
        # 颜色渐变操作
        elif 'rate' in op:
            rate = op.get('rate', 2.0)
            try:
                value = process_dlg_text(value, rate)
            except Exception as e:
                logger.warning(f"颜色渐变处理出错 (rate={rate}): {e}")
        else:
            logger.warning(f"未知操作类型: {op}")

    return value

def exec_json(data: dict, config: list) -> dict:
    """
    根据规则列表更新数据。
    config: 规则列表，每个元素格式：
        {
            "aimFile": "regex for file path",      # 可选，在 fancy_main 中预筛选
            "aim": "path regex (no trigger) or path template (with trigger)",
            "trigger": { "aim": "path regex", "re": "content regex" },  # 可选
            "action": [ {"from": "...", "to": "..."}, {"rate": 2.0} ]   # 操作列表，可混合多种类型
        }
    """
    flat_data = flatten_dict_enhanced(data)
    updates = {}

    # 将扁平数据转换为 (点路径, 元组路径, 值) 列表，便于多次匹配
    flat_items = [(path_tuple_to_str(k), k, v) for k, v in flat_data.items()]

    for rule in config:
        aim_pattern_str = rule.get('aim')
        if not aim_pattern_str:
            continue

        # 获取操作列表，兼容旧格式
        operations = rule.get('action', [])
        trigger = rule.get('trigger')

        if trigger:
            # 有 trigger 的情况
            trigger_aim_re = re.compile(trigger['aim'])
            trigger_re_re = re.compile(trigger['re'])

            # 匹配 trigger.aim 路径
            matched_paths = [
                (key_str, key_tuple, val)
                for key_str, key_tuple, val in flat_items
                if trigger_aim_re.search(key_str)
            ]

            # 对每个匹配的路径，检查值是否匹配 trigger.re
            for src_str, src_tuple, src_val in matched_paths:
                if isinstance(src_val, str) and trigger_re_re.search(src_val):
                    # 路径转换
                    dst_tuple = transform_path(src_tuple, aim_pattern_str)
                    # 应用操作列表
                    new_val = apply_operations(get_value_by_path(data, dst_tuple), operations)
                    updates[dst_tuple] = new_val
        else:
            # 无 trigger：直接匹配 aim 路径
            aim_re = re.compile(aim_pattern_str)
            matched_paths = [
                (key_str, key_tuple, val)
                for key_str, key_tuple, val in flat_items
                if aim_re.search(key_str)
            ]
            for key_str, key_tuple, val in matched_paths:
                new_val = apply_operations(val, operations)
                updates[key_tuple] = new_val

    # 将更新应用到原始数据
    return update_dict_with_flattened(data, updates)

def fancy_main(game_path: str, package_name: str, config: list):
    """
    处理语言包下的所有 JSON 文件。
    config: 规则集列表，每个元素包含 "rules" 列表。
    """
    # 展开所有规则集，提取所有规则
    all_rules = []
    for ruleset in config:
        all_rules.extend(ruleset.get('rules', []))

    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang' / package_name
    files = list(lang_path.rglob('*.json'))
    logger.info(f'一共{len(files)}个文件')

    for file in files:
        # 筛选适用于当前文件的规则
        using_config = []
        for rule in all_rules:
            aim_file_pattern = rule.get('aimFile')
            if aim_file_pattern and re.search(aim_file_pattern, str(file)):
                using_config.append(rule)

        if using_config:
            logger.debug(f'{file}可用，启用规则{using_config}')
            try:
                data = json.loads(file.read_text(encoding='utf-8-sig'))
                data = exec_json(data, using_config)
                file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=4), encoding='utf-8-sig')
            except Exception as e:
                logger.exception(f"处理文件 {file} 时出错: {e}")

if __name__ == '__main__':
    fancy_main('C:\\Program Files (x86)\\Steam\\steamapps\\common\\Limbus Company\\',
               'LLc-CN-LCTA', json.loads((Path(__file__).parent / 'build-in-fancy.json')
                                         .read_text(encoding='utf-8')))