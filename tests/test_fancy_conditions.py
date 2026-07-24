import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from webutils.function_fancy import _normalize_rule

def test_normalize_old_trigger_format():
    rule = {
        "trigger": {"aim": r"dataList\.\d+\.id", "re": "^10001$"},
        "aim": "[back].name",
        "action": [{"from": "大于", "to": ">"}]
    }
    result = _normalize_rule(rule)
    assert "conditions" in result
    assert len(result["conditions"]) == 1
    assert result["conditions"][0]["trigger"]["re"] == "^10001$"
    assert result["conditions"][0]["aim"] == "[back].name"
    assert "trigger" not in result

def test_normalize_old_aim_only_format():
    rule = {
        "aim": r"dataList\.\d+\.desc",
        "action": [{"from": "大于", "to": ">"}]
    }
    result = _normalize_rule(rule)
    assert len(result["conditions"]) == 1
    assert result["conditions"][0]["aim"] == r"dataList\.\d+\.desc"
    assert "trigger" not in result["conditions"][0]

def test_normalize_new_format_passthrough():
    rule = {
        "conditions": [
            {"trigger": {"aim": r"dataList\.\d+\.id", "re": "^10001$"}, "aim": "[back].name"},
        ],
        "action": [{"from": "大于", "to": ">"}]
    }
    result = _normalize_rule(rule)
    assert len(result["conditions"]) == 1
    assert result == rule

def make_flat_data(data):
    from webutils.function_fancy import flatten_dict_enhanced
    return flatten_dict_enhanced(data)

def create_test_skill_data():
    return {
        "dataList": [
            {"id": 10001, "name": "强烈斩击", "desc": "大于目标体力则造成额外伤害"},
            {"id": 10002, "name": "精准穿刺", "desc": "指定目标造成大量伤害"},
            {"id": 10003, "name": "横扫", "desc": "大于自身护盾则追加伤害"},
        ]
    }

def test_exec_json_single_condition():
    from webutils.function_fancy import exec_json
    data = create_test_skill_data()
    config = [{
        "aimFile": "Skill.*\\.json$",
        "conditions": [{
            "trigger": {"aim": r"dataList\.\d+\.id", "re": "^10001$"},
            "aim": "[back].name"
        }],
        "action": [{"from": "^(.*)$", "to": "[\\1]"}]
    }]
    result = exec_json(data, config)
    assert result["dataList"][0]["name"] == "[强烈斩击]"
    assert result["dataList"][1]["name"] == "精准穿刺"

def test_exec_json_multi_condition_and():
    from webutils.function_fancy import exec_json
    data = create_test_skill_data()
    config = [{
        "aimFile": "Skill.*\\.json$",
        "conditions": [
            {"trigger": {"aim": r"dataList\.\d+\.id", "re": "^10002$"}, "aim": "[back].name"},
            {"trigger": {"aim": r"dataList\.\d+\.desc", "re": "指定"}, "aim": "[back].name"}
        ],
        "action": [{"from": "^(.*)$", "to": "★\\1★"}]
    }]
    result = exec_json(data, config)
    assert result["dataList"][1]["name"] == "★精准穿刺★"
    assert result["dataList"][0]["name"] == "强烈斩击"

def test_exec_json_old_format_still_works():
    from webutils.function_fancy import exec_json
    data = create_test_skill_data()
    config = [{
        "trigger": {"aim": r"dataList\.\d+\.id", "re": "^10001$"},
        "aim": "[back].name",
        "action": [{"from": "^(.*)$", "to": "OLD"}]
    }]
    result = exec_json(data, config)
    assert result["dataList"][0]["name"] == "OLD"
    assert result["dataList"][1]["name"] == "精准穿刺"