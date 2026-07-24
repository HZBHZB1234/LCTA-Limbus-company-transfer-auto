"""美化规则编辑器后端 API — 文件浏览、规则 CRUD、智能生成"""

import json
import os
import re
import logging
from pathlib import Path
from typing import Optional

from globalManagers.ConfigManager import ConfigManager
from webutils.function_fancy import (
    load_fancy_folder_rules, save_ruleset_to_folder,
    delete_ruleset_from_folder, _get_fancy_folder, _sanitize_filename
)

logger = logging.getLogger('rule_editor')

FILE_PREFIX_RULES = [
    ('BattleSpeechBubbleDlg', '战斗气泡'), ('BattleResultHint', '战斗结果提示'),
    ('BattleKeywords', '战斗关键词'), ('BattlePass', '通行证'),
    ('BattleUIText', '战斗UI'), ('BossRaidUI', '战斗映射UI'),
    ('BattleHint', '战斗提示'), ('BuffAbilities', '战斗Buff'),
    ('Bufs_Mirror', '镜牢Buff'), ('MirrorDungeon', '镜牢'),
    ('DailyLoginEvent', '签到'), ('CultivationEvent', '惜春养成'),
    ('CouponUIText', '兑换码UI'), ('ChoiceEvent', '事件选择'),
    ('DanteAbility', '但丁能力'), ('ActionEvents', '镜牢事件'),
    ('AbEventsResultLog', '事件效果'), ('AbnormalityGuides', '异想体线索/提示'),
    ('AttributeText', '七大罪'), ('AbEvents', '异想体事件'),
    ('AbDlg', '事件判定'), ('Announcer', '播报相关内容'),
    ('Assist', '援助相关'), ('ErrorCodeMsg', '错误代码'),
    ('UnitKeyword', '关键词'), ('Personalities', '人格'),
    ('Characters', '角色'), ('EGOgift', 'EGO饰品'),
    ('Dungeon', '地牢'), ('Enemies', '敌人'),
    ('PanicInfo', '效果'), ('Passives', '被动'),
    ('Railway', '轨道线'), ('Egos', '角色EGO'),
    ('Skill', '技能'), ('Stage', '舞台'),
    ('Story', '故事'), ('Event', '活动'), ('Bufs', '通用Buff'),
]

CATEGORY_FILE_PATTERNS = {
    'Skill': r'Skill.*\.json$', 'Bufs': r'Bufs.*\.json$',
    'BattleSpeechBubbleDlg': r'BattleSpeechBubbleDlg.*\.json$',
    'Egos': r'(Skills_Ego_Personality|Egos).*\.json$',
    'Passives': r'Passives.*\.json$', 'Personalities': r'Personalities.*\.json$',
    'Enemies': r'Enemies.*\.json$', 'EGOgift': r'EGOgift.*\.json$',
    'Railway': r'Railway.*\.json$', 'MirrorDungeon': r'MirrorDungeon.*\.json$',
    'Dungeon': r'Dungeon.*\.json$', 'Stage': r'Stage.*\.json$',
    'Story': r'Story.*\.json$', 'Event': r'Event.*\.json$',
    'BattleUIText': r'BattleUIText.*\.json$', 'BattleKeywords': r'BattleKeywords.*\.json$',
    'AbEvents': r'AbEvents.*\.json$', 'Announcer': r'Announcer.*\.json$',
    'UnitKeyword': r'UnitKeyword.*\.json$',
}


def _get_lang_dir() -> Optional[Path]:
    config = ConfigManager()
    game_path = config.get('game_path', '')
    if not game_path:
        return None
    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'Lang'
    try:
        config_json = lang_path / 'config.json'
        if config_json.exists():
            lang_name = json.loads(config_json.read_text(encoding='utf-8')).get('lang', '')
            lang_path = lang_path / lang_name
    except Exception:
        pass
    return lang_path if lang_path.exists() else None

def get_lang_files() -> list:
    lang_dir = _get_lang_dir()
    if not lang_dir:
        return []
    json_files = []
    for root, dirs, files in os.walk(lang_dir):
        for f in files:
            if f.endswith('.json'):
                full_path = Path(root) / f
                try:
                    json_files.append(str(full_path.relative_to(lang_dir)))
                except ValueError:
                    json_files.append(str(full_path))
    return sorted(json_files)

