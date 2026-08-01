"""美化规则编辑器后端 API — 文件浏览、规则 CRUD、智能生成"""

import json
import os
import re
import shutil
import logging
from pathlib import Path
from typing import Optional

from globalManagers.ConfigManager import ConfigManager
from webutils.function_fancy import (
    load_fancy_folder_rules, save_ruleset_to_folder,
    delete_ruleset_from_folder, _get_fancy_folder, _sanitize_filename,
)
from webutils.bus_engine import compile_bus_ruleset, is_bus_ruleset
from webutils.fancy_engine import RuleValidationError, apply_rules, compile_rulesets
from webutils.rule_editor_constants import FILE_PREFIX_RULES, CATEGORY_FILE_PATTERNS

logger = logging.getLogger('rule_editor')


_lang_dir_cache = None

def _get_lang_dir() -> Optional[Path]:
    global _lang_dir_cache
    if _lang_dir_cache is not None:
        return _lang_dir_cache
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
    _lang_dir_cache = lang_path if lang_path.exists() else None
    return _lang_dir_cache

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
    resolved_lang_dir = lang_dir.resolve()
    full_path = (resolved_lang_dir / relative_path).resolve()
    try:
        full_path.relative_to(resolved_lang_dir)
    except ValueError:
        return {"error": f"文件路径超出语言包目录: {relative_path}"}
    if not full_path.exists():
        return {"error": f"文件不存在: {relative_path}"}
    try:
        raw = full_path.read_text(encoding='utf-8-sig')
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        return {"raw": raw, "parsed": parsed, "file_classification": get_category(relative_path)}
    except Exception as e:
        return {"error": str(e), "raw": None, "parsed": None}

def search_files(keyword: str, case_sensitive: bool = False) -> dict:
    lang_dir = _get_lang_dir()
    if not lang_dir or not isinstance(keyword, str) or not keyword:
        return {"results_by_category": {}, "total_matches": 0}
    results_by_category = {}
    total_matches = 0
    search_keyword = keyword if case_sensitive else keyword.lower()

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
                content = full_path.read_text(encoding='utf-8-sig')
                searchable_content = content if case_sensitive else content.lower()
                matches = searchable_content.count(search_keyword)
                if matches > 0:
                    category = get_category(rel_path)
                    if category not in results_by_category:
                        results_by_category[category] = []
                    results_by_category[category].append((rel_path, matches))
                    total_matches += matches
            except (OSError, UnicodeError) as exc:
                logger.debug("搜索文件内容失败 %s: %s", full_path, exc)
    return {"results_by_category": results_by_category, "total_matches": total_matches}

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
    template = {"version": 2, "name": name, "desc": "", "rules": []}
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

def _analyze_value_change(old_val, new_val) -> dict:
    if not isinstance(old_val, str) or not isinstance(new_val, str):
        return {"change_type": "UNKNOWN"}
    if old_val and old_val in new_val:
        idx = new_val.index(old_val)
        prefix_added = new_val[:idx]
        suffix_added = new_val[idx + len(old_val):]
        core_old = old_val
        core_new = new_val
        if prefix_added and suffix_added:
            change_type = "PURE_WRAP"
        elif prefix_added:
            change_type = "PREFIX_ONLY"
        elif suffix_added:
            change_type = "SUFFIX_ONLY"
        else:
            change_type = "PURE_REPLACE"
    else:
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
        prefix_added = ""
        suffix_added = ""
        core_old = old_val[lcp_len:len(old_val)-lcs_len]
        core_new = new_val[lcp_len:len(new_val)-lcs_len]
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
    sort_key = lambda a: (
        a["change_type"],
        a.get("prefix_added", ""), a.get("suffix_added", ""),
        a.get("core_old", ""), a.get("core_new", ""),
    )
    analyzed.sort(key=sort_key)
    groups = []
    current = [analyzed[0]]
    for item in analyzed[1:]:
        prev = current[-1]
        if item["change_type"] in ("PURE_REPLACE",):
            if item.get("core_old") == prev.get("core_old") and item.get("core_new") == prev.get("core_new"):
                current.append(item)
            else:
                groups.append(current)
                current = [item]
        else:
            if item.get("prefix_added") == prev.get("prefix_added") and item.get("suffix_added") == prev.get("suffix_added"):
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

