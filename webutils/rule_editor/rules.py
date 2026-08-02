from __future__ import annotations

import copy
import json
import logging

from ..fancy.bus import compile_bus_ruleset, is_bus_ruleset
from ..fancy.engine import RuleValidationError, apply_rules, compile_rulesets
from ..function_fancy import (
    load_fancy_folder_rules, save_ruleset_to_folder,
    delete_ruleset_from_folder, _get_fancy_folder, _sanitize_filename,
)
from .constants import CATEGORY_FILE_PATTERNS, TEMPLATES

logger = logging.getLogger('rule_editor')


def get_ruleset_list() -> list:
    rulesets = [ruleset for ruleset in load_fancy_folder_rules() if ruleset.get('version') == 2]
    return [
        {"name": rs["name"], "desc": rs.get("desc", ""), "rule_count": len(rs.get("rules", []))}
        for rs in rulesets
    ]

def get_ruleset(name: str) -> dict:
    folder = _get_fancy_folder()
    filename = _sanitize_filename(name) + '.json'
    filepath = folder / filename
    if not filepath.exists():
        return {"error": f"规则集不存在: {name}"}
    try:
        return json.loads(filepath.read_text(encoding='utf-8'))
    except Exception as e:
        return {"error": str(e)}

def save_ruleset(name: str, data: dict) -> dict:
    try:
        if 'name' not in data:
            data['name'] = name
        if is_bus_ruleset(data):
            compile_bus_ruleset(data)
        else:
            data['version'] = 2
            errors = validate_rule(json.dumps(data, ensure_ascii=False)).get('errors', [])
            if errors:
                return {"success": False, "error": "; ".join(errors)}
        filepath = save_ruleset_to_folder(name, data)
        return {"success": True, "path": str(filepath)}
    except Exception as e:
        return {"success": False, "error": str(e)}

def create_ruleset(name: str) -> dict:
    template = copy.deepcopy(TEMPLATES[0]["template"])
    template["name"] = name
    return save_ruleset(name, template)

def delete_ruleset(name: str) -> dict:
    success = delete_ruleset_from_folder(name)
    if success:
        return {"success": True}
    return {"success": False, "error": f"规则集不存在或删除失败: {name}"}

def _file_pattern_from_selection(selection: str) -> str:
    if selection in CATEGORY_FILE_PATTERNS:
        return CATEGORY_FILE_PATTERNS[selection]
    return selection or '*.json'

def build_rule_from_form(form_data: dict) -> dict:
    aim_file = _file_pattern_from_selection(form_data.get("file_pattern", ""))
    item_ids = form_data.get("item_ids", [])
    scope = form_data.get("scope", "dataList[*]")
    target_paths = form_data.get("target_paths") or [form_data.get("field_path", "desc")]
    operations = form_data.get("operations", [])
    extra_conditions = form_data.get("extra_conditions", [])

    conditions = []
    if item_ids:
        normalized_ids = [int(item) if str(item).isdigit() else item for item in item_ids]
        conditions.append({
            "path": "id",
            "operator": "in",
            "value": normalized_ids,
        })

    for ec in extra_conditions:
        path = ec.get("path") or ec.get("field")
        operator = ec.get("operator", "regex")
        value = ec.get("value", ec.get("pattern"))
        if not path or value in (None, ""):
            continue
        if operator == "in" and isinstance(value, str):
            value = [part.strip() for part in value.split(',') if part.strip()]
            value = [int(part) if str(part).isdigit() else part for part in value]
        conditions.append({"path": path, "operator": operator, "value": value})

    actions = []
    for operation in operations:
        if operation.get('type'):
            actions.append(operation)
        elif operation.get('from') is not None and operation.get('to') is not None:
            actions.append({
                "type": "replace",
                "mode": operation.get("mode", "literal"),
                "from": operation["from"],
                "to": operation["to"],
            })
    return {
        "files": [aim_file],
        "scope": scope,
        "targets": target_paths,
        "where": conditions,
        "actions": actions,
    }

def validate_rule(rule_json: str) -> dict:
    try:
        payload = json.loads(rule_json)
    except json.JSONDecodeError as e:
        return {"valid": False, "errors": [f"JSON 语法错误: {e}"]}
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["规则必须是 JSON 对象"]}
    try:
        compile_rulesets([payload])
    except RuleValidationError as exc:
        return {"valid": False, "errors": [str(exc)]}
    return {"valid": True, "errors": []}


def apply_ruleset_to_content(ruleset_name: str, file_path: str, content: str) -> dict:
    """将规则集应用到单个文件的内存内容，返回修改后的内容（不写磁盘）"""
    rulesets = load_fancy_folder_rules()
    ruleset = None
    for r in rulesets:
        if r.get('name') == ruleset_name:
            ruleset = r
            break
    if not ruleset:
        return {"success": False, "error": "规则集不存在"}

    try:
        matching_rules = compile_rulesets([ruleset]).for_file(file_path)
    except RuleValidationError as exc:
        return {"success": False, "error": f"规则验证失败: {exc}"}
    if not matching_rules.rules:
        return {"success": True, "modified_content": content, "rules_applied": 0}

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON 格式错误: {e}"}

    try:
        result = apply_rules(data, matching_rules)
    except Exception as e:
        return {"success": False, "error": f"规则执行异常: {e}"}

    modified = json.dumps(result.data, ensure_ascii=False, indent=4)
    return {
        "success": True,
        "modified_content": modified,
        "rules_applied": len(matching_rules.rules),
        "values_changed": result.changed_count,
    }
