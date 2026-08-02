import copy

import pytest

from webutils.fancy.engine import RuleValidationError, apply_rules, compile_rulesets
from webutils.function_fancy import exec_json


def create_test_skill_data():
    return {
        "dataList": [
            {"id": 10001, "name": "强烈斩击", "desc": "大于目标体力则造成额外伤害"},
            {"id": 10002, "name": "精准穿刺", "desc": "指定目标造成大量伤害"},
            {"id": 10003, "name": "横扫", "desc": "大于自身护盾则追加伤害"},
        ]
    }


def test_v2_single_condition_and_literal_replace():
    data = create_test_skill_data()
    rules = [{
        "files": ["Skill*.json"],
        "scope": "dataList[*]",
        "targets": ["name"],
        "where": [{"path": "id", "operator": "equals", "value": 10001}],
        "actions": [{"type": "wrap", "prefix": "[", "suffix": "]"}],
    }]

    result = exec_json(data, rules)

    assert result["dataList"][0]["name"] == "[强烈斩击]"
    assert result["dataList"][1]["name"] == "精准穿刺"


def test_v2_multi_condition_and_uses_same_scope():
    data = create_test_skill_data()
    rules = [{
        "files": ["Skill*.json"],
        "scope": "dataList[*]",
        "targets": ["name"],
        "where": [
            {"path": "id", "operator": "in", "value": [10002, 10003]},
            {"path": "desc", "operator": "contains", "value": "指定"},
        ],
        "actions": [{"type": "wrap", "prefix": "★", "suffix": "★"}],
    }]

    result = exec_json(data, rules)

    assert result["dataList"][1]["name"] == "★精准穿刺★"
    assert result["dataList"][2]["name"] == "横扫"


def test_nested_scope_and_fixed_index_targets():
    data = {
        "dataList": [{
            "id": 1,
            "levelList": [
                {"desc": "指定", "name": "第一层"},
                {"desc": "普通", "name": "第二层"},
            ],
        }]
    }
    rules = [{
        "files": ["*.json"],
        "scope": "dataList[*].levelList[*]",
        "targets": ["name"],
        "where": [{"path": "desc", "operator": "contains", "value": "指定"}],
        "actions": [{"type": "replace", "mode": "literal", "from": "层", "to": "级"}],
    }, {
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["levelList[1].name"],
        "where": [],
        "actions": [{"type": "wrap", "prefix": "<", "suffix": ">"}],
    }]

    result = exec_json(data, rules)

    assert result["dataList"][0]["levelList"][0]["name"] == "第一级"
    assert result["dataList"][0]["levelList"][1]["name"] == "<第二层>"


def test_actions_run_in_order_and_later_rules_see_changes():
    data = {"dataList": [{"name": "目标"}]}
    rules = [{
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["name"],
        "where": [],
        "actions": [
            {"type": "replace", "mode": "literal", "from": "目标", "to": "单位"},
            {"type": "wrap", "prefix": "[", "suffix": "]"},
        ],
    }, {
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["name"],
        "where": [],
        "actions": [{"type": "replace", "mode": "literal", "from": "单位", "to": "敌人"}],
    }]

    result = apply_rules(data, compile_rulesets(rules))

    assert result.data["dataList"][0]["name"] == "[敌人]"
    assert result.changed_count == 1


def test_file_glob_matching():
    compiled = compile_rulesets([{
        "files": ["StoryData/*.json", "Skill*.json"],
        "scope": "dataList[*]",
        "targets": ["desc"],
        "where": [],
        "actions": [{"type": "replace", "mode": "literal", "from": "a", "to": "b"}],
    }])

    assert compiled.for_file("StoryData/E001.json").rules
    assert compiled.for_file("Skills.json").rules
    assert not compiled.for_file("Passives.json").rules


def test_file_glob_matching_normalizes_backslash_patterns():
    compiled = compile_rulesets([{
        "files": [r"StoryData\*.json"],
        "scope": "dataList[*]",
        "targets": ["desc"],
        "where": [],
        "actions": [{"type": "replace", "mode": "literal", "from": "a", "to": "b"}],
    }])

    assert compiled.for_file("StoryData/E001.json").rules
    assert compiled.for_file("StoryData\\E001.json").rules
    assert not compiled.for_file("Passives.json").rules


def test_in_condition_skips_unhashable_values():
    data = {"dataList": [{"id": 1, "name": "目标", "extra": {"a": 1}}]}
    rules = [{
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["name"],
        "where": [{"path": "extra", "operator": "in", "value": [1, 2]}],
        "actions": [{"type": "wrap", "prefix": "[", "suffix": "]"}],
    }, {
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["name"],
        "where": [],
        "actions": [{"type": "replace", "mode": "literal", "from": "目标", "to": "敌人"}],
    }]

    result = apply_rules(data, compile_rulesets(rules))

    assert result.data["dataList"][0]["name"] == "敌人"


def test_gradient_rate_rejects_non_finite_values():
    for bad_rate in (float("nan"), float("inf"), float("-inf")):
        rules = [{
            "files": ["*.json"],
            "scope": "dataList[*]",
            "targets": ["desc"],
            "where": [],
            "actions": [{"type": "gradient", "rate": bad_rate}],
        }]
        with pytest.raises(RuleValidationError):
            compile_rulesets(rules)


def test_invalid_rule_rejected_before_execution():
    invalid = [{
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["desc"],
        "where": [{"path": "id", "operator": "regex", "value": "("}],
        "actions": [{"type": "replace", "mode": "literal", "from": "a", "to": "b"}],
    }]

    with pytest.raises(RuleValidationError):
        compile_rulesets(invalid)


def test_apply_does_not_change_source_shape():
    data = create_test_skill_data()
    original = copy.deepcopy(data)
    rules = [{
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["missing"],
        "where": [],
        "actions": [{"type": "wrap", "prefix": "[", "suffix": "]"}],
    }]

    result = apply_rules(data, compile_rulesets(rules))

    assert result.changed_count == 0
    assert data == original


def test_change_reverted_by_later_rule_is_not_reported():
    data = {"dataList": [{"name": "原值"}]}
    rules = [{
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["name"],
        "where": [],
        "actions": [{"type": "replace", "mode": "literal", "from": "原值", "to": "临时值"}],
    }, {
        "files": ["*.json"],
        "scope": "dataList[*]",
        "targets": ["name"],
        "where": [],
        "actions": [{"type": "replace", "mode": "literal", "from": "临时值", "to": "原值"}],
    }]

    result = apply_rules(data, compile_rulesets(rules))

    assert result.changed_count == 0
    assert data["dataList"][0]["name"] == "原值"
