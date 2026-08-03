from __future__ import annotations
import json
import logging
import os
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from globalManagers.LogManager import LogManager
from webutils.fancy.bus import (
    BUS_FORMAT,
    BUS_VERSION,
    CompiledBus,
    apply_bus,
    compile_bus_ruleset,
    convert_edits_to_bus_ruleset,
    convert_lcje_config,
    convert_tiaozhua_config,
    is_bus_ruleset,
    is_lcje_config,
    is_tiaozhua_config,
)
from webutils.fancy.engine import ApplyResult, CompiledRules, apply_rules, compile_rulesets

_log_manager = LogManager()

logger = logging.getLogger('fancy')

def exec_json(data: dict, config: list) -> dict:
    """应用 v2 规则；保留该入口供规则编辑器内容预览使用。"""
    return apply_rules(data, compile_rulesets(config)).data


@dataclass(frozen=True)
class FancyRunStats:
    files_scanned: int
    files_matched: int
    files_changed: int
    values_changed: int
    elapsed_seconds: float
    resource_cache_hit: bool


@dataclass(frozen=True)
class _CompiledRuleset:
    kind: str
    compiled: CompiledRules | CompiledBus


def _write_json_atomic(file: Path, data: dict) -> None:
    serialized = json.dumps(data, ensure_ascii=False, indent=4)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8-sig',
            newline='',
            dir=file.parent,
            prefix=f'.{file.name}.',
            suffix='.tmp',
            delete=False,
        ) as temp_file:
            temp_file.write(serialized)
            temp_path = Path(temp_file.name)
        os.replace(temp_path, file)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _select_enabled_rulesets(config: list, enable_map: Optional[Mapping] = None) -> list:
    if enable_map is None:
        return list(config)
    if not isinstance(enable_map, Mapping):
        logger.warning('美化启用配置格式无效，跳过全部规则集')
        return []
    return [
        ruleset for ruleset in config
        if enable_map.get(ruleset.get('name', ''), False)
    ]


def _compile_mixed_rulesets(rulesets: list) -> tuple[_CompiledRuleset, ...]:
    compiled: list[_CompiledRuleset] = []
    for ruleset in rulesets:
        if is_bus_ruleset(ruleset):
            compiled.append(_CompiledRuleset("bus", compile_bus_ruleset(ruleset)))
        else:
            compiled.append(_CompiledRuleset("v2", compile_rulesets([ruleset])))
    return tuple(compiled)


def fancy_main(
    game_path: str,
    package_name: str,
    config: list,
    enable_map: Optional[Mapping] = None,
) -> FancyRunStats:
    """
    处理语言包下的所有 JSON 文件。
    config: 规则集列表，每个元素包含 "rules" 列表。
    enable_map: 可选的规则集启用状态；传入时仅编译和执行明确启用的规则集。
    """
    started_at = time.perf_counter()
    enabled_rulesets = _select_enabled_rulesets(config, enable_map)
    compiled_rulesets = _compile_mixed_rulesets(enabled_rulesets)
    resource_cache_hit = False
    if any(
        item.kind == "v2" and item.compiled.requires_skill_color
        for item in compiled_rulesets
    ):
        from webutils.fancy.builtin_func import skillColorHandler

        skillColorHandler.last_cache_hit = False
        skillColorHandler.prepare()
        resource_cache_hit = skillColorHandler.last_cache_hit

    lang_path = Path(game_path) / 'LimbusCompany_Data' / 'lang' / package_name
    files = list(lang_path.rglob('*.json'))
    logger.info(f'一共{len(files)}个文件')
    files_matched = 0
    files_changed = 0
    values_changed = 0

    for file in files:
        relative_path = file.relative_to(lang_path).as_posix()
        matched_entries = []
        for entry in compiled_rulesets:
            if entry.kind == "v2":
                file_rules = entry.compiled.for_file(relative_path)
                if file_rules.rules:
                    matched_entries.append((entry.kind, file_rules))
            elif entry.compiled.for_file(relative_path):
                matched_entries.append((entry.kind, entry.compiled))
        if not matched_entries:
            continue
        files_matched += 1
        try:
            data = json.loads(file.read_text(encoding='utf-8-sig'))
            file_changed_paths: set[tuple] = set()
            for kind, matched_rules in matched_entries:
                if kind == "v2":
                    result = apply_rules(data, matched_rules)
                else:
                    result = apply_bus(data, matched_rules, relative_path)
                data = result.data
                file_changed_paths.update(result.changed_paths)
            changed_count = len(file_changed_paths)
            if changed_count:
                _write_json_atomic(file, data)
                files_changed += 1
                values_changed += changed_count
        except Exception as e:
            logger.exception(f"处理文件 {file} 时出错: {e}")
            _log_manager.log_error(e)

    stats = FancyRunStats(
        files_scanned=len(files),
        files_matched=files_matched,
        files_changed=files_changed,
        values_changed=values_changed,
        elapsed_seconds=time.perf_counter() - started_at,
        resource_cache_hit=resource_cache_hit,
    )
    logger.info(
        '文本美化完成：扫描%s，匹配%s，修改%s个文件/%s个字段，耗时%.3f秒',
        stats.files_scanned,
        stats.files_matched,
        stats.files_changed,
        stats.values_changed,
        stats.elapsed_seconds,
    )
    return stats

