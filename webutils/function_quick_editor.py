"""简易翻译编辑器后端 API — diff 追踪、路径导航、持久化、应用"""

import json
import logging
import re
from pathlib import Path
from collections import defaultdict
from typing import Optional

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


# ──── Path Navigation ────

def _set_value_by_path(obj, path_str, value):
    """按点分隔路径导航 JSON 树并设值。
    路径示例: "dataList.0.name" → obj["dataList"][0]["name"] = value
    移植自 test2_reconstructed.py """
    if not path_str:
        return
    # 分割路径: "dataList.0.name" → ["dataList", "0", "name"]
    parts = re.findall(r'\w+|\[\d+\]', path_str)
    if not parts:
        return
    # 导航到父节点
    for i, part in enumerate(parts[:-1]):
        if part.startswith('['):
            idx = int(part[1:-1])
            obj = obj[idx]
        elif part.isdigit():
            obj = obj[int(part)]
        else:
            obj = obj[part]
    # 设置最后一个节点
    last = parts[-1]
    if last.startswith('['):
        idx = int(last[1:-1])
        obj[idx] = value
    elif last.isdigit():
        obj[int(last)] = value
    else:
        obj[last] = value


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
    直接接收 JS 传来的 edits 数组，包裹为标准结构后写入。"""
    from webutils.function_rule_editor import _get_lang_dir
    path = _get_quick_edits_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "name": "_quick_edits",
        "desc": "简易翻译编辑",
        "version": 1,
        "edits": edits
    }
    try:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        return {"success": True, "path": str(path)}
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

    # 按文件分组
    by_file = defaultdict(list)
    for edit in edits:
        by_file[edit['file']].append(edit)

    success_count = 0
    fail_count = 0
    errors = []

    for rel_path, file_edits in by_file.items():
        full_path = lang_dir / rel_path
        if not full_path.exists():
            fail_count += len(file_edits)
            errors.append(f"文件不存在: {rel_path}")
            continue
        try:
            content = full_path.read_text(encoding='utf-8')
            data_obj = json.loads(content)
            for edit in file_edits:
                try:
                    _set_value_by_path(data_obj, edit['path'], edit['new'])
                    success_count += 1
                except (KeyError, IndexError, TypeError) as e:
                    fail_count += 1
                    errors.append(f"{rel_path} / {edit['path']}: {e}")
            # 写回文件（无 .bak 备份）
            formatted = json.dumps(data_obj, ensure_ascii=False, indent=2)
            full_path.write_text(formatted, encoding='utf-8')
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
