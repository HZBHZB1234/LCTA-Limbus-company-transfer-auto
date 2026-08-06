"""
webutils/llm_fancy/scanner.py
bus 语法选择规则的编译与语言包文本候选收集。

与 webutils/fancy/bus.py 保持语义一致（文件匹配器 glob/exact/regex、
bus 路径 token 解析），但实现独立，避免与翻译功能耦合。
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from typing import Any, Optional

from webutils.fancy.bus import (
    IndexToken,
    KeyToken,
    SelectorToken,
    WildcardToken,
    parse_bus_path,
)
from webutils.fancy.engine import RuleValidationError

JsonPath = tuple[Any, ...]

EMPTY_TEXT = {"", "-"}


@dataclass(frozen=True)
class CompiledFileMatcher:
    kind: str
    value: str
    pattern: Optional[re.Pattern[str]] = None

    def matches(self, normalized: str, filename: str) -> bool:
        if self.kind == "exact":
            return normalized == self.value
        if self.kind == "regex":
            target = normalized if "/" in self.value else filename
            return bool(self.pattern.search(target))
        target = normalized if "/" in self.value else filename
        return fnmatch.fnmatchcase(target, self.value)


@dataclass(frozen=True)
class CompiledSelectionRule:
    files: tuple[CompiledFileMatcher, ...]
    tokens: tuple  # tuple[BusToken, ...]
    all_string_leaves: bool

    def matches_file(self, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/")
        filename = normalized.rsplit("/", 1)[-1]
        return any(matcher.matches(normalized, filename) for matcher in self.files)


@dataclass(frozen=True)
class CompiledSelection:
    name: str
    rules: tuple[CompiledSelectionRule, ...]

    def for_file(self, relative_path: str) -> tuple[CompiledSelectionRule, ...]:
        return tuple(rule for rule in self.rules if rule.matches_file(relative_path))


@dataclass(frozen=True)
class Candidate:
    """一个待美化的文本候选。"""

    file: str          # 语言包内相对路径（posix 风格）
    path: JsonPath     # 解析后的 JSON 路径
    bus_path: str      # 可回写的 bus 路径字符串
    value: str


def compile_file_matcher(value: Any, field_name: str) -> CompiledFileMatcher:
    """编译文件匹配器，与 bus.py 的 _compile_file_matcher 语义一致。"""
    if isinstance(value, str) and value:
        return CompiledFileMatcher(kind="glob", value=value.replace("\\", "/"))
    if not isinstance(value, dict):
        raise RuleValidationError(f"{field_name} 必须是非空 glob 字符串或匹配对象")
    if isinstance(value.get("exact"), str) and value["exact"]:
        normalized = value["exact"].replace("\\", "/")
        return CompiledFileMatcher(kind="exact", value=normalized)
    regex = value.get("regex")
    if not isinstance(regex, str) or not regex:
        raise RuleValidationError(f"{field_name} 正则匹配对象需要非空 regex")
    try:
        pattern = re.compile(regex)
    except re.error as exc:
        raise RuleValidationError(f"{field_name} 正则错误: {exc}") from exc
    return CompiledFileMatcher(kind="regex", value=regex, pattern=pattern)


def compile_selection(selection: Any) -> CompiledSelection:
    """校验并编译选择规则。

    结构：{"name": str, "files": [匹配器...], "rules": [{"files": [匹配器...], "path": str}]}
    path 为空字符串表示匹配全部字符串叶子。
    """
    if not isinstance(selection, dict):
        raise RuleValidationError("选择规则必须是对象 {name, files, rules}")
    name = selection.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RuleValidationError("选择规则 name 必须是非空字符串")
    raw_rules = selection.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise RuleValidationError("选择规则 rules 必须是非空数组")
    default_files = selection.get("files", ["*.json"])
    if not isinstance(default_files, list) or not default_files:
        raise RuleValidationError("选择规则 files 必须是非空数组")
    compiled_default_files = tuple(
        compile_file_matcher(item, f"files[{index}]")
        for index, item in enumerate(default_files)
    )

    compiled_rules: list[CompiledSelectionRule] = []
    for rule_index, rule in enumerate(raw_rules):
        if not isinstance(rule, dict):
            raise RuleValidationError(f"rules[{rule_index}] 必须是对象")
        raw_path = rule.get("path", "")
        if not isinstance(raw_path, str):
            raise RuleValidationError(f"rules[{rule_index}].path 必须是字符串")
        raw_files = rule.get("files")
        if raw_files is None:
            files = compiled_default_files
        else:
            if not isinstance(raw_files, list) or not raw_files:
                raise RuleValidationError(f"rules[{rule_index}].files 必须是非空数组")
            files = tuple(
                compile_file_matcher(item, f"rules[{rule_index}].files[{file_index}]")
                for file_index, item in enumerate(raw_files)
            )
        compiled_rules.append(CompiledSelectionRule(
            files=files,
            tokens=parse_bus_path(raw_path),
            all_string_leaves=raw_path == "",
        ))
    return CompiledSelection(name=name.strip(), rules=tuple(compiled_rules))


def validate_selection(selection: Any) -> list[str]:
    """校验选择规则，返回错误列表（空列表表示通过）。"""
    try:
        compile_selection(selection)
    except RuleValidationError as exc:
        return [str(exc)]
    return []


def dedup_candidates(candidates: list[Candidate]) -> tuple[list[Candidate], dict[int, list[Candidate]]]:
    """按精确文本去重，保持扫描顺序。

    返回 (代表候选列表, {代表索引: 全部同文本候选})。
    相同文本只送一次 LLM，结果随后展开应用到组内所有路径。
    """
    representatives: list[Candidate] = []
    groups: dict[int, list[Candidate]] = {}
    index_by_value: dict[str, int] = {}
    for candidate in candidates:
        rep_index = index_by_value.get(candidate.value)
        if rep_index is None:
            rep_index = len(representatives)
            index_by_value[candidate.value] = rep_index
            representatives.append(candidate)
            groups[rep_index] = []
        groups[rep_index].append(candidate)
    return representatives, groups


def _path_to_bus_str(path: JsonPath) -> str:
    """将解析后的 JSON 路径序列化为 bus 路径字符串。"""
    segments: list[str] = []
    for item in path:
        if isinstance(item, int):
            if segments:
                segments[-1] += f"[{item}]"
            else:
                segments.append(f"[{item}]")
        else:
            segments.append(str(item))
    return ".".join(segments)


def resolve_candidates(
    data: Any,
    tokens: tuple,
    *,
    all_string_leaves: bool,
) -> list[tuple[JsonPath, str]]:
    """解析数据中匹配 token 的 (路径, bus路径字符串) 列表。"""
    results: list[tuple[JsonPath, str]] = []

    if all_string_leaves:
        def walk_leaves(current: Any, current_path: JsonPath) -> None:
            if isinstance(current, str):
                results.append((current_path, _path_to_bus_str(current_path)))
            elif isinstance(current, dict):
                for key, value in current.items():
                    walk_leaves(value, current_path + (key,))
            elif isinstance(current, list):
                for index, value in enumerate(current):
                    walk_leaves(value, current_path + (index,))
        walk_leaves(data, ())
        return results

    def walk(current: Any, token_index: int, current_path: JsonPath) -> None:
        if token_index == len(tokens):
            results.append((current_path, _path_to_bus_str(current_path)))
            return
        token = tokens[token_index]
        if isinstance(token, KeyToken):
            if isinstance(current, dict):
                if token.name in current:
                    walk(current[token.name], token_index + 1, current_path + (token.name,))
                return
            if isinstance(current, list):
                for list_index, item in enumerate(current):
                    if isinstance(item, dict):
                        walk(item, token_index, current_path + (list_index,))
                return
            return
        if isinstance(token, WildcardToken):
            if isinstance(current, list):
                for list_index, item in enumerate(current):
                    walk(item, token_index + 1, current_path + (list_index,))
            return
        if isinstance(token, IndexToken):
            if isinstance(current, list) and 0 <= token.index < len(current):
                walk(current[token.index], token_index + 1, current_path + (token.index,))
            return
        if isinstance(current, list):
            for item_index, item in enumerate(current):
                if isinstance(item, dict) and str(item.get(token.field)) == token.value:
                    walk(item, token_index + 1, current_path + (item_index,))
                    break

    walk(data, 0, ())
    return results


def scan_data(data: Any, relative_path: str, selection: CompiledSelection) -> list[Candidate]:
    """扫描单个文件数据，收集匹配的文本候选（跳过空串与占位符）。"""
    candidates: list[Candidate] = []
    for rule in selection.for_file(relative_path):
        resolved = resolve_candidates(
            data,
            rule.tokens,
            all_string_leaves=rule.all_string_leaves,
        )
        for path, bus_path in resolved:
            value = data
            try:
                for item in path:
                    value = value[item]
            except (KeyError, IndexError, TypeError):
                continue
            if not isinstance(value, str) or value.strip() in EMPTY_TEXT:
                continue
            candidates.append(Candidate(
                file=relative_path,
                path=path,
                bus_path=bus_path,
                value=value,
            ))
    return candidates
