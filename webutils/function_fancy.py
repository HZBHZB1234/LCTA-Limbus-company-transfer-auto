import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from globalManagers.LogManager import LogManager
from webutils.fancy_engine import ApplyResult, CompiledRules, apply_rules, compile_rulesets

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


def fancy_main(game_path: str, package_name: str, config: list) -> FancyRunStats:
    """
    处理语言包下的所有 JSON 文件。
    config: 规则集列表，每个元素包含 "rules" 列表。
    """
    started_at = time.perf_counter()
    compiled = compile_rulesets(config)
    resource_cache_hit = False
    if compiled.requires_skill_color:
        from webutils.builtinFancyFunc import skillColorHandler

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
        file_rules = compiled.for_file(relative_path)
        if not file_rules.rules:
            continue
        files_matched += 1
        logger.debug(f'{relative_path} 匹配 {len(file_rules.rules)} 条规则')
        try:
            data = json.loads(file.read_text(encoding='utf-8-sig'))
            result: ApplyResult = apply_rules(data, file_rules)
            if result.changed_count:
                _write_json_atomic(file, result.data)
                files_changed += 1
                values_changed += result.changed_count
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
            content = f.read_text(encoding='utf-8')
            data = json.loads(content)
            if isinstance(data, dict) and data.get('version') == 2 and 'name' in data and 'rules' in data:
                compile_rulesets([data])
                rulesets.append(data)
            else:
                logger.warning(f"跳过无效 v2 规则集文件: {f.name}")
        except json.JSONDecodeError as e:
            logger.warning(f"跳过无效 JSON 文件: {f.name} — {e}")
        except Exception as e:
            logger.warning(f"跳过文件读取失败: {f.name} — {e}")
    return rulesets

def save_ruleset_to_folder(name: str, data: dict) -> Path:
    """保存规则集到 fancy/{name}.json，返回保存路径"""
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

def delete_ruleset_from_folder(name: str) -> bool:
    """删除规则集文件，返回是否成功"""
    folder = _get_fancy_folder()
    filename = _sanitize_filename(name) + '.json'
    filepath = folder / filename
    if filepath.exists():
        filepath.unlink()
        return True
    return False
