"""简易翻译编辑器后端 API — diff 追踪、路径导航、持久化、应用"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from collections import defaultdict
from typing import Optional

from ..fancy.bus import apply_bus, compile_bus_ruleset, convert_edits_to_bus_ruleset
from ..function_fancy import _get_fancy_folder

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

_quick_edits_lock = threading.Lock()


def _get_quick_edits_path() -> Path:
    """返回 fancy/_quick_edits.json 的绝对路径"""
    return _get_fancy_folder() / QUICK_EDITS_FILENAME


def _write_quick_edits_atomic(path: Path, data: dict) -> None:
    """同目录临时文件 + os.replace 原子写。

    复制自 function_fancy._write_json_atomic，但使用 utf-8（无 BOM）与
    indent=2，与 _quick_edits.json 的读取端（load_quick_edits、
    load_fancy_folder_rules 均按 utf-8 读取）保持一致。
    """
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            newline='',
            dir=path.parent,
            prefix=f'.{path.name}.',
            suffix='.tmp',
            delete=False,
        ) as temp_file:
            temp_file.write(serialized)
            temp_path = Path(temp_file.name)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


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
        with _quick_edits_lock:
            data = json.loads(path.read_text(encoding='utf-8'))
        if 'edits' not in data:
            data['edits'] = []
        if 'rules' not in data:
            migrated, _ = convert_edits_to_bus_ruleset(data['edits'])
            migrated.update({key: value for key, value in data.items() if key not in migrated})
            data = migrated
        return data
    except Exception as e:
        logger.warning(f"加载快速编辑文件失败: {e}")
        return {
            "name": "_quick_edits",
            "desc": "简易翻译编辑",
            "version": 1,
            "edits": []
        }


def save_quick_edits(edits: list) -> dict:
    """保存 edits 列表到 fancy/_quick_edits.json。
    直接接收 JS 传来的 edits 数组，并派生可执行的 bus 规则。
    线程锁 + 原子写，防止双窗口并发保存写坏/丢失数据。"""
    path = _get_quick_edits_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data, report = convert_edits_to_bus_ruleset(edits)
        with _quick_edits_lock:
            _write_quick_edits_atomic(path, data)
        return {"success": True, "path": str(path), "report": report}
    except Exception as e:
        logger.error(f"保存快速编辑文件失败: {e}")
        return {"success": False, "error": str(e)}


# ──── Apply 前校验 ────

_MISSING = object()


def _get_value_at_quick_path(data, path: str):
    """按 quick 路径格式（如 dataList.5.desc，数字为列表索引）取当前值。
    路径不存在返回 _MISSING，与 _convert_quick_path 的语义保持一致。"""
    if not path:
        return _MISSING
    current = data
    for part in path.split('.'):
        if part.isdigit():
            index = int(part)
            if not isinstance(current, list) or index >= len(current):
                return _MISSING
            current = current[index]
        else:
            if not isinstance(current, dict) or part not in current:
                return _MISSING
            current = current[part]
    return current


def _old_value_matches(current, old) -> bool:
    """校验当前值是否仍等于记录的原值。

    old 为 None 表示原值不存在（插入语义）：当前值缺位或为 null 均视为匹配；
    其余情况要求路径存在且值相等。"""
    if old is None:
        return current is _MISSING or current is None
    return current is not _MISSING and current == old


def apply_quick_edits() -> dict:
    """应用所有 edits 到游戏文件。
    按文件分组、逐文件读取→修改→写回，不创建 .bak 备份
    （与文本美化行为保持一致）。
    应用前逐条校验 edit 的 old 值是否与文件当前值匹配；
    列表索引漂移导致的原值不匹配会被报告并跳过，而不是静默写错对象。"""
    from .browser import _get_lang_dir

    lang_dir = _get_lang_dir()
    if not lang_dir:
        return {"success": False, "error": "Lang 文件夹未配置", "applied": 0, "failed": 0}

    data = load_quick_edits()
    edits = data.get('edits', [])
    if not edits:
        return {"success": True, "applied": 0, "failed": 0, "message": "没有待应用的修改"}

    ruleset, report = convert_edits_to_bus_ruleset(edits)
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
            valid_edits = []
            for edit in file_edits:
                path = edit.get('path')
                if not isinstance(path, str) or path == '':
                    # 非法/根节点编辑已在整体转换时计入 skipped
                    continue
                old = edit.get('old')
                current = _get_value_at_quick_path(data_obj, path)
                if 'old' in edit and not _old_value_matches(current, old):
                    current_display = (
                        '(不存在)'
                        if current is _MISSING
                        else json.dumps(current, ensure_ascii=False)
                    )
                    fail_count += 1
                    errors.append(
                        f"原值不匹配 {rel_path} / {path}: 当前值 {current_display}"
                        f" ≠ 记录原值 {json.dumps(old, ensure_ascii=False)}"
                    )
                    continue
                valid_edits.append(edit)
            if not valid_edits:
                continue
            file_ruleset, _ = convert_edits_to_bus_ruleset(valid_edits)
            result = apply_bus(data_obj, compile_bus_ruleset(file_ruleset), rel_path.replace('\\', '/'))
            success_count += result.matched_rules
            fail_count += result.failed_rules
            errors.extend(result.errors)
            if result.changed_count:
                from ..function_fancy import _write_json_atomic

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