def get_category(relative_path: str) -> str:
    for prefix, category in FILE_PREFIX_RULES:
        if relative_path.startswith(prefix) or prefix in relative_path:
            return category
    return 'Other'

def get_file_content(relative_path: str) -> dict:
    lang_dir = _get_lang_dir()
    if not lang_dir:
        return {"error": "Lang 文件夹未配置"}
    full_path = lang_dir / relative_path
    if not full_path.exists():
        return {"error": f"文件不存在: {relative_path}"}
    try:
        raw = full_path.read_text(encoding='utf-8')
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        return {"raw": raw, "parsed": parsed, "file_classification": get_category(relative_path)}
    except Exception as e:
        return {"error": str(e), "raw": None, "parsed": None}

def search_files(keyword: str, case_sensitive: bool = False) -> dict:
    lang_dir = _get_lang_dir()
    if not lang_dir:
        return {"results_by_category": {}, "total_matches": 0}
    results_by_category = {}
    total_matches = 0
    search_keyword = keyword if case_sensitive else keyword.lower()

    def count_matches(obj):
        count = 0
        if isinstance(obj, str):
            target = obj if case_sensitive else obj.lower()
            if search_keyword in target:
                count += 1
        elif isinstance(obj, dict):
            for k, v in obj.items():
                count += count_matches(k) + count_matches(v)
        elif isinstance(obj, list):
            for item in obj:
                count += count_matches(item)
        return count

    for root, dirs, files in os.walk(lang_dir):
        for f in files:
            if not f.endswith('.json'):
                continue
            full_path = Path(root) / f
            try:
                rel_path = str(full_path.relative_to(lang_dir))
            except ValueError:
                rel_path = str(full_path)
            try:
                data = json.loads(full_path.read_text(encoding='utf-8'))
                matches = count_matches(data)
                if matches > 0:
                    category = get_category(rel_path)
                    if category not in results_by_category:
                        results_by_category[category] = []
                    results_by_category[category].append((rel_path, matches))
                    total_matches += matches
            except Exception:
                pass
    return {"results_by_category": results_by_category, "total_matches": total_matches}

def get_ruleset_list() -> list:
    rulesets = load_fancy_folder_rules()
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
        filepath = save_ruleset_to_folder(name, data)
        return {"success": True, "path": str(filepath)}
    except Exception as e:
        return {"success": False, "error": str(e)}

def create_ruleset(name: str) -> dict:
    template = {"name": name, "desc": "", "rules": []}
    return save_ruleset(name, template)

def delete_ruleset(name: str) -> dict:
    success = delete_ruleset_from_folder(name)
    if success:
        return {"success": True}
    return {"success": False, "error": f"规则集不存在或删除失败: {name}"}

def _file_pattern_from_selection(selection: str) -> str:
    if selection in CATEGORY_FILE_PATTERNS:
        return CATEGORY_FILE_PATTERNS[selection]
    if any(c in selection for c in '.*+?^${}[]|()\\'):
        return selection
    return f"{re.escape(selection)}.*\\.json$"

def build_rule_from_form(form_data: dict) -> dict:
    aim_file = _file_pattern_from_selection(form_data.get("file_pattern", ""))
    item_ids = form_data.get("item_ids", [])
    field_path = form_data.get("field_path", "desc")
    operations = form_data.get("operations", [])
    extra_conditions = form_data.get("extra_conditions", [])

    conditions = []
    if item_ids:
        id_pattern = "^(" + "|".join(str(i) for i in item_ids) + ")$"
        conditions.append({
            "trigger": {"aim": r"dataList\.\d+\.id", "re": id_pattern},
            "aim": f"[back].{field_path}"
        })
    else:
        conditions.append({"aim": rf"dataList\.\d+\.{field_path}"})

    for ec in extra_conditions:
        cond = {}
        if ec.get("field") and ec.get("pattern"):
            cond["trigger"] = {
                "aim": rf"dataList\.\d+\.{ec['field']}",
                "re": ec["pattern"]
            }
            cond["aim"] = f"[back].{field_path}"
        conditions.append(cond)

    action = [{"from": op["from"], "to": op["to"]} for op in operations]
    return {"aimFile": aim_file, "conditions": conditions, "action": action}

