from __future__ import annotations

import re

from .browser import get_category
from .constants import COMMON_REPLACEMENTS

_KNOWN_COMPARISON_REPLACEMENTS = {
    item["from"]: item["to"] for item in COMMON_REPLACEMENTS[:4]
}


def _analyze_value_change(old_val, new_val) -> dict:
    if not isinstance(old_val, str) or not isinstance(new_val, str):
        return {
            "change_type": "UNKNOWN",
            "prefix_added": "", "suffix_added": "",
            "core_old": str(old_val), "core_new": str(new_val),
            "old_val": old_val, "new_val": new_val,
        }
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
    if any(isinstance(item.get("new_val"), str) and "<color=" in item.get("new_val") for item in group):
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
            for term, sym in _KNOWN_COMPARISON_REPLACEMENTS.items():
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
            if all(isinstance(c.get("new_val"), str) and c["new_val"] in "><≥≤" for c in group):
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
            for term, sym in _KNOWN_COMPARISON_REPLACEMENTS.items():
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


def _rule_covers_items(actions: list, items: list) -> bool:
    """判断规则 actions（按顺序的字面全局替换）是否能在 items 上推广。

    将 actions 依次应用到每条 item 的 old_val（与引擎 literal 模式一致，
    即 str.replace 全局替换），若所有 item 的结果都恰好等于其 new_val，
    则说明该规则可以覆盖这些变更，满足合并条件。
    """
    if not actions or not items:
        return False
    for item in items:
        old_val = item.get("old_val")
        new_val = item.get("new_val")
        if not isinstance(old_val, str) or not isinstance(new_val, str):
            return False
        result = old_val
        for action in actions:
            from_str = action.get("from")
            to_str = action.get("to")
            if not isinstance(from_str, str) or not isinstance(to_str, str) or not from_str:
                return False
            result = result.replace(from_str, to_str)
        if result != new_val:
            return False
    return True


def _detect_merge_candidates(groups: list) -> list:
    """检测可合并的组对（语义验证）。

    合并条件：某一组的规则（action_preview，按字面全局替换语义）能推广到
    另一组的全部原始变更上（old_val 应用规则后恰等于 new_val）。同规则的
    组对天然双向通过，也能合并以扩大文件范围。
    返回 (idx1, idx2, score, reason) 列表，按 score 降序。
    """
    candidates = []
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            g1, g2 = groups[i], groups[j]

            if g1.get("change_type") != g2.get("change_type"):
                continue

            actions1 = g1.get("action_preview", [])
            actions2 = g2.get("action_preview", [])
            items1 = g1.get("_raw_changes", [])
            items2 = g2.get("_raw_changes", [])

            if not actions1 or not actions2 or not items1 or not items2:
                continue

            cov1 = _rule_covers_items(actions1, items2)
            cov2 = _rule_covers_items(actions2, items1)
            if not cov1 and not cov2:
                continue

            files1 = set(g1.get("l1_options", {}).get("exact_files", []))
            files2 = set(g2.get("l1_options", {}).get("exact_files", []))
            cats1 = set(c["name"] for c in g1.get("l1_options", {}).get("categories", []))
            cats2 = set(c["name"] for c in g2.get("l1_options", {}).get("categories", []))

            score = 20
            if len(files1 & files2) >= 2:
                score += 5
            if len(cats1 & cats2) >= 2:
                score += 3

            if cov1 and cov2:
                rule_src = g1 if len(actions1) <= len(actions2) else g2
            else:
                rule_src = g1 if cov1 else g2
            covered_count = len(items2) if cov1 else len(items1)
            ap_text = "、".join(
                f'{a.get("from", "")} → {a.get("to", "")}' for a in rule_src.get("action_preview", [])
            )
            reason = f'规则 "{ap_text}" 可推广覆盖另外 {covered_count} 项变更'
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
            if all(isinstance(c.get("new_val"), str) and c["new_val"] in "><≥≤" for c in items):
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
            "_raw_changes": [
                {"old_val": c.get("old_val", ""), "new_val": c.get("new_val", "")}
                for c in items
            ],
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