def _get_fancy_folder() -> Path:
    """获取 fancy/ 文件夹路径（位于项目根目录）"""
    project_root = Path(__file__).parent.parent
    return project_root / 'fancy'

def _sanitize_filename(name: str) -> str:
    """过滤文件名中的非法字符"""
    illegal_chars = r'\/:*?"<>|'
    for char in illegal_chars:
        name = name.replace(char, '_')
    return name.strip()

def load_fancy_folder_rules(fancy_dir: str = None) -> list:
    """从 fancy/ 文件夹加载所有用户规则集"""
    if fancy_dir:
        folder = Path(fancy_dir)
    else:
        folder = _get_fancy_folder()
    if not folder.exists():
        return []
    rulesets = []
    for f in sorted(folder.glob('*.json')):
        try:
            content = f.read_text(encoding='utf-8-sig')
            data = json.loads(content)
            if (
                f.name == '_quick_edits.json'
                and isinstance(data, dict)
                and isinstance(data.get('edits'), list)
                and 'rules' not in data
            ):
                migrated, _ = convert_edits_to_bus_ruleset(data['edits'])
                migrated.update({key: value for key, value in data.items() if key not in migrated})
                data = migrated
            if is_bus_ruleset(data):
                data.setdefault('format', BUS_FORMAT)
                compile_bus_ruleset(data)
                rulesets.append(data)
            elif isinstance(data, dict) and data.get('version') == 2 and 'name' in data and 'rules' in data:
                compile_rulesets([data])
                rulesets.append(data)
            else:
                logger.warning(f"跳过无效规则集文件: {f.name}")
        except json.JSONDecodeError as e:
            logger.warning(f"跳过无效 JSON 文件: {f.name} — {e}")
        except Exception as e:
            logger.warning(f"跳过文件读取失败: {f.name} — {e}")
    return rulesets

def save_ruleset_to_folder(name: str, data: dict) -> Path:
    """保存规则集到 fancy/{name}.json，返回保存路径"""
    if is_bus_ruleset(data):
        data['format'] = BUS_FORMAT
        data['version'] = BUS_VERSION
        compile_bus_ruleset(data)
    else:
        data['version'] = 2
        compile_rulesets([data])
    folder = _get_fancy_folder()
    folder.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(name) + '.json'
    filepath = folder / filename
    filepath.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    return filepath


def _unique_ruleset_name(name: str) -> str:
    base_name = name.strip() or '导入的文本替换规则'
    if base_name == '_quick_edits':
        base_name = '导入的文本替换规则'
    existing_names = {
        ruleset.get('name', '')
        for ruleset in load_fancy_folder_rules()
    }
    candidate = base_name
    suffix = 2
    while candidate in existing_names or (_get_fancy_folder() / (_sanitize_filename(candidate) + '.json')).exists():
        candidate = f'{base_name} ({suffix})'
        suffix += 1
    return candidate


def import_bus_rules_file(file_path: str, name: str = None) -> dict:
    source_path = Path(file_path)
    data = json.loads(source_path.read_text(encoding='utf-8-sig'))
    target_name = _unique_ruleset_name(name or data.get('name') or source_path.stem)
    if is_tiaozhua_config(data):
        ruleset, stats = convert_tiaozhua_config(data, name=target_name)
    elif is_lcje_config(data):
        ruleset, stats = convert_lcje_config(data, name=target_name)
    elif is_bus_ruleset(data):
        ruleset = dict(data)
        ruleset['name'] = target_name
        compile_bus_ruleset(ruleset)
        stats = {
            'source_rules': len(ruleset.get('rules', [])),
            'converted_rules': len(ruleset.get('rules', [])),
            'converted_actions': sum(
                len(rule.get('replacements', []))
                for rule in ruleset.get('rules', [])
            ),
            'skipped': 0,
            'warnings': [],
        }
    else:
        raise ValueError('文件不是 bus、调爪或 LCJE 替换规则配置')
    saved_path = save_ruleset_to_folder(target_name, ruleset)
    return {
        'file': source_path.name,
        'ruleset_name': target_name,
        'path': str(saved_path),
        'stats': stats,
    }

def delete_ruleset_from_folder(name: str) -> bool:
    """删除规则集文件，返回是否成功"""
    folder = _get_fancy_folder()
    filename = _sanitize_filename(name) + '.json'
    filepath = folder / filename
    if filepath.exists():
        filepath.unlink()
        return True
    return False