def validate_rule(rule_json: str) -> dict:
    errors = []
    try:
        rule = json.loads(rule_json)
    except json.JSONDecodeError as e:
        return {"valid": False, "errors": [f"JSON 语法错误: {e}"]}
    if not isinstance(rule, dict):
        return {"valid": False, "errors": ["规则必须是 JSON 对象"]}
    if "aimFile" not in rule or not rule["aimFile"]:
        errors.append("缺少 aimFile 字段（文件匹配模式）")
    conds = rule.get("conditions", [])
    if not conds and "aim" not in rule and "trigger" not in rule:
        errors.append("缺少 conditions 或 aim 字段（定位条件）")
    action = rule.get("action", [])
    if not action:
        errors.append("缺少 action 字段（操作列表）")
    else:
        for i, act in enumerate(action):
            if not isinstance(act, dict):
                errors.append(f"action[{i}] 不是有效的操作对象")
            elif "from" in act and "to" not in act:
                errors.append(f"action[{i}] 有 from 但缺少 to")
            elif "to" in act and "from" not in act:
                errors.append(f"action[{i}] 有 to 但缺少 from")
    try:
        re.compile(rule.get("aimFile", ""))
    except re.error as e:
        errors.append(f"aimFile 正则语法错误: {e}")
    return {"valid": len(errors) == 0, "errors": errors}

def _analyze_value_change(old_val, new_val) -> dict:
    if not isinstance(old_val, str) or not isinstance(new_val, str):
        return {"change_type": "UNKNOWN"}
    lcp_len = 0
    for a, b in zip(old_val, new_val):
        if a == b:
            lcp_len += 1
        else:
            break
    old_rem = old_val[lcp_len:]
    new_rem = new_val[lcp_len:]
    lcs_len = 0
    for a, b in zip(reversed(old_rem), reversed(new_rem)):
        if a == b:
            lcs_len += 1
        else:
            break
    prefix_added = new_val[:lcp_len]
    if lcs_len:
        core_old = old_val[lcp_len:len(old_val)-lcs_len]
        core_new = new_val[lcp_len:len(new_val)-lcs_len]
    else:
        core_old = old_val[lcp_len:]
        core_new = new_val[lcp_len:]
    if lcs_len:
        suffix_added = new_val[len(new_val)-lcs_len:]
    else:
        suffix_added = ""

    if core_old == core_new:
        if prefix_added and suffix_added:
            change_type = "PURE_WRAP"
        elif prefix_added:
            change_type = "PREFIX_ONLY"
        elif suffix_added:
            change_type = "SUFFIX_ONLY"
        else:
            change_type = "PURE_REPLACE"
    else:
        if prefix_added or suffix_added:
            change_type = "REPLACE_WRAP"
        else:
            change_type = "PURE_REPLACE"

    return {
        "change_type": change_type, "prefix_added": prefix_added,
        "core_old": core_old, "core_new": core_new,
        "suffix_added": suffix_added, "old_val": old_val, "new_val": new_val
    }

def _cluster_changes(changes: list) -> list:
    analyzed = []
    for c in changes:
        info = _analyze_value_change(c["old_val"], c["new_val"])
        info.update(c)
        analyzed.append(info)
    if not analyzed:
        return []
    first_type = analyzed[0]["change_type"]
    if first_type in ("PURE_REPLACE",):
        sort_key = lambda a: (a["change_type"], a["core_old"], a["core_new"])
    else:
        sort_key = lambda a: (a["change_type"], a["prefix_added"], a["suffix_added"])
    analyzed.sort(key=sort_key)
    groups = []
    current = [analyzed[0]]
    for item in analyzed[1:]:
        prev = current[-1]
        if item["change_type"] in ("PURE_REPLACE",):
            if item["core_old"] == prev["core_old"] and item["core_new"] == prev["core_new"]:
                current.append(item)
            else:
                groups.append(current)
                current = [item]
        else:
            if item["prefix_added"] == prev["prefix_added"] and item["suffix_added"] == prev["suffix_added"]:
                current.append(item)
            else:
                groups.append(current)
                current = [item]
    groups.append(current)
    return groups

