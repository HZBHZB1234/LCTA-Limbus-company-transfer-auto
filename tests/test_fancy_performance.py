import re
import time

from webutils.fancy.bus import (
    _resolve_paths,
    _safe_replace,
    compile_bus_ruleset,
    parse_bus_path,
)
from webutils.fancy.engine import apply_rules, compile_rulesets
from webutils.fancy.faust import (
    apply_color_gradient_custom,
    hex_to_rgb,
    interpolate_color,
    rgb_to_hex,
)


def _run_case(size):
    data = {
        "dataList": [
            {"id": index, "name": f"name-{index}", "desc": "target" if index == size - 1 else "other"}
            for index in range(size)
        ]
    }
    compiled = compile_rulesets([{
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["name"],
        "where": [
            {"path": "id", "operator": "equals", "value": size - 1},
            {"path": "desc", "operator": "contains", "value": "target"},
        ],
        "actions": [{"type": "wrap", "prefix": "[", "suffix": "]"}],
    }])
    started = time.perf_counter()
    result = apply_rules(data, compiled)
    return time.perf_counter() - started, result


def test_multi_condition_growth_is_near_linear():
    small_elapsed, small_result = _run_case(2000)
    large_elapsed, large_result = _run_case(4000)

    assert small_result.changed_count == 1
    assert large_result.changed_count == 1
    assert small_elapsed < 1.0
    assert large_elapsed < max(1.5, small_elapsed * 3 + 0.05)


def _reference_safe_replace(text, old, new):
    if not old:
        return text.replace(old, new)
    if old not in text:
        return text
    if old not in new:
        return text.replace(old, new)
    result = []
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


def _build_safe_corpus():
    corpus = []
    fillers = ["普通文本内容。", "描述文字 desc。", "技能效果展示 Skill Description。"]
    pairs = [
        ("X", "XX"),
        ("ab", "ba"),
        ("a", "aa"),
        ("AA", "A"),
        ("目标", "<u><color=#7C5738>目标</color></u>"),
        ("自我", "自身"),
        ("ab", "abc"),
        ("", "-"),
    ]
    for old, new in pairs:
        base = "".join(fillers)
        corpus.append((base * 8, old, new))
        corpus.append(((old * 50 + "夹" + base[:30]) * 4, old, new))
        corpus.append(("前缀" + old + "后缀" + new * 10, old, new))
        corpus.append((base[:100] + old * 3 + base[100:], old, new))
    return corpus


def _best_time(fn, corpus):
    best = None
    for _ in range(3):
        started = time.perf_counter()
        for item in corpus:
            fn(*item)
        elapsed = time.perf_counter() - started
        best = elapsed if best is None else min(best, elapsed)
    return best


def test_safe_replace_matches_reference_and_is_faster():
    corpus = _build_safe_corpus() * 200
    for text, old, new in corpus:
        assert _safe_replace(text, old, new) == _reference_safe_replace(text, old, new)

    new_elapsed = _best_time(_safe_replace, corpus)
    reference_elapsed = _best_time(_reference_safe_replace, corpus)
    assert new_elapsed < reference_elapsed * 0.6


def test_bus_file_match_index_matches_reference_and_is_faster():
    rules = []
    for rule_index in range(600):
        file_index = rule_index % 60
        rules.append({
            "name": f"rule-{rule_index}",
            "files": [{"regex": f"^File_{file_index}\\.json$"}],
            "path": "name",
            "replacements": [{"from": "A", "to": "B"}],
        })
    compiled = compile_bus_ruleset({
        "format": "lcta-bus",
        "version": 1,
        "name": "performance",
        "files": ["*.json"],
        "exclude_dirs": [],
        "rules": rules,
    })
    paths = [f"Folder/File_{index % 80}.json" for index in range(1000)]
    corpus = [(compiled, path) for path in paths]

    def reference(compiled_rules, relative_path):
        return tuple(
            rule
            for rule in compiled_rules.rules
            if rule.matches_file(relative_path)
        )

    def optimized(compiled_rules, relative_path):
        return compiled_rules.for_file(relative_path)

    for item in corpus:
        assert optimized(*item) == reference(*item)

    optimized_elapsed = _best_time(optimized, corpus)
    reference_elapsed = _best_time(reference, corpus)
    assert optimized_elapsed < reference_elapsed * 0.4