def _infer_file_scope(files: list, all_files_count: int = 0) -> dict:
    categories = {}
    for f in files:
        cat = get_category(f)
        categories[cat] = categories.get(cat, 0) + 1
    cat_names = sorted(categories.keys())
    cat_count = len(cat_names)

    # 计算分类覆盖的总文件数（用于推广阶梯显示）
    category_file_count = sum(categories.values())

    available = [
        {"level": "exact", "label": "仅涉及文件", "count": len(files)},
        {"level": "category", "label": "同分类文件", "count": category_file_count},
    ]
    if all_files_count > 0 and all_files_count > category_file_count:
        available.append(
            {"level": "all", "label": "所有文件", "count": all_files_count}
        )
    else:
        available.append(
            {"level": "all", "label": "所有文件", "count": category_file_count}
        )

    return {
        "suggested": "exact",  # 默认最精确约束，用户可通过推广按钮放宽
        "categories": [{"name": c, "count": categories[c], "selected": True} for c in cat_names],
        "exact_files": files,
        "available": available
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


def analyze_changes_v2(changes: list, bias: str = 'conservative') -> dict:
    if not changes:
        return {"groups": [], "merge_suggestions": []}
    groups = _cluster_changes(changes)
    result_groups = []
    merge_suggestions = []
    for group in groups:
        files = list(set(c["file"] for c in group))
        field_paths = list(set(c["field_path"] for c in group))
        item_ids = list(set(c.get("item_id") for c in group if c.get("item_id")))
        first = group[0]
        score = _score_group(group)

        if bias == 'conservative' and len(files) < 3:
            continue

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

        merge_suggestion = False
        if bias == 'aggressive' and len(files) < 3:
            merge_suggestion = True
            merge_suggestions.append(
                f'组 "{first["core_old"]} → {first["core_new"]}" 出现于 {len(files)} 个文件，建议合并到其他组'
            )

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
            "score": score,
            "merge_suggestion": merge_suggestion
        })

    result_groups.sort(key=lambda g: g["score"]["priority"], reverse=True)
    return {"groups": result_groups, "merge_suggestions": merge_suggestions}


def _detect_merge_candidates(groups: list) -> list:
    """Detect pairs of groups that could be merged into broader rules.
    Returns list of (idx1, idx2, score, reason) sorted by score desc.
    """
    candidates = []
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            g1, g2 = groups[i], groups[j]

            if g1.get("change_type") != g2.get("change_type"):
                continue

            f1 = set(g1.get("l3_options", {}).get("fields", []))
            f2 = set(g2.get("l3_options", {}).get("fields", []))
            field_overlap = len(f1 & f2)
            if field_overlap == 0:
                continue

            ap1 = [a.get("from") for a in g1.get("action_preview", [])]
            ap2 = [a.get("from") for a in g2.get("action_preview", [])]
            if ap1 == ap2:
                continue

            files1 = set(g1.get("l1_options", {}).get("exact_files", []))
            files2 = set(g2.get("l1_options", {}).get("exact_files", []))
            cats1 = set(c["name"] for c in g1.get("l1_options", {}).get("categories", []))
            cats2 = set(c["name"] for c in g2.get("l1_options", {}).get("categories", []))

            score = 0
            if field_overlap > 0:
                score += 10
            if len(files1 & files2) >= 2:
                score += 5
            if len(cats1 & cats2) >= 2:
                score += 3

            if score >= 8:
                shared_field = list(f1 & f2)[0]
                shared_files = len(files1 & files2)
                reason = f"相同字段 '{shared_field}'，文件重叠 {shared_files} 个，分类重叠 {len(cats1 & cats2)} 个"
                candidates.append((i, j, score, reason))

    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates


