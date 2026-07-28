import time

from webutils.fancy_engine import apply_rules, compile_rulesets


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
