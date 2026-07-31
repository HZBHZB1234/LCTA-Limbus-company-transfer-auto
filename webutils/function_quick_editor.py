"""简易翻译编辑器后端 API — diff 追踪、路径导航、持久化、应用"""

import json
import logging
from pathlib import Path
from collections import defaultdict
from typing import Optional

from webutils.bus_engine import apply_bus, compile_bus_ruleset, convert_edits_to_bus_ruleset
from webutils.function_fancy import _get_fancy_folder
from webutils.rule_editor_constants import FILE_PREFIX_RULES

logger = logging.getLogger('quick_editor')


# ──── Diff ────

def diff_json(original, modified, prefix=''):
    """深度比较两个 JSON 结构，返回变更列表 [{path, old, new}]。
    路径格式: 点分隔，列表索引用数字。如 "dataList.0.desc"
    移植自 test2_reconstructed.py """
    changes = []
    if type(original) != type(modified):
        changes.append({'path': prefix, 'old': original, 'new': modified})
    elif isinstance(original, dict):
        all_keys = set(original.keys()) | set(modified.keys())
        for key in sorted(all_keys):
            new_prefix = f'{prefix}.{key}' if prefix else key
            if key not in original:
                changes.append({'path': new_prefix, 'old': None, 'new': modified[key]})
            elif key not in modified:
                changes.append({'path': new_prefix, 'old': original[key], 'new': None})
            else:
                changes.extend(diff_json(original[key], modified[key], new_prefix))
    elif isinstance(original, list):
        for i in range(max(len(original), len(modified))):
            new_prefix = f'{prefix}.{i}'
            if i >= len(original):
                changes.append({'path': new_prefix, 'old': None, 'new': modified[i]})
            elif i >= len(modified):
                changes.append({'path': new_prefix, 'old': original[i], 'new': None})
            else:
                changes.extend(diff_json(original[i], modified[i], new_prefix))
    elif original != modified:
        changes.append({'path': prefix, 'old': original, 'new': modified})
    return changes


# ──── Quick Edits Persistence ────

QUICK_EDITS_FILENAME = '_quick_edits.json'


def _get_quick_edits_path() -> Path:
    """返回 fancy/_quick_edits.json 的绝对路径"""
    return _get_fancy_folder() / QUICK_EDITS_FILENAME


def load_quick_edits() -> dict:
    """加载快速编辑文件，不存在则返回空结构"""
    path = _get_quick_edits_path()
    if not path.exists():
        return {
            "name": "_quick_edits",
            "desc": "简易翻译编辑",
            "version": 1,
            "edits": []
        }
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if 'edits' not in data:
            data['edits'] = []
        if 'rules' not in data:
            migrated, _ = convert_edits_to_bus_ruleset(data['edits'])
            migrated.update({key: value for key, value in data.items() if key not in migrated})
            data = migrated
        return data
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"加载快速编辑文件失败: {e}")
        return {
            "name": "_quick_edits",
            "desc": "简易翻译编辑",
            "version": 1,
            "edits": []
        }


def save_quick_edits(edits: list) -> dict:
    """保存 edits 列表到 fancy/_quick_edits.json。
    直接接收 JS 传来的 edits 数组，并派生可执行的 bus 规则。"""
    path = _get_quick_edits_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data, report = convert_edits_to_bus_ruleset(edits)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        return {"success": True, "path": str(path), "report": report}
    except Exception as e:
        logger.error(f"保存快速编辑文件失败: {e}")
        return {"success": False, "error": str(e)}


def apply_quick_edits() -> dict:
    """应用所有 edits 到游戏文件。
    按文件分组、逐文件读取→修改→写回，不创建 .bak 备份
    （与文本美化行为保持一致）。"""
    from webutils.function_rule_editor import _get_lang_dir

    lang_dir = _get_lang_dir()
    if not lang_dir:
        return {"success": False, "error": "Lang 文件夹未配置", "applied": 0, "failed": 0}

    data = load_quick_edits()
    edits = data.get('edits', [])
    if not edits:
        return {"success": True, "applied": 0, "failed": 0, "message": "没有待应用的修改"}

    ruleset, report = convert_edits_to_bus_ruleset(edits)
    compiled = compile_bus_ruleset(ruleset)
    by_file = defaultdict(list)
    for edit in edits:
        if isinstance(edit, dict) and isinstance(edit.get('file'), str):
            by_file[edit['file']].append(edit)

    success_count = 0
    fail_count = report['skipped']
    errors = list(report['warnings'])
    resolved_lang_dir = lang_dir.resolve()

    for rel_path, file_edits in by_file.items():
        full_path = (resolved_lang_dir / rel_path).resolve()
        try:
            full_path.relative_to(resolved_lang_dir)
        except ValueError:
            fail_count += len(file_edits)
            errors.append(f"文件路径超出语言包目录: {rel_path}")
            continue
        if not full_path.exists():
            fail_count += len(file_edits)
            errors.append(f"文件不存在: {rel_path}")
            continue
        try:
            content = full_path.read_text(encoding='utf-8-sig')
            data_obj = json.loads(content)
            result = apply_bus(data_obj, compiled, rel_path.replace('\\', '/'))
            success_count += result.matched_rules
            fail_count += result.failed_rules
            errors.extend(result.errors)
            if result.changed_count:
                from webutils.function_fancy import _write_json_atomic

                _write_json_atomic(full_path, result.data)
        except json.JSONDecodeError as e:
            fail_count += len(file_edits)
            errors.append(f"JSON 解析失败 {rel_path}: {e}")
        except Exception as e:
            fail_count += len(file_edits)
            errors.append(f"写入失败 {rel_path}: {e}")

    return {
        "success": fail_count == 0,
        "applied": success_count,
        "failed": fail_count,
        "errors": errors[:10]  # 最多返回 10 条错误
    }