def _score_group(group: list) -> dict:
    n = len(group)
    files = set(item["file"] for item in group)
    items = set(item.get("item_id") for item in group if item.get("item_id"))
    categories = set(get_category(f) for f in files)
    change_type = group[0]["change_type"]
    has_ids = len(items) > 0

    s1 = min(100, len(files) * 8 + len(items) * 3 + n * 1)
    if change_type == "PURE_REPLACE":
        s2 = 100
    elif change_type == "PURE_WRAP":
        s2 = 95
    elif change_type == "REPLACE_WRAP":
        s2 = 70
    else:
        s2 = 60
    if len(categories) >= 3:
        s3 = 100
    elif len(categories) == 2:
        s3 = 80
    else:
        s3 = 60
    s3 += 10 if has_ids else 0
    s4 = 95 if has_ids else 60
    if n >= 5:
        s5 = 100
    elif n >= 3:
        s5 = 80
    elif n == 2:
        s5 = 60
    else:
        s5 = 30
    if change_type == "PURE_REPLACE" and not group[0].get("prefix_added"):
        s5 = min(100, s5 + 15)
    if any("<color=" in item.get("new_val", "") for item in group):
        s5 = min(100, s5 + 10)
    priority = 0.25 * s1 + 0.20 * s2 + 0.20 * s3 + 0.20 * s4 + 0.15 * s5
    return {"s1_coverage": s1, "s2_purity": s2, "s3_generalizability": s3,
            "s4_stability": s4, "s5_intent": s5, "priority": round(priority, 1)}

def _infer_file_scope(files: list) -> dict:
    categories = {}
    for f in files:
        cat = get_category(f)
        categories[cat] = categories.get(cat, 0) + 1
    cat_names = sorted(categories.keys())
    return {
        "suggested": "category" if len(cat_names) <= 2 else "multi_category",
        "categories": [{"name": c, "count": categories[c], "selected": True} for c in cat_names],
        "exact_files": files
    }

def analyze_changes(changes: list) -> dict:
    if not changes:
        return {"groups": [], "merge_suggestions": []}
    groups = _cluster_changes(changes)
    result_groups = []
    for group in groups:
        files = list(set(c["file"] for c in group))
        field_paths = list(set(c["field_path"] for c in group))
        item_ids = list(set(c.get("item_id") for c in group if c.get("item_id")))
        first = group[0]
        score = _score_group(group)

        if first["change_type"] == "PURE_REPLACE" and len(group) >= 3:
            if all(c["new_val"] in "><≥≤" for c in group):
                summary = "你似乎在对数学比较符号做统一替换"
            else:
                summary = f"检测到 {len(group)} 处相同的文本替换"
        elif first["change_type"] in ("PURE_WRAP", "REPLACE_WRAP"):
            colors = set()
            for part in [first["prefix_added"], first["suffix_added"]]:
                for m in re.finditer(r'color=#([0-9a-fA-F]{6})', part):
                    colors.add(m.group(1))
            if colors:
                summary = f"你似乎在对词汇做统一着色（颜色: #{list(colors)[0]}）"
            else:
                summary = f"检测到 {len(group)} 处文本格式化"
        else:
            summary = f"检测到 {len(group)} 处相同修改"

        suggestions = []
        if first["change_type"] == "PURE_REPLACE":
            compare_terms = [c["core_old"] for c in group]
            known = {"大于": ">", "小于": "<", "不低于": "≥", "不高于": "≤"}
            for term, sym in known.items():
                if term not in compare_terms:
                    suggestions.append(f"你也可以添加: {term} → {sym}")

        done_cores = set()
        action_preview = []
        for c in group:
            key = (c["core_old"], c["core_new"])
            if key not in done_cores:
                action_preview.append({"from": c["core_old"], "to": c["core_new"]})
                done_cores.add(key)

        result_groups.append({
            "change_type": first["change_type"],
            "summary": summary,
            "suggestions": suggestions,
            "action_preview": action_preview[:5],
            "file_count": len(files), "item_count": len(item_ids),
            "occurrence_count": len(group),
            "l1_options": _infer_file_scope(files),
            "l2_options": {"suggested": "id" if item_ids else "full_text", "item_ids": item_ids},
            "l3_options": {"suggested": "restricted" if len(field_paths) == 1 else "all_text",
                           "fields": field_paths},
            "l4_options": {"suggested": "exact" if first["change_type"] == "PURE_REPLACE" else "none"},
            "score": score
        })

    result_groups.sort(key=lambda g: g["score"]["priority"], reverse=True)
    return {"groups": result_groups, "merge_suggestions": []}