def test_selector_index_matches_reference_and_is_faster():
    data = {
        "dataList": [
            {"id": index, "name": f"name-{index}"}
            for index in range(4000)
        ],
    }
    paths = [parse_bus_path(f"dataList[?id={index}].name") for index in range(600)]
    corpus = [(data, paths)]

    def reference(source, token_paths):
        return tuple(
            _resolve_paths(
                source,
                tokens,
                allow_missing_final=False,
            )
            for tokens in token_paths
        )

    def optimized(source, token_paths):
        selector_cache = {}
        return tuple(
            _resolve_paths(
                source,
                tokens,
                allow_missing_final=False,
                selector_cache=selector_cache,
            )
            for tokens in token_paths
        )

    assert optimized(*corpus[0]) == reference(*corpus[0])
    optimized_elapsed = _best_time(optimized, corpus)
    reference_elapsed = _best_time(reference, corpus)
    assert optimized_elapsed < reference_elapsed * 0.2


_REFERENCE_TAG_PATTERN = re.compile(r'(<[^>]+>)')


def _reference_extract_text_and_tags(text):
    parts = []
    for segment in _REFERENCE_TAG_PATTERN.split(text):
        if not segment:
            continue
        if segment.startswith('<') and segment.endswith('>'):
            parts.append(('tag', segment))
        else:
            for char in segment:
                if char in ['\n', '\t', '\r']:
                    parts.append(('special', char))
                else:
                    parts.append(('char', char))
    return parts


def _reference_apply_color_gradient_custom(text, start_color, end_color, gradient_rate=2.0):
    if not text:
        return text
    parts = _reference_extract_text_and_tags(text)
    char_count = sum(1 for part_type, _ in parts if part_type == 'char')
    if char_count == 0:
        return f"<color={start_color}>{text}</color>"
    start_rgb = hex_to_rgb(start_color)
    end_rgb = hex_to_rgb(end_color)
    result_parts = []
    char_index = 0
    for part_type, content in parts:
        if part_type == 'tag' or part_type == 'special':
            result_parts.append(content)
        else:
            if char_count > 1:
                linear_ratio = char_index / (char_count - 1)
                ratio = 1 - (1 - linear_ratio) ** gradient_rate
            else:
                ratio = 0
            current_rgb = interpolate_color(start_rgb, end_rgb, ratio)
            current_color = rgb_to_hex(current_rgb)
            result_parts.append(f"<color={current_color}>{content}</color>")
            char_index += 1
    return ''.join(result_parts)


def _build_gradient_corpus():
    corpus = []
    texts = [
        "技能描述文本" * 30 + "，包含标点。" * 10,
        "前缀<color=#ff0000>" + "中间文本" * 20 + "</color>后缀",
        "第一行<color=#00ff00>跨\n行文本</color>结尾\t制表符",
        "<b><i><color=#8915D1>" + "嵌套" * 15 + "</color></i></b>",
        "a" + "<color=#00ff00>b" * 40 + "</color>" + "c",
        "a\nb\tc" * 40,
        "",
        "单",
        "< 3 >",
        "<color=#ff0000>只</color>有标签段",
    ]
    for text in texts:
        for rate in (0.3, 0.4, 0.5, 2.0):
            corpus.append((text, rate))
    return corpus * 20


def test_gradient_matches_reference_and_is_faster():
    corpus = _build_gradient_corpus()

    def new_fn(text, rate):
        return apply_color_gradient_custom(text, "#2020ED", "#ffffff", rate)

    def reference_fn(text, rate):
        return _reference_apply_color_gradient_custom(text, "#2020ED", "#ffffff", rate)

    for text, rate in corpus:
        assert new_fn(text, rate) == reference_fn(text, rate)

    new_elapsed = _best_time(new_fn, corpus)
    reference_elapsed = _best_time(reference_fn, corpus)
    assert new_elapsed < reference_elapsed * 0.7
