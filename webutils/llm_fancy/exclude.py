"""
webutils/llm_fancy/exclude.py
通过 bus 引擎模拟执行已有规则集，找出已处理的文本路径，避免重复送 LLM。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

from webutils.fancy.bus import CompiledBus, apply_bus, compile_bus_ruleset, is_bus_ruleset
from webutils.function_fancy import load_fancy_folder_rules

JsonPath = tuple[Any, ...]


def compile_exclusion_rulesets(names: list) -> tuple[tuple[CompiledBus, ...], list[str]]:
    """按名称编译 fancy/ 中的 bus 规则集作为排除项。

    返回 (已编译规则集, 找不到的规则集名列表)。非 bus 格式的规则集被忽略。
    """
    if not names:
        return (), []
    by_name: dict[str, dict] = {}
    for ruleset in load_fancy_folder_rules():
        if is_bus_ruleset(ruleset):
            by_name[ruleset.get("name", "")] = ruleset
    missing: list[str] = []
    compiled: list[CompiledBus] = []
    for name in names:
        ruleset = by_name.get(name)
        if ruleset is None:
            missing.append(str(name))
            continue
        compiled.append(compile_bus_ruleset(ruleset))
    return tuple(compiled), missing


def excluded_paths(
    data: Any,
    relative_path: str,
    compiled_exclusions: tuple[CompiledBus, ...],
) -> set[JsonPath]:
    """模拟执行全部排除规则集，返回其会修改的路径集合。

    每个规则集在独立深拷贝上执行；失败规则集的部分变更不残留
    （副本直接丢弃），成功后将副本接回以保持依序累积语义。
    """
    if not compiled_exclusions:
        return set()
    copy = deepcopy(data)
    changed: set[JsonPath] = set()
    for compiled in compiled_exclusions:
        rules = compiled.for_file(relative_path)
        if not rules:
            continue
        try:
            working = deepcopy(copy)
            result = apply_bus(working, compiled, relative_path, rules=rules)
            changed.update(result.changed_paths)
            copy = working
        except Exception:
            continue
    return changed
