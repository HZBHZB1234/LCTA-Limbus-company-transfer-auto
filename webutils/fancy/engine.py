from __future__ import annotations

import fnmatch
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


class RuleValidationError(ValueError):
    pass


WILDCARD = object()
PathToken = Any
JsonPath = tuple


@dataclass(frozen=True)
class CompiledCondition:
    path: tuple[PathToken, ...]
    operator: str
    value: Any
    pattern: re.Pattern[str] | None = None


@dataclass(frozen=True)
class CompiledAction:
    type: str
    mode: str | None = None
    source: str | None = None
    replacement: str | None = None
    pattern: re.Pattern[str] | None = None
    prefix: str = ""
    suffix: str = ""
    rate: float = 2.0
    id_path: tuple[PathToken, ...] = ()


@dataclass(frozen=True)
class CompiledRule:
    files: tuple[str, ...]
    scope: tuple[PathToken, ...]
    targets: tuple[tuple[PathToken, ...], ...]
    where: tuple[CompiledCondition, ...]
    actions: tuple[CompiledAction, ...]

    def matches_file(self, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/")
        filename = normalized.rsplit("/", 1)[-1]
        for pattern in self.files:
            normalized_pattern = pattern.replace("\\", "/")
            target = normalized if "/" in normalized_pattern else filename
            if fnmatch.fnmatchcase(target, normalized_pattern):
                return True
        return False


@dataclass(frozen=True)
class CompiledRules:
    rules: tuple[CompiledRule, ...]

    @property
    def requires_skill_color(self) -> bool:
        return any(
            action.type == "skill_color"
            for rule in self.rules
            for action in rule.actions
        )

    def for_file(self, relative_path: str) -> "CompiledRules":
        return CompiledRules(tuple(rule for rule in self.rules if rule.matches_file(relative_path)))


@dataclass(frozen=True)
class ApplyResult:
    data: Any
    changed_paths: tuple[JsonPath, ...]

    @property
    def changed_count(self) -> int:
        return len(self.changed_paths)


def parse_structured_path(path: str, *, field_name: str) -> tuple[PathToken, ...]:
    if path == "" or path is None:
        return ()
    if not isinstance(path, str):
        raise RuleValidationError(f"{field_name} 必须是字符串")

    tokens: list[PathToken] = []
    for segment in path.split("."):
        if not segment:
            raise RuleValidationError(f"{field_name} 包含空路径段: {path}")
        position = 0
        key_match = re.match(r"^[^\[\]]+", segment)
        if key_match:
            tokens.append(key_match.group(0))
            position = key_match.end()
        while position < len(segment):
            index_match = re.match(r"\[(\*|\d+)\]", segment[position:])
            if not index_match:
                raise RuleValidationError(f"{field_name} 路径语法错误: {path}")
            raw_index = index_match.group(1)
            tokens.append(WILDCARD if raw_index == "*" else int(raw_index))
            position += index_match.end()
        if position == 0:
            raise RuleValidationError(f"{field_name} 路径语法错误: {path}")
    return tuple(tokens)


def _compile_condition(condition: dict, index: int) -> CompiledCondition:
    if not isinstance(condition, dict):
        raise RuleValidationError(f"where[{index}] 必须是对象")
    path = parse_structured_path(condition.get("path", ""), field_name=f"where[{index}].path")
    operator = condition.get("operator", "equals")
    if operator not in {"equals", "in", "contains", "regex"}:
        raise RuleValidationError(f"where[{index}].operator 不支持: {operator}")
    value = condition.get("value")
    if operator == "in" and not isinstance(value, list):
        raise RuleValidationError(f"where[{index}].value 在 in 条件下必须是数组")
    if operator in {"contains", "regex"} and not isinstance(value, str):
        raise RuleValidationError(f"where[{index}].value 在 {operator} 条件下必须是字符串")
    pattern = None
    if operator == "regex":
        try:
            pattern = re.compile(value)
        except re.error as exc:
            raise RuleValidationError(f"where[{index}] 正则错误: {exc}") from exc
    if operator == "in":
        try:
            value = frozenset(value)
        except TypeError as exc:
            raise RuleValidationError(f"where[{index}].value 只能包含基础值") from exc
    return CompiledCondition(path=path, operator=operator, value=value, pattern=pattern)


def _compile_action(action: dict, index: int) -> CompiledAction:
    if not isinstance(action, dict):
        raise RuleValidationError(f"actions[{index}] 必须是对象")
    action_type = action.get("type")
    if action_type == "replace":
        mode = action.get("mode", "literal")
        if mode not in {"literal", "regex"}:
            raise RuleValidationError(f"actions[{index}].mode 不支持: {mode}")
        source = action.get("from")
        replacement = action.get("to")
        if not isinstance(source, str) or not isinstance(replacement, str):
            raise RuleValidationError(f"actions[{index}] replace 需要字符串 from/to")
        pattern = None
        if mode == "regex":
            try:
                pattern = re.compile(source)
            except re.error as exc:
                raise RuleValidationError(f"actions[{index}] 替换正则错误: {exc}") from exc
        return CompiledAction(
            type=action_type,
            mode=mode,
            source=source,
            replacement=replacement,
            pattern=pattern,
        )
    if action_type == "wrap":
        prefix = action.get("prefix", "")
        suffix = action.get("suffix", "")
        if not isinstance(prefix, str) or not isinstance(suffix, str):
            raise RuleValidationError(f"actions[{index}] wrap 需要字符串 prefix/suffix")
        return CompiledAction(type=action_type, prefix=prefix, suffix=suffix)
    if action_type == "gradient":
        rate = action.get("rate", 2.0)
        if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
            raise RuleValidationError(f"actions[{index}].rate 必须是正数")
        return CompiledAction(type=action_type, rate=float(rate))
    if action_type == "skill_color":
        id_path = parse_structured_path(
            action.get("idPath", "id"), field_name=f"actions[{index}].idPath"
        )
        return CompiledAction(type=action_type, id_path=id_path)
    raise RuleValidationError(f"actions[{index}].type 不支持: {action_type}")


def compile_rule(rule: dict, *, index: int = 0) -> CompiledRule:
    if not isinstance(rule, dict):
        raise RuleValidationError(f"rules[{index}] 必须是对象")
    files = rule.get("files")
    if not isinstance(files, list) or not files or not all(isinstance(item, str) and item for item in files):
        raise RuleValidationError(f"rules[{index}].files 必须是非空字符串数组")
    scope = parse_structured_path(rule.get("scope", ""), field_name=f"rules[{index}].scope")
    targets = rule.get("targets")
    if not isinstance(targets, list) or not targets:
        raise RuleValidationError(f"rules[{index}].targets 必须是非空数组")
    compiled_targets = []
    for target_index, target in enumerate(targets):
        if not isinstance(target, str) or not target:
            raise RuleValidationError(f"rules[{index}].targets[{target_index}] 必须是非空字符串")
        compiled_targets.append(
            parse_structured_path(target, field_name=f"rules[{index}].targets[{target_index}]")
        )
    where = rule.get("where", [])
    actions = rule.get("actions")
    if not isinstance(where, list):
        raise RuleValidationError(f"rules[{index}].where 必须是数组")
    if not isinstance(actions, list) or not actions:
        raise RuleValidationError(f"rules[{index}].actions 必须是非空数组")
    return CompiledRule(
        files=tuple(files),
        scope=scope,
        targets=tuple(compiled_targets),
        where=tuple(_compile_condition(item, item_index) for item_index, item in enumerate(where)),
        actions=tuple(_compile_action(item, item_index) for item_index, item in enumerate(actions)),
    )


def _iter_rule_dicts(rulesets: Iterable[dict]) -> Iterable[dict]:
    for item in rulesets:
        if not isinstance(item, dict):
            raise RuleValidationError("规则集必须是对象")
        if "rules" in item:
            if item.get("version") != 2:
                raise RuleValidationError(f"规则集 {item.get('name', '?')} 缺少 version: 2")
            rules = item.get("rules")
            if not isinstance(rules, list):
                raise RuleValidationError(f"规则集 {item.get('name', '?')} 的 rules 必须是数组")
            yield from rules
        else:
            yield item


def compile_rulesets(rulesets: Sequence[dict]) -> CompiledRules:
    return CompiledRules(tuple(compile_rule(rule, index=index) for index, rule in enumerate(_iter_rule_dicts(rulesets))))


class _PathResolver:
    def __init__(self, data: Any):
        self.data = data
        self._cache: dict[tuple[JsonPath, tuple[PathToken, ...]], tuple[JsonPath, ...]] = {}

    def resolve(self, base_path: JsonPath, tokens: tuple[PathToken, ...]) -> tuple[JsonPath, ...]:
        cache_key = (base_path, tokens)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        paths: list[JsonPath] = []

        def walk(current: Any, token_index: int, current_path: JsonPath) -> None:
            if token_index == len(tokens):
                paths.append(current_path)
                return
            token = tokens[token_index]
            if token is WILDCARD:
                if isinstance(current, list):
                    for list_index, value in enumerate(current):
                        walk(value, token_index + 1, current_path + (list_index,))
                return
            if isinstance(token, int):
                if isinstance(current, list) and 0 <= token < len(current):
                    walk(current[token], token_index + 1, current_path + (token,))
                return
            if isinstance(current, dict) and token in current:
                walk(current[token], token_index + 1, current_path + (token,))

        try:
            base_value = get_value(self.data, base_path)
        except (KeyError, IndexError, TypeError):
            result: tuple[JsonPath, ...] = ()
        else:
            walk(base_value, 0, base_path)
            result = tuple(paths)
        self._cache[cache_key] = result
        return result


def get_value(data: Any, path: JsonPath) -> Any:
    current = data
    for token in path:
        current = current[token]
    return current


def set_value(data: Any, path: JsonPath, value: Any) -> None:
    current = data
    for token in path[:-1]:
        current = current[token]
    current[path[-1]] = value


def _condition_matches(condition: CompiledCondition, values: Iterable[Any]) -> bool:
    if condition.operator == "equals":
        return any(value == condition.value for value in values)
    if condition.operator == "in":
        allowed = condition.value
        for value in values:
            try:
                if value in allowed:
                    return True
            except TypeError:
                continue
        return False
    if condition.operator == "contains":
        return any(condition.value in value for value in values if isinstance(value, str))
    return any(condition.pattern.search(str(value)) for value in values if isinstance(value, (str, int, float, bool)))


def _apply_actions(
    value: Any,
    actions: tuple[CompiledAction, ...],
    *,
    data: Any,
    scope_path: JsonPath,
    resolver: _PathResolver,
) -> Any:
    if not isinstance(value, str):
        return value
    result = value
    for action in actions:
        if action.type == "replace":
            if action.mode == "literal":
                result = result.replace(action.source, action.replacement)
            else:
                result = action.pattern.sub(action.replacement, result)
        elif action.type == "wrap":
            result = f"{action.prefix}{result}{action.suffix}"
        elif action.type == "gradient":
            from webutils.fancy.faust import process_dlg_text

            result = process_dlg_text(result, action.rate)
        elif action.type == "skill_color":
            from webutils.fancy.builtin_func import skillColorHandler

            id_paths = resolver.resolve(scope_path, action.id_path)
            if id_paths:
                result = skillColorHandler.apply(result, get_value(data, id_paths[0]))
    return result


def apply_rules(data: Any, compiled_rules: CompiledRules) -> ApplyResult:
    resolver = _PathResolver(data)
    changed_paths: list[JsonPath] = []
    changed_seen: set[JsonPath] = set()
    original_values: dict[JsonPath, Any] = {}

    for rule in compiled_rules.rules:
        for scope_path in resolver.resolve((), rule.scope):
            conditions_met = True
            for condition in rule.where:
                condition_paths = resolver.resolve(scope_path, condition.path)
                condition_values = (get_value(data, path) for path in condition_paths)
                if not _condition_matches(condition, condition_values):
                    conditions_met = False
                    break
            if not conditions_met:
                continue

            for target in rule.targets:
                for target_path in resolver.resolve(scope_path, target):
                    old_value = get_value(data, target_path)
                    new_value = _apply_actions(
                        old_value,
                        rule.actions,
                        data=data,
                        scope_path=scope_path,
                        resolver=resolver,
                    )
                    if new_value != old_value:
                        if target_path not in original_values:
                            original_values[target_path] = old_value
                        set_value(data, target_path, new_value)
                        if target_path not in changed_seen:
                            changed_seen.add(target_path)
                            changed_paths.append(target_path)

    final_changed_paths = tuple(
        path for path in changed_paths if get_value(data, path) != original_values[path]
    )
    return ApplyResult(data=data, changed_paths=final_changed_paths)


def validate_ruleset(ruleset: dict) -> list[str]:
    try:
        compile_rulesets([ruleset])
    except RuleValidationError as exc:
        return [str(exc)]
    return []
