from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Union

from .engine import ApplyResult, RuleValidationError


BUS_FORMAT = "lcta-bus"
BUS_VERSION = 1
MISSING = object()


@dataclass(frozen=True)
class KeyToken:
    name: str


@dataclass(frozen=True)
class IndexToken:
    index: int


@dataclass(frozen=True)
class WildcardToken:
    pass


@dataclass(frozen=True)
class SelectorToken:
    field: str
    value: str


BusToken = Union[KeyToken, IndexToken, WildcardToken, SelectorToken]
JsonPath = tuple[Any, ...]


@dataclass(frozen=True)
class CompiledFileMatcher:
    kind: str
    value: str
    pattern: Optional[re.Pattern[str]] = None

    def matches(self, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/")
        filename = normalized.rsplit("/", 1)[-1]
        if self.kind == "exact":
            return normalized == self.value
        if self.kind == "regex":
            target = normalized if "/" in self.value else filename
            return bool(self.pattern.search(target))
        target = normalized if "/" in self.value else filename
        return fnmatch.fnmatchcase(target, self.value)


@dataclass(frozen=True)
class CompiledReplacement:
    kind: str
    source: Optional[str] = None
    replacement: Optional[str] = None
    mode: str = "literal"
    safe: bool = False
    pattern: Optional[re.Pattern[str]] = None
    value: Any = None


@dataclass(frozen=True)
class CompiledBusRule:
    name: str
    files: tuple[CompiledFileMatcher, ...]
    path: tuple[BusToken, ...]
    all_string_leaves: bool
    replacements: tuple[CompiledReplacement, ...]
    required: bool

    def matches_file(self, relative_path: str) -> bool:
        return any(matcher.matches(relative_path) for matcher in self.files)


@dataclass(frozen=True)
class CompiledBus:
    name: str
    rules: tuple[CompiledBusRule, ...]
    exclude_dirs: tuple[str, ...]

    def is_excluded(self, relative_path: str) -> bool:
        directory_parts = Path(relative_path.replace("\\", "/")).parts[:-1]
        lowered_keywords = tuple(keyword.casefold() for keyword in self.exclude_dirs)
        return any(
            keyword in part.casefold()
            for part in directory_parts
            for keyword in lowered_keywords
        )

    def for_file(self, relative_path: str) -> tuple[CompiledBusRule, ...]:
        if self.is_excluded(relative_path):
            return ()
        return tuple(rule for rule in self.rules if rule.matches_file(relative_path))


@dataclass(frozen=True)
class BusApplyResult:
    data: Any
    changed_paths: tuple[JsonPath, ...]
    matched_rules: int
    failed_rules: int
    errors: tuple[str, ...]

    @property
    def changed_count(self) -> int:
        return len(self.changed_paths)

    def as_apply_result(self) -> ApplyResult:
        return ApplyResult(data=self.data, changed_paths=self.changed_paths)


def is_bus_ruleset(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("version") != BUS_VERSION or not isinstance(data.get("rules"), list):
        return False
    return data.get("format", BUS_FORMAT) == BUS_FORMAT


def is_tiaozhua_config(data: Any) -> bool:
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        return False
    if "version" in data or "edits" in data:
        return False
    rules = data["rules"]
    if not rules:
        return False
    return all(
        isinstance(rule, dict) and "action" in rule
        for rule in rules
    )


def is_lcje_config(data: Any) -> bool:
    if not isinstance(data, dict) or not data:
        return False
    if not all(
        isinstance(key, str) and key.lower().endswith(".json")
        for key in data
    ):
        return False
    if not all(isinstance(value, dict) for value in data.values()):
        return False
    return any(bool(value) for value in data.values())


def parse_bus_path(path: str) -> tuple[BusToken, ...]:
    if path == "":
        return ()
    if not isinstance(path, str):
        raise RuleValidationError("bus path 必须是字符串")

    tokens: list[BusToken] = []
    for segment in path.split("."):
        if not segment:
            raise RuleValidationError(f"bus path 包含空路径段: {path}")
        position = 0
        key_match = re.match(r"^[^\[\]]+", segment)
        if key_match:
            tokens.append(KeyToken(key_match.group(0)))
            position = key_match.end()
        while position < len(segment):
            bracket_match = re.match(r"\[([^\]]+)\]", segment[position:])
            if not bracket_match:
                raise RuleValidationError(f"bus path 路径语法错误: {path}")
            raw = bracket_match.group(1)
            if raw == "*":
                tokens.append(WildcardToken())
            elif raw.isdigit():
                tokens.append(IndexToken(int(raw)))
            elif raw.startswith("?") and "=" in raw:
                field, value = raw[1:].split("=", 1)
                if not field:
                    raise RuleValidationError(f"bus path selector 字段为空: {path}")
                tokens.append(SelectorToken(field, value))
            else:
                raise RuleValidationError(f"bus path 路径语法错误: {path}")
            position += bracket_match.end()
        if position == 0:
            raise RuleValidationError(f"bus path 路径语法错误: {path}")
    return tuple(tokens)


def _compile_file_matcher(value: Any, field_name: str) -> CompiledFileMatcher:
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


def _compile_replacement(value: Any, field_name: str) -> CompiledReplacement:
    if not isinstance(value, dict):
        raise RuleValidationError(f"{field_name} 必须是对象")
    if "set" in value:
        return CompiledReplacement(kind="set", value=value["set"])

    source = value.get("from")
    replacement = value.get("to")
    if not isinstance(source, str) or not isinstance(replacement, str):
        raise RuleValidationError(f"{field_name} 需要字符串 from/to 或 set")
    mode = value.get("mode", "literal")
    if mode not in {"literal", "regex", "end"}:
        raise RuleValidationError(f"{field_name}.mode 不支持: {mode}")
    pattern = None
    if mode == "regex":
        try:
            pattern = re.compile(source)
        except re.error as exc:
            raise RuleValidationError(f"{field_name} 替换正则错误: {exc}") from exc
    return CompiledReplacement(
        kind="replace",
        source=source,
        replacement=replacement,
        mode=mode,
        safe=bool(value.get("safe", False)),
        pattern=pattern,
    )


def compile_bus_ruleset(ruleset: dict) -> CompiledBus:
    if not is_bus_ruleset(ruleset):
        raise RuleValidationError("bus 规则集需要 format: lcta-bus、version: 1 和 rules 数组")
    name = ruleset.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RuleValidationError("bus 规则集 name 必须是非空字符串")
    default_files = ruleset.get("files", ["*.json"])
    if not isinstance(default_files, list) or not default_files:
        raise RuleValidationError("bus 规则集 files 必须是非空数组")
    compiled_default_files = tuple(
        _compile_file_matcher(item, f"files[{index}]")
        for index, item in enumerate(default_files)
    )
    exclude_dirs = ruleset.get("exclude_dirs", [])
    if not isinstance(exclude_dirs, list) or not all(
        isinstance(item, str) and item for item in exclude_dirs
    ):
        raise RuleValidationError("bus 规则集 exclude_dirs 必须是字符串数组")

    compiled_rules: list[CompiledBusRule] = []
    for rule_index, rule in enumerate(ruleset["rules"]):
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
                _compile_file_matcher(item, f"rules[{rule_index}].files[{file_index}]")
                for file_index, item in enumerate(raw_files)
            )
        replacements = rule.get("replacements")
        if not isinstance(replacements, list) or not replacements:
            raise RuleValidationError(f"rules[{rule_index}].replacements 必须是非空数组")
        compiled_rules.append(CompiledBusRule(
            name=str(rule.get("name", f"规则 {rule_index + 1}")),
            files=files,
            path=parse_bus_path(raw_path),
            all_string_leaves=raw_path == "",
            replacements=tuple(
                _compile_replacement(item, f"rules[{rule_index}].replacements[{replacement_index}]")
                for replacement_index, item in enumerate(replacements)
            ),
            required=bool(rule.get("required", False)),
        ))
    return CompiledBus(
        name=name,
        rules=tuple(compiled_rules),
        exclude_dirs=tuple(exclude_dirs),
    )


def validate_bus_ruleset(ruleset: dict) -> list[str]:
    try:
        compile_bus_ruleset(ruleset)
    except RuleValidationError as exc:
        return [str(exc)]
    return []


def _get_value(data: Any, path: JsonPath, default: Any = MISSING) -> Any:
    current = data
    try:
        for token in path:
            current = current[token]
    except (KeyError, IndexError, TypeError):
        return default
    return current


def _set_value(data: Any, path: JsonPath, value: Any) -> Any:
    if not path:
        return value
    current = data
    for token in path[:-1]:
        current = current[token]
    current[path[-1]] = value
    return data


def _resolve_paths(
    data: Any,
    tokens: tuple[BusToken, ...],
    *,
    allow_missing_final: bool,
) -> tuple[JsonPath, ...]:
    paths: list[JsonPath] = []

    def walk(current: Any, token_index: int, current_path: JsonPath) -> None:
        if token_index == len(tokens):
            paths.append(current_path)
            return
        token = tokens[token_index]
        final_token = token_index == len(tokens) - 1
        if isinstance(token, KeyToken):
            if isinstance(current, dict):
                if token.name in current:
                    walk(current[token.name], token_index + 1, current_path + (token.name,))
                elif allow_missing_final and final_token:
                    paths.append(current_path + (token.name,))
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
            for list_index, item in enumerate(current):
                if isinstance(item, dict) and str(item.get(token.field)) == token.value:
                    walk(item, token_index + 1, current_path + (list_index,))
                    break

    walk(data, 0, ())
    return tuple(paths)


def _iter_string_leaf_paths(data: Any) -> tuple[JsonPath, ...]:
    paths: list[JsonPath] = []

    def walk(current: Any, current_path: JsonPath) -> None:
        if isinstance(current, str):
            paths.append(current_path)
        elif isinstance(current, dict):
            for key, value in current.items():
                walk(value, current_path + (key,))
        elif isinstance(current, list):
            for index, value in enumerate(current):
                walk(value, current_path + (index,))

    walk(data, ())
    return tuple(paths)


class _PathResolver:
    def __init__(self, data: Any):
        self._data = data
        self._resolve_cache: dict[
            tuple[tuple[BusToken, ...], bool],
            tuple[JsonPath, ...],
        ] = {}
        self._leaf_cache: Optional[tuple[JsonPath, ...]] = None
        self._structure_changed = False

    def _invalidate(self) -> None:
        self._resolve_cache.clear()
        self._leaf_cache = None

    def resolve(
        self,
        tokens: tuple[BusToken, ...],
        *,
        allow_missing_final: bool,
    ) -> tuple[JsonPath, ...]:
        if self._structure_changed:
            self._structure_changed = False
            self._invalidate()
        cache_key = (tokens, allow_missing_final)
        cached = self._resolve_cache.get(cache_key)
        if cached is not None:
            return cached
        result = _resolve_paths(
            self._data,
            tokens,
            allow_missing_final=allow_missing_final,
        )
        self._resolve_cache[cache_key] = result
        return result

    def string_leaf_paths(self) -> tuple[JsonPath, ...]:
        if self._structure_changed:
            self._structure_changed = False
            self._invalidate()
        if self._leaf_cache is None:
            self._leaf_cache = _iter_string_leaf_paths(self._data)
        return self._leaf_cache

    def note_structural_change(self) -> None:
        self._structure_changed = True


def _is_structural_change(old_value: Any, new_value: Any) -> bool:
    return (
        old_value is MISSING
        or isinstance(old_value, (dict, list))
        or isinstance(new_value, (dict, list))
    )


def _safe_replace(text: str, old: str, new: str) -> str:
    if not old:
        return text.replace(old, new)
    if old not in text:
        return text
    if old not in new:
        return text.replace(old, new)
    result: list[str] = []
    position = 0
    while position < len(text):
        if text[position:position + len(new)] == new:
            result.append(new)
            position += len(new)
        elif text[position:position + len(old)] == old:
            result.append(new)
            position += len(old)
        else:
            result.append(text[position])
            position += 1
    return "".join(result)


def _apply_replacements(value: Any, replacements: tuple[CompiledReplacement, ...]) -> Any:
    result = value
    for replacement in replacements:
        if replacement.kind == "set":
            result = replacement.value
            continue
        if not isinstance(result, str):
            continue
        if replacement.mode == "regex":
            result = replacement.pattern.sub(replacement.replacement, result)
        elif replacement.mode == "end":
            if result.endswith(replacement.source):
                result = result[:-len(replacement.source)] + replacement.replacement
        elif replacement.safe:
            result = _safe_replace(result, replacement.source, replacement.replacement)
        else:
            result = result.replace(replacement.source, replacement.replacement)
    return result


def apply_bus(data: Any, compiled: CompiledBus, relative_path: str) -> BusApplyResult:
    rules = compiled.for_file(relative_path)
    changed_paths: list[JsonPath] = []
    changed_seen: set[JsonPath] = set()
    original_values: dict[JsonPath, Any] = {}
    matched_rules = 0
    failed_rules = 0
    errors: list[str] = []
    resolver = _PathResolver(data)

    for rule in rules:
        allow_missing_final = any(item.kind == "set" for item in rule.replacements)
        target_paths = (
            resolver.string_leaf_paths()
            if rule.all_string_leaves
            else resolver.resolve(rule.path, allow_missing_final=allow_missing_final)
        )
        if not target_paths:
            if rule.required:
                failed_rules += 1
                errors.append(f"{relative_path} / {rule.name}: 路径未命中")
            continue
        matched_rules += 1
        for target_path in target_paths:
            old_value = _get_value(data, target_path)
            new_value = _apply_replacements(old_value, rule.replacements)
            if new_value == old_value:
                continue
            if target_path not in original_values:
                original_values[target_path] = old_value
            data = _set_value(data, target_path, new_value)
            if _is_structural_change(old_value, new_value):
                resolver.note_structural_change()
            if target_path not in changed_seen:
                changed_seen.add(target_path)
                changed_paths.append(target_path)

    final_changed_paths = tuple(
        path for path in changed_paths
        if _get_value(data, path) != original_values[path]
    )
    return BusApplyResult(
        data=data,
        changed_paths=final_changed_paths,
        matched_rules=matched_rules,
        failed_rules=failed_rules,
        errors=tuple(errors),
    )


def _parse_tiaozhua_path(path: str) -> list[tuple[str, Any]]:
    tokens: list[tuple[str, Any]] = []
    for part in path.split("."):
        part = part.strip()
        if not part:
            continue
        numeric_field = re.match(r"^(\w+)\[(\d+)\]$", part)
        if numeric_field:
            field, raw_value = numeric_field.groups()
            if field.lower() == "id":
                tokens.append(("selector", (field, raw_value)))
            else:
                tokens.append(("key", field))
                tokens.append(("index", int(raw_value)))
            continue
        selector = re.match(r"^(\w+)\[([^\]]+)\]$", part)
        if selector:
            tokens.append(("selector", selector.groups()))
            continue
        index = re.match(r"^\[(\d+)\]$", part)
        if index:
            tokens.append(("index", int(index.group(1))))
            continue
        if part == "*":
            tokens.append(("wildcard", None))
        else:
            tokens.append(("key", part))
    return tokens


def _serialize_bus_path(tokens: Iterable[tuple[str, Any]]) -> str:
    segments: list[str] = []
    for kind, value in tokens:
        if kind == "key":
            segments.append(str(value))
            continue
        suffix = "[*]" if kind == "wildcard" else (
            f"[{value}]" if kind == "index" else f"[?{value[0]}={value[1]}]"
        )
        if segments:
            segments[-1] += suffix
        else:
            segments.append(suffix)
    return ".".join(segments)


def convert_tiaozhua_config(
    data: dict,
    *,
    name: Optional[str] = None,
) -> tuple[dict, dict]:
    if not is_tiaozhua_config(data):
        raise RuleValidationError("不是可识别的调爪规则配置")
    indexed_rules = list(enumerate(data["rules"]))

    def specificity(item: tuple[int, dict]) -> tuple[int, int]:
        rule = item[1]
        aim_file = str(rule.get("aimFile", "")).strip()
        aim = str(rule.get("aim", "")).strip()
        return (1 if aim_file else 0, len(aim.split(".")) if aim else 0)

    sorted_rules = sorted(indexed_rules, key=specificity, reverse=True)
    converted_rules: list[dict] = []
    action_count = 0
    for source_index, source_rule in sorted_rules:
        aim_file = str(source_rule.get("aimFile", "")).strip()
        file_matchers: list[Any] = [{"regex": aim_file}] if aim_file else ["*.json"]
        raw_aim = str(source_rule.get("aim", "")).strip()
        aim_paths = [item.strip() for item in raw_aim.split(",")] if raw_aim else [""]
        replacements: list[dict] = []
        for action in source_rule.get("action", []):
            if not isinstance(action, dict):
                continue
            source = action.get("from", "")
            replacement = action.get("to", "")
            mode = action.get("mode", "all")
            converted: dict[str, Any] = {"from": source, "to": replacement}
            if mode in {"regex", "end"}:
                converted["mode"] = mode
            if (
                mode not in {"regex", "end"}
                and source
                and replacement
                and (source in replacement or replacement in source)
            ):
                converted["safe"] = True
            replacements.append(converted)
            action_count += 1
        if not replacements:
            continue
        for aim_index, aim_path in enumerate(aim_paths):
            converted_rules.append({
                "name": str(source_rule.get("_note", f"调爪规则 {source_index + 1}")),
                "files": file_matchers,
                "path": _serialize_bus_path(_parse_tiaozhua_path(aim_path)) if aim_path else "",
                "replacements": replacements,
                "_source_order": [source_index, aim_index],
            })

    ruleset = {
        "format": BUS_FORMAT,
        "version": BUS_VERSION,
        "name": name or str(data.get("name") or "导入的文本替换规则"),
        "desc": str(data.get("_note") or "由调爪配置机械转换导入"),
        "files": ["*.json"],
        "exclude_dirs": list(data.get("blacklist", [])),
        "rules": converted_rules,
    }
    compile_bus_ruleset(ruleset)
    return ruleset, {
        "source_rules": len(data["rules"]),
        "converted_rules": len(converted_rules),
        "converted_actions": action_count,
        "skipped": 0,
        "warnings": [],
    }


def _convert_lcje_file_matcher(raw_file: str) -> str:
    """将 LCJE 补丁文件键转为 bus exact 匹配路径。

    剥离首段包名目录（如 LLC_zh-CN），保留其余相对路径（可能含子目录），
    与 fancy_main 中的包内相对路径语义一致。
    """
    normalized = raw_file.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    if parts and parts[0].lower().startswith("llc_"):
        parts = parts[1:]
    return "/".join(parts)


def convert_lcje_config(
    data: dict,
    *,
    name: Optional[str] = None,
) -> tuple[dict, dict]:
    if not is_lcje_config(data):
        raise RuleValidationError("不是可识别的 LCJE 补丁配置")
    converted_rules: list[dict] = []
    action_count = 0
    skipped = 0
    warnings: list[str] = []
    for file_index, (raw_file, file_map) in enumerate(data.items()):
        relative_path = _convert_lcje_file_matcher(raw_file)
        if not relative_path:
            warnings.append(f"文件 {raw_file} 无法解析路径，跳过")
            skipped += 1
            continue
        file_matchers: list[Any] = [{"exact": relative_path}]
        for aim_index, (raw_aim, value) in enumerate(file_map.items()):
            raw_aim = str(raw_aim).strip()
            if not raw_aim:
                warnings.append(f"{raw_file} 存在空路径条目，跳过")
                skipped += 1
                continue
            converted_rules.append({
                "name": f"{relative_path} / {raw_aim}",
                "files": file_matchers,
                "path": _serialize_bus_path(_parse_tiaozhua_path(raw_aim)),
                "replacements": [{"set": value}],
                "_source_order": [file_index, aim_index],
            })
            action_count += 1

    ruleset = {
        "format": BUS_FORMAT,
        "version": BUS_VERSION,
        "name": name or str(data.get("name") or "导入的文本替换规则"),
        "desc": "由LCJE补丁配置机械转换导入",
        "files": ["*.json"],
        "exclude_dirs": [],
        "rules": converted_rules,
    }
    compile_bus_ruleset(ruleset)
    return ruleset, {
        "source_rules": sum(len(file_map) for file_map in data.values()),
        "converted_rules": len(converted_rules),
        "converted_actions": action_count,
        "skipped": skipped,
        "warnings": warnings,
    }


def _convert_quick_path(path: str) -> str:
    if not path:
        return ""
    segments: list[str] = []
    for part in path.split("."):
        if part.isdigit():
            if not segments:
                segments.append(f"[{part}]")
            else:
                segments[-1] += f"[{part}]"
        else:
            segments.append(part)
    return ".".join(segments)


def convert_edits_to_bus_ruleset(edits: list, *, name: str = "_quick_edits") -> tuple[dict, dict]:
    if not isinstance(edits, list):
        raise RuleValidationError("快速编辑 edits 必须是数组")
    rules: list[dict] = []
    warnings: list[str] = []
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            warnings.append(f"第 {index + 1} 条编辑不是对象")
            continue
        file_name = edit.get("file")
        path = edit.get("path")
        if not isinstance(file_name, str) or not file_name or not isinstance(path, str):
            warnings.append(f"第 {index + 1} 条编辑缺少 file/path")
            continue
        if path == "":
            warnings.append(f"第 {index + 1} 条编辑修改了 JSON 根节点，bus 快速编辑不支持")
            continue
        rules.append({
            "name": f"快速编辑 {index + 1}",
            "files": [{"exact": file_name.replace("\\", "/")}],
            "path": _convert_quick_path(path),
            "replacements": [{"set": edit.get("new")}],
            "required": True,
        })
    ruleset = {
        "format": BUS_FORMAT,
        "version": BUS_VERSION,
        "name": name,
        "desc": "简易翻译编辑",
        "files": ["*.json"],
        "exclude_dirs": [],
        "rules": rules,
        "edits": edits,
    }
    compile_bus_ruleset(ruleset)
    return ruleset, {
        "source_edits": len(edits),
        "converted_rules": len(rules),
        "skipped": len(warnings),
        "warnings": warnings,
    }
