import json
import re
import logging
from pathlib import Path
from copy import deepcopy
from typing import List, Dict, Optional, Union

# 导入颜色渐变处理函数
from .Faust_fancy import process_dlg_text
from .builtinFancyFunc import builtinFunc
from translateFunc.proper.flat import *

logger = logging.getLogger('fancy')

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

def apply_operations(value: str, operations: list, data: Dict[tuple, str] = {}, dst_tuple: tuple = ()) -> str:
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

        if 'builtIn' in op:
            funcSelectName = op['builtIn']
            try:
                funcSelect = builtinFunc[funcSelectName]
            except:
                logger.warning(f'尝试使用未定义的func: {funcSelectName}')
            value = funcSelect(value, data, dst_tuple)
        # 正则替换操作
        elif 'from' in op and 'to' in op:
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
                    new_val = apply_operations(get_value_by_path(data, dst_tuple), operations,
                     data=flat_data, dst_tuple=dst_tuple)
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
                new_val = apply_operations(val, operations, data=flat_data, dst_tuple=key_tuple)
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