def analyze_changes_v3(changes: list) -> dict:
    """V3 统一智能分析：自动合并相似变更 + 即时展示所有结果。

    与 V2 的关键区别：
    1. 无 bias 参数 —— 不再全局过滤，所有变更都展示
    2. 按 (old_val, new_val, field_path) 自动合并跨文件相同变更
    3. 返回 merged_from / is_merged 字段供前端展示合并来源
    4. 返回 merge_candidates 供前端显示可合并的组对
    5. 返回 stats 摘要信息
    """
    if not changes:
        return {
            "groups": [], "merge_suggestions": [],
            "stats": {"change_count": 0, "group_count": 0, "file_count": 0, "category_count": 0},
            "merge_candidates": []
        }

    # 第一轮：按 (old_val, new_val, field_path) 合并 key 分桶
    merge_buckets = {}
    merge_order = []
    for c in changes:
        key = (str(c.get("old_val", "")), str(c.get("new_val", "")), str(c.get("field_path", "")))
        if key not in merge_buckets:
            merge_buckets[key] = []
            merge_order.append(key)
        merge_buckets[key].append(c)

    # 第二轮：对每个 merge bucket 汇总
    all_files = set()
    all_categories = set()
    merged_groups = []
    merge_key_index = {}  # key -> group index in merged_groups

    for key in merge_order:
        items = merge_buckets[key]
        first = items[0]

        # 收集该 merge key 下的所有文件、条目、字段
        files = list(dict.fromkeys(c["file"] for c in items))
        item_ids = list(dict.fromkeys(
            c.get("item_id") for c in items if c.get("item_id")
        ))
        field_paths = list(dict.fromkeys(
            c.get("field_path") for c in items
        ))

        for f in files:
            all_files.add(f)
            cat = get_category(f)
            all_categories.add(cat)

        # 分析变化类型
        change_info = _analyze_value_change(first.get("old_val", ""), first.get("new_val", ""))
        change_type = change_info.get("change_type", "PURE_REPLACE")

        # 从所有 items 收集 action_preview（去重）
        done_cores = set()
        action_preview = []
        for c in items:
            info = _analyze_value_change(c.get("old_val", ""), c.get("new_val", ""))
            core_key = (info.get("core_old", ""), info.get("core_new", ""))
            if core_key not in done_cores:
                action_preview.append({"from": info.get("core_old", c.get("old_val", "")),
                                       "to": info.get("core_new", c.get("new_val", ""))})
                done_cores.add(core_key)

        # 生成摘要
        if change_type == "PURE_REPLACE" and len(items) >= 3:
            if all(c.get("new_val", "") in "><≥≤" for c in items):
                summary = "你似乎在对数学比较符号做统一替换"
            else:
                old_sample = first.get("old_val", "")
                new_sample = first.get("new_val", "")
                summary = f"检测到 {len(items)} 处相同的文本替换 ({old_sample} → {new_sample})"
        elif change_type in ("PURE_WRAP", "REPLACE_WRAP"):
            colors = set()
            for part in [change_info.get("prefix_added", ""), change_info.get("suffix_added", "")]:
                for m in re.finditer(r'color=#([0-9a-fA-F]{6})', part):
                    colors.add(m.group(1))
            if colors:
                summary = f"你似乎在对词汇做统一着色（颜色: #{list(colors)[0]}）"
            else:
                summary = f"检测到 {len(items)} 处文本格式化"
        else:
            summary = f"检测到 {len(items)} 处相同修改"

        # 构建 group 对象
        total_items_count = len(item_ids) if item_ids else len(items)
        group = {
            "change_type": change_type,
            "summary": summary,
            "suggestions": [],
            "action_preview": action_preview[:5],
            "file_count": len(files),
            "item_count": len(item_ids),
            "occurrence_count": len(items),
            "l1_options": _infer_file_scope(files),
            "l2_options": {
                "suggested": "id" if item_ids else "full_text",
                "item_ids": item_ids,
                "available": [
                    {"level": "id", "label": "按ID定位", "count": len(item_ids)},
                    {"level": "full_text", "label": "全文匹配", "count": total_items_count},
                ]
            },
            "l3_options": {
                "suggested": "restricted" if len(field_paths) == 1 else "all_text",
                "fields": field_paths,
                "available": [
                    {"level": "restricted", "label": "限定字段", "count": len(field_paths)},
                    {"level": "all_text", "label": "全部字段", "count": len(field_paths)},
                ]
            },
            "l4_options": {
                "suggested": "exact" if change_type == "PURE_REPLACE" else "none",
                "available": [
                    {"level": "exact", "label": "完整匹配"},
                    {"level": "none", "label": "子串匹配"},
                ]
            },
            "score": _score_group(_make_scorable(items)),
            "merged_from": [
                {"file": f, "count": sum(1 for c in items if c["file"] == f)}
                for f in files
            ],
            "is_merged": len(files) > 1,
            "merge_candidates": []
        }

        merged_groups.append(group)
        for f in files:
            for mf_entry in group["merged_from"]:
                pass  # already built above

    # 第三轮：评分 + 排序
    merged_groups.sort(key=lambda g: g["score"]["priority"], reverse=True)

    # 第四轮：检测可合并的组对
    candidates = _detect_merge_candidates(merged_groups)
    for i, j, score, reason in candidates:
        merged_groups[i].setdefault("merge_candidates", []).append([j, score, reason])
        merged_groups[j].setdefault("merge_candidates", []).append([i, score, reason])

    return {
        "groups": merged_groups,
        "merge_suggestions": [],
        "stats": {
            "change_count": len(changes),
            "group_count": len(merged_groups),
            "file_count": len(all_files),
            "category_count": len(all_categories)
        },
        "merge_candidates": [
            {"idx1": i, "idx2": j, "score": score, "reason": reason}
            for i, j, score, reason in candidates
        ]
    }


def _make_scorable(changes: list) -> list:
    """Convert change dicts to the format _score_group expects."""
    out = []
    for c in changes:
        info = _analyze_value_change(c.get("old_val", ""), c.get("new_val", ""))
        out.append({
            "change_type": info.get("change_type", "PURE_REPLACE"),
            "file": c["file"],
            "item_id": c.get("item_id"),
            "prefix_added": info.get("prefix_added", ""),
            "new_val": c.get("new_val", "")
        })
    return out


def save_file_content(relative_path: str, content: str) -> dict:
    """Save edited file content back to the game Lang directory.
    Validates JSON, creates a .bak backup, and writes the file.
    """
    lang_dir = _get_lang_dir()
    if not lang_dir:
        return {"success": False, "error": "Lang 文件夹未配置"}
    resolved_lang_dir = lang_dir.resolve()
    full_path = (resolved_lang_dir / relative_path).resolve()
    try:
        full_path.relative_to(resolved_lang_dir)
    except ValueError:
        return {"success": False, "error": f"文件路径超出语言包目录: {relative_path}"}
    if not full_path.exists():
        return {"success": False, "error": f"文件不存在: {relative_path}"}
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON 格式错误: {e}"}
    try:
        backup_path = full_path.with_suffix('.json.bak')
        shutil.copy2(full_path, backup_path)
    except Exception as e:
        logger.warning("备份文件失败: %s", e)
    try:
        full_path.write_text(content, encoding='utf-8-sig')
        return {"success": True, "path": str(full_path)}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
