"""美化规则编辑器后端 API — 文件浏览、规则 CRUD、智能生成"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Optional

from globalManagers.ConfigManager import ConfigManager
from .constants import FILE_PREFIX_RULES

logger = logging.getLogger('rule_editor')


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
    # Skills_Ego_*（人格EGO技能）与 'Skill' 前缀冲突，优先归入 Egos（与前端 classifyPath 一致）
    if 'Skills_Ego' in relative_path:
        for prefix, category in FILE_PREFIX_RULES:
            if prefix == 'Egos':
                return category
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
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8-sig',
                newline='',
                dir=full_path.parent,
                prefix=f'.{full_path.name}.',
                suffix='.tmp',
                delete=False,
            ) as temp_file:
                temp_file.write(content)
                temp_path = Path(temp_file.name)
            os.replace(temp_path, full_path)
            return {"success": True, "path": str(full_path)}
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
    except Exception as e:
        return {"success": False, "error": str(e)}
