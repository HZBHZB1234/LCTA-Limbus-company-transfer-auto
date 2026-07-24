import json
import re
import logging
from pathlib import Path
from copy import deepcopy
from typing import List, Dict, Optional, Union

from globalManagers.LogManager import LogManager
_log_manager = LogManager()

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
                continue
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

def _normalize_rule(rule: dict) -> dict:
    """将旧版 trigger/aim 格式归一化为 conditions 数组格式"""
    if "conditions" in rule:
        return rule
    rule = dict(rule)
    condition = {}
    if "trigger" in rule:
        condition["trigger"] = rule.pop("trigger")
    if "aim" in rule:
        condition["aim"] = rule.pop("aim")
    if "fallback" in rule:
        condition["fallback"] = rule.pop("fallback")
    rule["conditions"] = [condition]
    return rule

def exec_json(data: dict, config: list) -> dict:
    """
    根据规则列表更新数据。
    支持三种规则格式（经 _normalize_rule 归一化后统一为 conditions 数组）：
        1. 旧版 aim-only：{"aim": "path regex", "action": [...]}
        2. 旧版 trigger+aim：{"trigger": {"aim": "path regex", "re": "content regex"}, "aim": "template", "action": [...]}
        3. 新版 conditions：{"conditions": [{"trigger": {...}, "aim": "template"}, ...], "action": [...]}
           多个 condition 之间为 AND 关系，需在同一 dataList[N] 父条目内同时成立。
    """
    flat_data = flatten_dict_enhanced(data)
    updates = {}
    flat_items = [(path_tuple_to_str(k), k, v) for k, v in flat_data.items()]

    for rule in config:
        rule = _normalize_rule(rule)
        conditions = rule.get('conditions', [])
        if not conditions:
            continue

        operations = rule.get('action', [])
        first_cond = conditions[0]

        if first_cond.get('trigger'):
            first_aim_pattern = first_cond['trigger']['aim']
        else:
            first_aim_pattern = first_cond['aim']

        first_aim_re = re.compile(first_aim_pattern)

        matched_paths = [
            (key_str, key_tuple, val)
            for key_str, key_tuple, val in flat_items
            if first_aim_re.search(key_str)
        ]

        for key_str, key_tuple, val in matched_paths:
            all_conditions_met = True
            for cond in conditions:
                if cond.get('trigger'):
                    trigger_aim_re = re.compile(cond['trigger']['aim'])
                    trigger_re_re = re.compile(cond['trigger']['re'])
                    trigger_matched_paths = [
                        (ks, kt, v2)
                        for ks, kt, v2 in flat_items
                        if trigger_aim_re.search(ks) and _is_same_parent(kt, key_tuple)
                    ]
                    trigger_hit = any(
                        isinstance(v2, (str, int, float, bool)) and trigger_re_re.search(str(v2))
                        for _, _, v2 in trigger_matched_paths
                    )
                    if not trigger_hit:
                        all_conditions_met = False
                        break
                else:
                    aim_re = re.compile(cond['aim'])
                    if not aim_re.search(key_str):
                        all_conditions_met = False
                        break

            if not all_conditions_met:
                continue

            for cond in conditions:
                if cond.get('trigger'):
                    dst_tuple = transform_path(key_tuple, cond.get('aim', ''))
                else:
                    dst_tuple = key_tuple
                new_val = apply_operations(
                    get_value_by_path(data, dst_tuple),
                    operations,
                    data=flat_data,
                    dst_tuple=dst_tuple
                )
                updates[dst_tuple] = new_val

    return update_dict_with_flattened(data, updates)


def _is_same_parent(tuple_a: tuple, tuple_b: tuple) -> bool:
    """判断两个扁平路径是否属于同一个 dataList 父条目"""
    def find_datalist_index(t):
        for i, part in enumerate(t):
            if part == 'dataList' and i + 1 < len(t):
                return i + 1
        return None
    idx_a = find_datalist_index(tuple_a)
    idx_b = find_datalist_index(tuple_b)
    if idx_a is None or idx_b is None:
        return False
    return tuple_a[idx_a] == tuple_b[idx_b]

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
                _log_manager.log_error(e)